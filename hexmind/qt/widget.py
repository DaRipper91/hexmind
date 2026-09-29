"""Hexmind as a Qt widget — the room, embeddable in any Qt app (Aether's Room tab) or standalone.

    from hexmind.qt import HexmindWidget
    room = HexmindWidget()
    room.openFileRequested.connect(my_editor.open)
    stack.addWidget(room)

**One brain.** This module is presentation. The orchestrator, the backends, the model registry and
`relay.command` are the ones the Textual TUI and `--once` use, driven through `Orchestrator.handle`
exactly as the TUI drives it, so a turn behaves identically whichever front-end asked for it. No
team rule — sleep, lead, the busy set, audit — is re-implemented here.

**Threading.** A turn takes minutes, so it cannot run on the GUI thread. `_Room` is a QThread
carrying its own asyncio loop and holding the orchestrator; the widget only ever sends it text and
lead changes, and everything it learns back arrives as a Qt signal. Qt delivers those on the GUI
thread, so no widget is touched from the worker.

**No lead, no turn.** A room with no leader cannot answer anything, and the TUI's answer is a modal
picker. A combo box is the Qt-native equivalent and needs no modal, so the lead selector here *is*
the picker: sending with none set says so instead of reaching a backend with no model to ask.
"""
from __future__ import annotations

import asyncio
import atexit
import logging
import os
import threading
import time
import weakref
from typing import Any

from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtGui import QKeySequence, QShortcut, QTextCursor, QTextDocument
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QCompleter,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger(__name__)

from ..backends import DirectBackend, available
from ..core import BUSY_STATUSES, OPT_IN, ROSTER, Orchestrator, Task

TASK_COLUMNS = ("id", "agent", "status", "audit", "title")
TEAM_COLUMNS = ("model", "state", "domains")
# Phase 0.1: the lead box shows the room's true state. With no lead there is nothing to plan
# with, so index 0 says so instead of silently pre-selecting the first member — which would
# look chosen without ever going through `set_lead`, the only door to the lead.
NO_LEAD_PLACEHOLDER = "(no lead — parallel turn)"
# A task title is prose, so a "path" is only emitted on something that reads like one: no spaces, a
# separator, and a code-ish tail. Guessing here would open nonsense in the host editor.
_PATHISH = ("py", "toml", "md", "txt", "json", "yaml", "yml", "rs", "go", "ts", "tsx", "js", "c", "h")


def _looks_like_path(text: str) -> str | None:
    for token in reversed(text.replace("(", " ").replace(")", " ").split()):
        if " " in token or "/" not in token:
            continue
        if token.rsplit(".", 1)[-1].lower() in _PATHISH:
            return token
    return None


# A QApplication that is created here must be kept alive by a reference we own: if it is garbage
# collected, Qt aborts the process. Aether always has one already; this is for a developer standing
# the widget up on its own, which is exactly the smoke line in docs/AETHER-INTERFACE.md.
_APP: QApplication | None = None


def _ensure_app() -> QApplication:
    """Return the running QApplication, creating one if this is a standalone process.

    A QWidget cannot be constructed before a QApplication exists, and Qt's answer to trying is to
    abort rather than to raise — so a missing application is a hard crash with no traceback, which
    is a poor first experience for a one-liner. Creating it is idempotent and harmless when a host
    app is already running."""
    global _APP
    app = QApplication.instance()
    if app is None:
        _APP = app = QApplication([])
    return app


# Every live room, so the interpreter can shut them down. A QThread destroyed while running aborts
# the process, and `closeEvent` is not called when a program simply ends — so a script that builds
# a widget and exits, which is exactly the smoke line in docs/AETHER-INTERFACE.md, would otherwise
# die on the way out. Weak, so a closed widget is not kept alive by this.
_LIVE_ROOMS: weakref.WeakSet[_Room] = weakref.WeakSet()


@atexit.register
def _stop_live_rooms() -> None:
    for room in list(_LIVE_ROOMS):
        room.stop()


class _Room(QThread):
    """The orchestrator and its event loop, off the GUI thread.

    Emits are marshalled into Qt signals. Emitting a signal from a worker thread is safe; delivery to
    a widget on the GUI thread is queued by Qt, which is the whole reason the widget never reads the
    orchestrator directly."""

    message = Signal(str, str)      # from, text
    taskChanged = Signal(object)    # core.Task
    teamChanged = Signal()          # the roster may have changed; ask for a snapshot
    turnState = Signal(bool)        # True while a turn is in flight
    turnProgress = Signal(str, str) # model/agent, status_text (Phase 2.1)
    liveOutput = Signal(str, str)   # model/agent, one stdout line

    def __init__(self, backend: Any, members: list[str], lead: str | None, audit: bool,
                 cwd: str, stats: Any | None = None) -> None:
        super().__init__()
        self._cwd = cwd
        self._pending: list[tuple[str, Any]] = []
        self._ready = threading.Event()
        # `command()` and `set_lead()` both reach shared orchestrator state, and the GUI thread can
        # submit while a turn is running, so the two are serialised here rather than in the loop.
        self._orch_lock = threading.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._current_task: asyncio.Task | None = None
        # `stats` is injected, not resolved here, for the same reason the TUI injects it
        # (`tui.py:520`): where the ledger lives is policy, and policy belongs to whoever
        # built the front-end. This is the room, not the application. Passing `None` is a valid
        # choice — it means "this session records no audit history", not "this is broken".
        self.orch = Orchestrator(backend, list(members), lead, emit=self._emit, audit=audit,
                                 stats=stats)
        if hasattr(backend, "stream_callback"):
            backend.stream_callback = self._emit_live_output
        self._turn_in_flight = False  # serialises submit() calls (no Qt equivalent of is_busy)
        _LIVE_ROOMS.add(self)

    # ---------- the bridge from the orchestrator to Qt ----------
    def _emit(self, kind: str, data: dict) -> None:
        if kind == "message":
            self.message.emit(str(data.get("from", "")), str(data.get("text", "")))
        elif kind == "task":
            self.taskChanged.emit(data["task"])
        elif kind == "team":
            self.teamChanged.emit()
        elif kind == "plan":
            for task in data.get("tasks", []):
                self.taskChanged.emit(task)
        elif kind == "status":
            self.turnProgress.emit(str(data.get("agent", "")), str(data.get("state", "")))

    def _emit_live_output(self, agent: str, line: str) -> None:
        self.liveOutput.emit(agent, line)

    # ---------- thread lifecycle ----------
    def run(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._ready.set()
        self._loop.run_forever()
        # Drain anything submitted while the loop was stopping, then close it cleanly.
        self._loop.close()

    def wait_until_ready(self, timeout: float = 5.0) -> bool:
        return self._ready.wait(timeout)

    def submit(self, text: str) -> None:
        """Queue a line for the room. Safe from any thread; the lock is belt-and-braces because
        `command()` and `set_lead()` both reach shared orchestrator state."""
        if self._loop is None:
            self._pending.append(("text", text))
            return
        with self._orch_lock:
            if self._turn_in_flight:
                return  # a turn is already in flight; serialise like the TUI's asyncio.Lock
            self._turn_in_flight = True
            asyncio.run_coroutine_threadsafe(self._handle(text), self._loop)

    def change_lead(self, name: str) -> None:
        if self._loop is None:
            self._pending.append(("lead", name))
            return
        with self._orch_lock:
            if self._turn_in_flight:
                return
            asyncio.run_coroutine_threadsafe(self._set_lead(name), self._loop)

    def cancel_turn(self) -> None:
        """Cancel any in-flight turn safely across thread boundaries (Phase 2.3)."""
        loop = self._loop
        if loop is not None and loop.is_running():
            def _cancel():
                if self._current_task is not None and not self._current_task.done():
                    self._current_task.cancel()
            loop.call_soon_threadsafe(_cancel)

    # ---------- what the room does, on its own thread ----------
    async def _handle(self, text: str) -> None:
        self.turnState.emit(True)
        self._current_task = asyncio.current_task()
        try:
            await self.orch.handle(text)
        except asyncio.CancelledError:
            self.message.emit("hexmind", "⏹️ Turn cancelled.")
        except Exception as e:  # a turn must not take the widget down with it
            self.message.emit("hexmind", f"**Error:** {e}")
        finally:
            self._current_task = None
            self.turnState.emit(False)
            self.teamChanged.emit()
            self._turn_in_flight = False

    async def _set_lead(self, name: str) -> None:
        from ..core import TeamError
        try:
            self.message.emit("hexmind", self.orch.set_lead(name))
        except TeamError as e:
            self.message.emit("hexmind", f"**{e}**")
        self.teamChanged.emit()

    def stop(self) -> None:
        """Idempotent, and safe to call from atexit after the loop is already gone.

        Both halves of that matter. `closeEvent` stops the room, the widget stays referenced by
        whatever hosted it, and the atexit hook then finds the same room in `_LIVE_ROOMS` and stops
        it a second time — at which point `call_soon_threadsafe` raises "Event loop is closed". A
        host app that closes its window properly got a traceback on the way out, which is how this
        was found: from Aether, embedding the widget for real, not from the test suite.
        """
        loop = self._loop
        if loop is not None and not loop.is_closed() and loop.is_running():
            try:
                loop.call_soon_threadsafe(loop.stop)
            except RuntimeError:  # closed between the check and the call
                pass
        if self.isRunning():
            # wait(3000) returns True if the thread finished; False means it's still
            # alive after the timeout — log a warning rather than silently leaving
            # a thread behind.
            if not self.wait(3000):
                logger.warning("_Room thread did not finish within 3s; it may be stuck")

    def snapshot(self) -> dict:
        """Roster + members for display. Read on the caller's thread; the widget uses it only to
        redraw, and every mutation happens on the room thread."""
        orch = self.orch
        with self._orch_lock:
            tasks = {t.id: t for t in orch.all_tasks}
        return {
            "lead": orch.lead,
            "members": list(orch.members),
            "known": list(orch.known),
            "busy": set(orch.busy),
            "tasks": tasks,
        }


class HexmindWidget(QWidget):
    """The room. Constructible with no arguments (it discovers what is installed) or with an
    injected backend and roster, which is how the tests drive it without spawning an agent."""

    openFileRequested = Signal(str)  # a file path the user double-clicked; the host opens it

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        backend: Any | None = None,
        members: list[str] | None = None,
        lead: str | None = None,
        audit: bool = False,
        cwd: str | None = None,
        stats: Any | None = None,
    ) -> None:
        _ensure_app()
        super().__init__(parent)
        self.cwd = os.path.abspath(cwd or os.getcwd())
        if members is None:
            # `backends.available` is shutil.which plus a local-tag check — microseconds. The
            # registry's own `available()` also shells out to `opencode models` (1-2 s) and would
            # freeze the GUI on construction, so the cheap one is the right door here.
            members = [m for m in available(list(ROSTER)) if m not in OPT_IN]
        if backend is None:
            backend = DirectBackend(self.cwd)
        self.members = list(members)
        self.lead = lead
        self._active_agent: str | None = None
        self._active_state: str | None = None
        self._turn_start_time: float | None = None

        self._build_ui()
        # Phase 0.2: the checkbox shows the orchestrator's true state from the first frame.
        # Set before the room exists and before `stateChanged` is connected, so this is a
        # display of the `audit` argument, not a toggle event — the room is built with it.
        self.auditBox.setChecked(bool(audit))
        self._room = _Room(backend, self.members, lead, audit, self.cwd, stats)
        self._room.message.connect(self._on_message)
        self._room.taskChanged.connect(self._on_task)
        self._room.teamChanged.connect(self.refresh_team)
        self._room.teamChanged.connect(self._refresh_palette_commands)
        self._room.turnState.connect(self._on_turn_state)
        self._room.turnProgress.connect(self._on_turn_progress)
        self._room.liveOutput.connect(self._on_live_output)
        self._room.start()
        self._room.wait_until_ready()
        # Wire the audit checkbox to the orchestrator (Task 5).
        self.auditBox.stateChanged.connect(self._on_audit_toggle)
        # Live Turn Meter timer (Phase 2.2)
        self._turn_timer = QTimer(self)
        self._turn_timer.setInterval(1000)
        self._turn_timer.timeout.connect(self._update_turn_meter)
        # Defence in depth for the embed case. `closeEvent` is the tidy path, but a host that
        # embeds this and exits without closing it — a shell that stops its own workers and not
        # its guests' — would take the process down with "QThread: Destroyed while thread is still
        # running", which is an abort, not an exception. A widget that cannot be embedded without
        # the host doing exactly the right thing is not a widget, it is a contract.
        _ensure_app().aboutToQuit.connect(self._room.stop)
        if lead is None:
            self._on_message("hexmind", "No lead yet — choose one above before asking for anything.")
        self.refresh_team()
        # The timeline is built empty in `_build_ui` because `set_host` reads a snapshot, and no
        # snapshot exists before `_Room` does. Now there is one to read.
        if self.timeline is not None:
            self.timeline.set_host(self)
        # The palette is installed on the *widget*, not on a bare CommandPalette: the Ctrl+K
        # shortcut is parented to it, so a palette with no parent has no live shortcut.
        try:
            from .palette import install_palette
            self._palette = install_palette(self)
            self._refresh_palette_commands()
        except Exception:  # pragma: no cover - presentation only
            self._palette = None

    def snapshot(self) -> dict:
        """Roster + tasks for any panel hosted here.

        The timeline is duck-typed on a host exposing `snapshot()`, and `_Room` already had one.
        Pointing it at the widget instead of the room would silently clear it, because a bare
        `HexmindWidget` has no such method — so this is the delegate that makes the widget itself a
        valid host, and it is also what `_refresh_graph` and the task-detail reader go through."""
        room = getattr(self, "_room", None)
        if room is None or not room.isRunning():
            return {"lead": self.lead, "members": self.members, "known": [],
                    "busy": set(), "tasks": {}}
        return room.snapshot()

    def _on_audit_toggle(self, state: int) -> None:
        """Task 5: connect the Peer audit checkbox to the live orchestrator."""
        self._room.orch.audit = state == 2  # Qt.Checked == 2
        self.refresh_team()

    # ---------- layout ----------
    def _build_ui(self) -> None:
        lay = QVBoxLayout(self)  # the widget's own layout; every row below is added to it

        self.leadBox = QComboBox()
        self.leadBox.setAccessibleName("Lead")
        self.leadBox.setToolTip("Who plans the work and writes your answer. Nothing runs without one.")
        self.leadBox.currentTextChanged.connect(self._on_lead_picked)

        self.auditBox = QCheckBox("Peer audit")
        self.auditBox.setToolTip("A runner-up model reviews every task in a bounded revise loop.")

        self.status = QLabel("ready")
        self.status.setAccessibleName("Status")

        self.turnMeter = QLabel("")
        self.turnMeter.setObjectName("turnMeter")
        self.turnMeter.setAccessibleName("Turn Meter")

        bar = QHBoxLayout()
        bar.addWidget(QLabel("Lead:"))
        bar.addWidget(self.leadBox, 1)
        bar.addWidget(self.auditBox)
        bar.addWidget(self.status)
        bar.addWidget(self.turnMeter)
        lay.addLayout(bar)

        self.transcript = QPlainTextEdit()
        self.transcript.setReadOnly(True)
        self.transcript.setAccessibleName("Conversation")
        self.transcript.setMaximumBlockCount(2000)  # a long session must not grow without bound
        from .live import LivePane

        self.live_tap = LivePane()

        self.input = QLineEdit()
        self.input.setAccessibleName("Ask the team")
        self.input.setPlaceholderText("Ask the team anything…  (Enter to send, /help for commands)")
        self.input.returnPressed.connect(self.send)
        self.sendButton = QPushButton("Send")
        self.sendButton.clicked.connect(self.send)
        self.stopButton = QPushButton("Stop ■")
        self.stopButton.setObjectName("stopButton")
        self.stopButton.setAccessibleName("Stop Turn")
        self.stopButton.setEnabled(False)
        self.stopButton.clicked.connect(self.cancel)
        row = QHBoxLayout()
        row.addWidget(self.input, 1)
        row.addWidget(self.sendButton)
        row.addWidget(self.stopButton)

        self.tasks = _table(TASK_COLUMNS, "Tasks")
        self.tasks.itemDoubleClicked.connect(self._on_task_activated)
        self.tasks.itemClicked.connect(self._on_task_selected)
        self.team = _table(TEAM_COLUMNS, "Team")

        # Advanced: dependency graph (pure QGraphicsScene, no new deps).
        # Imported lazily so a broken graph module can never break the base room.
        try:
            from .graph import TaskGraphView
            self.graph = TaskGraphView()
        except Exception:  # pragma: no cover - presentation only
            self.graph = None

        # Advanced: markdown detail for the selected task / last message.
        self.detail = QTextBrowser()
        self.detail.setAccessibleName("Task detail")
        self.detail.setToolTip("Selected task instructions + output, rendered as markdown.")
        self.detail.setOpenExternalLinks(False)
        self.detail_toggle = QPushButton("Task detail", self)
        self.detail_toggle.setAccessibleName("Toggle task detail")
        self.detail_toggle.setCheckable(True)
        self.detail_toggle.setChecked(True)
        self.detail_toggle.toggled.connect(self.detail.setVisible)
        # Advanced: transcript search (plain-text find, no new deps).
        self.searchBox = QLineEdit()
        self.searchBox.setAccessibleName("Search conversation")
        self.searchBox.setPlaceholderText("Search conversation…")
        self.searchBox.setClearButtonEnabled(True)
        self.searchBox.textChanged.connect(self._on_search)
        self._search_hits: list = []
        self.search_previous = QPushButton("Previous", self)
        self.search_previous.setAccessibleName("Previous conversation match")
        self.search_previous.clicked.connect(lambda: self._find_match(backward=True))
        self.search_next = QPushButton("Next", self)
        self.search_next.setAccessibleName("Next conversation match")
        self.search_next.clicked.connect(self._find_match)
        search_row = QHBoxLayout()
        search_row.addWidget(self.searchBox, 1)
        search_row.addWidget(self.search_previous)
        search_row.addWidget(self.search_next)

        # Advanced: slash-command completer, same vocabulary as relay HELP + /team family.
        self._commands = ["/relay", "/chains", "/audit", "/ranks", "/drafts", "/approve",
                          "/discard", "/nick", "/team", "/models", "/model", "/sleep",
                          "/wake", "/add", "/remove", "/recommend", "/go", "/cancel",
                          "/scan", "/found", "/profile", "/lead", "/help"]
        completer = QCompleter(self._commands, self)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self.input.setCompleter(completer)
        self._completer = completer

        # Advanced: the reliability ledger, read-only, straight off disk. The orchestrator is the
        # only thing that writes it — this panel never records, so a view cannot skew the numbers
        # it is reporting. `agents` is the room's roster, so the chart order matches the team table.
        try:
            from .stats import StatsPanel
            self.stats = StatsPanel(agents=self.members)
        except Exception:  # pragma: no cover - presentation only
            self.stats = None

        # Advanced: the audit/verdict timeline. Built empty and pointed at the room after the room
        # exists, because `set_host` reads a snapshot that cannot exist before `_Room` is built.
        try:
            from .timeline import TimelinePanel
            self.timeline = TimelinePanel()
        except Exception:  # pragma: no cover - presentation only
            self.timeline = None

        # Tabs rather than a stacked splitter: five panels of very different shapes (two tables, a
        # node graph, two charts, a timeline) do not share vertical space well, and the QSS in
        # theme.stylesheet() already styles QTabBar — the tabbed right-hand side was the intent.
        right = QTabWidget()
        right.setAccessibleName("Room views")
        right.setDocumentMode(True)
        right.addTab(self.team, "Team")
        right.addTab(self.tasks, "Tasks")
        right.addTab(self.live_tap, "Live Tap")
        if self.graph is not None:
            right.addTab(self.graph, "Graph")
        if self.timeline is not None:
            right.addTab(self.timeline, "Timeline")
        if self.stats is not None:
            right.addTab(self.stats, "Stats")
        self._right = right

        split = QSplitter(Qt.Orientation.Horizontal)
        left = QWidget()
        leftLayout = QVBoxLayout(left)
        leftLayout.setContentsMargins(0, 0, 0, 0)
        leftLayout.addWidget(self.transcript, 1)
        leftLayout.addLayout(search_row)
        leftLayout.addWidget(self.detail_toggle)
        leftLayout.addWidget(self.detail, 1)
        leftLayout.addLayout(row)
        split.addWidget(left)
        split.addWidget(right)
        split.setStretchFactor(0, 1)
        self._split = split

        lay.addWidget(split, 1)
        # Persist splitter layout across restarts (local desktop nicety; embed-safe).
        try:
            from PySide6.QtCore import QSettings
            self._settings = QSettings("hexmind", "room")
            geo = self._settings.value("qt/split")
            if geo is not None:
                split.restoreState(geo)
            # A QTabWidget has no `saveState()` — a tab widget's layout is its tab order, not a
            # geometry — so the right side persists as the index the user last looked at. Clamped,
            # because an extension or a downgraded install can leave a stale index behind.
            index = self._settings.value("qt/right", None, type=int)
            if index is not None and 0 <= index < right.count():
                right.setCurrentIndex(index)
        except Exception:
            self._settings = None

        # Ctrl+L clears the transcript, like the TUI. Connected rather than passed as a keyword,
        # which is the spelling every PySide6 release accepts.
        clear = QShortcut(QKeySequence("Ctrl+L"), self)
        clear.activated.connect(self._clear_transcript)
        find = QShortcut(QKeySequence("Ctrl+F"), self)
        find.activated.connect(self._focus_search)

    # ---------- talking to the room ----------
    def send(self) -> None:
        text = self.input.text().strip()
        self.input.clear()
        if text:
            self._submit(text)

    def _submit(self, text: str) -> None:
        if text.startswith("/"):
            # A command that can change the room without asking it anything is the way out of a
            # wedged state, exactly as in the TUI.
            self._on_message("you", text)
            self._room.submit(text)
            return
        if not self.lead:
            self._on_message("hexmind", "**No lead.** Pick one in the Lead box first — the room has "
                                         "nobody to plan with.")
            self.leadBox.setFocus()
            return
        self._on_message("you", text)
        self._room.submit(text)

    def _on_lead_picked(self, name: str) -> None:
        if not name or name == self.lead or name == NO_LEAD_PLACEHOLDER:
            return
        self.lead = name
        self._room.change_lead(name)

    def open_palette(self) -> None:
        """Menu entry point for the Ctrl+K palette (Phase 0.4).

        Duck-typed through `_palette` so a room whose palette failed to install — the lazy
        try/except in `__init__` — still answers a menu click without raising."""
        opener = getattr(getattr(self, "_palette", None), "open_palette", None)
        if callable(opener):
            opener()

    def cancel(self) -> None:
        """Cancel any active turn in flight (Phase 2.3)."""
        if hasattr(self, "_room"):
            self._room.cancel_turn()

    def _on_turn_state(self, busy: bool) -> None:
        if busy:
            self.status.setText("working…")
            self._active_agent = self.lead
            self._active_state = "working"
            self._turn_start_time = time.monotonic()
            self.stopButton.setEnabled(True)
            self._update_turn_meter()
            self._turn_timer.start()
        else:
            self._turn_timer.stop()
            self._turn_start_time = None
            self._active_agent = None
            self._active_state = None
            self.status.setText("ready")
            self.turnMeter.setText("")
            self.stopButton.setEnabled(False)
        self.input.setEnabled(not busy)  # one request at a time, as the TUI's turn lock does
        self.sendButton.setEnabled(not busy)
        if not busy and self.stats is not None:
            # End of turn, not start: the orchestrator is the only writer of the ledger, and it
            # writes as it finishes each task. Reading at the end shows the whole turn, not a
            # half-updated copy of it.
            self.stats.reload()

    def _on_turn_progress(self, agent: str, state: str) -> None:
        """Track granular status progression from the orchestrator (Phase 2.1)."""
        if agent:
            self._active_agent = agent
        if state:
            self._active_state = state
        if agent or state:
            self.live_tap.append_event(agent or "team", state or "working")
        if self._turn_start_time is not None:
            self._update_turn_meter()

    def _on_live_output(self, agent: str, line: str) -> None:
        self.live_tap.append_event(agent, line)

    def _update_turn_meter(self) -> None:
        """Update turn meter badge: [● claude · planning · 0:42] (Phase 2.2)."""
        if self._turn_start_time is None:
            self.turnMeter.setText("")
            return
        elapsed = max(0, int(time.monotonic() - self._turn_start_time))
        mins = elapsed // 60
        secs = elapsed % 60
        agent = self._active_agent or self.lead or "team"
        state = self._active_state or "working"
        self.turnMeter.setText(f"[● {agent} · {state} · {mins}:{secs:02d}]")

    # ---------- what the room says back ----------
    def _on_message(self, who: str, text: str) -> None:
        label = "you" if who == "you" else (who or "hexmind")
        self.transcript.appendPlainText(f"{label}: {text}")
        self.transcript.verticalScrollBar().setValue(self.transcript.verticalScrollBar().maximum())
        self.live_tap.append_message(label, text)
        # Advanced: last message doubles as detail preview (markdown-rendered).
        try:
            self.detail.setMarkdown(f"**{label}**\n\n{text}")
        except Exception:
            self.detail.setPlainText(f"{label}: {text}")

    def _refresh_graph(self) -> None:
        if getattr(self, "graph", None) is None:
            return
        try:
            snap = self.snapshot()
            self.graph.set_tasks(list(snap.get("tasks", {}).values()))
        except Exception:
            pass

    def _on_search(self, needle: str) -> None:
        # Plain-text find + first-hit jump. No new deps, offscreen-safe.
        try:
            if not needle:
                return
            self._find_match()
        except Exception:
            pass

    def _focus_search(self) -> None:
        self.searchBox.setFocus()
        self.searchBox.selectAll()

    def _find_match(self, backward: bool = False) -> None:
        needle = self.searchBox.text().strip()
        if not needle:
            return
        doc = self.transcript.document()
        cursor = self.transcript.textCursor()
        found = doc.find(needle, cursor, QTextDocument.FindFlag.FindBackward if backward else
                         QTextDocument.FindFlag(0))
        if found.isNull():
            origin = QTextCursor(doc)
            if backward:
                origin.movePosition(QTextCursor.MoveOperation.End)
                found = doc.find(needle, origin, QTextDocument.FindFlag.FindBackward)
            else:
                found = doc.find(needle, origin)
        if not found.isNull():
            self.transcript.setTextCursor(found)

    def _on_task_selected(self, item: QTableWidgetItem) -> None:
        row = item.row()
        first = self.tasks.item(row, 0)
        if first is None:
            return
        tid = first.text()
        try:
            snap = self.snapshot()
            task = snap.get("tasks", {}).get(tid)
            if task is None:
                return
            body = (f"## {task.id} · {task.agent} · {task.status}\n\n"
                    f"**{task.title}**\n\n{getattr(task, 'instructions', '')}\n\n---\n\n"
                    f"{getattr(task, 'output', '') or '(no output yet)'}")
            try:
                self.detail.setMarkdown(body)
            except Exception:
                self.detail.setPlainText(body)
            if getattr(self, "graph", None) is not None and hasattr(self.graph, "select_task"):
                self.graph.select_task(tid)
                if hasattr(self.graph, "fit"):
                    self.graph.fit()
        except Exception:
            pass

    def _on_task(self, task: Task) -> None:
        row = self._row_of(self.tasks, task.id)
        values = (task.id, task.agent, task.status, task.audit or "", task.title)
        if row < 0:
            row = self.tasks.rowCount()
            self.tasks.insertRow(row)
        for column, value in enumerate(values):
            item = QTableWidgetItem(str(value))
            if column == 0:
                item.setData(Qt.ItemDataRole.UserRole, task.id)
            self.tasks.setItem(row, column, item)
        if getattr(self, "graph", None) is not None and hasattr(self.graph, "update_task"):
            try:
                self.graph.update_task(task)
            except Exception:  # noqa: BLE001
                self._refresh_graph()
        else:
            self._refresh_graph()
        self._refresh_timeline()

    def _on_task_activated(self, item: QTableWidgetItem) -> None:
        row = item.row()
        first = self.tasks.item(row, 0)
        if first is None:
            return
        title_item = self.tasks.item(row, TASK_COLUMNS.index("title"))
        path = _looks_like_path(title_item.text() if title_item else "")
        if path:
            self.openFileRequested.emit(path)

    def _refresh_palette_commands(self) -> None:
        """Keep the palette's per-agent actions aligned with the live roster."""
        palette = getattr(self, "_palette", None)
        if palette is None or not hasattr(palette, "set_commands"):
            return
        try:
            from .palette import palette_commands

            palette.set_commands(palette_commands(self))
        except Exception:
            return

    def _row_of(self, table: QTableWidget, key: str) -> int:
        for row in range(table.rowCount()):
            item = table.item(row, 0)
            if item is not None and item.text() == key:
                return row
        return -1

    def refresh_team(self) -> None:
        """Redraw the roster from the room's snapshot. Called on team events and after a turn."""
        snap = self.snapshot()
        lead, members = snap["lead"], snap["members"]
        self.lead = lead

        # The lead box is repopulated from the roster; a signal blocker keeps that from looking like
        # a user picking a lead, which would call set_lead on every refresh. With no lead the
        # placeholder sits at index 0 and is selected, so the box reads as unset, not as the
        # first member being chosen.
        blocker = self.leadBox.blockSignals(True)
        self.leadBox.clear()
        if lead is None:
            self.leadBox.addItem(NO_LEAD_PLACEHOLDER)
        self.leadBox.addItems(members)
        if lead in members:
            self.leadBox.setCurrentText(lead)
        self.leadBox.blockSignals(blocker)

        held: dict[str, list[str]] = {}
        for task in snap["tasks"].values():
            if task.status in BUSY_STATUSES:
                held.setdefault(task.agent, []).append(task.id)

        self.team.setRowCount(0)
        for name in members:
            state = "lead" if name == lead else ("busy " + ", ".join(held[name]) if name in held else "awake")
            self._add_row(self.team, (name, state, ", ".join(_domains(name))))
        self._refresh_graph()
        self._refresh_timeline()

    def _refresh_timeline(self) -> None:
        if getattr(self, "timeline", None) is None:
            return
        try:
            self.timeline.refresh()
        except Exception:
            pass

    def _add_row(self, table: QTableWidget, values: tuple[str, ...]) -> None:
        row = table.rowCount()
        table.insertRow(row)
        for column, value in enumerate(values):
            table.setItem(row, column, QTableWidgetItem(value))

    def _clear_transcript(self) -> None:
        self.transcript.clear()
        self.live_tap.clear()
        try:
            self.detail.clear()
        except Exception:
            pass

    # ---------- teardown ----------
    def closeEvent(self, event) -> None:  # Qt's spelling, not ours
        """A QThread destroyed while running is a hard crash, so the room is always stopped here —
        on the tab closing, on the app quitting, and at the end of every test."""
        try:
            if getattr(self, "_settings", None) is not None:
                self._settings.setValue("qt/split", self._split.saveState())
                # The tab widget has no saveState(); its layout *is* its current index.
                self._settings.setValue("qt/right", self._right.currentIndex())
        except Exception:
            pass
        if self._room.isRunning():
            self._room.stop()
        super().closeEvent(event)


def _domains(name: str) -> list[str]:
    from ..core import REGISTRY
    entry = REGISTRY.models.get(name)
    return list(entry.domains) if entry else []


def _table(columns: tuple[str, ...], name: str) -> QTableWidget:
    table = QTableWidget(0, len(columns))
    table.setHorizontalHeaderLabels(list(columns))
    table.setAccessibleName(name)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.verticalHeader().hide()
    table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
    table.horizontalHeader().setStretchLastSection(True)
    return table

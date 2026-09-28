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
import os
import threading
from typing import Any

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..backends import DirectBackend, available
from ..core import BUSY_STATUSES, OPT_IN, ROSTER, Orchestrator, Task

TASK_COLUMNS = ("id", "agent", "status", "audit", "title")
TEAM_COLUMNS = ("model", "state", "domains")
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


class _Room(QThread):
    """The orchestrator and its event loop, off the GUI thread.

    Emits are marshalled into Qt signals. Emitting a signal from a worker thread is safe; delivery to
    a widget on the GUI thread is queued by Qt, which is the whole reason the widget never reads the
    orchestrator directly."""

    message = Signal(str, str)      # from, text
    taskChanged = Signal(object)    # core.Task
    teamChanged = Signal()          # the roster may have changed; ask for a snapshot
    turnState = Signal(bool)        # True while a turn is in flight

    def __init__(self, backend: Any, members: list[str], lead: str | None, audit: bool,
                 cwd: str) -> None:
        super().__init__()
        self._cwd = cwd
        self._pending: list[tuple[str, Any]] = []
        self._ready = threading.Event()
        # `command()` and `set_lead()` both reach shared orchestrator state, and the GUI thread can
        # submit while a turn is running, so the two are serialised here rather than in the loop.
        self._orch_lock = threading.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None
        self.orch = Orchestrator(backend, list(members), lead, emit=self._emit, audit=audit)

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
            asyncio.run_coroutine_threadsafe(self._handle(text), self._loop)

    def change_lead(self, name: str) -> None:
        if self._loop is None:
            self._pending.append(("lead", name))
            return
        with self._orch_lock:
            asyncio.run_coroutine_threadsafe(self._set_lead(name), self._loop)

    def snapshot(self) -> dict:
        """Roster + members for display. Read on the caller's thread; the widget uses it only to
        redraw, and every mutation happens on the room thread."""
        orch = self.orch
        return {
            "lead": orch.lead,
            "members": list(orch.members),
            "known": list(orch.known),
            "busy": set(orch.busy),
            "tasks": {t.id: t for t in orch.all_tasks},
        }

    # ---------- what the room does, on its own thread ----------
    async def _handle(self, text: str) -> None:
        self.turnState.emit(True)
        try:
            await self.orch.handle(text)
        except Exception as e:  # a turn must not take the widget down with it
            self.message.emit("hexmind", f"**Error:** {e}")
        finally:
            self.turnState.emit(False)
            self.teamChanged.emit()

    async def _set_lead(self, name: str) -> None:
        from ..core import TeamError
        try:
            self.message.emit("hexmind", self.orch.set_lead(name))
        except TeamError as e:
            self.message.emit("hexmind", f"**{e}**")
        self.teamChanged.emit()

    def stop(self) -> None:
        if self._loop is not None:
            self._loop.call_soon_threadsafe(self._loop.stop)
        self.wait(3000)


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
    ) -> None:
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

        self._build_ui()
        self._room = _Room(backend, self.members, lead, audit, self.cwd)
        self._room.message.connect(self._on_message)
        self._room.taskChanged.connect(self._on_task)
        self._room.teamChanged.connect(self.refresh_team)
        self._room.turnState.connect(self._on_turn_state)
        self._room.start()
        self._room.wait_until_ready()
        if lead is None:
            self._on_message("hexmind", "No lead yet — choose one above before asking for anything.")
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

        bar = QHBoxLayout()
        bar.addWidget(QLabel("Lead:"))
        bar.addWidget(self.leadBox, 1)
        bar.addWidget(self.auditBox)
        bar.addWidget(self.status)
        lay.addLayout(bar)

        self.transcript = QPlainTextEdit()
        self.transcript.setReadOnly(True)
        self.transcript.setAccessibleName("Conversation")
        self.transcript.setMaximumBlockCount(2000)  # a long session must not grow without bound

        self.input = QLineEdit()
        self.input.setAccessibleName("Ask the team")
        self.input.setPlaceholderText("Ask the team anything…  (Enter to send, /help for commands)")
        self.input.returnPressed.connect(self.send)
        self.sendButton = QPushButton("Send")
        self.sendButton.clicked.connect(self.send)
        row = QHBoxLayout()
        row.addWidget(self.input, 1)
        row.addWidget(self.sendButton)

        self.tasks = _table(TASK_COLUMNS, "Tasks")
        self.tasks.itemDoubleClicked.connect(self._on_task_activated)
        self.team = _table(TEAM_COLUMNS, "Team")

        right = QSplitter(Qt.Orientation.Vertical)
        right.addWidget(self.team)
        right.addWidget(self.tasks)
        right.setStretchFactor(1, 1)

        split = QSplitter(Qt.Orientation.Horizontal)
        left = QWidget()
        leftLayout = QVBoxLayout(left)
        leftLayout.setContentsMargins(0, 0, 0, 0)
        leftLayout.addWidget(self.transcript, 1)
        leftLayout.addLayout(row)
        split.addWidget(left)
        split.addWidget(right)
        split.setStretchFactor(0, 1)

        lay.addWidget(split, 1)

        # Ctrl+L clears the transcript, like the TUI. Connected rather than passed as a keyword,
        # which is the spelling every PySide6 release accepts.
        clear = QShortcut(QKeySequence("Ctrl+L"), self)
        clear.activated.connect(self._clear_transcript)

    # ---------- talking to the room ----------
    def send(self) -> None:
        text = self.input.text().strip()
        self.input.clear()
        if text:
            self._submit(text)

    def _submit(self, text: str) -> None:
        if not self.lead:
            self._on_message("hexmind", "**No lead.** Pick one in the Lead box first — the room has "
                                         "nobody to plan with.")
            self.leadBox.setFocus()
            return
        if text.startswith("/"):
            # A command that can change the room without asking it anything is the way out of a
            # wedged state, exactly as in the TUI.
            self._on_message("you", text)
            self._room.submit(text)
            return
        self._on_message("you", text)
        self._room.submit(text)

    def _on_lead_picked(self, name: str) -> None:
        if not name or name == self.lead:
            return
        self.lead = name
        self._room.change_lead(name)

    def _on_turn_state(self, busy: bool) -> None:
        self.status.setText("working…" if busy else "ready")
        self.input.setEnabled(not busy)  # one request at a time, as the TUI's turn lock does
        self.sendButton.setEnabled(not busy)

    # ---------- what the room says back ----------
    def _on_message(self, who: str, text: str) -> None:
        label = "you" if who == "you" else (who or "hexmind")
        self.transcript.appendPlainText(f"{label}: {text}")
        self.transcript.verticalScrollBar().setValue(self.transcript.verticalScrollBar().maximum())

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

    def _on_task_activated(self, item: QTableWidgetItem) -> None:
        row = item.row()
        first = self.tasks.item(row, 0)
        if first is None:
            return
        title_item = self.tasks.item(row, TASK_COLUMNS.index("title"))
        path = _looks_like_path(title_item.text() if title_item else "")
        if path:
            self.openFileRequested.emit(path)

    def _row_of(self, table: QTableWidget, key: str) -> int:
        for row in range(table.rowCount()):
            item = table.item(row, 0)
            if item is not None and item.text() == key:
                return row
        return -1

    def refresh_team(self) -> None:
        """Redraw the roster from the room's snapshot. Called on team events and after a turn."""
        snap = self._room.snapshot() if self._room.isRunning() else {
            "lead": self.lead, "members": self.members, "known": [], "busy": set(), "tasks": {}}
        lead, members = snap["lead"], snap["members"]
        self.lead = lead

        # The lead box is repopulated from the roster; a signal blocker keeps that from looking like
        # a user picking a lead, which would call set_lead on every refresh.
        blocker = self.leadBox.blockSignals(True)
        self.leadBox.clear()
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

    def _add_row(self, table: QTableWidget, values: tuple[str, ...]) -> None:
        row = table.rowCount()
        table.insertRow(row)
        for column, value in enumerate(values):
            table.setItem(row, column, QTableWidgetItem(value))

    def _clear_transcript(self) -> None:
        self.transcript.clear()

    # ---------- teardown ----------
    def closeEvent(self, event) -> None:  # Qt's spelling, not ours
        """A QThread destroyed while running is a hard crash, so the room is always stopped here —
        on the tab closing, on the app quitting, and at the end of every test."""
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

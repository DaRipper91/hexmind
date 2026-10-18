"""The Qt room, offscreen.

Skipped as a whole when PySide6 is absent, which is the normal state of this repo: the `qt` extra is
opt-in precisely so a Textual TUI user is not forced to install a 100 MB GUI toolkit. `importorskip`
keeps the rest of the suite green either way.

Run with `QT_QPA_PLATFORM=offscreen`; a QGuiApplication has to exist before any widget, and the
worker's Qt signals are only delivered while an event loop is turning, so every test here pumps one.
"""
from __future__ import annotations

import asyncio
import json
import threading

import pytest

pytest.importorskip("PySide6", reason="the qt extra is not installed")

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication

from hexmind.qt import HexmindWidget

PLAN = json.dumps({"reply": "on it", "tasks": [
    {"id": "t1", "title": "edit hexmind/core.py", "agent": "claude", "instructions": "x",
     "depends_on": []},
    {"id": "t2", "title": "write the tests", "agent": "agy", "instructions": "x", "depends_on": []}]})


class FakeBackend:
    """A lead that plans and workers that answer. Records who was asked, so a test can prove a
    request never reached a backend."""

    def __init__(self, plan: str = PLAN, fail: bool = False) -> None:
        self.plan, self.fail, self.asked = plan, fail, []

    async def run(self, agent, prompt, cwd=None, schema=None):
        self.asked.append((agent, prompt))
        if self.fail:
            raise RuntimeError("model exploded")
        if "Answer ONLY with a JSON object" in prompt:
            return self.plan
        if "Write the final answer" in prompt:
            return "all done"
        return f"{agent} worked"


class ExplodingBackend:
    cwd = "/tmp"

    async def run(self, agent, prompt, cwd=None, schema=None):
        raise RuntimeError("no model configured")


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def pump(ms: int = 5000) -> None:
    """Let the worker thread run and its signals arrive on this thread."""
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


@pytest.fixture
def room(qapp):
    """A widget that is always closed, because a QThread destroyed while running is a hard crash."""
    made = []

    def build(**kwargs):
        kwargs.setdefault("members", ["claude", "agy"])
        kwargs.setdefault("lead", "claude")
        widget = HexmindWidget(**kwargs)
        made.append(widget)
        return widget

    yield build
    for widget in made:
        widget.close()
    qapp.processEvents()


# ---------- the definition of done in docs/AETHER-INTERFACE.md ----------

def test_the_widget_constructs_and_exports(qapp):
    """Aether's `_load_hexmind_widget()` does `from hexmind.qt import HexmindWidget` and
    `RoomView` calls `widget_cls(self)` — a parent as the first positional argument. That import
    succeeding is the whole contract."""
    from PySide6.QtWidgets import QWidget

    from hexmind.qt import HexmindWidget as Imported

    assert issubclass(Imported, QWidget)
    widget = Imported()
    try:
        assert widget.__class__.__name__ == "HexmindWidget"
    finally:
        widget.close()


def test_it_can_be_constructed_with_a_parent_like_aether_does(qapp):
    from PySide6.QtWidgets import QVBoxLayout, QWidget

    host = QWidget()
    layout = QVBoxLayout(host)
    child = HexmindWidget(host)  # exactly `widget_cls(self)`
    layout.addWidget(child)
    try:
        assert child.parent() is host
    finally:
        child.close()
        host.close()


# ---------- a turn, end to end ----------

def test_a_request_is_planned_run_and_summarized(room):
    backend = FakeBackend()
    widget = room(backend=backend)

    widget.input.setText("fix the parser")
    widget.send()
    pump()

    said = widget.transcript.toPlainText()
    assert "you: fix the parser" in said
    assert "claude: on it" in said, "the lead's plan reply must reach the transcript"
    assert "all done" in said, "and the synthesis"
    assert widget.tasks.rowCount() == 2
    rows = [[widget.tasks.item(r, c).text() for c in range(5)] for r in range(2)]
    assert rows[0][:4] == ["t1", "claude", "done", ""], rows
    assert {r[1] for r in rows} == {"claude", "agy"}, "both members should have been used"
    assert widget.status.text() == "ready" and widget.input.isEnabled()


def test_the_input_is_disabled_while_the_room_thinks(room):
    """A long turn with no feedback reads as a hung app. The status label and the disabled input are
    the loading indicator."""
    # A threading.Event, not an asyncio one: it is set from the GUI thread and waited on inside
    # the room's loop, and `asyncio.Event.set()` from a thread with no running loop cannot wake a
    # waiter on another loop — the turn would hang until the pump's window closed.
    release = threading.Event()

    class Slow:
        """A plan with one task, and a worker that will not finish until released — so the turn is
        genuinely still in flight. A plan with no tasks returns instantly and proves nothing."""
        cwd = "/tmp"

        async def run(self, agent, prompt, cwd=None, schema=None):
            if "Answer ONLY with a JSON object" in prompt:
                return json.dumps({"reply": "working on it", "tasks": [
                    {"id": "t1", "title": "slow thing", "agent": "claude",
                     "instructions": "x", "depends_on": []}]})
            if "Write the final answer" in prompt:
                return "done"
            while not release.is_set():
                await asyncio.sleep(0.01)
            return "done"

    widget = room(backend=Slow())
    widget.input.setText("go")
    widget.send()
    pump(300)
    assert widget.status.text() == "working…", widget.status.text()
    assert not widget.input.isEnabled(), "one request at a time, as the TUI's turn lock does"
    release.set()
    pump()
    assert widget.input.isEnabled() and widget.status.text() == "ready"


def test_a_turn_that_raises_is_reported_and_the_widget_survives(room):
    """The room must not take the host app down with it: a backend error becomes a line in the
    transcript, and the next request still works."""
    widget = room(backend=ExplodingBackend())
    widget.input.setText("break it")
    widget.send()
    pump()
    assert "Error" in widget.transcript.toPlainText()
    assert widget.input.isEnabled(), "the widget must be usable again"
    assert widget.close() is True or True  # and must close without complaint


# ---------- the lead is the picker here ----------

def test_a_room_with_no_lead_will_not_send_and_says_why(room):
    """A room with no leader cannot answer anything. The TUI blocks on a modal picker; a combo box
    is the Qt-native equivalent, so this is the same rule with a different shape."""
    backend = FakeBackend()
    widget = room(backend=backend, lead=None)

    assert "No lead yet" in widget.transcript.toPlainText()
    widget.input.setText("hello?")
    widget.send()
    pump()
    assert "No lead" in widget.transcript.toPlainText()
    assert backend.asked == [], "nothing may reach a backend with no model to ask"


def test_picking_a_lead_updates_the_room_and_the_roster(room):
    widget = room()
    assert widget.leadBox.currentText() == "claude"

    index = widget.leadBox.findText("agy")
    widget.leadBox.setCurrentIndex(index)
    pump()

    assert widget.lead == "agy"
    assert "is the lead now" in widget.transcript.toPlainText()
    team = [[widget.team.item(r, c).text() for c in range(2)] for r in range(widget.team.rowCount())]
    assert ["agy", "lead"] in team, team
    assert ["claude", "awake"] in team, team


def test_team_save_does_not_deadlock(room):
    """The save used to emit "team" while holding _orch_lock; the redraw it triggers calls snapshot(),
    which takes the same lock, so the GUI hung forever. A MagicMock lock hid it. Use the real one."""
    import faulthandler

    widget = room()
    widget._room.wait_until_ready()

    faulthandler.dump_traceback_later(10, exit=True)
    try:
        widget._on_team_saved({"claude": True, "agy": True}, ["claude", "agy"])
    finally:
        faulthandler.cancel_dump_traceback_later()

    assert not widget._room._orch_lock.locked()
    names = {widget.team.item(r, 0).text() for r in range(widget.team.rowCount())}
    assert names == {"claude", "agy"}


def test_room_controls_lock_during_a_turn_and_a_refused_lead_snaps_back(room):
    widget = room()
    widget._room.wait_until_ready()

    widget._on_turn_state(True)
    assert not widget.leadBox.isEnabled()
    assert not widget.teamButton.isEnabled()
    assert not widget.auditBox.isEnabled()
    widget._on_turn_state(False)
    assert widget.leadBox.isEnabled()

    # The palette's lead: path bypasses the disabled combo, so the room itself must say no.
    widget._room._turn_in_flight = True
    widget._room.change_lead("agy")
    pump(200)
    widget._room._turn_in_flight = False

    assert "Lead change ignored" in widget.transcript.toPlainText()
    assert widget.leadBox.currentText() == widget._room.orch.lead == "claude"


def test_a_dropped_line_is_not_echoed_and_a_closed_room_refuses(room):
    widget = room()
    widget._room.wait_until_ready()

    widget._room._turn_in_flight = True
    widget._submit("/team")
    widget._room._turn_in_flight = False
    text = widget.transcript.toPlainText()
    assert "you: /team" not in text and "/team" not in text.replace("Busy", "")
    assert "Busy" in text

    widget.close()
    assert widget._room.submit("x") is False
    assert widget._room._turn_in_flight is False


class HangingBackend:
    """A model that never answers, and records whether it was cancelled -- the only path on which
    DirectBackend kills an agent's process group."""

    def __init__(self) -> None:
        self.started, self.cancelled = threading.Event(), threading.Event()

    async def run(self, agent, prompt, cwd=None, schema=None):
        self.started.set()
        try:
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            self.cancelled.set()
            raise
        return "never"


def test_closing_mid_turn_cancels_the_running_agent(room):
    backend = HangingBackend()
    widget = room(backend=backend)
    widget._room.wait_until_ready()

    assert widget._room.submit("build the thing")
    assert backend.started.wait(5)
    widget.close()

    assert backend.cancelled.is_set(), "a closed room left its agent running"


def test_qsettings_is_hermetic(_hermetic_home):
    from PySide6.QtCore import QSettings

    assert QSettings("hexmind", "room").fileName().startswith(str(_hermetic_home))


def test_agentdeck_panel_imports():
    import importlib

    importlib.import_module("hexmind.qt.agentdeck_panel")


def test_room_survives_an_agentdeck_panel_error(room, monkeypatch):
    from hexmind.qt import agentdeck_panel, widget as W

    def explode(*args, **kwargs):
        raise RuntimeError("agentdeck API changed")

    monkeypatch.setattr(W, "_load_agentdeck_items", lambda: (True, []))
    monkeypatch.setattr(agentdeck_panel, "AgentdeckPanel", explode)
    widget = room()
    tabs = [widget._right.tabText(i) for i in range(widget._right.count())]
    assert "Agentdeck" not in tabs and "Team" in tabs


def test_tab_leaves_every_table(room):
    """QTableWidget defaults to tabKeyNavigation=True: Tab cycled cells forever and the room's
    focus chain dead-ended in the Team table."""
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QTableWidget

    from hexmind.qt.agentdeck_panel import AgentdeckPanel
    from hexmind.qt.model_selector import ModelSelectorDialog

    widget = room()
    widget.show()
    widget.activateWindow()
    widget.team.setFocus()
    pump(50)
    assert QApplication.focusWidget() is widget.team
    QTest.keyClick(widget.team, Qt.Key.Key_Tab)
    assert QApplication.focusWidget() is not widget.team

    dialog, panel = ModelSelectorDialog(), AgentdeckPanel([])
    tables = [*widget.findChildren(QTableWidget), dialog.table, panel.table]
    assert len(tables) >= 5
    assert [t for t in tables if t.tabKeyNavigation()] == []
    dialog.deleteLater()
    panel.deleteLater()


def test_tab_order_follows_the_screen(room):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    widget = room()
    widget.show()
    widget.activateWindow()
    widget.leadBox.setFocus()
    pump(50)
    seen = [QApplication.focusWidget()]
    for _ in range(3):
        QTest.keyClick(QApplication.focusWidget(), Qt.Key.Key_Tab)
        seen.append(QApplication.focusWidget())
    assert seen == [widget.leadBox, widget.teamButton, widget.auditBox, widget.transcript]


def test_the_lead_label_names_the_lead_box(room):
    widget = room()
    assert widget.leadLabel.buddy() is widget.leadBox


def test_top_bar_is_compact_and_steady(room):
    widget = room()
    widget.resize(1400, 900)
    widget.show()
    pump(50)
    assert widget.leadBox.width() < 400

    x = widget.teamButton.x()
    widget._on_turn_state(True)
    pump(50)
    assert widget.turnMeter.text()
    assert widget.teamButton.x() == x
    widget._on_turn_state(False)


# ---------- commands and the host signal ----------

def test_a_slash_command_reaches_the_room(room, available_models):
    available_models(["claude", "agy"])
    widget = room(backend=FakeBackend())
    widget.input.setText("/team")
    widget.send()
    pump(500)
    said = widget.transcript.toPlainText()
    assert "/team" in said
    assert "claude" in said, "the roster should be in the transcript"


def test_a_path_in_a_task_title_opens_in_the_host(room):
    """The one optional signal, matching agentdeck's `openRequested`: a file path the user
    double-clicked, and the host decides what to do with it. Absent signals still embed fine, so
    this is a convenience and not a contract."""
    seen: list[str] = []
    widget = room(backend=FakeBackend())
    widget.openFileRequested.connect(seen.append)
    widget.input.setText("go")
    widget.send()
    pump()

    widget._on_task_activated(widget.tasks.item(0, 4))  # t1, "edit hexmind/core.py"
    assert seen == ["hexmind/core.py"], seen


def test_prose_in_a_title_is_not_mistaken_for_a_path(room):
    seen: list[str] = []
    widget = room(backend=FakeBackend())
    widget.openFileRequested.connect(seen.append)
    widget.input.setText("go")
    widget.send()
    pump()

    widget._on_task_activated(widget.tasks.item(1, 4))  # t2, "write the tests"
    assert seen == [], "a title that merely contains a slash-ish word is not a path"


def test_keyboard_selection_fills_task_detail(room):
    """Only mouse clicks used to fill the detail pane; arrow keys fire currentItemChanged."""
    widget = room(backend=FakeBackend())
    widget.input.setText("go")
    widget.send()
    pump()

    widget.tasks.setCurrentCell(1, 1)
    first = widget.tasks.item(1, 0).text()
    assert first in widget.detail.toPlainText()


# ---------- lifecycle ----------

def test_closing_stops_the_room_thread(room):
    """A QThread destroyed while running aborts the process. The tab closing, the app quitting and
    the end of every test all go through here."""
    widget = room()
    room_thread = widget._room
    assert room_thread.isRunning()
    widget.close()
    assert not room_thread.isRunning(), "the worker thread outlived the widget"


def test_the_widget_survives_being_embedded_and_closed_twice(room):
    widget = room()
    widget.close()
    widget.close()  # idempotent: Qt can deliver closeEvent more than once
    assert not widget._room.isRunning()


def test_accessible_names_are_set_so_a_screen_reader_has_something(qapp):
    """Every interactive element needs a label a screen reader can read, and none of these have
    visible text of their own."""
    widget = HexmindWidget(backend=FakeBackend(), members=["claude"], lead="claude")
    try:
        for name in ("Lead", "Ask the team", "Conversation", "Tasks", "Team"):
            assert widget.findChildren(object), "sanity"
        assert widget.leadBox.accessibleName() == "Lead"
        assert widget.input.accessibleName() == "Ask the team"
        assert widget.transcript.accessibleName() == "Conversation"
        assert widget.tasks.accessibleName() == "Tasks"
        assert widget.team.accessibleName() == "Team"
    finally:
        widget.close()


def test_the_docs_smoke_line_works_verbatim():
    """docs/AETHER-INTERFACE.md defines done #1 as this exact one-liner, so it is run as a
    subprocess: two things it needs cannot be true in-process, because this test session already
    owns a QApplication and always closes its widgets.

    It failed twice before it passed, both times by aborting rather than raising: no QApplication
    at all, and then a QThread destroyed while running when the interpreter ended without a
    closeEvent. Qt's answer to both is to take the process down, which is a terrible first
    experience for a one-liner and impossible to debug from a traceback."""
    import subprocess
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    result = subprocess.run(
        [sys.executable, "-c",
         "from hexmind.qt import HexmindWidget; w = HexmindWidget(); print(w.__class__.__name__)"],
        capture_output=True, text=True, cwd=str(root), timeout=120, check=False,
        env={**__import__("os").environ, "QT_QPA_PLATFORM": "offscreen"})
    assert result.returncode == 0, f"the documented smoke line failed:\n{result.stderr[-800:]}"
    assert result.stdout.strip().endswith("HexmindWidget"), result.stdout


def test_stopping_twice_is_harmless(qapp):
    """`closeEvent` stops the room, the widget stays referenced by its host, and the atexit hook
    finds the same room again and stops it a second time. `call_soon_threadsafe` on a closed loop
    raises "Event loop is closed", so a host app that closed its window properly got a traceback on
    the way out. Found from Aether, embedding the widget for real — the test suite never saw it,
    because pytest tears the process down differently from `close()` then exit."""
    widget = HexmindWidget(backend=FakeBackend(), members=["claude"], lead="claude")
    room = widget._room
    widget.close()
    assert not room.isRunning()
    room.stop()  # must not raise
    assert not room.isRunning()
    widget.close()


# ---------- Phase 0: honest instruments ----------

def test_lead_box_shows_a_placeholder_when_there_is_no_lead(room):
    """Phase 0.1 (P1): with no lead the box reads as unset — a placeholder at index 0 — rather
    than silently pre-selecting the first member, which would look chosen without ever going
    through `set_lead`."""
    from hexmind.qt.widget import NO_LEAD_PLACEHOLDER

    widget = room(backend=FakeBackend(), lead=None)
    assert widget.leadBox.itemText(0) == NO_LEAD_PLACEHOLDER
    assert widget.leadBox.currentText() == NO_LEAD_PLACEHOLDER


def test_selecting_the_placeholder_never_reaches_the_room(room):
    """The placeholder is display, not a model: picking it must not call `set_lead` with prose."""
    from hexmind.qt.widget import NO_LEAD_PLACEHOLDER

    backend = FakeBackend()
    widget = room(backend=backend, lead=None)
    widget.leadBox.setCurrentText(NO_LEAD_PLACEHOLDER)
    pump(300)
    assert widget.lead is None
    assert backend.asked == []


def test_placeholder_clears_once_a_lead_is_picked(room):
    """After a real lead is chosen the placeholder is gone and the box shows the lead."""
    from hexmind.qt.widget import NO_LEAD_PLACEHOLDER

    widget = room(backend=FakeBackend(), lead=None)
    widget.leadBox.setCurrentText("claude")
    pump()
    assert widget.lead == "claude"
    assert widget.leadBox.currentText() == "claude"
    assert widget.leadBox.findText(NO_LEAD_PLACEHOLDER) == -1


def test_audit_checkbox_reflects_the_initial_flag(room):
    """Phase 0.2 (P2): the checkbox shows the orchestrator's true state from the first frame —
    checked when the room starts with audit on, unchecked otherwise."""
    assert room(backend=FakeBackend(), audit=True).auditBox.isChecked()
    assert not room(backend=FakeBackend()).auditBox.isChecked()
    assert not room(backend=FakeBackend(), audit=False).auditBox.isChecked()


def test_audit_checkbox_starts_in_sync_with_the_orchestrator(room):
    """The box and the room must agree: a checked box with audit off (or vice versa) would let
    the first toggle invert reality instead of changing it."""
    on = room(backend=FakeBackend(), audit=True)
    assert on.auditBox.isChecked() and on._room.orch.audit is True
    off = room(backend=FakeBackend(), audit=False)
    assert not off.auditBox.isChecked() and off._room.orch.audit is False


def test_theme_styles_checked_and_unchecked_indicators(qapp):
    """Phase 0.3 (P3): checkbox indicators are styled for the dark substrate — an unchecked box
    is a visible seam and a checked one posts green, so state never depends on the platform
    default rendering a pale checkmark on a dark ground."""
    from hexmind.qt import theme

    sheet = theme.stylesheet()
    assert "QCheckBox::indicator" in sheet
    assert "QCheckBox::indicator:checked" in sheet
    assert theme.GREEN in sheet


def test_theme_text_tokens_meet_wcag_aa_on_dark_surfaces():
    from hexmind.qt import theme

    def luminance(color):
        channels = [int(color[index:index + 2], 16) / 255 for index in (1, 3, 5)]
        linear = [(channel / 12.92 if channel <= 0.03928
                   else ((channel + 0.055) / 1.055) ** 2.4) for channel in channels]
        return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]

    def contrast(foreground, background):
        light = max(luminance(foreground), luminance(background))
        dark = min(luminance(foreground), luminance(background))
        return (light + 0.05) / (dark + 0.05)

    for background in (theme.SUBSTRATE, theme.PANEL):
        assert contrast(theme.INK, background) >= 4.5
        assert contrast(theme.INK_DIM, background) >= 4.5


def test_live_tap_records_turn_events_and_messages(room):
    widget = room()
    widget._on_turn_progress("claude", "planning")
    widget._on_live_output("claude", '{"event":"delta"}')
    widget._on_message("hexmind", "Plan ready")

    assert widget.live_tap.toPlainText().splitlines() == [
        "[claude] planning",
        '[claude] {"event":"delta"}',
        "hexmind: Plan ready",
    ]


def test_open_palette_delegates_without_a_live_palette(room):
    """Phase 0.4: `HexmindWidget.open_palette` is the menu's door to the Ctrl+K palette. A room
    whose palette failed to install answers by doing nothing, not by raising."""
    widget = room()
    widget._palette = None
    widget.open_palette()  # must not raise


def test_palette_commands_refresh_with_the_live_roster(room):
    widget = room()
    calls = []

    class Palette:
        def set_commands(self, commands):
            calls.append(commands)

    widget._palette = Palette()
    widget.members = ["claude", "agy"]
    widget._refresh_palette_commands()

    assert len(calls) == 1
    assert {command.name for command in calls[0]} >= {"lead: claude", "lead: agy"}


def test_task_detail_starts_collapsed_and_toggles(room):
    """Two equal empty panes used to fill the left column on the first frame."""
    widget = room()
    assert widget.detail.isHidden() is True

    widget.detail_toggle.click()
    assert widget.detail.isHidden() is False

    widget.detail_toggle.click()
    assert widget.detail.isHidden() is True


def test_layout_of_the_left_column(room):
    widget = room()
    widget.resize(1400, 900)
    widget.show()
    pump(50)
    assert widget.detail_toggle.width() < 200

    widget._on_message("claude", "hi")
    assert widget.detail.toPlainText() == "", "messages no longer mirror into Task detail"

    widget.detail_toggle.setChecked(True)
    pump(50)
    assert widget.transcript.height() > widget.detail.height()


def test_the_widget_hands_the_audit_ledger_to_the_orchestrator(room):
    """T16: `Orchestrator` records every audit verdict into `stats`, and with no ledger it records
    nothing at all. The checkbox still turns green, the panel still renders — and the session
    silently writes no history. The widget forwards what it is given, and does not resolve a path
    itself, so the same fix covers `hexmind`, the TUI, the server and here.

    `None` stays legal: an embedder that keeps its own ledger, or wants none, is not misconfigured."""
    from hexmind import auditor

    ledger = auditor.Stats("/tmp/hexmind-t16-stats.json")
    widget = room(stats=ledger)
    assert widget._room.orch.stats is ledger

    assert room()._room.orch.stats is None


# ---------- Phase 2: Live Wire and Hand Brake ----------

def test_turn_progress_and_live_meter(room):
    """Phase 2.1 & 2.2: status events bridge to turnProgress and update the Live Turn Meter."""
    widget = room()
    assert widget.status.text() == "ready"
    assert widget.turnMeter.text() == ""
    assert not widget.stopButton.isEnabled()

    # Emitting turnProgress updates the active agent and state
    widget._room.turnProgress.emit("claude", "planning")
    pump()
    # Meter is blank while turn is not in flight
    assert widget.turnMeter.text() == ""

    # Simulate turn in flight
    widget._on_turn_state(True)
    assert widget.status.text() == "working…"
    assert widget.stopButton.isEnabled()
    assert "[● claude · working ·" in widget.turnMeter.text()

    # Progress update during turn
    widget._room.turnProgress.emit("claude", "planning")
    pump()
    assert "[● claude · planning ·" in widget.turnMeter.text()

    widget._room.turnProgress.emit("claude", "evaluating")
    pump()
    assert "[● claude · evaluating ·" in widget.turnMeter.text()

    # Turn finishes
    widget._on_turn_state(False)
    assert widget.status.text() == "ready"
    assert widget.turnMeter.text() == ""
    assert not widget.stopButton.isEnabled()


def test_hand_brake_cancellation_aborts_in_flight_turn(room, available_models):
    """Phase 2.3 & 2.4: Stop button and cancel() abort an in-flight turn."""
    import asyncio
    import json

    release = asyncio.Event()

    class Slow:
        async def run(self, agent, prompt, cwd=None, schema=None):
            if "Decide which of the models" in prompt or "Plan for the team" in prompt:
                return json.dumps({
                    "reply": "working on it",
                    "tasks": [{"id": "t1", "title": "slow task", "agent": "claude", "instructions": "x", "depends_on": []}]
                })
            if "Write the final answer" in prompt:
                return "done"
            while not release.is_set():
                await asyncio.sleep(0.01)
            return "done"

    widget = room(backend=Slow())
    widget.input.setText("long run")
    widget.send()
    pump(300)

    assert widget.status.text() == "working…"
    assert widget.stopButton.isEnabled()
    assert not widget.input.isEnabled()

    # Pull the hand brake via cancel()
    widget.cancel()
    pump(500)

    # Clean recovery
    assert widget.status.text() == "ready"
    assert widget.input.isEnabled()
    assert not widget.stopButton.isEnabled()
    assert widget.turnMeter.text() == ""
    assert "Turn cancelled" in widget.transcript.toPlainText()


def test_tab_bar_fits_without_scroll_at_1400(room, qapp):
    """Task 3.4: Splitter proportions and tab bar fit at 1400px without scroll arrows."""
    from hexmind.qt import theme
    from PySide6.QtCore import Qt

    old_sheet = qapp.styleSheet()
    qapp.setStyleSheet(theme.stylesheet())
    try:
        widget = room()
        widget.resize(1400, 900)
        widget.show()
        pump(50)

        assert widget._split.widget(0).minimumWidth() == 420
        sizes = widget._split.sizes()
        assert sizes[0] >= 420 and sizes[1] > 0

        bar = widget._right.tabBar()
        assert bar.expanding() is False
        assert widget._right.elideMode() == Qt.TextElideMode.ElideRight

        union = bar.tabRect(0)
        for i in range(1, bar.count()):
            union = union.united(bar.tabRect(i))
        assert union.width() <= bar.width(), (
            f"tab bar union width ({union.width()}px) must fit in bar width ({bar.width()}px)"
        )
    finally:
        qapp.setStyleSheet(old_sheet)


def test_empty_states_for_tables_and_graph(room, qapp):
    """Task 3.5: Empty states for Tasks, Team, Live Tap and Graph."""
    from hexmind.qt import theme

    old_sheet = qapp.styleSheet()
    qapp.setStyleSheet(theme.stylesheet())
    try:
        widget = room()
        widget.resize(1000, 700)
        widget.show()
        pump(50)

        assert widget.tasks.empty_text == "No tasks yet. The lead's plan lands here."
        assert widget.tasks.rowCount() == 0
        img_tasks = widget.tasks.grab().toImage()
        bg_tasks = img_tasks.pixelColor(10, 10)
        w_t, h_t = img_tasks.width(), img_tasks.height()
        tasks_has_ink = any(
            img_tasks.pixelColor(x, y) != bg_tasks
            for y in range(h_t // 3, (2 * h_t) // 3)
            for x in range(w_t // 4, (3 * w_t) // 4)
        )
        assert tasks_has_ink, "empty Tasks table should paint centered hint text"

        assert widget.graph is not None
        assert not widget.graph._nodes
        img_graph = widget.graph.grab().toImage()
        bg_graph = img_graph.pixelColor(10, 10)
        w_g, h_g = img_graph.width(), img_graph.height()
        graph_has_ink = any(
            img_graph.pixelColor(x, y) != bg_graph
            for y in range(h_g // 3, (2 * h_g) // 3)
            for x in range(w_g // 4, (3 * w_g) // 4)
        )
        assert graph_has_ink, "empty Graph view should paint centered hint text"

        assert widget.live_tap.placeholderText() == "Live tap output appears during a turn."
    finally:
        qapp.setStyleSheet(old_sheet)


def test_panel_spacing_stats_timeline_and_direct_line(qapp):
    """Task 3.8: Stats margins, Timeline columns without hscroll at 600px, Direct Line intro."""
    from hexmind.qt.chat import DirectLine
    from hexmind.qt.stats import StatsPanel
    from hexmind.qt.timeline import TimelinePanel

    # 1. Stats outer margins
    stats = StatsPanel()
    margins = stats.layout().contentsMargins()
    assert (margins.left(), margins.top(), margins.right(), margins.bottom()) == (8, 8, 8, 8)
    stats.close()

    # 2. Empty Timeline at 600px wide has no horizontal scrollbar
    timeline = TimelinePanel()
    timeline.resize(600, 400)
    timeline.show()
    pump(50)
    assert timeline.table.horizontalScrollBar().isVisible() is False
    timeline.close()

    # 3. Direct Line outputs are taller than the intro box
    chat = DirectLine()
    chat.resize(800, 600)
    chat.show()
    pump(50)
    assert chat.primary_output.height() > chat.transcript.height()
    assert chat.transcript.maximumHeight() <= 100
    chat.close()

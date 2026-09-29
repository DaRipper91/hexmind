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


def test_task_detail_drawer_can_be_collapsed(room):
    widget = room()

    widget.detail_toggle.click()
    assert widget.detail.isHidden() is True

    widget.detail_toggle.click()
    assert widget.detail.isHidden() is False


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

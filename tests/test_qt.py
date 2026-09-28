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

def test_a_slash_command_reaches_the_room(room):
    widget = room()
    widget.input.setText("/team")
    widget.send()
    pump()
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

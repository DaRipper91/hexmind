import asyncio
import json
import os
from unittest.mock import patch

from textual.widgets import Static
from hexmind.tui import HelpModal, HexmindApp, TaskSheet, TaskTable, copy_to_clipboard, is_ascii
from tests.test_core import FakeBackend


def make_test_plan():
    return json.dumps({
        "reply": "plan ready",
        "tasks": [
            {"id": "a", "agent": "claude", "title": "build database", "instructions": "setup tables"},
            {"id": "b", "agent": "agy", "title": "write api", "depends_on": ["a"], "instructions": "add endpoints"},
        ]
    })


def test_narrow_portrait_layout_and_columns():
    """Verify 40x20 narrow portrait has tabbed collapse, 3-column table, and shortened subtitle."""
    async def go():
        app = HexmindApp(FakeBackend(make_test_plan()), ["claude", "agy"], "claude", "test")
        async with app.run_test(size=(40, 20)) as pilot:
            assert app.has_class("narrow")
            assert not app.has_class("wide")
            assert app.active_tab == "chat"
            assert app.query_one("#left").display is True
            assert app.query_one("#right").display is False

            # Check 3-column table in narrow mode
            table = app.query_one("#tasks", TaskTable)
            assert [c.value for c in table.columns.keys()] == ["task", "status", "title"]

            # Check compact subtitle on < 60 cols
            assert "test · claude" in app.sub_title

    asyncio.run(go())


def test_tab_switching_touch_and_keys():
    """Verify switching between Chat and Tasks tabs via touch buttons and single-key navigation."""
    async def go():
        app = HexmindApp(FakeBackend(make_test_plan()), ["claude", "agy"], "claude", "test")
        async with app.run_test(size=(40, 20)) as pilot:
            # Tap Tasks tab button
            await pilot.click("#btn-tasks")
            assert app.active_tab == "tasks"
            assert app.query_one("#left").display is False
            assert app.query_one("#right").display is True
            assert app.query_one("#btn-tasks").has_class("-active-tab")
            assert not app.query_one("#btn-chat").has_class("-active-tab")

            # Toggle view via 'v' key
            await pilot.press("v")
            assert app.active_tab == "chat"
            assert app.query_one("#left").display is True
            assert app.query_one("#right").display is False

            # Switch back to tasks, then press 'i' to jump back and focus input
            await pilot.click("#btn-tasks")
            assert app.active_tab == "tasks"
            await pilot.press("i")
            assert app.active_tab == "chat"
            assert app.query_one("#input").has_focus

    asyncio.run(go())


def test_escape_to_blur():
    """Verify escape blurs the text input."""
    async def go():
        app = HexmindApp(FakeBackend(make_test_plan()), ["claude", "agy"], "claude", "test")
        async with app.run_test(size=(40, 20)) as pilot:
            inp = app.query_one("#input")
            inp.focus()
            assert inp.has_focus
            await pilot.press("escape")
            assert not inp.has_focus

    asyncio.run(go())


def test_single_tap_task_selection_opens_tasksheet():
    """Verify tapping a row in narrow mode opens the TaskSheet modal screen."""
    async def go():
        app = HexmindApp(FakeBackend(make_test_plan()), ["claude", "agy"], "claude", "test")
        async with app.run_test(size=(40, 20)) as pilot:
            # Run plan
            await pilot.click("#input")
            await pilot.press(*"start", "enter")
            await app.workers.wait_for_complete()
            await pilot.pause()

            # Switch to tasks view
            await pilot.click("#btn-tasks")
            assert app.active_tab == "tasks"
            table = app.query_one("#tasks", TaskTable)
            assert table.row_count == 2

            # Tap row
            await pilot.click(TaskTable, offset=(2, 1))
            await pilot.pause()
            assert isinstance(app.screen, TaskSheet)

            # Close modal via Close button
            await pilot.click("#sheet-close")
            await pilot.pause()
            assert not isinstance(app.screen, TaskSheet)

    asyncio.run(go())


def test_help_modal_and_clear_action():
    """Verify Action Bar help button and clear chat button."""
    async def go():
        app = HexmindApp(FakeBackend(make_test_plan()), ["claude", "agy"], "claude", "test")
        async with app.run_test(size=(40, 20)) as pilot:
            # Open help modal via button
            await pilot.click("#btn-help")
            await pilot.pause()
            assert isinstance(app.screen, HelpModal)

            # Close help modal with escape
            await pilot.press("escape")
            await pilot.pause()
            assert not isinstance(app.screen, HelpModal)

            # Verify Clear button clears chat
            chat = app.query_one("#chat")
            assert len(chat.lines) > 0
            await pilot.click("#btn-clear")
            assert len(chat.lines) == 0

    asyncio.run(go())


def test_short_and_ultra_short_modes():
    """Verify short height (<20) collapses #team, and ultra-short (<12) hides header/footer gracefully."""
    async def go():
        app = HexmindApp(FakeBackend(make_test_plan()), ["claude", "agy"], "claude", "test")
        async with app.run_test(size=(40, 15)) as pilot:
            assert app.has_class("short")
            assert not app.has_class("ultra-short")
            team_text = app.query_one("#team", Static).content
            # In short mode, team is 1 summary line
            assert "busy" in str(team_text) and "idle" in str(team_text)

    async def go_ultra_short():
        app = HexmindApp(FakeBackend(make_test_plan()), ["claude", "agy"], "claude", "test")
        async with app.run_test(size=(40, 10)) as pilot:
            assert app.has_class("ultra-short")
            assert app.query_one("Header").display is False
            assert app.query_one("Footer").display is False

    asyncio.run(go())
    asyncio.run(go_ultra_short())


def test_wide_landscape_mode():
    """Verify wide landscape viewport (100x24) retains desktop dual-column layout with 5 columns."""
    async def go():
        app = HexmindApp(FakeBackend(make_test_plan()), ["claude", "agy"], "claude", "test")
        async with app.run_test(size=(100, 24)) as pilot:
            assert app.has_class("wide")
            assert not app.has_class("narrow")
            assert app.query_one("#left").display is True
            assert app.query_one("#right").display is True
            assert app.query_one("#detail").display is True

            table = app.query_one("#tasks", TaskTable)
            assert [c.value for c in table.columns.keys()] == ["task", "agent", "status", "audit", "title"]

    asyncio.run(go())


def test_ascii_mode_environment_variable():
    """Verify FORCE_ASCII=1 triggers ASCII tab labels and glyphs."""
    with patch.dict(os.environ, {"FORCE_ASCII": "1"}):
        assert is_ascii() is True
        app = HexmindApp(FakeBackend(make_test_plan()), ["claude", "agy"], "claude", "test")
        assert app.ascii_mode is True


def test_clipboard_helper():
    """Verify copy_to_clipboard executes without error."""
    assert copy_to_clipboard("") is False
    assert copy_to_clipboard("test output string") is True

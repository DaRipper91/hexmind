"""Headless Textual pilot tests for phone-size screens, touch taps and resizing.

Covers the acceptance matrix for the mobile/touch spec: render at 40x24, 60x30
and 120x40 with every critical control on screen, breakpoint switching, taps on
the action bar, single-key alternatives to the Ctrl chords, and resizing while
a request is running.
"""
import asyncio
import json
from unittest.mock import patch

import pytest
from rich.cells import cell_len
from textual.widgets import Button, Input, RichLog

from hexmind.tui import HelpModal, HexmindApp, TaskTable
from tests.test_core import FakeBackend

PLAN = json.dumps({"reply": "plan ready", "tasks": [
    {"id": "a", "agent": "claude", "title": "build database", "instructions": "setup tables"},
    {"id": "b", "agent": "agy", "title": "write api", "depends_on": ["a"], "instructions": "add endpoints"},
]})
ACTION_BUTTONS = ["#btn-chat", "#btn-tasks", "#btn-clear", "#btn-help", "#btn-quit"]
WIDE_COLUMNS = ["task", "agent", "status", "audit", "title"]
NARROW_COLUMNS = ["task", "status", "title"]


def make_app(backend=None):
    return HexmindApp(backend or FakeBackend(PLAN), ["claude", "agy"], "claude", "test")


def columns(app):
    return [c.value for c in app.query_one("#tasks", TaskTable).columns.keys()]


def assert_on_screen(app, selector):
    """The widget is displayed, has area, and lies fully inside the terminal."""
    widget = app.query_one(selector)
    region = widget.region
    assert widget.display, f"{selector} hidden"
    assert region.width > 0 and region.height > 0, f"{selector} has no area: {region}"
    assert app.screen.region.contains_region(region), f"{selector} clipped: {region} vs {app.screen.region}"
    return widget


def assert_action_bar_fits(app):
    buttons = [assert_on_screen(app, sel) for sel in ACTION_BUTTONS]
    for b in buttons:
        assert b.region.width >= cell_len(str(b.label)), f"{b.id} label clipped in {b.region}"
    for i, a in enumerate(buttons):
        for b in buttons[i + 1:]:
            assert not a.region.overlaps(b.region), f"{a.id} overlaps {b.id}"


# ---------- (1) rendering at target sizes ----------

@pytest.mark.parametrize("size", [(40, 24), (60, 30), (120, 40)])
def test_renders_at_size_without_clipping_critical_controls(size):
    async def go():
        app = make_app()
        async with app.run_test(size=size) as pilot:
            await pilot.pause()
            assert app.size == size
            app.export_screenshot()  # full render of every widget must not raise
            assert_action_bar_fits(app)
            assert_on_screen(app, "#input")
            assert_on_screen(app, "#chat")
            if size[0] >= 80:
                assert_on_screen(app, "#tasks")
                assert_on_screen(app, "#detail")
            else:
                await pilot.click("#btn-tasks")
                await pilot.pause()
                assert_on_screen(app, "#tasks")
                assert_action_bar_fits(app)
            app.export_screenshot()

    asyncio.run(go())


def test_renders_task_board_with_rows_at_every_size():
    async def go():
        app = make_app()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.click("#input")
            await pilot.press(*"start", "enter")
            await app.workers.wait_for_complete()
            await pilot.pause()
            for size in [(40, 24), (60, 30), (120, 40)]:
                await pilot.resize_terminal(*size)
                await pilot.pause()
                if size[0] < 80:
                    app.switch_tab("tasks")
                    await pilot.pause()
                table = assert_on_screen(app, "#tasks")
                assert table.row_count == 2
                if size[0] < 80:  # phone table fits its pane: no sideways scrolling
                    assert table.virtual_size.width <= table.scrollable_content_region.width
                app.export_screenshot()

    asyncio.run(go())


# ---------- (2) breakpoint switching ----------

@pytest.mark.parametrize("width,narrow", [(79, True), (80, False), (40, True), (120, False)])
def test_width_breakpoint(width, narrow):
    async def go():
        app = make_app()
        async with app.run_test(size=(width, 30)):
            assert app.has_class("narrow") is narrow
            assert app.has_class("wide") is not narrow
            assert columns(app) == (NARROW_COLUMNS if narrow else WIDE_COLUMNS)
            assert app.query_one("#detail").display is not narrow
            assert app.query_one("#right").display is not narrow  # narrow starts on Chat

    asyncio.run(go())


@pytest.mark.parametrize("height,short,ultra", [(20, False, False), (19, True, False),
                                                (12, True, False), (11, True, True)])
def test_height_breakpoints(height, short, ultra):
    async def go():
        app = make_app()
        async with app.run_test(size=(60, height)):
            assert app.has_class("short") is short
            assert app.has_class("ultra-short") is ultra
            assert app.query_one("Header").display is not ultra
            assert app.query_one("Footer").display is not ultra
            assert_on_screen(app, "#input")
            assert_action_bar_fits(app)

    asyncio.run(go())


def test_subtitle_shortens_below_60_columns():
    async def go():
        app = make_app()
        async with app.run_test(size=(59, 24)) as pilot:
            assert app.sub_title == "test · claude · audit:off"
            await pilot.resize_terminal(60, 24)
            await pilot.pause()
            assert app.sub_title == "test backend · lead: claude · audit: off"

    asyncio.run(go())


# ---------- (3) taps on action-bar buttons ----------

@pytest.mark.parametrize("size", [(40, 24), (120, 40)])
def test_action_bar_taps_trigger_actions(size):
    async def go():
        app = make_app()
        async with app.run_test(size=size) as pilot:
            await pilot.click("#btn-tasks")
            assert app.active_tab == "tasks"
            assert app.query_one("#tasks").has_focus
            assert app.query_one("#btn-tasks").has_class("-active-tab")

            await pilot.click("#btn-chat")
            assert app.active_tab == "chat"
            assert app.query_one("#input").has_focus
            assert app.query_one("#btn-chat").has_class("-active-tab")

            await pilot.click("#btn-help")
            await pilot.pause()
            assert isinstance(app.screen, HelpModal)
            await pilot.click("#help-close")
            await pilot.pause()
            assert not isinstance(app.screen, HelpModal)

            chat = app.query_one("#chat", RichLog)
            assert chat.lines
            await pilot.click("#btn-clear")
            assert not chat.lines and not app.chat_history

            with patch.object(app, "exit") as exit_:
                await pilot.click("#btn-quit")
                exit_.assert_called_once()

    asyncio.run(go())


def test_quit_button_exits_app():
    async def go():
        app = make_app()
        async with app.run_test(size=(40, 24)) as pilot:
            await pilot.click("#btn-quit")
            await pilot.pause()
        assert app.return_code == 0

    asyncio.run(go())


def test_tapping_tab_buttons_does_not_steal_typed_text():
    async def go():
        app = make_app()
        async with app.run_test(size=(40, 24)) as pilot:
            await pilot.press(*"half")
            await pilot.click("#btn-tasks")
            await pilot.click("#btn-chat")
            assert app.query_one("#input", Input).value == "half"

    asyncio.run(go())


# ---------- (4) single-key alternatives to chords ----------

def test_q_is_single_key_quit_like_ctrl_q():
    async def go():
        for keys in (["escape", "q"], ["ctrl+q"]):
            app = make_app()
            async with app.run_test(size=(40, 24)) as pilot:
                with patch.object(app, "action_quit") as quit_:
                    await pilot.press(*keys)
                    await pilot.pause()
                    quit_.assert_called_once()

    asyncio.run(go())


def test_c_is_single_key_clear_like_ctrl_l():
    async def go():
        for keys in (["escape", "c"], ["ctrl+l"]):
            app = make_app()
            async with app.run_test(size=(40, 24)) as pilot:
                assert app.query_one("#chat", RichLog).lines
                await pilot.press(*keys)
                await pilot.pause()
                assert not app.query_one("#chat", RichLog).lines

    asyncio.run(go())


def test_single_keys_are_typed_text_while_input_focused():
    async def go():
        app = make_app()
        async with app.run_test(size=(40, 24)) as pilot:
            await pilot.press(*"qcvi")
            assert app.query_one("#input", Input).value == "qcvi"
            assert app.is_running and app.active_tab == "chat"

    asyncio.run(go())


def test_view_help_and_focus_keys():
    async def go():
        app = make_app()
        async with app.run_test(size=(40, 24)) as pilot:
            await pilot.press("escape")
            assert not app.query_one("#input").has_focus
            await pilot.press("v")
            assert app.active_tab == "tasks"
            await pilot.press("tab")
            assert app.active_tab == "chat"
            await pilot.press("escape", "question_mark")
            await pilot.pause()
            assert isinstance(app.screen, HelpModal)
            await pilot.press("question_mark")
            await pilot.pause()
            assert not isinstance(app.screen, HelpModal)
            app.switch_tab("tasks")
            await pilot.press("i")
            assert app.active_tab == "chat" and app.query_one("#input").has_focus

    asyncio.run(go())


def test_v_moves_focus_between_panes_on_wide_screen():
    async def go():
        app = make_app()
        async with app.run_test(size=(120, 40)) as pilot:
            assert app.query_one("#input").has_focus
            await pilot.press("tab")
            assert app.query_one("#tasks").has_focus
            await pilot.press("v")
            assert app.query_one("#input").has_focus

    asyncio.run(go())


# ---------- (5) resizing while running ----------

class GatedBackend(FakeBackend):
    """Workers block until released, so the test can resize mid-request."""

    def __init__(self, lead_plan):
        super().__init__(lead_plan)
        self.release = asyncio.Event()
        self.started = asyncio.Event()

    async def run(self, agent, prompt, cwd=None):
        if "Your task (" in prompt:
            self.started.set()
            await self.release.wait()
        return await super().run(agent, prompt, cwd)


def test_resize_while_request_is_running():
    async def go():
        backend = GatedBackend(PLAN)
        app = make_app(backend)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.press(*"build it", "enter")
            await asyncio.wait_for(backend.started.wait(), 5)
            await pilot.pause()
            table = app.query_one("#tasks", TaskTable)
            assert table.row_count == 2
            assert app.tasks["1.a"].status == "running"
            history = list(app.chat_history)

            for size in [(40, 24), (100, 8), (60, 30), (39, 15), (120, 40), (40, 24)]:
                await pilot.resize_terminal(*size)
                await pilot.pause()
                narrow = size[0] < 80
                assert app.has_class("narrow") is narrow
                assert columns(app) == (NARROW_COLUMNS if narrow else WIDE_COLUMNS)
                assert table.row_count == 2
                assert app.chat_history == history
                assert_on_screen(app, "#input")
                assert_action_bar_fits(app)
                app.export_screenshot()

            # finish the run while narrow; the compressed table picks up updates
            backend.release.set()
            await app.workers.wait_for_complete()
            await pilot.pause()
            assert [t.status for t in app.tasks.values()] == ["done", "done"]
            assert str(table.get_cell("1.a", "status")) == "done"
            assert "Tasks" in str(app.query_one("#btn-tasks", Button).label)
            assert "(" not in str(app.query_one("#btn-tasks", Button).label)  # no active tasks badge

            await pilot.resize_terminal(120, 40)
            await pilot.pause()
            assert columns(app) == WIDE_COLUMNS
            assert str(table.get_cell("1.b", "agent")) == app.orch.name("agy")
            assert str(table.get_cell("1.b", "status")) == "done"

    asyncio.run(go())


def test_resize_keeps_table_cursor_and_tab():
    async def go():
        app = make_app()
        async with app.run_test(size=(40, 24)) as pilot:
            await pilot.press(*"start", "enter")
            await app.workers.wait_for_complete()
            await pilot.pause()
            app.switch_tab("tasks")
            table = app.query_one("#tasks", TaskTable)
            table.move_cursor(row=1)
            await pilot.resize_terminal(120, 40)
            await pilot.pause()
            assert table.cursor_row == 1
            await pilot.resize_terminal(40, 24)
            await pilot.pause()
            assert table.cursor_row == 1
            assert app.active_tab == "tasks"
            assert_on_screen(app, "#tasks")

    asyncio.run(go())


def test_chat_wraps_to_screen_width_and_rewraps_on_rotate():
    """RichLog's default min_width of 78 made the chat scroll sideways on a phone."""
    async def go():
        app = make_app()
        async with app.run_test(size=(40, 24)) as pilot:
            app.say("claude", "word " * 60)
            await pilot.pause()
            chat = app.query_one("#chat", RichLog)
            for size in [(40, 24), (60, 30), (120, 40), (40, 24)]:
                await pilot.resize_terminal(*size)
                await pilot.pause()
                await pilot.pause()
                assert chat.virtual_size.width <= chat.scrollable_content_region.width, size
                assert chat.virtual_size.width >= chat.scrollable_content_region.width - 2, size
    asyncio.run(go())

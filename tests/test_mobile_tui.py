"""Acceptance tests for docs/mobile-tui.md: 40x20, 60x30 and 120x40 layouts, taps, single keys, scrolling, resizing."""
import asyncio
import json

import pytest
from textual import events
from textual.containers import ScrollableContainer
from textual.widgets import DataTable, RichLog

from hexmind.tui import HexmindApp
from tests.test_core import FakeBackend

LONG = "a fairly long task title that could never fit on one line of a phone held upright in portrait"
PLAN = json.dumps({"reply": "on it " + "word " * 60, "tasks": [
    {"id": "a", "agent": "claude", "title": LONG},
    {"id": "b", "agent": "agy", "title": "b"},
    {"id": "c", "agent": "agy", "title": "c"}]})


def _app(plan=PLAN):
    return HexmindApp(FakeBackend(plan), ["claude", "agy"], "claude", "test")


async def _run_plan(app, pilot):
    app.query_one("#input").focus()
    await pilot.press(*"go", "enter")
    await app.workers.wait_for_complete()
    await pilot.pause()


def _assert_no_horizontal_overflow(app, width):
    for w in app.screen.walk_children(with_self=True):
        if not w.display or not w.region.width:
            continue
        assert w.region.right <= width, f"{w} sticks out past column {width}: {w.region}"
        if isinstance(w, (ScrollableContainer, RichLog)) and (width < 80 or w.id not in ("tasks", "detail")):
            # the 1fr desktop task pane always scrolled sideways; wide layout is deliberately unchanged
            assert w.max_scroll_x == 0, f"{w} scrolls sideways by {w.max_scroll_x}"


def _chat_lines(app):
    return len(app.query_one("#chat", RichLog).lines)


# ---------- layout matrix ----------
@pytest.mark.parametrize("size", [(40, 20), (60, 30), (120, 40)])
def test_layout_matrix(size):
    width, height = size
    narrow = width < 80

    async def go():
        app = _app()
        async with app.run_test(size=size) as pilot:
            await _run_plan(app, pilot)
            left, right, tabs = app.query_one("#left"), app.query_one("#right"), app.query_one("#tabs")
            table = app.query_one("#tasks", DataTable)
            assert app.has_class("narrow") is narrow and tabs.display is narrow
            if narrow:
                assert [c.value for c in table.columns] == ["task", "status", "title"]
                assert left.display and not right.display  # one primary view at a time
                assert left.region.width == width
            else:  # desktop layout untouched: 2fr / 1fr side by side, 5 columns, detail pane
                assert [c.value for c in table.columns] == ["task", "agent", "status", "audit", "title"]
                assert left.display and right.display and app.query_one("#detail").display
                assert left.region.width == pytest.approx(2 * right.region.width, abs=2)
                assert left.region.y == right.region.y
            for view in ("chat", "tasks") if narrow else ("chat",):
                app.set_view(view)
                await pilot.pause()
                _assert_no_horizontal_overflow(app, width)
            if narrow:  # task status readable without scrolling the table sideways
                status_right = sum(c.get_render_width(table) for c in table.ordered_columns[:2])
                assert status_right <= table.scrollable_content_region.width
                assert table.region.height >= 6
            for button in tabs.query("Button") if narrow else ():
                assert button.region.width >= len(str(button.label)) and button.region.height >= 1  # untruncated target

    asyncio.run(go())


@pytest.mark.parametrize("size", [(40, 20), (60, 30), (79, 30)])
def test_narrow_tab_bar_keeps_every_tap_target_whole(size):
    """Six auto-width buttons and a spacer in one row. 40 is the documented minimum viewport, so
    the bar has to fit its own labels there without padding them out; the help button at the far
    end is the one that fell off. Assert the whole bar, not one button, at every narrow width."""
    width, height = size

    async def go():
        app = _app()
        async with app.run_test(size=size) as pilot:
            await _run_plan(app, pilot)
            tabs = app.query_one("#tabs")
            assert tabs.region.right <= width
            for button in tabs.query("Button"):
                assert button.region.height == 1
                assert button.region.width >= len(str(button.label)), f"{button.id} is truncated"
                assert button.region.right <= width, f"{button.id} sticks out: {button.region}"
            _assert_no_horizontal_overflow(app, width)

    asyncio.run(go())


@pytest.mark.parametrize("size", [(40, 20), (30, 20), (14, 20)])
def test_task_sheet_button_row_stays_inside_the_viewport(size):
    """The same pattern the tab bar had (cc529e9): auto-width buttons in a one-row bar with a
    1-cell margin each. The tab bar had six controls and overflowed at the 40-column floor; the
    sheet has only two short labels (Close/Copy) so it has room to spare at 40 and only overflows at
    ≤14 columns. The margin-right: 0 fix prevents regression if more buttons or longer labels are
    added, and this test covers the actual overflow threshold (14) as well as the phone floor (30, 40)."""
    width, height = size

    async def go():
        app = _app()
        async with app.run_test(size=size) as pilot:
            await _run_plan(app, pilot)
            await pilot.press("escape")
            app.query_one("#tasks", DataTable).focus()
            await pilot.press("enter")  # one tap on a row opens its detail sheet
            await pilot.pause()
            assert type(app.screen).__name__ == "TaskScreen"
            for button in app.screen.query("Button"):
                assert button.region.height == 1
                assert button.region.width >= len(str(button.label)), f"{button.id} is truncated"
                assert button.region.right <= width, f"{button.id} sticks out: {button.region}"
            _assert_no_horizontal_overflow(app, width)

    asyncio.run(go())


def test_chat_wraps_inside_narrow_screen():
    async def go():
        app = _app()
        async with app.run_test(size=(60, 30)) as pilot:
            await _run_plan(app, pilot)
            chat = app.query_one("#chat", RichLog)
            assert max(line.cell_length for line in chat.lines) <= 58
            assert chat.max_scroll_x == 0

    asyncio.run(go())


# ---------- touch / mouse ----------
def test_every_primary_action_is_tappable():
    async def go():
        app = _app()
        async with app.run_test(size=(40, 20)) as pilot:
            await _run_plan(app, pilot)
            assert str(app.query_one("#tab-tasks").label) == "Tasks"  # all done: no pending count
            await pilot.click("#tab-tasks")
            assert app.view == "tasks" and app.focused is app.query_one("#tasks")
            await pilot.click("#tab-chat")
            assert app.view == "chat" and app.focused is app.query_one("#input")
            await pilot.click("#do-help")
            assert type(app.screen).__name__ == "HelpScreen"
            await pilot.click("#close")
            assert type(app.screen).__name__ == "Screen"
            await pilot.click("#tab-tasks")
            # one tap on a row that isn't highlighted opens its detail sheet
            table = app.query_one("#tasks", DataTable)
            assert table.cursor_row == 0
            await pilot.click("#tasks", offset=(2, 3))  # header + row 0 + row 1 -> row 2
            await pilot.pause()
            assert type(app.screen).__name__ == "TaskScreen"
            assert "1.c" in str(app.screen.query_one(RichLog).lines[0].text)
            await pilot.click("#close")
            await pilot.pause()
            assert type(app.screen).__name__ == "Screen" and app.view == "tasks"
            assert _chat_lines(app)
            await pilot.click("#do-clear")
            assert _chat_lines(app) == 0
            await pilot.click("#do-quit")
        assert not app.is_running

    asyncio.run(go())


def test_task_counter_on_tab_shows_unfinished_work():
    async def go():
        app = _app()
        async with app.run_test(size=(40, 20)) as pilot:
            await _run_plan(app, pilot)
            app.tasks["1.b"].status = "running"
            app.on_team_event("task", {"task": app.tasks["1.b"]})
            assert str(app.query_one("#tab-tasks").label) == "Tasks (1)"

    asyncio.run(go())


# ---------- single keys ----------
def test_primary_actions_have_single_key_bindings():
    keys = {b.action: b.key for b in HexmindApp.BINDINGS if not isinstance(b, tuple)}
    for action in ("quit", "clear", "toggle_view", "focus_input", "move(1)", "move(-1)", "help", "blur"):
        assert action in keys and any("+" not in k for k in keys[action].split(",")), action


def test_every_primary_action_by_single_key():
    async def go():
        app = _app()
        async with app.run_test(size=(40, 20)) as pilot:
            await _run_plan(app, pilot)
            await pilot.press("escape")  # leave the input; keys are shortcuts from here
            assert app.focused is app.query_one("#chat")
            await pilot.press("v")
            table = app.query_one("#tasks", DataTable)
            assert app.view == "tasks" and app.focused is table
            await pilot.press("j", "j")
            assert table.cursor_row == 2
            await pilot.press("k")
            assert table.cursor_row == 1
            await pilot.press("enter")  # Enter on a task row opens it rather than the input
            assert type(app.screen).__name__ == "TaskScreen"
            await pilot.press("q")  # q closes the sheet, it doesn't quit
            assert app.is_running and type(app.screen).__name__ == "Screen"
            await pilot.press("v")
            assert app.view == "chat"
            await pilot.press("escape", "question_mark")
            assert type(app.screen).__name__ == "HelpScreen"
            await pilot.press("question_mark")
            await pilot.press("escape", "c")
            assert _chat_lines(app) == 0
            await pilot.press("i")
            assert app.focused is app.query_one("#input")
            await pilot.press("escape", "enter")
            assert app.focused is app.query_one("#input")
            await pilot.press("escape", "q")
        assert not app.is_running

    asyncio.run(go())


def test_desktop_chords_still_work_while_typing():
    async def go():
        app = _app()
        async with app.run_test(size=(120, 40)) as pilot:
            await _run_plan(app, pilot)
            assert app.focused is app.query_one("#input")
            await pilot.press("ctrl+l")
            assert _chat_lines(app) == 0
            await pilot.press("ctrl+q")
        assert not app.is_running

    asyncio.run(go())


# ---------- scrolling ----------
async def _scroll(pilot, widget, down: bool, times: int = 3):
    cls = events.MouseScrollDown if down else events.MouseScrollUp
    for _ in range(times):
        widget.post_message(cls(widget, 1, 1, 0, 1 if down else -1, 0, False, False, False))
    await pilot.pause()


@pytest.mark.parametrize("size", [(40, 20), (120, 40)])
def test_scroll_events_move_chat_and_task_list(size):
    many = json.dumps({"reply": "on it", "tasks": [{"id": f"t{i}", "agent": "claude", "title": f"task {i}"}
                                                   for i in range(40)]})

    async def go():
        app = _app(many)
        async with app.run_test(size=size) as pilot:
            await _run_plan(app, pilot)
            chat = app.query_one("#chat", RichLog)
            assert chat.max_scroll_y > 0 and chat.scroll_y == chat.max_scroll_y  # follows the conversation
            await _scroll(pilot, chat, down=False)
            top = chat.scroll_y
            assert top < chat.max_scroll_y
            await _scroll(pilot, chat, down=True)
            assert chat.scroll_y > top
            await pilot.press("escape", "k")  # k scrolls the chat up one line
            assert chat.scroll_y < chat.max_scroll_y
            if app.has_class("narrow"):
                await pilot.press("v")
            table = app.query_one("#tasks", DataTable)
            assert table.max_scroll_y > 0 and table.scroll_y == 0
            await _scroll(pilot, table, down=True)
            assert table.scroll_y > 0
            await _scroll(pilot, table, down=False, times=10)
            assert table.scroll_y == 0

    asyncio.run(go())


# ---------- resizing while running ----------
def test_resize_while_running_reflows_everything():
    async def go():
        app = _app()
        async with app.run_test(size=(120, 40)) as pilot:
            await _run_plan(app, pilot)
            table = app.query_one("#tasks", DataTable)
            await pilot.press("escape")
            table.focus()
            await pilot.press("down")
            for size in [(40, 20), (60, 30), (120, 40), (40, 20), (79, 30), (80, 30), (60, 8), (60, 30)]:
                await pilot.resize_terminal(*size)
                await pilot.pause()
                width, height = size
                narrow = width < 80
                assert app.has_class("narrow") is narrow and app.has_class("tiny") is (height < 10)
                assert len(table.columns) == (3 if narrow else 5) and table.row_count == 3
                assert table.cursor_row == 1  # cursor survives the column rebuild
                chat_width = width if narrow else 2 * width // 3
                assert max(line.cell_length for line in app.query_one("#chat", RichLog).lines) <= chat_width - 2  # re-wrapped
                for view in ("chat", "tasks") if narrow else ("chat",):
                    app.set_view(view)
                    await pilot.pause()
                    _assert_no_horizontal_overflow(app, width)
            assert app.is_running

    asyncio.run(go())


def test_view_choice_survives_going_wide_and_back():
    async def go():
        app = _app()
        async with app.run_test(size=(40, 20)) as pilot:
            await pilot.click("#tab-tasks")
            await pilot.resize_terminal(120, 40)
            await pilot.pause()
            assert app.query_one("#left").display and app.query_one("#right").display
            await pilot.resize_terminal(40, 20)
            await pilot.pause()
            assert app.view == "tasks" and app.query_one("#right").display and not app.query_one("#left").display

    asyncio.run(go())

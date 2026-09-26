import asyncio
import json

from hexmind.tui import HexmindApp
from tests.test_core import FakeBackend


def test_room_runs_a_plan_and_fills_task_board():
    plan = json.dumps({"reply": "on it", "tasks": [
        {"id": "a", "agent": "claude", "title": "a"},
        {"id": "b", "agent": "agy", "title": "b", "depends_on": ["a"]}]})

    async def go():
        app = HexmindApp(FakeBackend(plan), ["claude", "agy"], "claude", "test")
        async with app.run_test() as pilot:
            await pilot.click("#input")
            await pilot.press(*"build it", "enter")
            await app.workers.wait_for_complete()
            await pilot.pause()
            assert [t.status for t in app.tasks.values()] == ["done", "done"]
            table = app.query_one("#tasks")
            assert table.row_count == 2
            assert str(table.get_cell("1.a", "audit")) == ""  # not audited
            t = app.tasks["1.a"]
            t.status, t.audit, t.auditor = "done", "fixed", "agy"
            app.on_team_event("task", {"task": t})
            assert str(table.get_cell("1.a", "audit")) == "fixed·agy"

    asyncio.run(go())


def _app():
    return HexmindApp(FakeBackend(json.dumps({"reply": "hi", "tasks": []})), ["claude", "agy"], "claude", "test")


def test_wide_layout_is_side_by_side():
    async def go():
        app = _app()
        async with app.run_test(size=(120, 40)) as pilot:
            assert not app.has_class("narrow")
            assert app.query_one("#left").display and app.query_one("#right").display
            assert not app.query_one("#tabs").display

    asyncio.run(go())


def test_narrow_layout_tabs_between_chat_and_tasks():
    async def go():
        app = _app()
        async with app.run_test(size=(40, 20)) as pilot:
            left, right = app.query_one("#left"), app.query_one("#right")
            assert app.has_class("narrow") and app.query_one("#tabs").display
            assert left.display and not right.display
            await pilot.click("#tab-tasks")
            assert not left.display and right.display
            await pilot.click("#tab-chat")
            assert left.display and not right.display
            await pilot.resize_terminal(120, 40)
            await pilot.pause()
            assert left.display and right.display and not app.has_class("narrow")

    asyncio.run(go())


def test_single_keys_only_fire_when_input_blurred():
    async def go():
        app = _app()
        async with app.run_test(size=(40, 20)) as pilot:
            await pilot.press("q", "v", "c")  # typed into the input, not shortcuts
            assert app.is_running and app.query_one("#input").value == "qvc" and app.view == "chat"
            await pilot.press("escape", "v")
            assert app.view == "tasks" and app.focused is app.query_one("#tasks")
            await pilot.press("i")
            assert app.view == "chat" and app.focused is app.query_one("#input")
            await pilot.press("escape", "question_mark")
            assert app.screen.__class__.__name__ == "HelpScreen"
            await pilot.press("escape", "q")
        assert not app.is_running

    asyncio.run(go())


def test_short_terminal_collapses_team_to_one_line():
    async def go():
        app = _app()
        async with app.run_test(size=(40, 15)) as pilot:
            assert app.has_class("short")
            assert "busy" in str(app.query_one("#team").render()) and "\n" not in str(app.query_one("#team").render())
            await pilot.resize_terminal(90, 7)
            await pilot.pause()
            assert app.has_class("tiny") and not app.query_one("Header").display

    asyncio.run(go())


def test_narrow_table_is_compact_and_rebuilds_on_resize():
    plan = json.dumps({"reply": "on it", "tasks": [{"id": "a", "agent": "claude", "title": "alpha"}]})

    async def go():
        app = HexmindApp(FakeBackend(plan), ["claude", "agy"], "claude", "test")
        async with app.run_test(size=(50, 20)) as pilot:
            await pilot.press(*"go", "enter")
            await app.workers.wait_for_complete()
            await pilot.pause()
            table = app.query_one("#tasks")
            assert [c.value for c in table.columns] == ["task", "status", "title"]
            assert str(table.get_cell("1.a", "title")) == "claude alpha"
            assert app.sub_title == "claude · audit:off"
            t = app.tasks["1.a"]
            t.audit, t.auditor = "pass", "agy"
            app.on_team_event("task", {"task": t})
            assert str(table.get_cell("1.a", "status")) == "done pass·agy"
            await pilot.press("escape", "v", "enter")  # open the task sheet
            assert app.screen.__class__.__name__ == "TaskScreen"
            await pilot.press("escape")
            await pilot.resize_terminal(120, 40)
            await pilot.pause()
            assert [c.value for c in table.columns] == ["task", "agent", "status", "audit", "title"]
            assert str(table.get_cell("1.a", "audit")) == "pass·agy" and table.row_count == 1
            assert app.sub_title == "test backend · lead: claude · audit: off"

    asyncio.run(go())

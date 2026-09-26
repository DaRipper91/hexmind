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

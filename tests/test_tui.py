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
            assert app.query_one("#tasks").row_count == 2

    asyncio.run(go())

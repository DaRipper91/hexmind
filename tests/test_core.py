import asyncio
import json

import pytest

from hexmind.core import Orchestrator, parse_plan


def plan(tasks, reply="ok"):
    return "```json\n" + json.dumps({"reply": reply, "tasks": tasks}) + "\n```"


def test_parse_plan_fixes_unknown_agent_and_bad_deps():
    _, tasks = parse_plan(plan([
        {"id": "a", "title": "x", "agent": "gpt9", "instructions": "i", "depends_on": ["zzz", "a"]},
    ]), ["claude", "agy"], "claude")
    assert tasks[0].agent == "claude" and tasks[0].depends_on == []


def test_parse_plan_rejects_cycle():
    with pytest.raises(ValueError):
        parse_plan(plan([
            {"id": "a", "agent": "claude", "depends_on": ["b"]},
            {"id": "b", "agent": "claude", "depends_on": ["a"]},
        ]), ["claude"], "claude")


class FakeBackend:
    """Lead returns a plan; workers echo. Records the max number of concurrent runs."""
    def __init__(self, lead_plan, fail=()):
        self.lead_plan, self.fail = lead_plan, set(fail)
        self.active = self.peak = 0

    async def run(self, agent, prompt, cwd=None):
        if "Answer ONLY with a JSON object" in prompt:
            return self.lead_plan
        if "Write the final answer" in prompt:
            return "summary"
        self.active += 1
        self.peak = max(self.peak, self.active)
        await asyncio.sleep(0.01)
        self.active -= 1
        task_id = prompt.split("Your task (")[1].split(":")[0]
        if task_id in self.fail:
            raise RuntimeError("boom")
        return f"{agent} did {task_id}"


def test_parallel_phases_and_failure_skips_dependents():
    backend = FakeBackend(plan([
        {"id": "a", "agent": "claude", "title": "a"},
        {"id": "b", "agent": "agy", "title": "b"},
        {"id": "c", "agent": "claude", "title": "c", "depends_on": ["a", "b"]},
        {"id": "d", "agent": "agy", "title": "d", "depends_on": ["c"]},
    ]), fail={"b"})
    events = []
    orch = Orchestrator(backend, ["claude", "agy"], "claude", emit=lambda k, d: events.append((k, d)))
    final = asyncio.run(orch.handle("do it"))
    status = {t.id: t.status for k, d in events if k == "plan" for t in d["tasks"]}
    assert status == {"a": "done", "b": "failed", "c": "skipped", "d": "skipped"}
    assert backend.peak == 2  # a and b ran at the same time
    assert final == "summary"


def test_prose_reply_becomes_direct_answer():
    orch = Orchestrator(FakeBackend("Just a chat answer, no JSON."), ["claude"], "claude")
    assert asyncio.run(orch.handle("hi")) == "Just a chat answer, no JSON."


def test_skip_cascades_even_when_dependents_are_listed_first():
    # rafa's review claim: pending dependents get stranded once `running` empties
    backend = FakeBackend(plan([
        {"id": "d", "agent": "agy", "title": "d", "depends_on": ["c"]},
        {"id": "c", "agent": "claude", "title": "c", "depends_on": ["a"]},
        {"id": "a", "agent": "claude", "title": "a"},
    ]), fail={"a"})
    events = []
    orch = Orchestrator(backend, ["claude", "agy"], "claude", emit=lambda k, d: events.append((k, d)))
    asyncio.run(orch.handle("do it"))
    status = {t.id: t.status for k, d in events if k == "plan" for t in d["tasks"]}
    assert status == {"a": "failed", "c": "skipped", "d": "skipped"}


def test_parse_plan_accepts_string_depends_on_and_trailing_braces():
    text = plan([{"id": "t1", "agent": "claude"}, {"id": "t2", "agent": "claude", "depends_on": "t1"}])
    _, tasks = parse_plan(text + "\nNote: use {curly} braces carefully.", ["claude"], "claude")
    assert tasks[1].depends_on == ["t1"]

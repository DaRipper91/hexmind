"""Approved port items owned by core/relay: clean_text, plan schema, draft approval, quota fallback."""
import asyncio
import json

from hexmind.core import Orchestrator, clean_text, PLAN_SCHEMA

PLAN = json.dumps({"reply": "ok", "tasks": [{"id": "t1", "agent": "codex", "title": "build",
                                               "instructions": "do", "depends_on": []}]})


class Fake:
    cwd = "."

    def __init__(self, fail=None):
        self.calls, self.fail = [], fail or {}

    async def run(self, agent, prompt, cwd=None, schema=None):
        self.calls.append((agent, schema is not None))
        if "Answer ONLY with a JSON object" in prompt:
            return PLAN
        if "Write the final answer" in prompt:
            return "summary\x1b[31m‮"
        if agent in self.fail:
            raise RuntimeError(f"{agent} exited 1: {self.fail[agent]}")
        return f"{agent} did it\x07"


def test_clean_text_strips_control_and_bidi_keeps_newlines():
    assert clean_text("a\x1b[0m‮b\n\tc\x00") == "a[0mb\n\tc"


def test_lead_gets_plan_schema_and_outputs_are_cleaned():
    b = Fake()
    orch = Orchestrator(b, ["claude", "codex"], "claude")
    assert asyncio.run(orch.handle("go")) == "summary[31m"
    assert b.calls[0] == ("claude", True) and PLAN_SCHEMA["required"] == ["reply", "tasks"]


def test_draft_plan_waits_then_approve_runs_and_discard_drops():
    b = Fake()
    orch = Orchestrator(b, ["claude", "codex"], "claude")
    orch.approve_plans = True
    asyncio.run(orch.handle("go"))
    assert orch.pending and not any(a == "codex" for a, _ in b.calls)  # nothing ran
    asyncio.run(orch.handle("/approve"))
    assert orch.pending is None and any(a == "codex" for a, _ in b.calls)
    asyncio.run(orch.handle("go"))
    assert "Discarded" in asyncio.run(orch.handle("/discard"))


def test_quota_failure_hands_task_to_next_member_other_failures_do_not():
    events = []
    b = Fake(fail={"codex": "You've hit your usage limit"})
    orch = Orchestrator(b, ["claude", "codex", "qwen"], "claude", lambda k, d: events.append((k, d)))
    asyncio.run(orch.handle("go"))
    task = next(d["tasks"][0] for k, d in events if k == "plan")
    assert (task.agent, task.status) == ("claude", "done")  # qwen is text-only, never a fallback
    b2 = Fake(fail={"codex": "SyntaxError in generated file"})
    events.clear()
    asyncio.run(Orchestrator(b2, ["claude", "codex"], "claude", lambda k, d: events.append((k, d))).handle("go"))
    task = next(d["tasks"][0] for k, d in events if k == "plan")
    assert (task.agent, task.status) == ("codex", "failed")

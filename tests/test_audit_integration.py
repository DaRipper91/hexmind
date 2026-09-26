"""Orchestrator + auditor wiring (sari's track). Needs rafa's hexmind/auditor.py."""
import asyncio
import json

from hexmind.auditor import Stats
from hexmind.core import Orchestrator


class AuditFake:
    """Lead plans t1 (gate) -> t2. Auditor verdicts come from a script per task id."""
    def __init__(self, verdicts):
        self.verdicts = verdicts  # task id -> list of "PASS"/"FAIL", consumed in order
        self.calls = []

    async def run(self, agent, prompt, cwd=None):
        self.calls.append(agent)
        if "Answer ONLY with a JSON object" in prompt:
            return json.dumps({"reply": "ok", "tasks": [
                {"id": "t1", "agent": "claude", "title": "core", "domain": "implementation", "gate": True},
                {"id": "t2", "agent": "agy", "title": "docs", "domain": "docs", "depends_on": ["t1"]}]})
        if "Write the final answer" in prompt:
            return "summary"
        if "VERDICT" in prompt:  # an audit request
            tid = "t1" if "core" in prompt else "t2"
            return f"VERDICT: {self.verdicts[tid].pop(0)}\n- issue"
        return f"{agent} work"


def run(verdicts, tmp_path):
    backend = AuditFake(verdicts)
    events = []
    orch = Orchestrator(backend, ["claude", "agy"], "claude", lambda k, d: events.append((k, d)),
                        audit=True, stats=Stats(str(tmp_path / "stats.json")))
    asyncio.run(orch.handle("go"))
    tasks = {t.id: t for k, d in events if k == "plan" for t in d["tasks"]}
    return tasks, orch, events


def test_fail_then_fixed_records_first_attempt_and_uses_other_model(tmp_path):
    tasks, orch, _ = run({"t1": ["FAIL", "PASS"], "t2": ["PASS"]}, tmp_path)
    assert (tasks["t1"].status, tasks["t1"].audit, tasks["t1"].auditor) == ("done", "fixed", "agy")
    assert (tasks["t2"].audit, tasks["t2"].auditor) == ("pass", "claude")
    assert orch.stats.score("claude", "implementation") < orch.stats.score("agy", "docs")


def test_unresolved_gate_blocks_dependents(tmp_path):
    tasks, _, _ = run({"t1": ["FAIL", "FAIL", "FAIL"], "t2": ["PASS"]}, tmp_path)
    assert (tasks["t1"].status, tasks["t1"].audit) == ("failed", "disputed")
    assert tasks["t2"].status == "skipped"

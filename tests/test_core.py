import asyncio
import json

import pytest

from hexmind.core import Orchestrator, Task, parse_plan


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


def test_parse_plan_accepts_string_tasks_and_ignores_invalid_items():
    text = plan(["write unit tests", {"id": "t2", "title": "fix bug", "agent": "agy"}, 12345, None])
    reply, tasks = parse_plan(text, ["claude", "agy"], "claude")
    assert reply == "ok"
    assert len(tasks) == 2
    assert tasks[0].id == "t1"
    assert tasks[0].title == "write unit tests"
    assert tasks[0].agent == "claude"
    assert tasks[0].instructions == "write unit tests"
    assert tasks[1].id == "t2"
    assert tasks[1].title == "fix bug"
    assert tasks[1].agent == "agy"


def test_orchestrator_falls_back_to_prose_on_malformed_plan_data():
    orch = Orchestrator(FakeBackend('{"tasks": "not a list or dict"}'), ["claude"], "claude")
    reply = asyncio.run(orch.handle("hi"))
    assert '{"tasks": "not a list or dict"}' in reply


def test_a_failed_stage_is_recorded_in_the_relay_notes_the_next_stage_reads(tmp_path):
    """A relay stage's notes file is what the next stage is told to read first. Written only on
    success, it reads as a clean run: a stage that never mentions its own failure leaves the next
    one reasoning from a report that skipped over the hole."""
    notes = tmp_path / "chain-A.md"
    notes.write_text("# Chain A notes\n")
    backend = FakeBackend(plan([
        {"id": "a", "agent": "claude", "title": "one"},
        {"id": "b", "agent": "agy", "title": "two", "depends_on": ["a"]},
    ]), fail={"a"})
    tasks = [Task(id="a", title="one", agent="claude", instructions="do it", notes=str(notes)),
             Task(id="b", title="two", agent="agy", instructions="do it more", depends_on=["a"],
                  notes=str(notes))]
    orch = Orchestrator(backend, ["claude", "agy"], "claude")
    asyncio.run(orch.run_tasks("do it", tasks))

    assert (tasks[0].status, tasks[1].status) == ("failed", "skipped")
    text = notes.read_text()
    assert "# Chain A notes" in text  # the chain's own header survives; we only append
    assert "claude did a" not in text  # a failed stage reported no work
    assert "error: boom" in text, text
    assert "failed" in text, text
    # a skipped stage must also leave an entry, or the next stage cannot tell "skipped on purpose"
    # from "never ran" — the same hole as the failed stage above
    assert "skipped" in text, text
    assert "two" in text, text  # the skipped task's title appears in its note entry


# ---------- worktree isolation: the prompt must say which folder is yours ----------

class PromptRecorder:
    """Captures the prompt of every call so a test can assert what the agent was told."""

    def __init__(self):
        self.prompts = []
        self.cwd = "/main"

    async def run(self, agent, prompt, cwd=None, schema=None):
        self.prompts.append(prompt)
        return "ok"


def test_a_worktree_task_is_told_exactly_which_directory_to_work_in():
    """A relay chain's notes file lives in the MAIN folder while each chain works in its own
    worktree, so any path the agent reads in the notes can point at a different checkout. An agent
    once edited the main checkout instead of its worktree because nothing in its prompt said
    otherwise, which defeated --workspace worktree entirely."""
    backend = PromptRecorder()
    orch = Orchestrator(backend, ["claude"], "claude")
    task = Task(id="A1", title="fix", agent="claude", instructions="do it",
                cwd="/repo/.hexmind/worktrees/run-A")

    asyncio.run(orch._run_one("req", task, []))

    prompt = backend.prompts[-1]
    assert "/repo/.hexmind/worktrees/run-A" in prompt
    assert "isolated copy" in prompt
    assert "Do not modify anything under" in prompt


def test_a_relay_stage_is_told_its_notes_file_lives_in_the_main_checkout():
    """The trap: the stage's own folder is a worktree, but the notes file it must read is in the
    main folder, so every path it reads points somewhere else. Say so explicitly."""
    backend = PromptRecorder()
    orch = Orchestrator(backend, ["claude"], "claude")
    backend.cwd = "/repo"
    task = Task(id="A1", title="fix", agent="claude", instructions="do it",
                cwd="/repo/.hexmind/worktrees/run-A", notes="/repo/.hexmind/runs/run/chain-A.md")

    asyncio.run(orch._run_one("req", task, []))

    prompt = backend.prompts[-1]
    assert "main checkout at /repo" in prompt
    assert "/repo/.hexmind/runs/run/chain-A.md" in prompt
    assert "/repo/.hexmind/worktrees/run-A" in prompt


def test_a_task_in_the_room_folder_is_not_told_about_a_directory():
    """t.cwd is None for an ordinary request, and naming the room folder there would be noise
    that trains agents to ignore the instruction."""
    backend = PromptRecorder()
    orch = Orchestrator(backend, ["claude"], "claude")
    task = Task(id="t1", title="x", agent="claude", instructions="do it")

    asyncio.run(orch._run_one("req", task, []))

    assert "isolated copy" not in backend.prompts[-1]

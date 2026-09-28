"""The lead's directives: relay chains it asks for, and skills it wants used or written (design §4).

The two properties that matter and are easy to get wrong:

- **A skill is never written.** `use` injects a path; `create` and `edit` come back to the user as a
  proposal. A model editing your skill directory is a privileged action, and a plan that quietly
  performs one is a plan you would not have approved.
- **A request the room cannot honour is reported, not dropped.** The lead's summary is the only
  thing the user is guaranteed to read, so a vanished chain or an uninstalled skill is a finding in
  the room, in the same turn.
"""
from __future__ import annotations

import asyncio
import json

import pytest

from hexmind.core import (
    ASSEMBLY_SCHEMA,
    PLAN_SCHEMA,
    Directives,
    Orchestrator,
    Task,
    parse_directives,
    skill_path,
)
from hexmind.relay import command


class FakeBackend:
    """Records what it was asked, so a test can prove a chain or a skill actually reached a stage."""

    def __init__(self, plan: str) -> None:
        self.plan, self.calls = plan, []

    async def run(self, agent, prompt, cwd=None, schema=None):
        self.calls.append((agent, prompt))
        if "Design a relay chain" in prompt:
            return json.dumps({"name": "port-it", "stages": [
                {"name": "read", "instructions": "read the code"},
                {"name": "change", "instructions": "make the change"}]})
        if "Answer ONLY with a JSON object" in prompt:
            return self.plan
        if "Write the final answer" in prompt:
            return "summary"
        return f"{agent} worked"


def make(plan: str, **kwargs) -> Orchestrator:
    return Orchestrator(FakeBackend(plan), ["claude", "agy"], "claude", **kwargs)


def plan_json(**extra) -> str:
    base = {"reply": "on it", "tasks": [
        {"id": "t1", "title": "do the thing", "agent": "claude", "instructions": "x",
         "depends_on": []}]}
    base.update(extra)
    return json.dumps(base)


# ---------- the schema is an extension, not a replacement ----------

def test_the_assembly_schema_is_the_plan_schema_plus_two_fields():
    """Anything that produced a valid PLAN_SCHEMA plan must still produce a valid ASSEMBLY_SCHEMA
    plan, or every existing lead prompt and every model in the wild is broken by this."""
    assert ASSEMBLY_SCHEMA["required"] == PLAN_SCHEMA["required"] == ["reply", "tasks"]
    assert ASSEMBLY_SCHEMA["properties"]["tasks"] == PLAN_SCHEMA["properties"]["tasks"]
    assert set(PLAN_SCHEMA["properties"]) < set(ASSEMBLY_SCHEMA["properties"])
    assert set(ASSEMBLY_SCHEMA["properties"]) - set(PLAN_SCHEMA["properties"]) == {"chains", "skills"}


def test_a_plan_with_no_directives_parses_exactly_as_before():
    tasks = [Task(id="t1", title="a", agent="claude", instructions="i")]
    assert parse_directives(plan_json(), tasks) == Directives()
    assert not parse_directives(plan_json(), tasks)


def test_a_prose_reply_has_no_directives_and_does_not_raise():
    """A lead that answers in prose is the common case, not an error."""
    assert not parse_directives("I think claude should do it.", [])


# ---------- parsing and validation ----------

def test_well_formed_directives_are_read():
    tasks = [Task(id="t1", title="a", agent="claude", instructions="i"),
             Task(id="t2", title="b", agent="agy", instructions="i")]
    d = parse_directives(plan_json(
        chains=[{"goal": "port the parser", "n": 2, "assign": "best", "why": "staged work"}],
        skills=[{"action": "use", "name": "hexmind-dev", "task": "t2", "why": "we follow it"},
                {"action": "create", "name": "hexmind-lead"}]), tasks)

    assert d.chains == [{"goal": "port the parser", "n": 2, "assign": "best",
                         "why": "staged work"}]
    assert [(s["action"], s["name"], s["task"]) for s in d.skills] == [
        ("use", "hexmind-dev", "t2"), ("create", "hexmind-lead", "")]
    assert d.findings == []


@pytest.mark.parametrize("entry,expected", [
    ({"assign": "pinned"}, "with no goal"),
    ({"goal": "g", "assign": "sideways"}, "assign='sideways' is not one of"),
    ({"goal": "g", "n": "many"}, "is not a number"),
    ("just a string", "not an object"),
])
def test_a_malformed_chain_is_reported_not_thrown(entry, expected):
    d = parse_directives(plan_json(chains=[entry]), [])
    assert any(expected in f for f in d.findings), d.findings
    # whatever survived is still usable
    for chain in d.chains:
        assert chain["goal"] and chain["assign"] in ("rotate", "best", "pinned")


def test_a_chain_count_is_clamped_to_something_sane():
    """`n` is how many copies of a chain to run. Unlimited would fork-bomb the user's machine."""
    assert parse_directives(plan_json(chains=[{"goal": "g", "n": 99}]), []).chains[0]["n"] == 5
    assert parse_directives(plan_json(chains=[{"goal": "g", "n": 0}]), []).chains[0]["n"] == 1


@pytest.mark.parametrize("entry,expected", [
    ({"action": "frobnicate", "name": "x"}, "action='frobnicate'"),
    ({"action": "use"}, "no name"),
    ({"action": "use", "name": "x", "task": "t9"}, "not in this plan"),
])
def test_a_malformed_skill_is_reported(entry, expected):
    tasks = [Task(id="t1", title="a", agent="claude", instructions="i")]
    d = parse_directives(plan_json(skills=[entry]), tasks)
    assert any(expected in f for f in d.findings), d.findings
    # a task that does not exist falls back to the whole plan rather than being dropped
    if entry.get("action") == "use" and entry.get("name") == "x":
        assert d.skills[0]["task"] == ""


# ---------- skills: use is injection, create/edit are proposals ----------

def test_use_injects_the_skill_path_into_the_named_task_only(tmp_path):
    skill = tmp_path / ".claude" / "skills" / "house-style" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("# house style\n")
    tasks = [Task(id="t1", title="a", agent="claude", instructions="write it"),
             Task(id="t2", title="b", agent="agy", instructions="write it")]
    orch = Orchestrator(FakeBackend("{}"), ["claude", "agy"], "claude")
    orch.backend.cwd = str(tmp_path)

    proposals, findings = orch.apply_skills(
        tasks, [{"action": "use", "name": "house-style", "task": "t2", "why": ""}])

    assert "## Skill: house-style" in tasks[1].instructions and str(skill) in tasks[1].instructions
    assert "## Skill:" not in tasks[0].instructions, "only the named task"
    assert proposals == [] and findings == []


def test_use_applies_to_every_task_when_no_task_is_named(tmp_path):
    skill = tmp_path / ".claude" / "skills" / "s" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("x")
    tasks = [Task(id="t1", title="a", agent="claude", instructions="i"),
             Task(id="t2", title="b", agent="agy", instructions="i")]
    orch = Orchestrator(FakeBackend("{}"), ["claude", "agy"], "claude")
    orch.backend.cwd = str(tmp_path)
    orch.apply_skills(tasks, [{"action": "use", "name": "s", "task": "", "why": ""}])
    assert all("## Skill: s" in t.instructions for t in tasks)


def test_using_a_skill_nobody_has_is_a_finding_not_a_dead_path(tmp_path):
    """Injecting a path that does not exist gives the model a file it cannot read and no idea that
    is why. The room has to say so."""
    tasks = [Task(id="t1", title="a", agent="claude", instructions="i")]
    orch = Orchestrator(FakeBackend("{}"), ["claude"], "claude")
    orch.backend.cwd = str(tmp_path)

    proposals, findings = orch.apply_skills(tasks, [{"action": "use", "name": "ghost", "task": "",
                                                     "why": ""}])

    assert "## Skill" not in tasks[0].instructions
    assert any("ghost" in f and "not installed" in f for f in findings), findings
    assert proposals == [], "a skill that cannot be used is a finding, not a proposal"


def test_create_and_edit_are_proposals_and_nothing_is_written(tmp_path):
    tasks = [Task(id="t1", title="a", agent="claude", instructions="i")]
    orch = Orchestrator(FakeBackend("{}"), ["claude"], "claude")
    orch.backend.cwd = str(tmp_path)

    proposals, findings = orch.apply_skills(
        tasks, [{"action": "create", "name": "hexmind-lead", "task": "", "why": "role doc"},
                {"action": "edit", "name": "hexmind-dev", "task": "", "why": "stale rule"}])

    assert len(proposals) == 2
    assert "create" in proposals[0] and "hexmind-lead" in proposals[0]
    assert any("Not written" in p for p in proposals)
    assert findings == []
    assert not (tmp_path / ".claude").exists(), "no skill directory may be created as a side effect"


def test_skill_path_prefers_the_project_over_the_user(monkeypatch, tmp_path):
    project = tmp_path / ".claude" / "skills" / "s" / "SKILL.md"
    project.parent.mkdir(parents=True)
    project.write_text("project")
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path / "home")
    user = tmp_path / "home" / ".claude" / "skills" / "s" / "SKILL.md"
    user.parent.mkdir(parents=True)
    user.write_text("user")

    assert skill_path("s", str(tmp_path)) == project
    assert skill_path("absent", str(tmp_path)) is None


# ---------- chains become real /relay runs ----------

def test_a_requested_chain_becomes_a_relay_run_with_its_provenance(monkeypatch, tmp_path):
    """The chain has to be a real run, reusing run_relay, and the only difference from a typed
    `/relay` is a line in its notes saying who asked. If the audit, /ranks or /relay clean could
    tell the difference, that would be a second kind of relay to maintain."""
    from hexmind import relay as relay_mod

    seen: dict = {}

    async def fake_run_relay(orch, ns, provenance=""):
        seen["ns"], seen["provenance"] = ns, provenance
        return "**Relay finished.**\n- chain A: t1 done"

    monkeypatch.setattr(relay_mod, "run_relay", fake_run_relay)
    orch = make(plan_json(chains=[{"goal": "port the parser", "n": 2, "assign": "best",
                                   "why": "staged"}]))
    orch.backend.cwd = str(tmp_path)

    report = asyncio.run(orch.run_chains("port the parser to 3.12",
                                         parse_directives(
                                             plan_json(chains=[{"goal": "port the parser", "n": 2,
                                                                "assign": "best", "why": "staged"}]),
                                             []).chains))

    assert seen["ns"].target == ["port the parser"]
    assert seen["ns"].chains == 2 and seen["ns"].assign == "best"
    assert "Requested by claude for: port the parser to 3.12" in seen["provenance"]
    assert "Why: staged" in seen["provenance"]
    assert "port the parser" in report


def test_run_relay_writes_the_provenance_into_the_chain_notes(tmp_path, monkeypatch):
    """Not just passed along: the notes are the only record that outlives the run."""
    import subprocess

    from hexmind import relay as relay_mod

    root = tmp_path / "repo"
    (root / "hexmind").mkdir(parents=True)
    (root / "hexmind" / "x.py").write_text("x = 1\n")
    for cmd in (["init", "-q"], ["add", "-A"],
                ["-c", "user.email=a@b", "-c", "user.name=a", "commit", "-qm", "x"]):
        subprocess.run(["git", "-C", str(root), *cmd], capture_output=True, check=True)

    import argparse
    ns = argparse.Namespace(target=["do the thing"], chains=1, assign="rotate", workspace="shared",
                            end="list", goal="")
    orch = Orchestrator(FakeBackend("{}"), ["claude"], "claude")
    orch.backend.cwd = str(root)

    async def go():
        return await relay_mod.run_relay(orch, ns, provenance="> Requested by claude for: the thing")

    report = asyncio.run(go())
    notes = sorted((root / ".hexmind" / "runs").glob("*/chain-*.md"))
    assert notes, report
    body = notes[0].read_text()
    assert "Requested by claude for: the thing" in body
    assert body.startswith("# Chain"), "the header is still the first line"


def test_a_chain_that_cannot_run_is_a_finding_not_a_dead_turn(monkeypatch, tmp_path):
    from hexmind import relay as relay_mod

    async def boom(orch, ns, provenance=""):
        raise RuntimeError("git worktree failed: not a git repo")

    monkeypatch.setattr(relay_mod, "run_relay", boom)
    orch = make(plan_json())
    orch.backend.cwd = str(tmp_path)

    report = asyncio.run(orch.run_chains("do it", [{"goal": "do it", "n": 1, "assign": "rotate",
                                                    "why": ""}]))

    assert "failed" in report and "not a git repo" in report


# ---------- end to end: a plan that asks for both ----------

def test_a_plan_with_chains_and_skills_runs_both_and_reports_everything_it_could_not_do(tmp_path, monkeypatch):
    from hexmind import relay as relay_mod

    skill = tmp_path / ".claude" / "skills" / "house" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("x")
    seen: dict = {}

    async def fake_run_relay(orch, ns, provenance=""):
        seen["goal"] = ns.target[0]
        return "**Relay finished.**"

    monkeypatch.setattr(relay_mod, "run_relay", fake_run_relay)
    said: list[str] = []
    orch = Orchestrator(FakeBackend(plan_json(
        chains=[{"goal": "port the parser", "why": "staged"}],
        skills=[{"action": "use", "name": "house", "task": "t1", "why": ""},
                {"action": "use", "name": "ghost", "task": "", "why": ""},
                {"action": "create", "name": "hexmind-lead", "task": "", "why": "role doc"}])),
        ["claude", "agy"], "claude", emit=lambda k, d: said.append(d.get("text", "")) if k == "message" else None)
    orch.backend.cwd = str(tmp_path)

    final = asyncio.run(orch.handle("port the parser to 3.12"))
    everything = "\n".join(said)

    assert seen["goal"] == "port the parser", "the chain ran"
    assert "## Skill: house" in orch.all_tasks[0].instructions, "the skill reached the task prompt"
    assert "create" in everything and "Not written" in everything, "create is a proposal"
    assert "ghost" in everything and "not installed" in everything, "the unusable one is reported"
    # the chain's outcome has to reach the lead's own summary, which is the one thing the user is
    # guaranteed to read
    synth = next(prompt for _, prompt in orch.backend.calls if "Write the final answer" in prompt)
    assert "Chains the lead asked for" in synth and "port the parser" in synth
    assert final == "summary"


# ---------- drafts: a plan's directives belong to the plan ----------

def test_a_draft_shows_its_directives_and_approve_runs_them(monkeypatch, tmp_path):
    from hexmind import relay as relay_mod

    ran: dict = {}

    async def fake_run_relay(orch, ns, provenance=""):
        ran["goal"] = ns.target[0]
        return "**Relay finished.**"

    monkeypatch.setattr(relay_mod, "run_relay", fake_run_relay)
    said: list[str] = []
    orch = Orchestrator(FakeBackend(plan_json(
        chains=[{"goal": "port the parser", "why": "staged"}],
        skills=[{"action": "use", "name": "ghost", "task": "", "why": ""}])),
        ["claude", "agy"], "claude",
        emit=lambda k, d: said.append(d.get("text", "")) if k == "message" else None)
    orch.approve_plans = True
    orch.backend.cwd = str(tmp_path)

    asyncio.run(orch.handle("port it"))
    preview = "\n".join(said)
    assert "Also in this plan" in preview and "port the parser" in preview, \
        "a draft whose extra work is invisible is a surprise, not a draft"
    assert ran == {}, "nothing may run before /approve"

    asyncio.run(command(orch, "/approve"))

    assert ran.get("goal") == "port the parser", "approving the task list runs its chain too"
    assert "not installed" in "\n".join(said)


def test_discard_drops_the_chains_too_and_says_so(monkeypatch, tmp_path):
    from hexmind import relay as relay_mod

    ran: dict = {}

    async def fake_run_relay(orch, ns, provenance=""):
        ran["goal"] = ns.target[0]
        return "done"

    monkeypatch.setattr(relay_mod, "run_relay", fake_run_relay)
    orch = Orchestrator(FakeBackend(plan_json(chains=[{"goal": "port it", "why": ""}])),
                        ["claude"], "claude")
    orch.approve_plans = True
    orch.backend.cwd = str(tmp_path)

    asyncio.run(orch.handle("port it"))
    reply = asyncio.run(command(orch, "/discard"))

    assert ran == {}, "a discarded plan runs nothing"
    assert "chain" in reply.lower(), f"the discard must account for the chain it dropped: {reply}"
    assert orch.pending is None and orch.pending_directives is None

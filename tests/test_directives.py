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

def test_the_assembly_schema_is_the_plan_schema_plus_its_directives():
    """Anything that produced a valid PLAN_SCHEMA plan must still produce a valid ASSEMBLY_SCHEMA
    plan, or every existing lead prompt and every model in the wild is broken by this."""
    assert ASSEMBLY_SCHEMA["required"] == PLAN_SCHEMA["required"] == ["reply", "tasks"]
    assert ASSEMBLY_SCHEMA["properties"]["tasks"] == PLAN_SCHEMA["properties"]["tasks"]
    assert set(PLAN_SCHEMA["properties"]) < set(ASSEMBLY_SCHEMA["properties"])
    assert set(ASSEMBLY_SCHEMA["properties"]) - set(PLAN_SCHEMA["properties"]) == \
        {"chains", "skills", "audit"}
    assert ASSEMBLY_SCHEMA["properties"]["audit"] == {"type": "boolean"}, \
        "a nullable field is not a request, so the schema must not invite `null` as a third state"


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


# ---------- peer audit as a plan directive ----------

def test_an_absent_audit_field_leaves_the_switch_alone():
    """A plan that never mentions audit must not turn it on or off. The field is a request, and an
    absent field is not a request — a control the lead can move without asking is one nobody can
    rely on."""
    tasks = [Task(id="t1", title="a", agent="claude", instructions="i")]
    for start in (True, False):
        orch = make(plan_json(), audit=start)
        asyncio.run(orch.handle("do the thing"))
        assert orch.audit is start, "a plan with no `audit` field changed a safety switch"


def test_explicit_null_is_the_same_as_absent():
    d = parse_directives(plan_json(audit=None), [])
    assert d.audit is None and not d.findings, "null is no opinion, not a malformed request"


@pytest.mark.parametrize("raw,expected", [
    (True, True), (False, False),
    ("true", True), ("on", True), ("yes", True), ("enable", True), ("1", True),
    ("false", False), ("off", False), ("no", False), ("disable", False), ("0", False),
    ("TRUE", True), (" Off ", False),
])
def test_the_lead_may_spell_the_audit_request_out(raw, expected):
    """A model asked for a boolean answers with whatever it likes. Reading only a literal `true`
    would make the directive work in the demo and fail in the room."""
    assert parse_directives(plan_json(audit=raw), []).audit is expected


def test_an_unreadable_audit_value_is_a_finding_and_changes_nothing():
    orch = make(plan_json(audit="maybe later"), audit=False)
    said: list[str] = []
    orch.emit = lambda k, d: said.append(d.get("text", "")) if k == "message" else None

    asyncio.run(orch.handle("do the thing"))

    assert orch.audit is False, "a request the room could not read must not be a guess"
    assert any("maybe later" in f for f in " ".join(said).splitlines()), \
        f"the dropped request must be visible: {said}"


def test_the_lead_turns_peer_audit_on_and_the_room_says_so():
    said: list[str] = []
    orch = make(plan_json(audit=True), audit=False,
                emit=lambda k, d: said.append(d.get("text", "")) if k == "message" else None)

    asyncio.run(orch.handle("do the thing"))

    assert orch.audit is True
    assert any("Peer audit is now on" in t for t in said), \
        f"a safety switch the lead moved must be said out loud: {said}"


def test_the_lead_turns_peer_audit_off_too():
    orch = make(plan_json(audit=False), audit=True)
    asyncio.run(orch.handle("do the thing"))
    assert orch.audit is False


def test_asking_for_the_state_the_room_is_already_in_changes_nothing():
    """Re-asserting a value is not a change. Emitting the 'Peer audit is now on' line for a no-op
    would train the user to ignore the one message that says the switch actually moved."""
    said: list[str] = []
    orch = make(plan_json(audit=True), audit=True,
                emit=lambda k, d: said.append(d.get("text", "")) if k == "message" else None)

    asyncio.run(orch.handle("do the thing"))

    assert orch.audit is True
    assert not any("Peer audit is now" in t for t in said), \
        f"a no-op must be silent: {said}"


def test_audit_is_applied_before_the_graph_runs():
    """`audit` decides whether each task gets a peer review as it completes, so it has to be set
    before the first task finishes — not after the plan."""
    asked: list[str] = []
    orch = make(plan_json(audit=True), audit=False)
    original = orch.ask

    async def spy(agent, prompt, schema=None):
        asked.append(prompt)
        return await original(agent, prompt, schema=schema)

    orch.ask = spy
    asyncio.run(orch.handle("do the thing"))

    assert orch.audit is True
    # the review prompt only exists when the room is auditing, so its presence is the proof
    assert any("peer review" in p.lower() or "audit" in p.lower() for p in asked), \
        "no task was reviewed, so audit never reached the executor"


def test_audit_on_in_a_room_with_no_ledger_is_reported_not_promised():
    """Without a `Stats` ledger there is nowhere to record a verdict, so `_run_one` skips the
    review entirely. Turning audit on there must say so, or the room promises review it never does."""
    orch = make(plan_json(audit=True), audit=False)  # no stats= argument
    assert orch.stats is None
    said: list[str] = []
    orch.emit = lambda k, d: said.append(d.get("text", "")) if k == "message" else None

    asyncio.run(orch.handle("do the thing"))

    assert orch.audit is True
    assert any("no audit ledger" in t for t in said), \
        f"audit-on with nothing to audit into must be flagged: {said}"


def test_audit_on_with_a_ledger_is_not_flagged():
    from hexmind.auditor import Stats
    orch = Orchestrator(FakeBackend(plan_json(audit=True)), ["claude", "agy"], "claude",
                        audit=False, stats=Stats("/tmp/hexmind-test-stats.json"))
    said: list[str] = []
    orch.emit = lambda k, d: said.append(d.get("text", "")) if k == "message" else None

    asyncio.run(orch.handle("do the thing"))

    assert orch.audit is True
    assert not any("no audit ledger" in t for t in said)


def test_an_audit_only_plan_costs_no_model_call():
    """A plan whose sole directive is `audit` has no tasks. `execute()` always ends in a lead
    synthesis round-trip, so routing the boolean through it would spend a model call to set a
    flag — and burn the room's context on a plan that does nothing else."""
    backend = FakeBackend(plan_json(tasks=[], audit=True))
    orch = Orchestrator(backend, ["claude", "agy"], "claude", audit=False)

    reply = asyncio.run(orch.handle("start peer audit from now on"))

    assert orch.audit is True, "an audit-only plan still has to take effect"
    assert not any("Write the final answer" in p for _, p in backend.calls), \
        "an audit-only plan must not trigger a synthesis round-trip"


def test_a_draft_audit_only_plan_shows_the_switch_and_applies_it_on_approve():
    said: list[str] = []
    orch = Orchestrator(FakeBackend(plan_json(tasks=[], audit=True)), ["claude", "agy"], "claude",
                        audit=False,
                        emit=lambda k, d: said.append(d.get("text", "")) if k == "message" else None)
    orch.approve_plans = True

    asyncio.run(orch.handle("start peer audit from now on"))
    preview = "\n".join(said)
    assert "**peer audit** on" in preview, \
        f"a draft that silently flips a safety switch is not a draft: {preview}"
    assert orch.audit is False, "a draft must not take effect before /approve"

    asyncio.run(command(orch, "/approve"))
    assert orch.audit is True, "approving the draft is what applies the switch"


def test_discard_leaves_the_audit_switch_untouched():
    orch = Orchestrator(FakeBackend(plan_json(tasks=[], audit=True)), ["claude", "agy"], "claude",
                        audit=False)
    orch.approve_plans = True

    asyncio.run(orch.handle("start peer audit from now on"))
    reply = asyncio.run(command(orch, "/discard"))

    assert orch.audit is False, "discarding the plan must not apply any part of it"
    assert "audit" in reply.lower(), f"the discard must account for the switch it dropped: {reply}"


# ---------- /audit, the switch the leader can turn by hand ----------

@pytest.mark.parametrize("start,word,end", [
    (False, "on", True), (True, "off", False),
    # Someone flipping a switch types whichever word is in their head first, so the obvious
    # synonyms all have to land on the same two states.
    (False, "true", True), (True, "false", False),
    (False, "yes", True), (True, "no", False),
    (False, "enable", True), (True, "disable", False),
    (False, "enabled", True), (True, "disabled", False),
    (False, "1", True), (True, "0", False),
    # ...and the case and spacing of a typed-in word are not a reason to do nothing.
    (False, "ON", True), (True, "Off", False),
    (False, "on ", True), (True, " OFF", False),
])
def test_audit_command_sets_the_switch_and_says_which_way_it_landed(start, word, end):
    orch = make(plan_json(), audit=start)

    reply = asyncio.run(command(orch, f"/audit {word}"))

    assert orch.audit is end, f"`/audit {word}` should land on {end}, not leave the switch at {start}"
    assert f"**{'on' if end else 'off'}**" in reply, \
        f"the reply has to state the resulting state, not just that a word was heard: {reply}"


def test_bare_audit_reports_the_state_without_changing_it():
    """`/audit` with no argument is a question, and the most natural way to ask it is bare."""
    orch = make(plan_json(), audit=True)

    reply = asyncio.run(command(orch, "/audit"))

    assert orch.audit is True
    assert "**on**" in reply, f"a bare `/audit` should report the current state: {reply}"


@pytest.mark.parametrize("junk", ["maybe", "onoff", "2", "true-ish", "audit", "✓"])
def test_an_unreadable_word_is_a_no_op_that_explains_itself(junk):
    """A safety switch must not be flipped by a typo. The reply leads with the rejection, then
    says what is accepted and what the switch is still doing — a state line first would read like
    the change already landed."""
    orch = make(plan_json(), audit=False)

    reply = asyncio.run(command(orch, f"/audit {junk}"))

    assert orch.audit is False, f"`{junk}` is not a setting; it must not move the switch"
    assert junk in reply, f"the reply should name the word it could not read: {reply}"
    assert "/audit on" in reply and "/audit off" in reply, \
        f"the reply should say what it would have accepted: {reply}"
    assert reply.index("isn't") < reply.index("still"), \
        f"the rejection has to come before the state echo, or it reads like a change: {reply}"


def test_an_unreadable_word_does_not_turn_audit_off_either():
    """The failure mode worth guarding: a switch that is *on* silently going off because someone
    typed `/audit onoff`."""
    orch = make(plan_json(), audit=True)

    reply = asyncio.run(command(orch, "/audit onoff"))

    assert orch.audit is True, "audit must not be turned off by a word that is not `off`"
    assert "**on**" in reply, f"the reply should confirm audit is still on: {reply}"


def test_the_help_line_documents_the_audit_command():
    from hexmind import relay as relay_mod

    line = next(l for l in relay_mod.HELP.splitlines() if "/audit " in l)

    assert "on" in line and "off" in line, f"the help must show the two settings: {line}"

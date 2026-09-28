"""Team state: sleep, wake, and leader changes — and INVARIANT S-1.

S-1: a model holding a live task cannot be put to sleep. No override, no queue. The model is
mid-edit in a real folder or a relay worktree; a half-written file is never worth the memory.
"""
import asyncio

import pytest

from hexmind.core import (BUSY_STATUSES, REGISTRY, Orchestrator, Task, TeamBusy, TeamError,
                          TEXT_ONLY)
from hexmind.relay import command


class FakeBackend:
    def __init__(self, cwd="/tmp", reply="done"):
        self.cwd = cwd
        self.reply = reply
        self.calls = []

    async def run(self, agent, prompt, cwd=None, schema=None):
        self.calls.append((agent, prompt))
        return self.reply


def make(members=("claude", "agy", "big-pickle", "ling-flash"), lead="claude"):
    events = []
    orch = Orchestrator(FakeBackend(), list(members), lead, emit=lambda k, d: events.append((k, d)),
                       known=list(REGISTRY.names()))
    return orch, events


def busy_task(agent="big-pickle", status="running"):
    t = Task(id="t1", title="do the thing", agent=agent, instructions="x")
    t.status = status
    return t


# ---------- INVARIANT S-1 ----------

def test_a_working_model_cannot_be_slept():
    orch, _ = make()
    orch.all_tasks.append(busy_task("big-pickle", "running"))
    orch.busy = {"big-pickle"}

    with pytest.raises(TeamBusy) as err:
        orch.sleep("big-pickle")

    assert "working on t1" in str(err.value)
    assert "big-pickle" in orch.members, "a refused sleep must not remove the model anyway"


@pytest.mark.parametrize("status", sorted(BUSY_STATUSES))
def test_every_live_status_blocks_sleep(status):
    orch, _ = make()
    orch.all_tasks.append(busy_task("big-pickle", status))
    orch.busy = {"big-pickle"}
    with pytest.raises(TeamBusy):
        orch.sleep("big-pickle")


@pytest.mark.parametrize("status", ["pending", "done", "failed", "skipped"])
def test_a_terminal_or_unstarted_task_does_not_block_sleep(status):
    orch, _ = make()
    orch.all_tasks.append(busy_task("big-pickle", status))
    orch.busy = {t.agent for t in orch.all_tasks if t.status in BUSY_STATUSES}

    assert orch.can_sleep("big-pickle")[0] is True
    assert "asleep" in orch.sleep("big-pickle")


def test_can_sleep_explains_why_rather_than_just_refusing():
    orch, _ = make()
    orch.all_tasks.append(busy_task())
    orch.busy = {"big-pickle"}

    allowed, reason = orch.can_sleep("big-pickle")
    assert allowed is False
    assert "t1" in reason and "do the thing" in reason, "the reason must name the task, not just the model"

    assert orch.can_sleep("claude")[1].startswith("claude is the lead")
    assert orch.can_sleep("agy")[0] is True, "an awake idle non-lead model may sleep"


def test_the_busy_set_tracks_a_real_run_and_clears_when_the_task_ends():
    """Two sources of truth for "is this model busy" would eventually disagree, and the
    disagreement would either wedge a model awake forever or interrupt a live edit. This drives
    the actual execution path rather than setting the set by hand."""
    orch, _ = make()
    release = asyncio.Event()

    class Blocking:
        cwd = "/tmp"

        async def run(self, agent, prompt, cwd=None, schema=None):
            await release.wait()
            return "done"

    orch.backend = Blocking()
    task = busy_task("big-pickle", "pending")

    async def go():
        run = asyncio.create_task(orch.run_tasks("req", [task]))
        for _ in range(50):  # let it reach `running`
            if "big-pickle" in orch.busy:
                break
            await asyncio.sleep(0.01)
        assert orch.busy == {"big-pickle"}, "a launched task must mark its model busy"
        assert orch.can_sleep("big-pickle")[0] is False
        assert orch.can_sleep("agy")[0] is True
        release.set()
        await run
        assert orch.busy == set(), "a finished task must clear its model's busy flag"
        assert task.status == "done"
        assert orch.can_sleep("big-pickle")[0] is True

    asyncio.run(go())


def test_a_cancelled_turn_does_not_wedge_a_model_awake_forever(tmp_path):
    """The finally branch matters: without it, quitting mid-task would leave the model
    permanently unsleepable for the rest of the session."""
    orch, _ = make()
    task = busy_task("big-pickle", "pending")
    notes = tmp_path / "chain-A.md"
    notes.write_text("# Chain A notes\n")
    task.notes = str(notes)

    class Never:
        cwd = "/tmp"

        async def run(self, *a, **k):
            await asyncio.sleep(3600)

    orch.backend = Never()

    async def go():
        run = asyncio.create_task(orch.run_tasks("req", [task]))
        for _ in range(50):
            if "big-pickle" in orch.busy:
                break
            await asyncio.sleep(0.01)
        run.cancel()
        with pytest.raises(asyncio.CancelledError):
            await run
        assert orch.busy == set(), "a cancelled task must not leave its model unsleepable"
        assert task.status == "failed", "the board must not claim cancelled work is still running"
        assert "cancelled" in task.output
        # the relay notes are read after the fact, so a cancelled stage must not leave a hole in them
        assert "failed" in notes.read_text() and "cancelled" in notes.read_text()

    asyncio.run(go())


# ---------- sleep / wake ----------

def test_sleep_removes_from_awake_but_keeps_the_model_known():
    orch, events = make()

    orch.sleep("ling-flash")

    assert "ling-flash" not in orch.members
    assert "ling-flash" in orch.asleep()
    assert "ling-flash" in orch.known, "a sleeping model must keep its registry entry"
    assert ("team", {"action": "sleep", "model": "ling-flash"}) in events


def test_wake_puts_it_back():
    orch, _ = make()
    orch.sleep("ling-flash")
    assert "awake" in orch.wake("ling-flash")
    assert "ling-flash" in orch.members
    assert "ling-flash" not in orch.asleep()


def test_waking_an_uninstalled_model_is_refused_with_a_reason(monkeypatch):
    orch, _ = make()
    monkeypatch.setattr(REGISTRY, "available", lambda: ["claude", "agy"])
    orch.sleep("ling-flash")

    reply = orch.wake("ling-flash")

    assert "cannot be woken" in reply and "not installed" in reply
    assert "ling-flash" not in orch.members


def test_waking_something_already_awake_is_a_no_op():
    orch, _ = make()
    assert "already in the room" in orch.wake("claude")


def test_unknown_models_are_rejected_by_both():
    orch, _ = make()
    with pytest.raises(TeamError, match="unknown model"):
        orch.sleep("gpt-9")
    with pytest.raises(TeamError, match="unknown model"):
        orch.wake("gpt-9")


def test_the_lead_cannot_be_slept_out_from_under_the_room():
    orch, _ = make()
    with pytest.raises(TeamBusy, match="is the lead"):
        orch.sleep("claude")


# ---------- leader ----------

def test_lead_can_change_mid_session():
    orch, events = make()
    orch.set_lead("nemotron-ultra")
    assert orch.lead == "nemotron-ultra"
    assert any(k == "team" and d.get("action") == "lead" and d.get("previous") == "claude"
               for k, d in events)


def test_a_text_only_model_cannot_be_lead():
    orch, _ = make()
    text_only = next(m for m in TEXT_ONLY if m in REGISTRY)
    with pytest.raises(TeamError, match="text-only"):
        orch.set_lead(text_only)


def test_promoting_an_asleep_model_wakes_it():
    orch, _ = make()
    orch.sleep("big-pickle")

    orch.set_lead("big-pickle")

    assert orch.lead == "big-pickle"
    assert "big-pickle" in orch.members, "leading implies being in the room"


def test_promoting_an_uninstalled_model_is_refused(monkeypatch):
    orch, _ = make()
    monkeypatch.setattr(REGISTRY, "available", lambda: ["claude", "agy"])
    with pytest.raises(TeamError, match="isn't installed"):
        orch.set_lead("nemotron-ultra")
    assert orch.lead == "claude", "a refused promotion must not change the lead"


# ---------- commands ----------

def test_team_command_lists_awake_asleep_and_installed():
    orch, _ = make(members=("claude", "big-pickle"))
    reply = asyncio.run(command(orch, "/team"))
    assert "1 awake" not in reply  # sanity: counts come from real state
    assert "2 awake" in reply
    assert "`claude`" in reply and "**lead**" in reply
    assert "asleep" in reply
    assert "/sleep NAME" in reply


def test_team_command_reports_which_task_blocks_a_sleep():
    orch, _ = make()
    orch.all_tasks.append(busy_task("big-pickle", "running"))
    orch.busy = {"big-pickle"}
    reply = asyncio.run(command(orch, "/team"))
    assert "working t1" in reply, "the board must show why a model cannot sleep"


def test_model_command_returns_a_reference_card():
    orch, _ = make()
    reply = asyncio.run(command(orch, "/model muse-spark"))
    assert "Best at:" in reply and "Not for:" in reply
    assert "longcat-preview" in reply, "the anti-pattern pointer must survive into the card"


def test_sleep_and_wake_commands_round_trip():
    orch, _ = make()
    assert "is asleep" in asyncio.run(command(orch, "/sleep ling-flash"))
    assert "ling-flash" not in orch.members
    assert "awake" in asyncio.run(command(orch, "/wake ling-flash"))


def test_sleep_command_on_a_busy_model_explains_instead_of_crashing():
    orch, _ = make()
    orch.all_tasks.append(busy_task("big-pickle", "running"))
    orch.busy = {"big-pickle"}
    reply = asyncio.run(command(orch, "/sleep big-pickle"))
    assert "Not now" in reply and "t1" in reply
    assert "big-pickle" in orch.members


def test_lead_command_switches_and_reports():
    orch, _ = make()
    reply = asyncio.run(command(orch, "/lead nemotron-ultra"))
    assert "is the lead now" in reply
    assert orch.lead == "nemotron-ultra"


def test_lead_command_with_no_args_lists_the_room():
    orch, _ = make()
    reply = asyncio.run(command(orch, "/lead"))
    assert "Lead is claude" in reply
    assert "/lead recommend" in reply


def test_lead_recommend_never_asks_the_outgoing_lead():
    """A model grading its own successor is the one judgement its track record cannot inform."""
    orch = make()[0]
    orch.backend.reply = '{"recommendation": "nemotron-ultra", "reason": "Best architecture record.", "runner_up": "agy"}'
    orch.set_lead("big-pickle")

    reply = asyncio.run(command(orch, "/lead recommend"))

    advisor = orch.backend.calls[0][0]
    assert advisor != "big-pickle", "the outgoing lead must not be the advisor"
    assert advisor in orch.members
    assert "nemotron-ultra" in reply
    assert "advising" in reply.lower()
    assert "nothing changes until" in reply, "recommendation must not silently change the lead"
    assert orch.lead == "big-pickle", "recommendation must not change the lead by itself"


def test_lead_recommend_falls_back_to_the_track_record_on_a_bad_reply():
    orch = make()[0]
    orch.backend.reply = "I think claude would be great, honestly"
    orch.set_lead("big-pickle")
    reply = asyncio.run(command(orch, "/lead recommend"))
    assert "track record's own pick" in reply
    assert orch.lead == "big-pickle"


def test_lead_recommend_says_so_when_there_is_no_one_to_ask():
    orch = Orchestrator(FakeBackend(), ["qwen"], "qwen", known=list(REGISTRY.names()))
    reply = asyncio.run(command(orch, "/lead recommend"))
    assert "no one else in the room" in reply


def test_help_lists_the_new_commands():
    reply = asyncio.run(command(make()[0], "/help"))
    for cmd in ("/team", "/models", "/model NAME", "/sleep NAME", "/wake NAME", "/lead"):
        assert cmd in reply


# ---------- add / remove: a model this session never had, and one it forgets ----------

def _session_without(*dropped):
    """An orchestrator whose `known` set starts life without these models — what a session that was
    launched with a narrow roster, or that has already used /remove, actually looks like."""
    known = [m for m in REGISTRY.names() if m not in dropped]
    events = []
    orch = Orchestrator(FakeBackend(), ["claude", "agy"], "claude", emit=lambda k, d: events.append((k, d)),
                        known=known)
    return orch, events


def test_add_brings_in_a_model_the_session_never_had(monkeypatch):
    monkeypatch.setattr(REGISTRY, "available", lambda: ["claude", "agy", "qwen"])
    orch, events = _session_without("qwen")

    reply = orch.add("qwen")

    assert "is in the room" in reply
    assert "qwen" in orch.members and "qwen" in orch.known
    assert ("team", {"action": "add", "model": "qwen"}) in events


def test_add_is_distinct_from_wake_and_says_which_one_you_want(monkeypatch):
    """Both bring a model into the room, but /wake revives one that is still known and /add brings
    in one that is not. Being unable to tell them apart is how a user ends up confused about why
    a model is missing, so each answer names the other."""
    monkeypatch.setattr(REGISTRY, "available", lambda: ["claude", "agy", "qwen"])
    orch, _ = _session_without("qwen")
    orch.add("qwen")
    orch.sleep("qwen")

    assert "already known and asleep" in orch.add("qwen"), "/add must point at /wake"
    assert "already in the room" in orch.add("agy")
    assert "qwen" not in orch.members, "a no-op must not wake the model as a side effect"


def test_adding_a_model_with_no_installed_cli_is_refused_with_a_reason(monkeypatch):
    """The same guard `wake` uses: a model whose tool is missing must not be added into failing
    tasks, and the answer has to say why rather than looking like success."""
    monkeypatch.setattr(REGISTRY, "available", lambda: ["claude", "agy"])
    orch, _ = _session_without("qwen")

    reply = orch.add("qwen")

    assert "cannot be added" in reply and "not installed" in reply
    assert "qwen" not in orch.known, "a refused add must not register the model anyway"


def test_add_rejects_a_model_that_is_not_in_the_registry_at_all():
    orch, _ = _session_without()
    with pytest.raises(TeamError, match="unknown model"):
        orch.add("gpt-9")


def test_remove_drops_the_model_from_the_session_entirely():
    """Unlike sleep, remove forgets the model: it must not reappear in /team, must not be offered
    as lead, and /add is the only way back."""
    orch, events = make()

    reply = orch.remove("ling-flash")

    assert "out of the session" in reply
    assert "ling-flash" not in orch.members
    assert "ling-flash" not in orch.known
    assert "ling-flash" not in orch.asleep()
    assert ("team", {"action": "remove", "model": "ling-flash"}) in events


def test_remove_keeps_the_registry_entry_its_stats_and_its_journal():
    """Only the session forgets the model. Dropping the registry entry would destroy every audit
    record and nickname ever learned about it."""
    orch, _ = make()
    orch.nicknames["ling-flash"] = "Ling"
    orch.remove("ling-flash")

    assert "ling-flash" in REGISTRY.models
    assert orch.nicknames["ling-flash"] == "Ling"


def test_a_working_model_cannot_be_removed():
    orch, _ = make()
    orch.all_tasks.append(busy_task("big-pickle", "running"))
    orch.busy = {"big-pickle"}

    with pytest.raises(TeamBusy) as err:
        orch.remove("big-pickle")

    assert "working on t1" in str(err.value)
    assert "big-pickle" in orch.members and "big-pickle" in orch.known


def test_the_lead_cannot_be_removed_from_under_the_room():
    orch, _ = make()
    with pytest.raises(TeamBusy, match="is the lead"):
        orch.remove("claude")
    assert "claude" in orch.known, "a refused removal must not drop the lead from the session"


def test_removing_something_the_session_does_not_have_says_so():
    orch, _ = _session_without("qwen")
    with pytest.raises(TeamBusy, match="not in this session"):
        orch.remove("qwen")


def test_a_model_removed_then_made_lead_comes_back_into_the_session(monkeypatch):
    """remove takes a model out of `known`; set_lead puts it in `members`. If it did not restore
    `known` too, the room would be led by a model that /team cannot see."""
    monkeypatch.setattr(REGISTRY, "available", lambda: ["claude", "agy", "codex"])
    orch, _ = make()
    orch.remove("codex")
    assert "codex" not in orch.known

    orch.set_lead("codex")

    assert orch.lead == "codex"
    assert "codex" in orch.known, "a lead must be visible to /team"
    assert "codex" in orch.members


# ---------- the commands ----------

def test_add_and_remove_commands_round_trip(monkeypatch):
    monkeypatch.setattr(REGISTRY, "available", lambda: ["claude", "agy", "qwen"])
    orch, _ = _session_without("qwen")

    assert "is in the room" in asyncio.run(command(orch, "/add qwen"))
    assert "qwen" in orch.members
    assert "out of the session" in asyncio.run(command(orch, "/remove qwen"))
    assert "qwen" not in orch.known


def test_a_busy_model_reports_not_now_rather_than_crashing_the_message_loop():
    orch, _ = make()
    orch.all_tasks.append(busy_task("big-pickle", "running"))
    orch.busy = {"big-pickle"}

    reply = asyncio.run(command(orch, "/remove big-pickle"))

    assert "Not now" in reply and "t1" in reply
    assert "big-pickle" in orch.known


def test_add_and_remove_need_a_model_name():
    orch, _ = make()
    for verb in ("/add", "/remove"):
        assert "Which model?" in asyncio.run(command(orch, verb))


def test_help_lists_add_and_remove():
    reply = asyncio.run(command(make()[0], "/help"))
    for cmd in ("/add NAME", "/remove NAME"):
        assert cmd in reply

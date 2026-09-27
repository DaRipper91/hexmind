"""Team state: sleep, wake, and leader changes — and INVARIANT S-1.

S-1: a model holding a live task cannot be put to sleep. No override, no queue. The model is
mid-edit in a real folder or a relay worktree; a half-written file is never worth the memory.
"""
import asyncio

import pytest

from hexmind.core import (BUSY_STATUSES, REGISTRY, Orchestrator, Task, TeamBusy, TeamError,
                          ROSTER, TEXT_ONLY)
from hexmind.relay import command


class FakeBackend:
    def __init__(self, cwd="/tmp", reply="done"):
        self.cwd = cwd
        self.reply = reply
        self.calls = []

    async def run(self, agent, prompt, cwd=None, schema=None):
        self.calls.append((agent, prompt))
        return self.reply


def make(members=("claude", "agy", "opencode-pickle", "opencode-ling"), lead="claude"):
    events = []
    orch = Orchestrator(FakeBackend(), list(members), lead, emit=lambda k, d: events.append((k, d)),
                       known=list(REGISTRY.names()))
    return orch, events


def busy_task(agent="opencode-pickle", status="running"):
    t = Task(id="t1", title="do the thing", agent=agent, instructions="x")
    t.status = status
    return t


# ---------- INVARIANT S-1 ----------

def test_a_working_model_cannot_be_slept():
    orch, _ = make()
    orch.all_tasks.append(busy_task("opencode-pickle", "running"))
    orch.busy = {"opencode-pickle"}

    with pytest.raises(TeamBusy) as err:
        orch.sleep("opencode-pickle")

    assert "working on t1" in str(err.value)
    assert "opencode-pickle" in orch.members, "a refused sleep must not remove the model anyway"


@pytest.mark.parametrize("status", sorted(BUSY_STATUSES))
def test_every_live_status_blocks_sleep(status):
    orch, _ = make()
    orch.all_tasks.append(busy_task("opencode-pickle", status))
    orch.busy = {"opencode-pickle"}
    with pytest.raises(TeamBusy):
        orch.sleep("opencode-pickle")


@pytest.mark.parametrize("status", ["pending", "done", "failed", "skipped"])
def test_a_terminal_or_unstarted_task_does_not_block_sleep(status):
    orch, _ = make()
    orch.all_tasks.append(busy_task("opencode-pickle", status))
    orch.busy = {t.agent for t in orch.all_tasks if t.status in BUSY_STATUSES}

    assert orch.can_sleep("opencode-pickle")[0] is True
    assert "asleep" in orch.sleep("opencode-pickle")


def test_can_sleep_explains_why_rather_than_just_refusing():
    orch, _ = make()
    orch.all_tasks.append(busy_task())
    orch.busy = {"opencode-pickle"}

    allowed, reason = orch.can_sleep("opencode-pickle")
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
    task = busy_task("opencode-pickle", "pending")

    async def go():
        run = asyncio.create_task(orch.run_tasks("req", [task]))
        for _ in range(50):  # let it reach `running`
            if "opencode-pickle" in orch.busy:
                break
            await asyncio.sleep(0.01)
        assert orch.busy == {"opencode-pickle"}, "a launched task must mark its model busy"
        assert orch.can_sleep("opencode-pickle")[0] is False
        assert orch.can_sleep("agy")[0] is True
        release.set()
        await run
        assert orch.busy == set(), "a finished task must clear its model's busy flag"
        assert task.status == "done"
        assert orch.can_sleep("opencode-pickle")[0] is True

    asyncio.run(go())


def test_a_cancelled_turn_does_not_wedge_a_model_awake_forever():
    """The finally branch matters: without it, quitting mid-task would leave the model
    permanently unsleepable for the rest of the session."""
    orch, _ = make()
    task = busy_task("opencode-pickle", "pending")

    class Never:
        cwd = "/tmp"

        async def run(self, *a, **k):
            await asyncio.sleep(3600)

    orch.backend = Never()

    async def go():
        run = asyncio.create_task(orch.run_tasks("req", [task]))
        for _ in range(50):
            if "opencode-pickle" in orch.busy:
                break
            await asyncio.sleep(0.01)
        run.cancel()
        with pytest.raises(asyncio.CancelledError):
            await run
        assert orch.busy == set(), "a cancelled task must not leave its model unsleepable"
        assert task.status == "failed", "the board must not claim cancelled work is still running"
        assert "cancelled" in task.output

    asyncio.run(go())


# ---------- sleep / wake ----------

def test_sleep_removes_from_awake_but_keeps_the_model_known():
    orch, events = make()

    orch.sleep("opencode-ling")

    assert "opencode-ling" not in orch.members
    assert "opencode-ling" in orch.asleep()
    assert "opencode-ling" in orch.known, "a sleeping model must keep its registry entry"
    assert ("team", {"action": "sleep", "model": "opencode-ling"}) in events


def test_wake_puts_it_back():
    orch, _ = make()
    orch.sleep("opencode-ling")
    assert "awake" in orch.wake("opencode-ling")
    assert "opencode-ling" in orch.members
    assert "opencode-ling" not in orch.asleep()


def test_waking_an_uninstalled_model_is_refused_with_a_reason(monkeypatch):
    orch, _ = make()
    monkeypatch.setattr(REGISTRY, "available", lambda: ["claude", "agy"])
    orch.sleep("opencode-ling")

    reply = orch.wake("opencode-ling")

    assert "cannot be woken" in reply and "not installed" in reply
    assert "opencode-ling" not in orch.members


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
    orch.set_lead("opencode-ultra")
    assert orch.lead == "opencode-ultra"
    assert any(k == "team" and d.get("action") == "lead" and d.get("previous") == "claude"
               for k, d in events)


def test_a_text_only_model_cannot_be_lead():
    orch, _ = make()
    text_only = next(m for m in TEXT_ONLY if m in REGISTRY)
    with pytest.raises(TeamError, match="text-only"):
        orch.set_lead(text_only)


def test_promoting_an_asleep_model_wakes_it():
    orch, _ = make()
    orch.sleep("opencode-pickle")

    orch.set_lead("opencode-pickle")

    assert orch.lead == "opencode-pickle"
    assert "opencode-pickle" in orch.members, "leading implies being in the room"


def test_promoting_an_uninstalled_model_is_refused(monkeypatch):
    orch, _ = make()
    monkeypatch.setattr(REGISTRY, "available", lambda: ["claude", "agy"])
    with pytest.raises(TeamError, match="isn't installed"):
        orch.set_lead("opencode-ultra")
    assert orch.lead == "claude", "a refused promotion must not change the lead"


# ---------- commands ----------

def test_team_command_lists_awake_asleep_and_installed():
    orch, _ = make(members=("claude", "opencode-pickle"))
    reply = asyncio.run(command(orch, "/team"))
    assert "1 awake" not in reply  # sanity: counts come from real state
    assert "2 awake" in reply
    assert "`claude`" in reply and "**lead**" in reply
    assert "asleep" in reply
    assert "/sleep NAME" in reply


def test_team_command_reports_which_task_blocks_a_sleep():
    orch, _ = make()
    orch.all_tasks.append(busy_task("opencode-pickle", "running"))
    orch.busy = {"opencode-pickle"}
    reply = asyncio.run(command(orch, "/team"))
    assert "working t1" in reply, "the board must show why a model cannot sleep"


def test_model_command_returns_a_reference_card():
    orch, _ = make()
    reply = asyncio.run(command(orch, "/model opencode-muse"))
    assert "Best at:" in reply and "Not for:" in reply
    assert "opencode-longcat" in reply, "the anti-pattern pointer must survive into the card"


def test_sleep_and_wake_commands_round_trip():
    orch, _ = make()
    assert "is asleep" in asyncio.run(command(orch, "/sleep opencode-ling"))
    assert "opencode-ling" not in orch.members
    assert "awake" in asyncio.run(command(orch, "/wake opencode-ling"))


def test_sleep_command_on_a_busy_model_explains_instead_of_crashing():
    orch, _ = make()
    orch.all_tasks.append(busy_task("opencode-pickle", "running"))
    orch.busy = {"opencode-pickle"}
    reply = asyncio.run(command(orch, "/sleep opencode-pickle"))
    assert "Not now" in reply and "t1" in reply
    assert "opencode-pickle" in orch.members


def test_lead_command_switches_and_reports():
    orch, _ = make()
    reply = asyncio.run(command(orch, "/lead opencode-ultra"))
    assert "is the lead now" in reply
    assert orch.lead == "opencode-ultra"


def test_lead_command_with_no_args_lists_the_room():
    orch, _ = make()
    reply = asyncio.run(command(orch, "/lead"))
    assert "Lead is claude" in reply
    assert "/lead recommend" in reply


def test_lead_recommend_never_asks_the_outgoing_lead():
    """A model grading its own successor is the one judgement its track record cannot inform."""
    orch = make()[0]
    orch.backend.reply = '{"recommendation": "opencode-ultra", "reason": "Best architecture record.", "runner_up": "agy"}'
    orch.set_lead("opencode-pickle")

    reply = asyncio.run(command(orch, "/lead recommend"))

    advisor = orch.backend.calls[0][0]
    assert advisor != "opencode-pickle", "the outgoing lead must not be the advisor"
    assert advisor in orch.members
    assert "opencode-ultra" in reply
    assert "advising" in reply.lower()
    assert "nothing changes until" in reply, "recommendation must not silently change the lead"
    assert orch.lead == "opencode-pickle", "recommendation must not change the lead by itself"


def test_lead_recommend_falls_back_to_the_track_record_on_a_bad_reply():
    orch = make()[0]
    orch.backend.reply = "I think claude would be great, honestly"
    orch.set_lead("opencode-pickle")
    reply = asyncio.run(command(orch, "/lead recommend"))
    assert "track record's own pick" in reply
    assert orch.lead == "opencode-pickle"


def test_lead_recommend_says_so_when_there_is_no_one_to_ask():
    orch = Orchestrator(FakeBackend(), ["qwen"], "qwen", known=list(REGISTRY.names()))
    reply = asyncio.run(command(orch, "/lead recommend"))
    assert "no one else in the room" in reply


def test_help_lists_the_new_commands():
    reply = asyncio.run(command(make()[0], "/help"))
    for cmd in ("/team", "/models", "/model NAME", "/sleep NAME", "/wake NAME", "/lead"):
        assert cmd in reply

"""Team assembly: the lead proposes a roster, the user edits the live one, `/go` hands it back and
the lead plans against the room the user actually chose.

The invariant under test throughout: there is exactly one roster. `/recommend` proposes; `/add`,
`/remove`, `/sleep` and `/wake` edit `members`; `/go` reviews the difference. A second copy of the
team would be a copy that drifts.
"""
import asyncio
import json

import pytest

from hexmind.core import Assembly, Orchestrator, TeamError
from hexmind.relay import command


class FakeBackend:
    """Answers a recommend call with a roster, and a plan call with tasks."""

    def __init__(self, recommend=None, plan=None, reply="done"):
        self.recommend, self.plan, self.reply = recommend, plan, reply
        self.calls = []

    async def run(self, agent, prompt, cwd=None, schema=None):
        self.calls.append((agent, prompt))
        if "Which members do you want" in prompt:
            return json.dumps(self.recommend) if self.recommend else "I think claude would be great"
        if "Plan for the team the user actually chose" in prompt:
            return json.dumps(self.plan or {"reply": "on it", "tasks": []})
        if "Answer ONLY with a JSON object" in prompt:
            return json.dumps({"reply": "ok", "tasks": []})
        return self.reply


def make(backend=None, members=("claude", "agy"), lead="claude", known=None, monkeypatch=None):
    from hexmind.core import REGISTRY
    if monkeypatch is not None:  # /add and /set_lead re-check what is actually installed
        monkeypatch.setattr(REGISTRY, "available", lambda: ["claude", "agy", "codex", "kimi"])
    return Orchestrator(backend or FakeBackend(), list(members), lead,
                        known=known if known is not None else list(REGISTRY.names()))


RECOMMEND = {"members": ["claude", "codex"], "reasons": {"claude": "review", "codex": "tests"}}
PLAN = {"reply": "on it", "tasks": [
    {"id": "t1", "title": "do it", "agent": "claude", "instructions": "x", "depends_on": []}]}


# ---------- /recommend ----------

def test_recommend_asks_the_lead_and_changes_nothing():
    backend = FakeBackend(recommend=RECOMMEND)
    orch = make(backend)
    before = list(orch.members)

    reply = asyncio.run(command(orch, "/recommend refactor the auth module"))

    assert backend.calls[0][0] == "claude", "the current lead makes the proposal"
    assert "refactor the auth module" in backend.calls[0][1]
    assert "claude" in reply and "review" in reply and "codex" in reply
    assert "proposal, not a decision" in reply
    assert orch.members == before, "a recommendation must not touch the roster"
    assert orch.assembly is not None and orch.assembly.recommended == ["claude", "codex"]


def test_recommend_ignores_a_model_that_does_not_exist():
    """A hallucinated name in a roster proposal would be offered to the user as a real member."""
    orch = make(FakeBackend(recommend={"members": ["claude", "gpt-9"], "reasons": {"gpt-9": "fast"}}))
    reply = asyncio.run(command(orch, "/recommend build a parser"))
    assert "gpt-9" not in reply
    assert orch.assembly.recommended == ["claude"]


def test_a_prose_answer_changes_nothing_and_says_so():
    orch = make(FakeBackend(recommend=None))
    reply = asyncio.run(command(orch, "/recommend write a poem"))
    assert "prose" in reply
    assert orch.assembly.recommended == [], "a failed proposal must leave an empty assembly"


def test_recommend_needs_a_request():
    orch = make(FakeBackend(recommend=RECOMMEND))
    assert "/recommend needs the request" in asyncio.run(command(orch, "/recommend"))
    assert orch.assembly is None, "a refused recommend must not leave a half-built assembly"


def test_recommend_falls_back_to_the_last_thing_the_user_asked():
    orch = make(FakeBackend(recommend=RECOMMEND))
    orch.history.append(("make the parser faster", "done"))
    asyncio.run(command(orch, "/recommend"))
    assert "make the parser faster" in orch.backend.calls[0][1]


def test_recommend_with_no_lead_is_refused_rather_than_asking_the_wrong_model():
    orch = make(FakeBackend(recommend=RECOMMEND), lead=None)
    assert "no lead yet" in asyncio.run(command(orch, "/recommend fix it"))


# ---------- the user edits the live roster ----------

def test_add_and_remove_edit_the_room_the_proposal_was_made_for(monkeypatch):
    from hexmind.core import REGISTRY
    orch = make(FakeBackend(recommend=RECOMMEND), known=[m for m in REGISTRY.names() if m != "codex"],
                monkeypatch=monkeypatch)
    assert "codex" not in orch.known, "the model is registered, but this session never had it"
    asyncio.run(command(orch, "/recommend write the tests"))
    assert orch.assembly.recommended == ["claude", "codex"]

    asyncio.run(command(orch, "/add codex"))   # the user agrees with the lead
    assert "codex" in orch.members

    asyncio.run(command(orch, "/remove agy"))  # and drops someone who was already there
    assert "agy" not in orch.members
    assert orch.assembly.dropped(orch.members) == [], "the lead asked for what is now in the room"


# ---------- /go: the review call sees the disagreement ----------

def test_go_tells_the_lead_what_the_user_dropped_and_added(monkeypatch):
    from hexmind.core import REGISTRY
    backend = FakeBackend(recommend=RECOMMEND, plan=PLAN)
    seen = []
    # codex and kimi entered models.toml after this session started, so they are not in `known` yet
    orch = Orchestrator(backend, ["claude", "agy"], "claude", emit=lambda k, d: seen.append((k, d)),
                        known=[m for m in REGISTRY.names() if m not in ("codex", "kimi")])
    monkeypatch.setattr(REGISTRY, "available", lambda: ["claude", "agy", "codex", "kimi"])
    asyncio.run(command(orch, "/recommend refactor auth"))
    assert orch.assembly.recommended == ["claude", "codex"]
    asyncio.run(command(orch, "/remove codex"))   # dropped one the lead asked for
    asyncio.run(command(orch, "/add kimi"))       # and added one it did not

    asyncio.run(command(orch, "/go"))

    review = next(p for a, p in backend.calls if "Plan for the team the user actually chose" in p)
    assert "You asked for and the user dropped: codex" in review, "the review must see the disagreement"
    assert "The user added: kimi" in review
    assert "added: agy" not in review, "agy was in the room before the proposal; not a change"

    # the note is a chat message the lead posts before the plan, not the final summary, which is
    # about the work. This is the only place the user is told what the roster change cost.
    said = "\n".join(d.get("text", "") for k, d in seen if k == "message")
    assert "Roster adjusted" in said
    assert "codex" in said and "kimi" in said


def test_go_plans_against_the_room_actually_in_place():
    """The whole point: the lead must not hand work to a model the user removed."""
    backend = FakeBackend(recommend=RECOMMEND, plan=PLAN)
    orch = make(backend, members=("claude", "agy"))
    asyncio.run(command(orch, "/recommend refactor auth"))
    asyncio.run(command(orch, "/remove agy"))

    asyncio.run(command(orch, "/go"))

    run_agents = {a for a, p in backend.calls if "Your task (t1" in p}
    assert run_agents == {"claude"}, "only members of the settled room may be given work"


def test_go_says_when_the_room_was_untouched():
    backend = FakeBackend(recommend=RECOMMEND, plan=PLAN)
    orch = make(backend)
    asyncio.run(command(orch, "/recommend tidy up"))
    reply = asyncio.run(command(orch, "/go"))
    assert "Roster adjusted" not in reply, "no disagreement means no adjustment note"


def test_go_is_consumed_so_a_second_one_cannot_re_review_it():
    backend = FakeBackend(recommend=RECOMMEND, plan=PLAN)
    orch = make(backend)
    asyncio.run(command(orch, "/recommend tidy up"))
    asyncio.run(command(orch, "/go"))
    assert orch.assembly is None
    reply = asyncio.run(command(orch, "/go"))
    assert "No team is being assembled" in reply


def test_go_with_an_empty_room_says_so_and_spends_nothing():
    """Reachable by parking every member, and by an assembly that outlived a wake/sleep round. It
    must not call the lead to plan work for a room that has nobody in it."""
    backend = FakeBackend(recommend=RECOMMEND, plan=PLAN)
    orch = make(backend, members=("claude", "agy"))
    asyncio.run(command(orch, "/recommend tidy up"))
    orch.members = []
    calls_before = len(backend.calls)

    reply = asyncio.run(command(orch, "/go"))

    assert "room is empty" in reply
    assert len(backend.calls) == calls_before, "an empty room must not reach the lead"
    assert orch.assembly is None


# ---------- /cancel ----------

def test_cancel_drops_the_proposal_and_leaves_the_room_alone(monkeypatch):
    from hexmind.core import REGISTRY
    backend = FakeBackend(recommend=RECOMMEND)
    orch = make(backend, monkeypatch=monkeypatch,
                known=[m for m in REGISTRY.names() if m != "codex"])
    asyncio.run(command(orch, "/recommend refactor auth"))
    asyncio.run(command(orch, "/add codex"))
    reply = asyncio.run(command(orch, "/cancel"))
    assert "Cancelled" in reply
    assert orch.assembly is None
    assert "codex" in orch.members, "cancel abandons the proposal, not the user's own edits"


def test_cancel_with_nothing_pending_says_nothing_to_cancel():
    assert "Nothing to cancel" in asyncio.run(command(make(), "/cancel"))


# ---------- help ----------

def test_help_lists_the_assembly_commands():
    reply = asyncio.run(command(make(), "/help"))
    for cmd in ("/recommend", "/go", "/cancel"):
        assert cmd in reply


# ---------- the Assembly value object itself ----------

def test_the_diff_is_measured_against_the_room_the_proposal_was_made_in():
    """Dropped is the lead's list minus the room; added is the room minus what it was when the
    lead spoke. Comparing both against the same list would report every pre-existing member as
    something the user chose, which is the opposite of the disagreement being reviewed."""
    a = Assembly(request="x", recommended=["claude", "codex"], room=["claude", "agy"])
    assert a.dropped(["claude", "kimi"]) == ["codex"]
    assert a.added(["claude", "kimi"]) == ["kimi"], "agy was already there and is not a change"


def test_add_refuses_a_model_with_no_registry_entry_and_says_what_would():
    """The roster every prompt is generated from is models.toml. A model with no entry has no
    best_at, no avoid_for and no colour, so admitting one at runtime would build a roster nothing
    else agrees with. The refusal has to say the way in, or it reads as a dead end."""
    orch = make()
    with pytest.raises(TeamError, match="/scan"):
        orch.add("gpt-9")
    with pytest.raises(TeamError, match="/profile"):
        orch.add("gpt-9")


def test_go_posts_its_reply_once_and_not_twice(monkeypatch):
    """`command()` posts the reply of every command, and `/go` posts the lead's plan and summary
    itself. Both paths ran, so the user saw the plan twice — the TUI reads emit events, not return
    values, which is why the command-layer tests could not see it."""
    from hexmind.core import REGISTRY
    seen = []
    orch = Orchestrator(FakeBackend(recommend=RECOMMEND, plan={"reply": "on it", "tasks": []}), ["claude"],
                        "claude", emit=lambda k, d: seen.append((k, d.get("text", ""))))
    monkeypatch.setattr(REGISTRY, "available", lambda: ["claude", "agy", "codex"])
    asyncio.run(command(orch, "/recommend tidy up"))

    seen.clear()
    asyncio.run(command(orch, "/go"))

    said = [t for k, t in seen if k == "message"]
    carrying = [t for t in said if "on it" in t]
    assert len(carrying) == 1, f"the plan reached the room {len(carrying)} times: {said}"
    assert len([t for t in said if t.startswith("**Roster adjusted.**")]) == 1, "and so did the note"

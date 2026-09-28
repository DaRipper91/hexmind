"""`/scan` catalogues what is installed, `/profile` promotes one find into a member, `/add` brings
it into the room.

The load-bearing claim, and the reason this is not just a file format: **a promoted model is
immediately real.** Six module-level values (ROSTER, TEXT_ONLY, OPT_IN, DIRECT_CMDS, LOCAL_MODELS,
AGENT_COLOR) are computed once at import, and the orchestrator snapshots `known` at construction.
A member that is in the registry but not in those is worse than one that is absent, because the
failure is a KeyError in the middle of a task.
"""
import asyncio
import json

import pytest

from hexmind import backends
from hexmind import models as models_mod
from hexmind.core import OPT_IN, REGISTRY, ROSTER, Orchestrator
from hexmind.relay import command
from hexmind.tui import AGENT_COLOR


class FakeBackend:
    def __init__(self):
        self.calls = []

    async def run(self, agent, prompt, cwd=None, schema=None):
        self.calls.append((agent, prompt))
        return "done"


ENTRIES = [
    {"model": "google/gemini-3-pro", "provider": "google", "name": "google-gemini-3-pro",
     "label": "Gemini 3 Pro", "cli": "opencode", "verify": "path", "tier": "cloud", "color": "cyan"},
    {"model": "google/gemini-2.5-flash-image", "provider": "google",
     "name": "google-gemini-2-5-flash-image", "label": "Gemini 2.5 Flash Image",
     "cli": "opencode", "verify": "path", "tier": "cloud", "color": "magenta"},
]


@pytest.fixture(autouse=True)
def isolated_registry(monkeypatch, tmp_path):
    """A user overlay and a catalogue that exist only for this test, and a registry that is put back
    the way it was afterwards.

    `Registry.load` reads BUNDLED and USER at call time, so pointing USER at a tmp file is enough to
    make a promotion land somewhere disposable.

    The paths are set with plain assignment rather than monkeypatch, and that is the whole reason
    this fixture restores them itself: a monkeypatch override is undone when monkeypatch is torn
    down, which happens *after* this fixture's post-yield code, so it would put the tmp path back and
    leave every later test reading a file that no longer exists. The registry reload at the end is
    not optional either — REGISTRY, ROSTER, DIRECT_CMDS and AGENT_COLOR are module globals, and a
    test that promoted a model would otherwise leave it in all of them for the rest of the session."""
    real_user, real_catalogue = models_mod.USER, models_mod.CATALOGUE
    user, catalogue = tmp_path / "models.toml", tmp_path / "catalogue.json"
    models_mod.USER, models_mod.CATALOGUE = user, catalogue
    monkeypatch.setattr(models_mod, "discover", lambda: list(ENTRIES))
    # Availability is a live provider question behind a subprocess, and a hermetic test cannot depend
    # on what this machine happens to be offered. Pinned here; the refusal path gets its own test.
    # Patched on the *instance*, not the class, and that is load-bearing. Most tests in this suite do
    # `monkeypatch.setattr(REGISTRY, "available", ...)`, and monkeypatch's undo leaves the bound
    # method it found in the instance __dict__ rather than deleting it. That copy then shadows the
    # class attribute for the rest of the session, so a class-level patch made by a later test is
    # silently ignored. Patch the same level the rest of the suite does.
    monkeypatch.setattr(REGISTRY, "available",
                        lambda: ["claude", "agy", "codex", "google-gemini-3-pro"])
    models_mod.publish(REGISTRY)  # bundled only, whatever a previous test promoted
    yield catalogue
    models_mod.USER, models_mod.CATALOGUE = real_user, real_catalogue
    models_mod.publish(REGISTRY)  # also rebuilds backends.GENERATED, so nothing generated leaks


def promote(orch, *tokens):
    """`/profile NAME key=value …`, with the tokens spelled out so a malformed one can be tested."""
    return asyncio.run(command(orch, "/profile " + " ".join(tokens)))


# ---------- /scan writes a catalogue and touches nothing else ----------

def test_scan_never_touches_the_registry():
    """A scan on a real machine finds ~100 ids, most of which cannot edit a file. Promoting them
    all would put a roster of entries with no best_at in front of the lead and in /team."""
    orch = Orchestrator(FakeBackend(), ["claude"], "claude")
    before_models, before_known = dict(REGISTRY.models), list(orch.known)

    reply = asyncio.run(command(orch, "/scan"))

    assert "Scanned 2 models" in reply and "2 of them not members yet" in reply
    assert dict(REGISTRY.models) == before_models, "a scan must not add a member"
    assert list(orch.known) == before_known
    assert "best_at" in reply, "and it must say what the deliberate step is"


def test_scan_reports_a_dead_machine_honestly(monkeypatch):
    monkeypatch.setattr(models_mod, "discover", list)
    reply = asyncio.run(command(Orchestrator(FakeBackend(), ["claude"], "claude"), "/scan"))
    assert "Nothing found" in reply
    assert "`/models` still lists" in reply, "a failed scan must not read as an empty catalogue"


def test_found_lists_the_catalogue_and_filters_it():
    orch = Orchestrator(FakeBackend(), ["claude"], "claude")
    asyncio.run(command(orch, "/scan"))

    every = asyncio.run(command(orch, "/found"))
    assert "google-gemini-3-pro" in every and "google-gemini-2-5-flash-image" in every
    assert "2 of 2 found" in every
    assert "**member**" in every or "not a member" in every

    only_image = asyncio.run(command(orch, "/found image"))
    assert "google-gemini-2-5-flash-image" in only_image
    assert "google-gemini-3-pro" not in only_image
    assert "1 of 2 found" in only_image


def test_found_with_no_catalogue_points_at_scan():
    reply = asyncio.run(command(Orchestrator(FakeBackend(), ["claude"], "claude"), "/found"))
    assert "/scan" in reply and "No catalogue yet" in reply


# ---------- /profile is the gate ----------

def test_profile_refuses_without_a_best_at():
    """best_at is the routing signal. Admitting a member without it would mean a name in /team that
    the lead has no basis to assign anything to, which is the exact failure the registry exists to
    prevent."""
    orch = Orchestrator(FakeBackend(), ["claude"], "claude")
    asyncio.run(command(orch, "/scan"))

    reply = promote(orch, "google-gemini-3-pro", "domains=implementation")

    assert "best_at` is required" in reply
    assert "google-gemini-3-pro" not in REGISTRY, "a refused profile must not register anything"
    assert "google-gemini-3-pro" not in orch.known


def test_profile_refuses_a_name_that_is_neither_member_nor_find():
    orch = Orchestrator(FakeBackend(), ["claude"], "claude")
    asyncio.run(command(orch, "/scan"))
    reply = promote(orch, "gpt-9", "best_at=anything")
    assert "not a member and not in the catalogue" in reply


def test_profile_needs_key_value_arguments():
    orch = Orchestrator(FakeBackend(), ["claude"], "claude")
    asyncio.run(command(orch, "/scan"))
    assert "must be key=value" in promote(orch, "google-gemini-3-pro", "fast code")  # no `=`
    assert "Which model, and what is it for?" in asyncio.run(command(orch, "/profile"))


# ---------- the load-bearing one: a promoted model is immediately real ----------

def test_a_promoted_model_is_usable_immediately_without_a_restart():
    """Every one of these is a separate import-time snapshot. Missing any of them and the model is
    half-present: visible in /models, invisible to the lead, and a KeyError once a task routes to
    it. The task at the end is the point — it is the first thing that would actually fail."""
    orch = Orchestrator(FakeBackend(), ["claude"], "claude")
    asyncio.run(command(orch, "/scan"))
    assert "google-gemini-3-pro" not in REGISTRY

    reply = promote(orch, "google-gemini-3-pro", "best_at=fast focused implementation",
                    "domains=implementation,tests")

    assert "is a member" in reply
    # the registry
    assert "google-gemini-3-pro" in REGISTRY
    # the snapshots
    assert "google-gemini-3-pro" in ROSTER and "fast focused implementation" in ROSTER["google-gemini-3-pro"]
    assert "google-gemini-3-pro" in backends.DIRECT_CMDS
    assert backends.DIRECT_CMDS["google-gemini-3-pro"] == ["opencode", "run", "--auto",
                                                         "-m", "google/gemini-3-pro"]
    assert AGENT_COLOR["google-gemini-3-pro"] != "white", "a promoted model must not arrive white"
    assert "google-gemini-3-pro" in orch.known, "or /add would still call it unknown"
    # and the hand-written CLIs survived the republish
    assert backends.DIRECT_CMDS["claude"][0] == "claude", "publish must only touch generated keys"

    # `/add` is for a model this session never had. A promoted one is known now, so `/add` must say
    # so and point at `/wake` rather than claiming success.
    added = asyncio.run(command(orch, "/add google-gemini-3-pro"))
    assert "already known and asleep" in added and "/wake google-gemini-3-pro" in added
    assert "google-gemini-3-pro" not in orch.members, "a redirect must not add it as a side effect"

    # now the thing that would actually break: bring it in and give it a task
    woke = asyncio.run(command(orch, "/wake google-gemini-3-pro"))
    assert "awake" in woke, woke
    from hexmind.core import Task
    task = Task(id="t1", title="write it", agent="google-gemini-3-pro", instructions="x")
    asyncio.run(orch.run_tasks("req", [task]))
    assert task.status == "done", task.output
    assert any(a == "google-gemini-3-pro" for a, _ in orch.backend.calls)


def test_a_promoted_model_cannot_auto_join_and_sorts_below_every_curated_one():
    """opt_in so a launch never silently gains a member, and a weight below the curated floor so
    by_weight cannot prefer a find over a hand-chosen model."""
    orch = Orchestrator(FakeBackend(), ["claude"], "claude")
    asyncio.run(command(orch, "/scan"))
    promote(orch, "google-gemini-3-pro", "best_at=fast focused implementation")

    model = REGISTRY.get("google-gemini-3-pro")
    assert model.opt_in is True
    assert "google-gemini-3-pro" in OPT_IN
    assert model.weight < min(m.weight for n, m in REGISTRY.models.items() if n != "google-gemini-3-pro")
    ordered = REGISTRY.by_weight([n for n in REGISTRY.models if n != "google-gemini-3-pro"]
                                 + ["google-gemini-3-pro"])
    assert ordered[-1] == "google-gemini-3-pro", "a find must sort last"


def test_profiling_an_existing_member_rewrites_its_entry():
    orch = Orchestrator(FakeBackend(), ["claude"], "claude")
    reply = promote(orch, "claude", "best_at=only this now")
    assert "is a member" in reply
    assert REGISTRY.get("claude").best_at == "only this now"
    assert ROSTER["claude"] == "Claude Code: only this now", "the snapshot must follow the file"


def test_an_unknown_field_is_refused_before_anything_is_written():
    """Writing the profile and then complaining would leave the model in the overlay file and
    absent from the registry — half-promoted, which is the state this whole command guards against."""
    orch = Orchestrator(FakeBackend(), ["claude"], "claude")
    asyncio.run(command(orch, "/scan"))
    reply = promote(orch, "google-gemini-3-pro", "best_at=x", "nonsense=y")
    assert "Unknown field" in reply and "nonsense" in reply
    assert "google-gemini-3-pro" not in REGISTRY
    assert not models_mod.USER.exists(), "nothing may be written when the command refuses"


# ---------- the catalogue itself ----------

def test_slugs_are_unique_and_survive_a_provider_disappearing():
    """A member name is what a profile, a nickname, a chain file and every past task's agent field
    refer to. A slug that renames itself on the next scan would orphan all of them."""
    ids = ["opencode/a", "google/x", "openai/x", "a/b-c", "a-b/c", "qwen2.5-coder:7b"]
    first = models_mod.assign_slugs(ids)
    assert len(set(first.values())) == len(ids), first
    fewer = [i for i in ids if i != "google/x"]
    assert all(models_mod.assign_slugs(fewer)[i] == first[i] for i in fewer), \
        "a model was renamed because a different provider disappeared"


def test_the_catalogue_survives_a_corrupt_file(tmp_path):
    bad = tmp_path / "corrupt.json"
    bad.write_text("{ not json")
    assert models_mod.load_catalogue(bad) == {}
    assert models_mod.load_catalogue(tmp_path / "missing.json") == {}


def test_saved_catalogue_records_when_it_scanned():
    orch = Orchestrator(FakeBackend(), ["claude"], "claude")
    asyncio.run(command(orch, "/scan"))
    data = json.loads(models_mod.CATALOGUE.read_text())
    assert data["scanned_at"] and len(data["models"]) == 2
    assert "scanned" in asyncio.run(command(orch, "/found"))


def test_a_promoted_model_the_provider_does_not_offer_cannot_be_woken(monkeypatch):
    """Learned the hard way while writing this: the first fixture used a model id that does not
    exist, and `/wake` refused it — correctly. Promoting a find is not a claim that the provider
    serves it, and a member that cannot be woken is a member that can never take a task. So the
    availability check stays in the path, and the profile says nothing that overrides it."""
    monkeypatch.setattr(REGISTRY, "available", lambda: ["claude", "agy", "codex"])
    orch = Orchestrator(FakeBackend(), ["claude"], "claude")
    asyncio.run(command(orch, "/scan"))
    promote(orch, "google-gemini-3-pro", "best_at=architecture, planning")

    reply = asyncio.run(command(orch, "/wake google-gemini-3-pro"))

    assert "cannot be woken" in reply and "not installed" in reply
    assert "google-gemini-3-pro" not in orch.members
    assert "google-gemini-3-pro" in REGISTRY, "the profile itself was still written, and is honest about it"


# ---------- the catalogue has to agree with the registry about names ----------

def test_a_find_that_is_already_curated_reports_the_registrys_name():
    """The eight curated opencode models are `big-pickle` and `opencode-ultra` in models.toml, but a
    scan slugs `opencode/big-pickle` to `opencode-big-pickle`. Unaligned, `/found` would list eight
    already-curated models as unpromoted finds and `/profile` on one would create a second member
    for a model the room already has."""
    assert "opencode-ultra" in REGISTRY.models
    real_id = REGISTRY.get("opencode-ultra").model
    entries = [{"model": real_id, "provider": "opencode", "name": "opencode-ultra-dup",
                "label": "wrong", "cli": "opencode", "verify": "path", "tier": "cloud",
                "color": "white"}]
    aligned = models_mod.align_entries(entries, REGISTRY.models)
    assert aligned[0]["name"] == "opencode-ultra"
    assert aligned[0]["curated"] is True
    assert aligned[0]["label"] == REGISTRY.get("opencode-ultra").label


def test_the_scan_count_excludes_models_already_in_the_registry(monkeypatch):
    real_id = REGISTRY.get("opencode-ultra").model
    entries = [
        {"model": real_id, "provider": "opencode", "name": "wrong-slug", "label": "x",
         "cli": "opencode", "verify": "path", "tier": "cloud", "color": "white"},
        {"model": "google/gpt-5", "provider": "openai", "name": "openai-gpt-5", "label": "GPT-5",
         "cli": "opencode", "verify": "path", "tier": "cloud", "color": "cyan"},
    ]
    monkeypatch.setattr(models_mod, "discover", lambda: entries)
    orch = Orchestrator(FakeBackend(), ["claude"], "claude")
    reply = asyncio.run(command(orch, "/scan"))
    assert "Scanned 2 models" in reply and "1 of them not members yet" in reply
    listed = asyncio.run(command(orch, "/found"))
    row = next(l for l in listed.splitlines() if "opencode-ultra" in l)
    assert row.endswith("asleep |"), f"a curated find must not read as unpromoted: {row}"
    assert "not a member" in listed, "the genuinely new one still does"

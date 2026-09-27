"""The model registry: loading, generated prose, and the invariants that stop roster drift."""
import asyncio
import tomllib
from pathlib import Path

import pytest

from hexmind.auditor import DOMAINS
from hexmind.core import OPT_IN, ROSTER, TEXT_ONLY, REGISTRY
from hexmind.models import BUNDLED, Registry

ALL_OPENCODE = ["opencode", "opencode-ultra", "opencode-muse", "opencode-mimo",
                "opencode-pickle", "opencode-ling", "opencode-bunny", "opencode-longcat"]


def write(tmp_path, text):
    path = tmp_path / "models.toml"
    path.write_text(text)
    return path


# ---------- the drift guard: the point of the whole exercise ----------

def test_roster_is_generated_from_the_registry_not_hand_written():
    assert ROSTER == REGISTRY.roster()
    assert set(ROSTER) == set(REGISTRY.names())


def test_every_model_is_described_by_its_own_fields():
    for name, prose in ROSTER.items():
        m = REGISTRY.get(name)
        assert prose.startswith(m.label), f"{name} lost its label"
        assert m.best_at in prose, f"{name} lost best_at"
        if m.avoid_for:
            assert m.avoid_for in prose, f"{name} lost avoid_for"
            assert "Not for" in prose, f"{name} must say what it is not for"


def test_domains_are_all_real_audit_domains():
    """A typo'd domain would silently never match a task's domain, so it is checked here."""
    for name, m in REGISTRY.models.items():
        unknown = set(m.domains) - set(DOMAINS)
        assert not unknown, f"{name} has unknown domains {unknown}"


def test_tier_and_verify_are_valid_and_consistent():
    for name, m in REGISTRY.models.items():
        assert m.tier in ("cloud", "local"), name
        assert m.verify in ("path", "ollama", "env"), name
        if m.verify == "env":
            assert m.env, f"{name} verifies via env but names no variable"
        if m.tier == "local":
            assert m.verify == "ollama" and m.model, f"{name} is local but names no Ollama tag"


# ---------- the eight free models ----------

def test_all_eight_free_opencode_models_are_registered():
    for name in ALL_OPENCODE:
        assert name in REGISTRY, f"{name} missing from the registry"
        assert REGISTRY.get(name).model.startswith("opencode/")
        assert REGISTRY.get(name).cli == "opencode"
        assert REGISTRY.get(name).tier == "cloud"


def test_the_three_previously_drifted_models_are_now_scoped_correctly():
    """These are the descriptions that were wrong and let work route to the wrong model."""
    muse = ROSTER["opencode-muse"]
    assert "skill" in muse.lower() and "prompt" in muse.lower()
    assert "opencode-longcat" in muse, "muse must point at longcat for repo scans"
    assert "1M context" not in muse, "muse must not claim longcat's context window"

    mimo = ROSTER["opencode-mimo"]
    assert "ui" in mimo.lower()
    assert "dom" in mimo.lower()

    pickle = ROSTER["opencode-pickle"]
    assert "tdd" in pickle.lower() or "failing tests" in pickle.lower()


def test_ui_domain_has_a_model_that_claims_it():
    """auditor.DOMAINS has a `ui` domain; before the registry nothing in the roster advertised it."""
    assert [n for n, m in REGISTRY.models.items() if "ui" in m.domains]


# ---------- text-only / opt-in ----------

def test_text_only_and_opt_in_come_from_the_registry():
    assert TEXT_ONLY == REGISTRY.text_only()
    assert OPT_IN == REGISTRY.opt_in()
    assert TEXT_ONLY == {"qwen", "qwen-large", "jules"}
    for name in TEXT_ONLY:
        assert REGISTRY.get(name).text_only


# ---------- preference weighting (plan R5) ----------

def test_opencode_models_outrank_the_rest():
    ordered = REGISTRY.by_weight()
    weights = {n: REGISTRY.get(n).weight for n in ordered}
    assert weights[ordered[0]] > weights["claude"]
    assert weights["claude"] > weights["copilot"] > weights["qwen"]
    for name in ALL_OPENCODE:
        assert weights[name] >= 80, f"{name} should be a preferred member"


def test_by_weight_can_rank_a_subset():
    ranked = REGISTRY.by_weight(["claude", "opencode-pickle", "agy"])
    assert ranked[0] == "opencode-pickle"


# ---------- loading and overrides ----------

def test_bundled_registry_loads_and_lists_every_member():
    reg = Registry.load()
    assert BUNDLED in reg.sources
    assert set(reg.names()) >= set(ALL_OPENCODE) | {"claude", "agy", "codex", "kimi", "copilot"}


def test_user_file_overrides_a_single_model_without_losing_the_rest(tmp_path):
    override = write(tmp_path, """
[models.opencode-mimo]
label = "My MiMo"
best_at = "only the ui work I care about"
""")
    reg = Registry.load([BUNDLED, override])

    assert reg.get("opencode-mimo").label == "My MiMo"
    assert reg.get("opencode-mimo").cli == "opencode", "unspecified fields must fall back to the bundled entry"
    assert "claude" in reg, "the rest of the bundled roster must survive"
    assert reg.get("opencode-ultra").label.startswith("NVIDIA")


def test_invalid_tier_or_verifier_is_rejected_not_ignored(tmp_path):
    bad = write(tmp_path, '[models.x]\nlabel="X"\nbest_at="y"\ncli="z"\nverify="path"\ntier="moon"\n')
    with pytest.raises(ValueError, match="tier must be one of"):
        Registry.load([bad])


def test_missing_registry_file_is_a_clear_error_not_an_empty_team(tmp_path):
    """A missing bundled file must fail loudly; silently yielding an empty roster is the bug class
    this registry exists to remove."""
    with pytest.raises(FileNotFoundError, match="model registry not found"):
        Registry.load([tmp_path / "does-not-exist.toml"])


def test_missing_user_override_is_fine(tmp_path):
    reg = Registry.load([BUNDLED, tmp_path / "never-created.toml"])
    assert "claude" in reg


# ---------- generated surfaces (plan R7) ----------

def test_describe_gives_a_reference_card_with_the_misuse_warnings():
    card = REGISTRY.describe("opencode-muse")
    for expected in ("Best at:", "Not for:", "Domains:", "Model id:"):
        assert expected in card
    assert "opencode-longcat" in card


def test_matrix_lists_every_model_with_tier_and_status():
    table = REGISTRY.matrix(live=set(ALL_OPENCODE), team={"opencode-pickle"}, lead="opencode-pickle")
    assert table.startswith("| model |")
    for name in ALL_OPENCODE:
        assert f"`{name}`" in table
    assert "**LEAD**" in table
    assert "| cloud |" in table


def test_matrix_marks_absent_models_rather_than_hiding_them():
    table = REGISTRY.matrix(live=set(), team=set())
    assert "not installed" in table


# ---------- availability ----------

def test_available_returns_preference_order_and_reports_opt_in_separately(monkeypatch):
    """available() reports what is installed; filtering opt-in members is the caller's job
    (__main__ applies `--with`). Keeping the two separate is what lets `/add qwen` work later."""
    reg = Registry.load()
    monkeypatch.setattr(reg, "_ollama_models", staticmethod(lambda: {"qwen2.5-coder:7b"}))
    monkeypatch.setattr(reg, "_opencode_models", staticmethod(lambda: set()))
    monkeypatch.setenv("JULES_API_KEY", "x")
    monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/fake")

    found = reg.available()
    team = [m for m in found if m not in reg.opt_in()]

    assert "jules" in found, "installed opt-in members are reported, just not auto-joined"
    assert "qwen" in found
    assert "jules" not in team and "qwen" not in team
    weights = [reg.get(n).weight for n in found]
    assert weights == sorted(weights, reverse=True), "available() must be preference-ordered"
    assert team == [m for m in found if m in reg.members()]


def test_opencode_member_with_a_bad_model_id_is_not_offered(monkeypatch):
    """The registry's whole point: a model id the CLI will reject must never reach the roster."""
    reg = Registry.load()
    monkeypatch.setattr(reg, "_opencode_models", staticmethod(lambda: {"opencode/big-pickle"}))
    monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/fake")

    found = reg.available()

    assert "opencode-pickle" in found
    assert "opencode-longcat" not in found, "longcat is not in the allowed set, so it must not join"


def test_detect_is_async_and_matches_available(monkeypatch):
    reg = Registry.load()
    monkeypatch.setattr(reg, "_opencode_models", staticmethod(lambda: set()))
    monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/fake")

    assert asyncio.run(reg.detect()) == reg.available()


# ---------- bundled file hygiene ----------

def test_bundled_toml_is_valid_and_documents_its_fields():
    data = tomllib.loads(BUNDLED.read_text())
    assert len(data["models"]) >= 15
    header = BUNDLED.read_text().split("[models.")[0]
    for field in ("best_at", "avoid_for", "domains", "weight", "think", "tier"):
        assert field in header, f"{field} is undocumented in the bundled file"


# ---------- bundled chain files must only pin agents that exist ----------

def test_every_agent_pinned_in_a_bundled_chain_is_a_real_member():
    """A chain that pins a model hexmind does not know silently degrades to rotation:
    relay.assign() only honours `st.agent` when `st.agent in members`. That failure is invisible,
    so it is checked here instead."""
    from hexmind.relay import BrokenChain, list_chains, load_chain

    checked, broken = 0, []
    for name, path in list_chains().items():
        try:
            chain = load_chain(path)
        except BrokenChain as e:
            broken.append(f"{name} ({e})")  # a different, already-reported failure; not our concern here
            continue
        for stage in chain.stages:
            if stage.agent:
                assert stage.agent in REGISTRY, (
                    f"chain '{name}' stage '{stage.name}' pins '{stage.agent}', "
                    f"which is not a registered model — it would silently rotate instead"
                )
                checked += 1
    assert checked, "no bundled chain pins an agent, so this guard is not actually testing anything"
    # a machine without the referenced agent files legitimately has broken chains; /chains reports them
    assert all(b for b in broken)


def test_opencode_team_chain_shape_is_the_adversarial_pipeline():
    from hexmind.relay import list_chains, load_chain

    chain = load_chain(list_chains()["opencode-team"])
    assert [s.name for s in chain.stages] == ["pre-audit", "tdd-build", "compliance-check", "post-critique"]
    assert chain.stages[0].agent == "opencode-ultra"
    assert chain.stages[1].agent == "opencode-pickle"
    assert chain.stages[2].agent == "opencode-longcat"
    assert chain.stages[3].agent == "opencode-ultra"
    # the builder must never be the reviewer
    assert chain.stages[1].agent not in {s.agent for s in (chain.stages[0], chain.stages[2], chain.stages[3])}
    # build and coverage gates: a failed implementation must not be rubber-stamped
    assert [s.gate for s in chain.stages] == [False, True, True, False]
    assert all(s.domain in DOMAINS for s in chain.stages)
    assert all(len(s.instructions.strip()) > 200 for s in chain.stages), "stage instructions must be self-contained"


def test_opencode_team_pinned_assignment_is_honoured():
    """The whole point of the chain: with --assign pinned, rotate must NOT be used."""
    from hexmind.relay import Chain, Stage, assign, list_chains, load_chain

    chain = load_chain(list_chains()["opencode-team"])
    members = ["claude", "agy", "codex", *ALL_OPENCODE]

    pinned = assign(chain, 1, members, "pinned")
    rotated = assign(chain, 1, members, "rotate")

    assert pinned[0] == [s.agent for s in chain.stages]
    assert pinned[0] != rotated[0], "rotation would have produced a different, unpinned assignment"


# ---------- `from =` resolution and bundled chain hygiene ----------

def test_from_accepts_a_bare_filename_and_searches_the_standard_agent_dirs(tmp_path, monkeypatch):
    from hexmind import relay

    agents = tmp_path / "agents"
    agents.mkdir()
    (agents / "my-reviewer.md").write_text("---\nname: r\n---\nReview the thing.\n")
    monkeypatch.setattr(relay, "AGENT_DIRS", [agents])

    assert relay.resolve_agent_file("my-reviewer.md") == agents / "my-reviewer.md"
    assert relay.resolve_agent_file("my-reviewer") == agents / "my-reviewer.md", "extension may be omitted"
    assert "Review the thing." in relay.read_agent_file(str(relay.resolve_agent_file("my-reviewer.md")))


def test_from_prefers_an_explicit_path_over_the_search_dirs(tmp_path, monkeypatch):
    from hexmind import relay

    explicit = tmp_path / "somewhere" / "agent.md"
    explicit.parent.mkdir()
    explicit.write_text("explicit wins")
    agents = tmp_path / "agents"
    agents.mkdir()
    (agents / "agent.md").write_text("searched")
    monkeypatch.setattr(relay, "AGENT_DIRS", [agents])

    resolved = relay.resolve_agent_file(str(explicit))

    assert resolved == explicit, "an existing path must be used as written, not via the search dirs"
    assert relay.read_agent_file(str(resolved)) == "explicit wins"


def test_a_path_that_looks_like_a_path_is_never_silently_searched_for(tmp_path, monkeypatch):
    """Writing a path and missing it is an error to report, not a hint to go looking elsewhere."""
    from hexmind import relay

    agents = tmp_path / "agents"
    agents.mkdir()
    (agents / "recon.md").write_text("should not be used")
    monkeypatch.setattr(relay, "AGENT_DIRS", [agents])

    assert relay.resolve_agent_file("~/nope/recon.md") is None


def test_missing_from_reports_where_it_looked(tmp_path, monkeypatch):
    from hexmind import relay
    from hexmind.relay import BrokenChain, load_chain

    monkeypatch.setattr(relay, "AGENT_DIRS", [tmp_path / "a", tmp_path / "b"])
    chain = tmp_path / "c.toml"
    chain.write_text('name = "c"\n[[stages]]\nname = "s"\nfrom = "ghost.md"\n')

    with pytest.raises(BrokenChain) as err:
        load_chain(chain)
    assert "missing ghost.md" in str(err.value)
    assert "looked for a file named this" in str(err.value)


def test_every_bundled_chain_loads_and_needs_nothing_external():
    """The reason the two user-specific chains moved to docs/examples/: a bundled chain that
    points outside the package is broken on every machine but the author's."""
    from hexmind.relay import list_chains, load_chain

    for name, path in list_chains().items():
        chain = load_chain(path)  # must not raise BrokenChain
        assert chain.stages, f"{name} has no stages"
        for stage in chain.stages:
            assert stage.instructions.strip(), f"{name}/{stage.name} has empty instructions"


def test_the_example_chains_are_no_longer_bundled():
    """doc-chain and rip-it-apart import agent files that live on one person's machine."""
    from hexmind.relay import list_chains

    bundled = set(list_chains())
    assert bundled == {"feature", "opencode-team"}
    examples = Path(__file__).parent.parent / "docs/examples/chains"
    assert {p.stem for p in examples.glob("*.toml")} == {"doc-chain", "rip-it-apart"}

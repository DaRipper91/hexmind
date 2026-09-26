from pathlib import Path

import pytest

from hexmind.relay import CHAIN_DIRS, list_chains, load_chain

CHAIN = Path(CHAIN_DIRS[-1]) / "doc-chain.toml"  # the bundled chains dir
AGENTS = Path.home() / "Projects/doc-chain/claude-code/.claude/agents"


def test_doc_chain_is_bundled_and_listed():
    assert CHAIN.is_file()
    assert list_chains().get("doc-chain") in (CHAIN, Path.home() / ".config/hexmind/chains/doc-chain.toml")


@pytest.mark.skipif(not AGENTS.is_dir(), reason="doc-chain agents not installed on this machine")
def test_doc_chain_loads_stages_in_order_with_verify_gate():
    chain = load_chain(CHAIN)
    assert chain.name == "doc-chain"
    assert [s.name for s in chain.stages] == ["plan", "draft", "verify", "review"]
    assert [s.domain for s in chain.stages] == ["docs", "docs", "shell", "review"]
    for stage in chain.stages:  # frontmatter stripped, body imported
        assert not stage.instructions.startswith("---") and stage.instructions.strip()
    assert "Only run this stage if doc-plan.md marked" in chain.stages[2].instructions  # its own gate


def test_doc_chain_without_agents_is_reported_broken(tmp_path, monkeypatch):
    import hexmind.relay as relay

    monkeypatch.setenv("HOME", str(tmp_path))  # "~" now has no doc-chain checkout
    with pytest.raises(relay.BrokenChain, match="missing ~/Projects/doc-chain"):
        load_chain(CHAIN)

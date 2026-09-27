"""doc-chain is an example chain, not a bundled one: it imports agent files that live in a
specific checkout on one person's machine, so it lives in docs/examples/chains/ instead.

What is still worth asserting is that the example is well-formed — users are told to copy it,
so a broken template is a real defect — and that a chain whose agents are missing is reported
rather than silently skipped.
"""
import tomllib
from pathlib import Path

import pytest

import hexmind.relay as relay
from hexmind.relay import BrokenChain, list_chains, load_chain

REPO = Path(relay.__file__).parent.parent          # hexmind/ -> repo root
EXAMPLE = REPO / "docs/examples/chains/doc-chain.toml"


def test_doc_chain_is_not_bundled():
    assert "doc-chain" not in list_chains()
    assert not (Path(relay.__file__).parent / "chains" / "doc-chain.toml").exists()


def test_the_example_is_present_and_well_formed():
    assert EXAMPLE.is_file(), f"the documented example is missing: {EXAMPLE}"
    data = tomllib.loads(EXAMPLE.read_text())
    assert data["name"] == "doc-chain"
    assert [s["name"] for s in data["stages"]] == ["plan", "draft", "verify", "review"]
    assert [s["domain"] for s in data["stages"]] == ["docs", "docs", "shell", "review"]
    # every stage imports an agent rather than inlining instructions, and each says which
    assert all(s.get("from") for s in data["stages"])
    assert all(not s.get("instructions") for s in data["stages"])


def test_copying_the_example_into_the_user_chain_dir_makes_it_available(tmp_path, monkeypatch):
    monkeypatch.setattr(relay, "CHAIN_DIRS", [tmp_path, Path(relay.__file__).parent / "chains"])
    (tmp_path / "doc-chain.toml").write_text(EXAMPLE.read_text())

    assert "doc-chain" in list_chains()


def test_a_chain_whose_agents_are_missing_is_reported_not_skipped(tmp_path, monkeypatch):
    """`/relay doc-chain` must fail with the missing path, not run stages with empty instructions."""
    monkeypatch.setenv("HOME", str(tmp_path))  # "~" now has no doc-chain checkout
    chain = tmp_path / "doc-chain.toml"
    chain.write_text(EXAMPLE.read_text())

    with pytest.raises(BrokenChain) as err:
        load_chain(chain)

    assert "missing ~/Projects/doc-chain" in str(err.value)
    # a path-shaped reference is not searched for by name, so no "looked in ..." hint is added
    assert "looked for a file named this" not in str(err.value)

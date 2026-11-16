"""Regression test for the `models.publish()` discipline (audit Task 2).

`REGISTRY`, `ROSTER`, `TEXT_ONLY`, `OPT_IN`, `DIRECT_CMDS`, `LOCAL_MODELS` and `AGENT_COLOR` are
all computed once at import time and held by name in other modules. A model promoted mid-session
must flow through `publish()`, which mutates all six derived globals *in place*. Direct mutation of
`REGISTRY.models` alone must leave them stale — otherwise a model can appear in `/models` but raise
`KeyError: DIRECT_CMDS[name]` the first time a task routes to it.

This test asserts exactly that: direct registry mutation does not republish; only `publish()`
does.
"""

from __future__ import annotations

from hexmind import models
from hexmind.core import REGISTRY
import hexmind.core as core
from hexmind import backends, tui


def _snapshot():
    """Capture the current state of all six import-time-derived globals."""
    return {
        "ROSTER": dict(core.ROSTER),
        "TEXT_ONLY": set(core.TEXT_ONLY),
        "OPT_IN": set(core.OPT_IN),
        "DIRECT_CMDS": dict(backends.DIRECT_CMDS),
        "LOCAL_MODELS": dict(backends.LOCAL_MODELS),
        "AGENT_COLOR": dict(tui.AGENT_COLOR),
    }


def _add_fake_member():
    """Add a throwaway member directly to REGISTRY.models (bypassing publish)."""
    fake = models.Model(
        name="zz-publish-test-member",
        label="ZZ Publish Test",
        best_at="testing the publish discipline",
        cli="opencode",
        verify="path",
        tier="cloud",
        domains=("tests",),
        model="opencode/zz-publish-test",
        weight=1,
        color="magenta",
    )
    REGISTRY.models["zz-publish-test-member"] = fake
    return fake


def _remove_fake_member():
    REGISTRY.models.pop("zz-publish-test-member", None)


def test_direct_registry_mutation_leaves_derived_globals_stale():
    before = _snapshot()

    _add_fake_member()
    try:
        # All six derived globals must be unchanged until publish() is called.
        assert _snapshot() == before, "direct mutation must not republish derived globals"
        assert "zz-publish-test-member" not in backends.DIRECT_CMDS
        assert "zz-publish-test-member" not in core.ROSTER
    finally:
        _remove_fake_member()

    # Restore the pre-test baseline so later tests see a clean registry.
    models.publish(REGISTRY)


def test_publish_republishes_from_disk_not_from_memory():
    """`publish()` re-reads `models.toml` from disk, so in-memory-only additions to
    `REGISTRY.models` are dropped. After `publish()`, derived globals reflect disk state."""
    before = _snapshot()

    _add_fake_member()
    try:
        # Direct mutation alone does not republish (verified in the previous test).
        assert _snapshot() == before

        # publish() reloads from disk: the in-memory fake member is not on disk, so derived
        # globals are restored to match disk state (the fake member is gone).
        models.publish(REGISTRY)

        after = _snapshot()
        assert after == before, "publish() restored disk state, not the in-memory mutation"
        assert "zz-publish-test-member" not in backends.DIRECT_CMDS
        assert "zz-publish-test-member" not in core.ROSTER
    finally:
        _remove_fake_member()

    # Restore the pre-test baseline.
    models.publish(REGISTRY)

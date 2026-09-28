"""The suite's own guardrails, asserted.

The two hazards these cover are invisible when they bite: a test that writes the developer's real
`~/.config/hexmind/models.toml` passes, and then a different test file fails because the registry
changed. And a leaked instance-level `available` makes a later patch silently do nothing. Both are
cheap to assert and expensive to debug.
"""
from pathlib import Path

from hexmind import config, models, relay
from hexmind.core import REGISTRY


def test_every_writable_user_path_points_at_a_temporary_directory():
    """Not "no test writes there" — that is what a leak looks like from the outside. The paths
    themselves are redirected, so there is nowhere real to write."""
    home = Path.home()
    for module, name in [(models, "USER"), (models, "CATALOGUE"), (config, "PATH")]:
        path = getattr(module, name)
        assert home not in Path(path).parents, f"{module.__name__}.{name} still points into the real home: {path}"
    # The bundled chain and agent directories must still resolve, or every test of `/chains` and
    # `from =` would be looking at an empty world and pass for the wrong reason.
    assert any("Projects" in str(d) or "site-packages" in str(d) for d in relay.CHAIN_DIRS[1:]), \
        relay.CHAIN_DIRS
    assert relay.CHAIN_DIRS[0] != Path.home() / ".config" / "hexmind" / "chains"


def test_aaa_leak_an_instance_level_available_patch():
    """Leaves a real leak behind, on purpose. `monkeypatch` is deliberately not used: this is a
    stand-in for the many existing call sites that patch the instance, and the point is the state
    they leave, not how it was set. The autouse `_no_leaked_registry_shadow` fixture is what has to
    clean it up — the next test is the assertion."""
    REGISTRY.available = lambda: ["leaked"]
    assert REGISTRY.available() == ["leaked"]


def test_and_the_autouse_fixture_cleared_it_before_this_test_ran(monkeypatch):
    """Order-dependent on the test above, which is the point: this is a cleanup fixture and the only
    way to observe it is from the next test. Run alone it passes trivially.

    Without the cleanup, the bound method monkeypatch-style undo would have left in the instance
    `__dict__` would still be there, and the class-level patch below would be silently ignored —
    a test that pins availability by patching the class would quietly stop working and no assertion
    anywhere would say so."""
    assert "available" not in REGISTRY.__dict__, \
        "the autouse cleanup did not run: an instance-level patch is shadowing the class"

    calls = []

    def _available(self):
        calls.append(1)
        return ["pinned"]

    monkeypatch.setattr(models.Registry, "available", _available, raising=False)
    assert REGISTRY.available() == ["pinned"], "the class patch was shadowed"
    assert calls, "and the real method was not the one answering"


def test_the_supported_way_to_pin_availability_is_the_fixture(available_models):
    available_models(["claude", "agy"])
    assert REGISTRY.available() == ["claude", "agy"]

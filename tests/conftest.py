"""Session-wide guardrails for the test suite.

Two hazards, both of which cost real debugging time, so they are fixed once here rather than left
to every test that happens to touch a user path or the registry.

**1. Tests must never write to the real home directory.** `hexmind` persists to four places under
`~`: the user model overlay, the scan catalogue, the nickname config, and the audit stats. A test
that writes a real profile does not fail — it changes the registry for every test that runs after
it, in a way that looks like an unrelated assertion. This happened: a fixture whose `monkeypatch`
override was undone *after* the fixture's own restore left a fictional model in the developer's
`~/.config/hexmind/models.toml`, and it broke a test in a different file.

Rather than relying on each test to redirect its paths — which is a fixture-ordering trap, because
`monkeypatch` is undone after the fixture that requested it — every writable user path is pointed
at a temporary directory for the whole session and put back at the end.

**2. `monkeypatch.setattr(REGISTRY, "available", ...)` leaves a permanent shadow.** Patching a
method on an *instance* stores the lambda in the instance `__dict__`; undoing it stores the bound
method it replaced, rather than deleting the attribute. That copy then beats any later *class*-level
patch for the rest of the session, so a test that patches the class is silently ignored if a test
that patches the instance ran first. Clearing the shadow before each test makes the trap
unreachable, and `available_models` below is the supported way to do it.
"""
from __future__ import annotations

import pytest

from hexmind import config, models
from hexmind.core import REGISTRY


@pytest.fixture(scope="session", autouse=True)
def _hermetic_home(tmp_path_factory):
    """Point every writable user path at a temp directory for the whole session."""
    home = tmp_path_factory.mktemp("hexmind-home")
    config_home = home / ".config" / "hexmind"
    data_home = home / ".local" / "share" / "hexmind"
    config_home.mkdir(parents=True)
    data_home.mkdir(parents=True)

    from hexmind import relay

    saved = [
        (models, "USER", models.USER),
        (models, "CATALOGUE", models.CATALOGUE),
        (config, "PATH", config.PATH),
        (relay, "CHAIN_DIRS", list(relay.CHAIN_DIRS)),
        (relay, "AGENT_DIRS", list(relay.AGENT_DIRS)),
    ]
    models.USER = config_home / "models.toml"
    models.CATALOGUE = data_home / "catalogue.json"
    config.PATH = config_home / "config.toml"
    # Only the user directory is redirected; the bundled chains/agents must still resolve, or every
    # test of `/chains` and `from =` would see an empty world.
    relay.CHAIN_DIRS = [config_home / "chains", *relay.CHAIN_DIRS[1:]]
    relay.AGENT_DIRS = [config_home / "agents", *relay.AGENT_DIRS[1:]]
    try:
        yield home
    finally:
        for module, name, value in saved:
            setattr(module, name, value)


@pytest.fixture(autouse=True)
def _no_leaked_registry_shadow():
    """Drop any instance-level `available` before each test.

    See the module docstring: `monkeypatch.setattr` on an instance leaves the replaced bound method
    in the instance `__dict__`, and that copy shadows the class attribute for good."""
    REGISTRY.__dict__.pop("available", None)
    yield
    REGISTRY.__dict__.pop("available", None)


@pytest.fixture
def available_models():
    """Pin what `Registry.available()` reports, and return the fixture so a test can change it.

    ```python
    def test_x(available_models):
        available_models(["claude", "agy"])
    ```

    Written to the instance, because that is what every other caller in the suite does, and cleaned
    up afterwards by `_no_leaked_registry_shadow` rather than by monkeypatch's undo — which is the
    half of it that leaves the shadow behind.
    """
    def set_(names: list[str]) -> None:
        REGISTRY.available = lambda: list(names)  # type: ignore[method-assign]
    return set_

"""Agent prerequisite diagnostics."""
from __future__ import annotations

from hexmind.qt import health


def test_health_scanner_reports_each_registry_model(monkeypatch):
    monkeypatch.setattr(health.shutil, "which", lambda cli: "/usr/bin/" + cli if cli == "claude" else None)
    monkeypatch.setattr(
        health.subprocess,
        "run",
        lambda *args, **kwargs: health.subprocess.CompletedProcess(args[0], 0),
    )

    results = health.HealthScanner().scan()

    assert {result.name for result in results} == set(health.REGISTRY.models)
    claude = next(result for result in results if result.name == "claude")
    assert claude.available is True
    assert claude.credential_checked is True
    assert claude.credential_status == "verified"
    assert claude.latency_ms >= 0


def test_health_scanner_skips_latency_for_unavailable_or_non_path_models(monkeypatch):
    monkeypatch.setattr(health.shutil, "which", lambda _: None)
    called = []
    monkeypatch.setattr(health.subprocess, "run", lambda *args, **kwargs: called.append(args))

    results = health.HealthScanner().scan()

    assert all(result.latency_ms == -1 for result in results)
    assert called == []


def test_health_scanner_does_not_guess_auth_checks_for_unknown_cli(monkeypatch):
    model = health.Model(
        name="unknown",
        label="Unknown",
        best_at="testing",
        cli="unknown-cli",
        verify="path",
        tier="cloud",
    )
    monkeypatch.setattr(health, "REGISTRY", type("RegistryStub", (), {"models": {"unknown": model}})())
    monkeypatch.setattr(health.shutil, "which", lambda _: "/usr/bin/unknown-cli")
    calls = []
    monkeypatch.setattr(
        health.subprocess,
        "run",
        lambda *args, **kwargs: calls.append((args, kwargs))
        or health.subprocess.CompletedProcess(args[0], 0),
    )

    result = health.HealthScanner().scan()[0]

    assert result.credential_ready is True
    assert result.credential_checked is False
    assert result.credential_status == "not-checked"
    assert calls == [((["unknown-cli", "--version"],), {
        "capture_output": True,
        "text": True,
        "timeout": 5,
        "check": False,
    })]


def test_health_scanner_reports_failed_allowlisted_auth_check(monkeypatch):
    model = health.Model(
        name="codex",
        label="Codex",
        best_at="testing",
        cli="codex",
        verify="path",
        tier="cloud",
    )
    monkeypatch.setattr(health, "REGISTRY", type("RegistryStub", (), {"models": {"codex": model}})())
    monkeypatch.setattr(health.shutil, "which", lambda _: "/usr/bin/codex")

    def run(args, **kwargs):
        return health.subprocess.CompletedProcess(args, 1, stderr="not logged in")

    monkeypatch.setattr(health.subprocess, "run", run)

    result = health.HealthScanner().scan()[0]

    assert result.available is True
    assert result.credential_ready is False
    assert result.credential_checked is True
    assert result.credential_status == "failed"


def test_health_scanner_reports_declared_environment_readiness(monkeypatch):
    model = health.Model(
        name="jules",
        label="Jules",
        best_at="testing",
        cli="jules",
        verify="env",
        tier="cloud",
        env="JULES_API_KEY",
    )
    monkeypatch.setattr(health, "REGISTRY", type("RegistryStub", (), {"models": {"jules": model}})())
    monkeypatch.delenv("JULES_API_KEY", raising=False)

    missing = health.HealthScanner().scan()[0]
    assert missing.credential_ready is False
    assert missing.credential_checked is True
    assert missing.credential_status == "missing"

    monkeypatch.setenv("JULES_API_KEY", "configured-for-test")
    ready = health.HealthScanner().scan()[0]
    assert ready.credential_ready is True
    assert ready.credential_status == "declared"

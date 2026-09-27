"""The CLI entry point: argument handling, member resolution, and headless error reporting."""
import sys

import pytest

from hexmind import __main__ as cli


class BoomBackend:
    """A backend whose every call fails the way a blocked or out-of-quota member does."""

    def __init__(self, cwd, timeout=1800):
        self.cwd = cwd

    async def run(self, agent, prompt, cwd=None, schema=None):
        raise RuntimeError("claude agent hexmind-abc is waiting for approval. Open it once yourself.")


def run_main(monkeypatch, argv, tmp_path, **env):
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(sys, "argv", ["hexmind", "--cwd", str(tmp_path), *argv])
    monkeypatch.setattr(cli, "DirectBackend", BoomBackend)
    monkeypatch.setattr("hexmind.backends.available", lambda members: ["claude"])
    return cli.main()


def test_once_reports_a_failed_agent_cleanly_and_exits_nonzero(monkeypatch, tmp_path, capsys):
    with pytest.raises(SystemExit) as err:
        run_main(monkeypatch, ["--once", "hello"], tmp_path)

    assert err.value.code == 1
    captured = capsys.readouterr()
    assert "hexmind: claude agent hexmind-abc is waiting for approval" in captured.err
    # the point of the fix: no traceback for an expected failure
    assert "Traceback" not in captured.err
    assert "RuntimeError" not in captured.err


def test_once_still_gives_the_traceback_when_asked(monkeypatch, tmp_path):
    monkeypatch.setenv("HEXMIND_TRACEBACK", "1")
    with pytest.raises(RuntimeError, match="waiting for approval"):
        run_main(monkeypatch, ["--once", "hello"], tmp_path)


def test_once_exits_130_on_interrupt(monkeypatch, tmp_path):
    class Interrupting(BoomBackend):
        async def run(self, *a, **k):
            raise KeyboardInterrupt

    monkeypatch.setattr(sys, "argv", ["hexmind", "--cwd", str(tmp_path), "--once", "hi"])
    monkeypatch.setattr(cli, "DirectBackend", Interrupting)
    monkeypatch.setattr("hexmind.backends.available", lambda members: ["claude"])
    with pytest.raises(SystemExit) as err:
        cli.main()
    assert err.value.code == 130


def test_hcom_notice_lists_the_opencode_models_it_cannot_drive(monkeypatch, tmp_path, capsys):
    # __main__ binds `available` into its own namespace at import, so patch it there.
    monkeypatch.setattr(cli, "available", lambda members: ["claude", "opencode", "opencode-longcat", "opencode-muse"])
    monkeypatch.setattr(sys, "argv", ["hexmind", "--backend", "hcom", "--cwd", str(tmp_path), "--once", "hi"])
    monkeypatch.setattr(cli, "Orchestrator", lambda *a, **k: type("O", (), {"handle": _noop})())

    cli.main()  # the fake orchestrator succeeds; we only care about the notice printed first

    err = capsys.readouterr().err
    assert "cannot drive 2 opencode model(s)" in err
    assert "opencode-longcat, opencode-muse" in err
    assert "--backend direct" in err
    assert "hcom picks a tool, not a model" in err


def test_hcom_notice_names_every_excluded_model_when_all_are_present(monkeypatch, tmp_path, capsys):
    from hexmind.backends import HCOM_EXCLUDED

    monkeypatch.setattr(cli, "available", lambda members: ["claude", "opencode", *sorted(HCOM_EXCLUDED)])
    monkeypatch.setattr(sys, "argv", ["hexmind", "--backend", "hcom", "--cwd", str(tmp_path), "--once", "hi"])
    monkeypatch.setattr(cli, "Orchestrator", lambda *a, **k: type("O", (), {"handle": _noop})())

    cli.main()

    err = capsys.readouterr().err
    assert f"cannot drive {len(HCOM_EXCLUDED)} opencode model(s)" in err
    for name in HCOM_EXCLUDED:
        assert name in err


def test_no_hcom_notice_for_the_direct_backend(monkeypatch, tmp_path, capsys):
    with pytest.raises(SystemExit):
        run_main(monkeypatch, ["--once", "hi"], tmp_path)
    assert "cannot drive" not in capsys.readouterr().err


def test_text_only_lead_is_refused_before_anything_starts(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr("hexmind.backends.available", lambda members: ["claude", "qwen"])
    monkeypatch.setattr(sys, "argv", ["hexmind", "--cwd", str(tmp_path), "--lead", "qwen", "--once", "hi"])
    with pytest.raises(SystemExit) as err:
        cli.main()
    assert "text-only" in str(err.value)


async def _noop(self, request):
    return ""


def test_bundled_model_registry_ships_with_the_package():
    """A non-editable install must carry models.toml, or the app cannot start at all."""
    import tomllib
    from pathlib import Path

    import hexmind

    pyproject = Path(hexmind.__file__).parent.parent / "pyproject.toml"
    data = tomllib.loads(pyproject.read_text())
    patterns = data["tool"]["setuptools"]["package-data"]["hexmind"]
    assert any("models.toml" in p for p in patterns), f"models.toml not packaged: {patterns}"
    assert (Path(hexmind.__file__).parent / "models.toml").is_file()

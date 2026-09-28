"""The CLI entry point: argument handling, member resolution, and headless error reporting."""
import json
import sys

import pytest

from hexmind import __main__ as cli


class BoomBackend:
    """A backend whose every call fails the way a blocked or out-of-quota member does."""

    def __init__(self, cwd, timeout=1800):
        self.cwd = cwd

    async def run(self, agent, prompt, cwd=None, schema=None):
        raise RuntimeError("claude agent hexmind-abc is waiting for approval. Open it once yourself.")


class WorkerFailsBackend:
    """The lead plans normally; the worker then dies with a multi-line diagnosis."""

    def __init__(self, cwd, timeout=1800):
        self.cwd = cwd

    async def run(self, agent, prompt, cwd=None, schema=None):
        if "Answer ONLY with a JSON object" in prompt:
            return json.dumps({"reply": "on it", "tasks": [
                {"id": "a", "agent": "claude", "title": "write the tests"}]})
        if "Write the final answer" in prompt:
            return "summary"
        raise RuntimeError("claude: resuming session 4f2a in /tmp instead of the room hangs forever\n"
                           "run it in the room's folder")


def run_main(monkeypatch, argv, tmp_path, **env):
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(sys, "argv", ["hexmind", "--cwd", str(tmp_path), *argv])
    monkeypatch.setattr(cli, "DirectBackend", BoomBackend)
    monkeypatch.setattr(cli, "available", lambda members: ["nemotron-ultra", "claude"])
    return cli.main()


def test_once_reports_a_failed_agent_cleanly_and_exits_nonzero(monkeypatch, tmp_path, capsys):
    with pytest.raises(SystemExit) as err:
        run_main(monkeypatch, ["--lead", "claude", "--once", "hello"], tmp_path)

    assert err.value.code == 1
    captured = capsys.readouterr()
    assert "hexmind: claude agent hexmind-abc is waiting for approval" in captured.err
    # the point of the fix: no traceback for an expected failure
    assert "Traceback" not in captured.err
    assert "RuntimeError" not in captured.err


def test_once_prints_why_a_task_failed(monkeypatch, tmp_path, capsys):
    """The TUI shows the first line of a failed task's output; headless printed only
    id/agent/status/title, so a script calling hexmind --once could see `failed` with no reason."""
    monkeypatch.setattr(sys, "argv", ["hexmind", "--cwd", str(tmp_path), "--lead", "claude", "--once", "hi"])
    monkeypatch.setattr(cli, "DirectBackend", WorkerFailsBackend)
    monkeypatch.setattr(cli, "available", lambda members: ["nemotron-ultra", "claude"])

    cli.main()

    out = capsys.readouterr().out
    failed = [line for line in out.splitlines() if "failed" in line]
    assert len(failed) == 1, out
    assert failed[0].split() == ["a", "claude", "failed", "write", "the", "tests"]  # the status line
    assert "resuming session 4f2a in /tmp instead of the room hangs forever" in out
    assert "run it in the room's folder" not in out  # only the first line, as the TUI shows


def test_once_still_gives_the_traceback_when_asked(monkeypatch, tmp_path):
    monkeypatch.setenv("HEXMIND_TRACEBACK", "1")
    with pytest.raises(RuntimeError, match="waiting for approval"):
        run_main(monkeypatch, ["--lead", "claude", "--once", "hello"], tmp_path)


def test_once_exits_130_on_interrupt(monkeypatch, tmp_path):
    class Interrupting(BoomBackend):
        async def run(self, *a, **k):
            raise KeyboardInterrupt

    monkeypatch.setattr(sys, "argv", ["hexmind", "--cwd", str(tmp_path), "--lead", "claude", "--once", "hi"])
    monkeypatch.setattr(cli, "DirectBackend", Interrupting)
    monkeypatch.setattr(cli, "available", lambda members: ["nemotron-ultra", "claude"])
    with pytest.raises(SystemExit) as err:
        cli.main()
    assert err.value.code == 130


def test_hcom_notice_lists_the_opencode_models_it_cannot_drive(monkeypatch, tmp_path, capsys):
    # __main__ binds `available` into its own namespace at import, so patch it there.
    monkeypatch.setattr(cli, "available", lambda members: ["claude", "nemotron-lightning", "longcat-preview", "muse-spark"])
    monkeypatch.setattr(sys, "argv", ["hexmind", "--backend", "hcom", "--lead", "claude", "--cwd", str(tmp_path), "--once", "hi"])
    monkeypatch.setattr(cli, "Orchestrator", lambda *a, **k: type("O", (), {"handle": _noop})())

    cli.main()  # the fake orchestrator succeeds; we only care about the notice printed first

    err = capsys.readouterr().err
    assert "cannot drive 2 opencode model(s)" in err
    assert "longcat-preview, muse-spark" in err
    assert "--backend direct" in err
    assert "hcom picks a tool, not a model" in err


def test_hcom_notice_names_every_excluded_model_when_all_are_present(monkeypatch, tmp_path, capsys):
    from hexmind.backends import HCOM_EXCLUDED

    monkeypatch.setattr(cli, "available", lambda members: ["claude", "nemotron-lightning", *sorted(HCOM_EXCLUDED)])
    monkeypatch.setattr(sys, "argv", ["hexmind", "--backend", "hcom", "--cwd", str(tmp_path), "--lead", "claude", "--once", "hi"])
    monkeypatch.setattr(cli, "Orchestrator", lambda *a, **k: type("O", (), {"handle": _noop})())

    cli.main()

    err = capsys.readouterr().err
    assert f"cannot drive {len(HCOM_EXCLUDED)} opencode model(s)" in err
    for name in HCOM_EXCLUDED:
        assert name in err


def test_no_hcom_notice_for_the_direct_backend(monkeypatch, tmp_path, capsys):
    with pytest.raises(SystemExit):
        run_main(monkeypatch, ["--lead", "claude", "--once", "hi"], tmp_path)
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


def test_default_lead_is_opencode_ultra():
    """Default leader must be nemotron-ultra (Nemotron 3 Ultra) per OPENCODE-TEAM-PLAN."""
    from hexmind.core import Orchestrator
    from hexmind.server import HexmindServer

    orch = Orchestrator(None, ["nemotron-ultra"])
    assert orch.lead == "nemotron-ultra"

    server = HexmindServer(cwd=".")
    assert server.lead == "nemotron-ultra"


# ---------- leader selection: no default, and headless surfaces must say so ----------

def test_the_tui_path_does_not_require_a_lead_at_all(monkeypatch, tmp_path):
    """No default lead, so the TUI starts with lead=None and the startup picker sets it. If a
    default were reintroduced this would still pass, so also assert the value the app receives."""
    import hexmind.__main__ as cli
    import hexmind.tui as tui_mod

    seen = {}

    class FakeApp:
        def __init__(self, backend, members, lead, *a, **k):
            seen["lead"] = lead
            seen["members"] = members
            self.orch = type("O", (), {"approve_plans": False})()

        def run(self):
            seen["ran"] = True

    monkeypatch.setattr(tui_mod, "HexmindApp", FakeApp)
    monkeypatch.setattr(sys, "argv", ["hexmind", "--cwd", str(tmp_path)])
    monkeypatch.setattr("hexmind.backends.available", lambda m: ["claude", "agy"])

    cli.main()

    assert seen.get("ran") is True, "the TUI must start without a lead being supplied"
    assert seen["lead"] is None, "the app must receive no default lead; the picker chooses one"
    assert "claude" in seen["members"]


def test_once_requires_an_explicit_lead(monkeypatch, tmp_path):
    import hexmind.__main__ as cli

    monkeypatch.setattr(sys, "argv", ["hexmind", "--cwd", str(tmp_path), "--once", "hi"])
    monkeypatch.setattr("hexmind.backends.available", lambda m: ["claude", "agy"])
    with pytest.raises(SystemExit) as err:
        cli.main()
    assert "--lead is required" in str(err.value)
    assert "claude" in str(err.value), "the error must list what is installed so the fix is obvious"


def test_serve_requires_an_explicit_lead(monkeypatch, tmp_path):
    import hexmind.__main__ as cli

    called = []
    monkeypatch.setattr(sys, "argv", ["hexmind", "--cwd", str(tmp_path), "--serve"])
    monkeypatch.setattr("hexmind.backends.available", lambda m: ["claude"])
    monkeypatch.setattr("hexmind.server", type("S", (), {"run_server": staticmethod(lambda **k: called.append(k))}),
                        raising=False)
    monkeypatch.setattr("hexmind.server", type("S", (), {"run_server": staticmethod(lambda **k: called.append(k))}))
    with pytest.raises(SystemExit) as err:
        cli.main()
    assert "--lead is required for --serve" in str(err.value)
    assert not called


def test_no_members_at_all_is_a_clear_error(monkeypatch, tmp_path):
    """Previously the message was 'lead is not available (installed members: none)', which pointed
    at the wrong thing entirely."""
    import hexmind.__main__ as cli

    monkeypatch.setattr(sys, "argv", ["hexmind", "--cwd", str(tmp_path), "--once", "hi"])
    monkeypatch.setattr(cli, "available", lambda m: [])
    with pytest.raises(SystemExit) as err:
        cli.main()
    assert "No team members available" in str(err.value)
    assert "PATH" in str(err.value)


# ---------- --timeout reaches the backend ----------

def test_the_timeout_flag_reaches_the_backend(monkeypatch, tmp_path):
    """A relay stage doing a real TDD cycle can outlast the 1800s default, and --timeout exists for
    exactly that. Nothing proved the parsed value got as far as the backend that enforces it, so a
    renamed or dropped keyword would have kept the help text and silently left the flag doing
    nothing. Assert the value the backend is built with, with and without the flag."""
    seen = {}

    class RecordingBackend:
        def __init__(self, cwd, timeout=1800):
            seen["timeout"], self.cwd = timeout, cwd

        async def run(self, agent, prompt, cwd=None, schema=None):
            if "Answer ONLY with a JSON object" in prompt:
                return json.dumps({"reply": "on it", "tasks": []})
            return "done"

    monkeypatch.setattr(cli, "DirectBackend", RecordingBackend)
    monkeypatch.setattr(cli, "available", lambda members: ["claude"])

    monkeypatch.setattr(sys, "argv", ["hexmind", "--cwd", str(tmp_path), "--lead", "claude", "--once", "hi"])
    cli.main()
    assert seen["timeout"] == 1800, "the documented default must still be what the backend gets"

    monkeypatch.setattr(sys, "argv", ["hexmind", "--cwd", str(tmp_path), "--lead", "claude",
                                      "--timeout", "7200", "--once", "hi"])
    cli.main()
    assert seen["timeout"] == 7200


def test_text_only_lead_error_lists_only_models_that_can_lead(monkeypatch, tmp_path):
    import hexmind.__main__ as cli

    monkeypatch.setattr(sys, "argv", ["hexmind", "--cwd", str(tmp_path), "--lead", "qwen",
                                      "--with", "qwen", "--once", "hi"])
    monkeypatch.setattr("hexmind.backends.available", lambda m: ["claude", "qwen"])
    with pytest.raises(SystemExit) as err:
        cli.main()
    assert "text-only" in str(err.value)
    assert "claude" in str(err.value) and "qwen" not in str(err.value).split("pick one of:")[1]


def test_serve_hands_the_timeout_to_the_backend_too(monkeypatch, tmp_path):
    """--serve built its backend inside HexmindServer and run_server took no timeout, so
    `hexmind --serve --timeout 60` was accepted by argparse and then quietly used 1800. The help
    text promises the flag applies to the agent, whichever surface you are on. The whole chain is
    exercised: argv -> main -> run_server -> HexmindServer -> backend, with only uvicorn stopped."""
    import types

    import hexmind.__main__ as cli
    from hexmind import server as server_mod

    seen = {}

    class RecordingBackend:
        def __init__(self, cwd, timeout=1800):
            seen["timeout"], self.cwd = timeout, cwd

        async def run(self, agent, prompt, cwd=None, schema=None):
            return ""

    monkeypatch.setattr(server_mod, "DirectBackend", RecordingBackend)
    monkeypatch.setattr(server_mod, "available", lambda members: ["claude"])
    monkeypatch.setattr("hexmind.__main__.available", lambda members: ["claude"])
    monkeypatch.setitem(sys.modules, "uvicorn", types.SimpleNamespace(run=lambda *a, **k: None))

    monkeypatch.setattr(sys, "argv", ["hexmind", "--cwd", str(tmp_path), "--lead", "claude",
                                      "--serve", "--timeout", "60"])
    cli.main()

    assert seen.get("timeout") == 60, f"--serve dropped the timeout: {seen}"


# ---------- the server extra is declared, and its absence is explained ----------

def test_serve_says_how_to_install_its_extra_instead_of_raising_a_traceback(monkeypatch, tmp_path):
    """`--serve` is documented in the README, and server.py imports fastapi and pydantic at module
    level while base `dependencies` declared only textual. So a clean install had a broken --serve
    that failed with a ModuleNotFoundError out of the argument parser. The dependencies are now an
    extra, and the path that finds them missing has to be helpful."""
    import builtins

    import hexmind.__main__ as cli

    real_import = builtins.__import__

    def blocked(name, *args, **kwargs):
        if name.split(".")[0] in ("fastapi", "uvicorn", "pydantic"):
            raise ImportError(f"No module named {name!r}")
        return real_import(name, *args, **kwargs)

    # An earlier test in this file imports hexmind.server, so without this the module is already in
    # sys.modules and the guarded import would never run — the test would pass for the wrong reason.
    monkeypatch.delitem(sys.modules, "hexmind.server", raising=False)
    monkeypatch.setattr(builtins, "__import__", blocked)
    monkeypatch.setattr("hexmind.__main__.available", lambda members: ["claude"])
    monkeypatch.setattr(sys, "argv", ["hexmind", "--cwd", str(tmp_path), "--lead", "claude", "--serve"])

    with pytest.raises(SystemExit) as err:
        cli.main()

    message = str(err.value)
    assert "--serve needs the server extra" in message
    assert "hexmind[server]" in message, "the message must say exactly what to install"
    assert "Traceback" not in message


def test_the_server_extra_is_actually_declared():
    """A guard against the same gap coming back: the extra has to name what server.py imports."""
    import tomllib
    from pathlib import Path

    pyproject = tomllib.loads((Path(__file__).resolve().parent.parent / "pyproject.toml").read_text())
    extras = pyproject["project"]["optional-dependencies"]
    assert "server" in extras, f"no server extra: {sorted(extras)}"
    declared = " ".join(extras["server"])
    assert "fastapi" in declared, extras["server"]
    assert "uvicorn" in declared, extras["server"]

    # and every third-party module server.py imports at module level is covered by some extra
    import re
    source = (Path(__file__).resolve().parent.parent / "hexmind" / "server.py").read_text()
    for module in ("fastapi", "pydantic", "uvicorn"):
        # `from fastapi import ...` as well as `import uvicorn`, wherever it appears in the file
        assert re.search(rf"^\s*(import {module}\b|from {module}\b)", source, re.MULTILINE), \
            f"{module} is no longer imported by server.py; trim the extra"
        assert module in declared, f"{module} is imported by server.py and named by no extra"


def test_serve_refuses_a_non_loopback_host_without_a_token(monkeypatch):
    """The --token help promised a token was required off loopback; the server only printed a
    warning and served unauthenticated on every interface."""
    import types

    from hexmind import server as server_mod

    monkeypatch.delenv("HEXMIND_TOKEN", raising=False)
    monkeypatch.setitem(sys.modules, "uvicorn", types.SimpleNamespace(run=lambda *a, **k: None))
    with pytest.raises(SystemExit, match="without a token"):
        server_mod.run_server(cwd=".", host="0.0.0.0")

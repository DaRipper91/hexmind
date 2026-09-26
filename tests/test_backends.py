import asyncio
import json
import os
import sys
import types

import pytest

from hexmind.backends import DIRECT_CMDS, DirectBackend, HcomBackend, available


class FakePipe:
    def __init__(self, data=b""):
        self.data = data
        self.written = b""

    async def read(self, size):
        data, self.data = self.data[:size], self.data[size:]
        return data

    def write(self, data):
        self.written += data

    async def drain(self):
        pass

    def close(self):
        pass


class FakeProcess:
    def __init__(self, args, stdout="answer", stderr="", returncode=0, timeout=False):
        self.args = args
        self.stdout = stdout.encode()
        self.stderr = stderr.encode()
        self.returncode = returncode
        self.timeout = timeout
        self.killed = False
        self.waited = False
        self.input = None
        self.pid = 4242
        self.stdin = FakePipe()
        if "--output-last-message" in args:
            path = args[args.index("--output-last-message") + 1]
            with open(path, "w") as f:
                f.write("answer")
        self.stdout = FakePipe((json.dumps({"event": "result", "result": {"response": "answer"}})
                                + "\n").encode() if "--input-format" in args else stdout.encode())
        self.stderr = FakePipe(stderr.encode())

    async def wait(self):
        if self.timeout and not self.killed:
            await asyncio.Event().wait()
        self.waited = True
        return self.returncode

    def kill(self):
        self.killed = True


@pytest.mark.parametrize("agent", [a for a in DIRECT_CMDS if a != "kimi"])  # kimi: see test below
def test_direct_backend_sends_prompt_over_stdin(monkeypatch, tmp_path, agent):
    prompt = "x" * 200_000
    proc = None

    async def create(*args, **kwargs):
        nonlocal proc
        proc = FakeProcess(args)
        return proc

    monkeypatch.setattr(asyncio, "create_subprocess_exec", create)
    assert asyncio.run(DirectBackend(str(tmp_path)).run(agent, prompt)) == "answer"
    assert "x" * 100 not in proc.args
    assert proc.stdin.written
    if agent == "agy":
        assert json.loads(proc.stdin.written)["message"]["content"] == prompt
    else:
        assert proc.stdin.written == prompt.encode()


def test_kimi_receives_prompt_as_arg_not_stdin(monkeypatch, tmp_path):
    """kimi's -p has no stdin-driven mode, so (unlike every other member) its prompt goes on argv
    and stdin is left empty."""
    proc = None

    async def create(*args, **kwargs):
        nonlocal proc
        proc = FakeProcess(args, stdout=json.dumps({"role": "assistant", "content": "answer"}) + "\n")
        return proc

    monkeypatch.setattr(asyncio, "create_subprocess_exec", create)
    assert asyncio.run(DirectBackend(str(tmp_path)).run("kimi", "prompt text")) == "answer"
    assert "prompt text" in proc.args
    assert proc.input == b""


def test_timeout_kills_and_waits_for_child(monkeypatch, tmp_path):
    proc = FakeProcess((), timeout=True)

    async def create(*args, **kwargs):
        return proc

    monkeypatch.setattr(asyncio, "create_subprocess_exec", create)
    monkeypatch.setattr("hexmind.backends._signal_group", lambda pid, sig: setattr(proc, "killed", True))
    with pytest.raises(RuntimeError, match="claude timed out"):
        asyncio.run(DirectBackend(str(tmp_path), timeout=0.01).run("claude", "prompt"))
    assert proc.killed and proc.waited


@pytest.mark.parametrize("stdout,stderr,expected", [
    ("useful stdout", "", "useful stdout"),
    ("ignored stdout", "useful stderr", "useful stderr"),
])
def test_nonzero_exit_uses_stderr_or_stdout(monkeypatch, tmp_path, stdout, stderr, expected):
    proc = FakeProcess((), stdout=stdout, stderr=stderr, returncode=2)

    async def create(*args, **kwargs):
        return proc

    monkeypatch.setattr(asyncio, "create_subprocess_exec", create)
    with pytest.raises(RuntimeError, match=expected):
        asyncio.run(DirectBackend(str(tmp_path)).run("claude", "prompt"))


@pytest.mark.parametrize("agent,flag", [("claude", "--json-schema"), ("agy", "--json-schema"),
                                         ("codex", "--output-schema")])
def test_schema_uses_native_cli_flag(monkeypatch, tmp_path, agent, flag):
    schema = {"type": "object", "properties": {"ok": {"type": "boolean"}}}
    captured = {}

    async def create(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        if "--output-schema" in args:
            with open(args[args.index("--output-schema") + 1]) as f:
                captured["schema_file"] = json.load(f)
        return FakeProcess(args)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", create)
    assert asyncio.run(DirectBackend(str(tmp_path)).run(agent, "json please", schema=schema)) == "answer"
    args = list(captured["args"])
    assert flag in args
    value = args[args.index(flag) + 1]
    if agent == "codex":
        assert captured["schema_file"] == schema
    else:
        assert json.loads(value) == schema
    assert captured["kwargs"]["start_new_session"] is True


def test_jules_available_only_with_api_key(monkeypatch):
    monkeypatch.delenv("JULES_API_KEY", raising=False)
    assert available(["jules"]) == []
    monkeypatch.setenv("JULES_API_KEY", "test-key")
    assert available(["jules"]) == ["jules"]


def test_direct_and_hcom_route_jules_without_hcom(monkeypatch, tmp_path):
    calls = []

    async def run(prompt, cwd):
        calls.append((prompt, cwd))
        return "jules reply"

    monkeypatch.setitem(sys.modules, "hexmind.jules", types.SimpleNamespace(run=run))
    assert asyncio.run(DirectBackend(str(tmp_path)).run("jules", "prompt")) == "jules reply"
    assert asyncio.run(HcomBackend(str(tmp_path)).run("jules", "prompt")) == "jules reply"
    assert calls == [("prompt", str(tmp_path)), ("prompt", str(tmp_path))]

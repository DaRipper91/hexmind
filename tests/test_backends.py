import asyncio
import json
import os

import pytest

from hexmind.backends import DIRECT_CMDS, DirectBackend


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

    async def communicate(self, input=None):
        self.input = input
        if self.timeout:
            raise asyncio.TimeoutError
        if "--output-last-message" in self.args:
            path = self.args[self.args.index("--output-last-message") + 1]
            with open(path, "w") as f:
                f.write("answer")
        if "--input-format" in self.args:
            self.stdout = (json.dumps({"event": "result", "result": {"response": "answer"}}) + "\n").encode()
        return self.stdout, self.stderr

    async def wait(self):
        self.waited = True

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
    assert proc.input is not None
    if agent == "agy":
        assert json.loads(proc.input)["message"]["content"] == prompt
    else:
        assert proc.input == prompt.encode()


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
    with pytest.raises(RuntimeError, match="claude timed out"):
        asyncio.run(DirectBackend(str(tmp_path), timeout=1).run("claude", "prompt"))
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

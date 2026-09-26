"""qwen: local, text-only Ollama members that share one memory slot (see backends.run_local)."""
import asyncio
import json
from unittest import mock

import pytest

import hexmind.backends as backends
from hexmind.core import Orchestrator, TEXT_ONLY
from hexmind.relay import Chain, Stage, assign


@pytest.fixture(autouse=True)
def _reset_active_local():
    backends._active_local = None
    yield
    backends._active_local = None


def _capture():
    """A fake urlopen that records every request body it's called with."""
    calls = []

    class Resp:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return json.dumps({"response": "OK"}).encode()

    def fake_urlopen(req, timeout):
        calls.append(json.loads(req.data))
        return Resp()

    return calls, fake_urlopen


def test_direct_backend_calls_ollama_with_thinking_off():
    calls, fake_urlopen = _capture()
    with mock.patch.object(backends.urllib.request, "urlopen", fake_urlopen):
        out = asyncio.run(backends.DirectBackend(".").run("qwen", "hi"))
    assert out == "OK"
    assert calls == [{"model": "qwen2.5-coder:7b", "prompt": "hi", "stream": False, "think": False}]


def test_available_needs_the_model_pulled():
    with mock.patch.object(backends, "_ollama_models", return_value={"qwen2.5-coder:7b"}):
        assert "qwen" in backends.available(["qwen"])
    with mock.patch.object(backends, "_ollama_models", return_value=set()):
        assert backends.available(["qwen"]) == []


def test_switching_local_models_unloads_the_previous_one():
    calls, fake_urlopen = _capture()
    with mock.patch.object(backends.urllib.request, "urlopen", fake_urlopen):
        asyncio.run(backends.run_local("qwen", "hi", 5))
        asyncio.run(backends.run_local("qwen-large", "hi", 5))
    assert calls == [
        {"model": "qwen2.5-coder:7b", "prompt": "hi", "stream": False, "think": False},
        {"model": "qwen2.5-coder:7b", "prompt": "", "stream": False, "think": False, "keep_alive": 0},
        {"model": "qwen2.5-coder:latest", "prompt": "hi", "stream": False, "think": False},
    ]


def test_reusing_the_same_local_model_does_not_unload_it():
    calls, fake_urlopen = _capture()
    with mock.patch.object(backends.urllib.request, "urlopen", fake_urlopen):
        asyncio.run(backends.run_local("qwen", "one", 5))
        asyncio.run(backends.run_local("qwen", "two", 5))
    assert len(calls) == 2 and all("keep_alive" not in c for c in calls)


def test_unload_failure_does_not_block_the_switch():
    calls, fake_urlopen = _capture()

    def flaky(req, timeout):
        body = json.loads(req.data)
        if body.get("keep_alive") == 0:
            raise OSError("connection refused")
        return fake_urlopen(req, timeout)

    with mock.patch.object(backends.urllib.request, "urlopen", flaky):
        asyncio.run(backends.run_local("qwen", "hi", 5))
        out = asyncio.run(backends.run_local("qwen-large", "hi", 5))
    assert out == "OK" and calls[-1]["model"] == "qwen2.5-coder:latest"


class Fake:
    cwd = "."
    def __init__(self):
        self.calls = []
    async def run(self, agent, prompt, cwd=None):
        self.calls.append((agent, prompt))
        if "Answer ONLY with a JSON object" in prompt:
            return json.dumps({"reply": "ok", "tasks": [{"id": "t1", "agent": "qwen", "title": "summarize"}]})
        if "VERDICT" in prompt:
            return "VERDICT: PASS"
        return "done"


def test_text_only_member_is_audited_by_a_tool_user_never_audits(tmp_path):
    from hexmind.auditor import Stats
    b = Fake()
    orch = Orchestrator(b, ["claude", "qwen"], "claude", audit=True, stats=Stats(str(tmp_path / "s.json")))
    asyncio.run(orch.handle("go"))
    auditors = [a for a, p in b.calls if "VERDICT" in p]
    assert auditors == ["claude"] and "qwen" in TEXT_ONLY


def test_rotation_skips_text_only_members_in_relays(tmp_path):
    b = Fake()
    b.cwd = str(tmp_path)
    orch = Orchestrator(b, ["claude", "agy", "qwen"], "claude")
    with mock.patch("hexmind.relay.extract_json", return_value={"name": "c", "stages": [
            {"name": "a", "instructions": "x"}, {"name": "b", "instructions": "y"}, {"name": "c", "instructions": "z"}]}):
        asyncio.run(orch.handle("/relay do things -n 2 --workspace shared --end list"))
    workers = {a for a, p in b.calls if "Your task (" in p}
    assert workers == {"claude", "agy"}

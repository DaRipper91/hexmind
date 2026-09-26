"""qwen: a local, text-only Ollama member."""
import asyncio
import json
from unittest import mock

import hexmind.backends as backends
from hexmind.core import Orchestrator, TEXT_ONLY
from hexmind.relay import Chain, Stage, assign


def test_direct_backend_calls_ollama_with_thinking_off():
    sent = {}

    class Resp:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return json.dumps({"response": "OK"}).encode()

    def fake_urlopen(req, timeout):
        sent.update(json.loads(req.data))
        return Resp()

    with mock.patch.object(backends.urllib.request, "urlopen", fake_urlopen):
        out = asyncio.run(backends.DirectBackend(".").run("qwen", "hi"))
    assert out == "OK" and sent == {"model": "qwen3:4b", "prompt": "hi", "stream": False, "think": False}


def test_available_needs_the_model_pulled():
    with mock.patch.object(backends, "_ollama_models", return_value={"qwen3:4b"}):
        assert "qwen" in backends.available(["qwen"])
    with mock.patch.object(backends, "_ollama_models", return_value=set()):
        assert backends.available(["qwen"]) == []


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

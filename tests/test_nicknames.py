import asyncio

import hexmind.config as config
from hexmind.core import Orchestrator


class Echo:
    cwd = "."
    async def run(self, agent, prompt, cwd=None):
        return prompt


def test_nick_sets_persists_clears_and_reaches_lead(tmp_path, monkeypatch):
    path = str(tmp_path / "config.toml")
    monkeypatch.setattr(config, "PATH", path)
    monkeypatch.setattr(config.load_nicknames, "__defaults__", (path,))
    monkeypatch.setattr(config.save_nicknames, "__defaults__", (path,))
    orch = Orchestrator(Echo(), ["claude", "agy"], "claude")
    asyncio.run(orch.handle('/nick agy "Big G"'))
    assert config.load_nicknames(path) == {"agy": "Big G"}
    assert orch.name("agy") == "Big G" and orch.name("claude") == "claude"
    assert 'the user calls it "Big G"' in orch._roster()
    asyncio.run(orch.handle("/nick agy"))
    assert config.load_nicknames(path) == {} and orch.name("agy") == "agy"

import asyncio
import json

from hexmind.backends import HcomBackend


class FakeProcess:
    def __init__(self, stdout="", stderr="", returncode=0):
        self.stdout = stdout.encode()
        self.stderr = stderr.encode()
        self.returncode = returncode

    async def communicate(self):
        return self.stdout, self.stderr

    async def wait(self):
        return self.returncode

    def kill(self):
        self.returncode = -9


class FakeHcom:
    def __init__(self):
        self.calls = []
        self.agents = []
        self.replies = iter(["first result", "second result"])

    async def create_process(self, *args, **kwargs):
        assert args[0] == "hcom"
        command = list(args[1:])
        self.calls.append(command)
        if command[:2] == ["list", "--json"]:
            out = json.dumps(self.agents)
        elif command[0] == "1":
            tool = command[1]
            directory = command[command.index("--dir") + 1]
            tag = command[command.index("--tag") + 1]
            member = {"claude": "claude", "antigravity": "agy", "codex": "codex"}[tool]
            self.agents.append({"name": f"hexmind-{member}", "tool": tool, "tag": tag,
                                "directory": directory, "status": "listening"})
            out = "ready"
        elif command[0] == "send":
            out = "sent"
        elif command[0] == "events":
            out = json.dumps({"data": {"text": next(self.replies)}})
        else:
            raise AssertionError(command)
        return FakeProcess(out)


def test_members_maps_hcom_tools_to_hexmind_aliases(monkeypatch, tmp_path):
    hcom = FakeHcom()
    hcom.agents = [
        {"tool": "claude"}, {"tool": "antigravity"}, {"tool": "codex"}, {"tool": "other"},
    ]
    monkeypatch.setattr(asyncio, "create_subprocess_exec", hcom.create_process)

    assert asyncio.run(HcomBackend(str(tmp_path)).members()) == ["claude", "agy", "codex"]


def test_run_starts_and_reuses_agent_with_isolated_threads(monkeypatch, tmp_path):
    hcom = FakeHcom()
    monkeypatch.setattr(asyncio, "create_subprocess_exec", hcom.create_process)
    backend = HcomBackend(str(tmp_path))

    assert asyncio.run(backend.run("agy", "first prompt")) == "first result"
    assert asyncio.run(backend.run("agy", "second prompt")) == "second result"

    launches = [call for call in hcom.calls if call[0] == "1"]
    sends = [call for call in hcom.calls if call[0] == "send"]
    waits = [call for call in hcom.calls if call[0] == "events"]
    assert len(launches) == 1
    assert launches[0][1] == "antigravity"
    assert launches[0][launches[0].index("--dir") + 1] == str(tmp_path)
    assert len(sends) == len(waits) == 2
    threads = [call[call.index("--thread") + 1] for call in sends]
    assert threads[0] != threads[1]
    assert all(call[call.index("--thread") + 1] == thread
               for call, thread in zip(waits, threads))

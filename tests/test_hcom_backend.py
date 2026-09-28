import asyncio
import json
import os

import pytest

from hexmind.backends import HCOM_EXCLUDED, HcomBackend, hcom_unsupported


class FakeStream:
    def __init__(self, data):
        self.data = data

    async def read(self, size):
        data, self.data = self.data[:size], self.data[size:]
        return data


class FakeProcess:
    def __init__(self, stdout="", stderr="", returncode=0):
        self.stdout = stdout.encode()
        self.stderr = stderr.encode()
        self.returncode = returncode
        self.stdout = FakeStream(self.stdout)
        self.stderr = FakeStream(self.stderr)

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
        self.launch_list_calls = 0
        self.envs = []
        self.timed_out = False

    async def create_process(self, *args, **kwargs):
        assert args[0] == "hcom"
        command = list(args[1:])
        self.calls.append(command)
        self.envs.append(kwargs.get("env"))
        if command[:2] == ["list", "--json"]:
            if any(a.get("status") == "launching" for a in self.agents):
                if self.launch_list_calls >= 2:
                    for agent in self.agents:
                        if agent.get("status") == "launching":
                            agent["status"] = "listening"
                self.launch_list_calls += 1
            out = json.dumps(self.agents)
        elif command[0] == "1":
            tool = command[1]
            directory = command[command.index("--dir") + 1]
            tag = command[command.index("--tag") + 1]
            member = {"claude": "claude", "antigravity": "agy", "codex": "codex"}[tool]
            self.agents.append({"name": f"hexmind-{member}", "base_name": member,
                                "tool": tool, "tag": tag,
                                "directory": directory, "status": "launching"})
            out = "Still launching after 10.0s"
            return FakeProcess(out, returncode=2)
        elif command[0] == "send":
            assert any(a.get("status") in {"listening", "active"} for a in self.agents)
            out = "sent"
        elif command[0] == "events":
            out = json.dumps({"timed_out": True} if self.timed_out else
                             {"data": {"text": next(self.replies)}})
        elif command[0] == "kill":
            self.agents = [a for a in self.agents if a.get("name") != command[1]]
            out = "killed"
        else:
            raise AssertionError(command)
        return FakeProcess(out)


def test_members_maps_hcom_tools_to_hexmind_aliases(monkeypatch, tmp_path):
    monkeypatch.delenv("JULES_API_KEY", raising=False)
    hcom = FakeHcom()
    hcom.agents = [
        {"tool": "claude"}, {"tool": "antigravity"}, {"tool": "codex"}, {"tool": "other"},
    ]
    monkeypatch.setattr(asyncio, "create_subprocess_exec", hcom.create_process)

    assert asyncio.run(HcomBackend(str(tmp_path)).members()) == ["claude", "agy", "codex"]


def test_run_waits_for_readiness_and_reuses_agent_with_isolated_threads(monkeypatch, tmp_path, capsys):
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
    assert all(call[call.index("--from") + 1] == "agy" for call in waits)
    assert all(call[1] == "@hexmind-agy" for call in sends)
    assert capsys.readouterr().out == ""  # launch progress is captured, never shown as a model reply


def test_blocked_agent_reports_approval_instructions_without_sending(monkeypatch, tmp_path):
    hcom = FakeHcom()
    backend = HcomBackend(str(tmp_path))
    hcom.agents = [{"name": "hexmind-claude", "tool": "claude", "tag": backend.tag,
                    "directory": str(tmp_path), "status": "blocked"}]
    monkeypatch.setattr(asyncio, "create_subprocess_exec", hcom.create_process)

    with pytest.raises(RuntimeError, match="waiting for approval") as err:
        asyncio.run(backend.run("claude", "first prompt"))

    message = str(err.value)
    assert "usually the folder-trust prompt in a folder that the CLI has never opened" in message
    assert f"cd {tmp_path} && claude" in message
    assert "then retry" in message
    assert "hcom term hexmind-claude" in message
    assert "term inject" not in message
    assert [call for call in hcom.calls if call[0] == "kill"] == [["kill", "hexmind-claude"]]
    assert not any(call[0] == "send" for call in hcom.calls)


def test_commands_strip_hcom_identity_environment_but_keep_hcom_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("HCOM_INSTANCE_NAME", "caller-agent")
    monkeypatch.setenv("HCOM_PROCESS_ID", "caller-process")
    monkeypatch.setenv("HCOM_LAUNCHED", "1")
    monkeypatch.setenv("HCOM_DIR", "/tmp/hcom-data")
    hcom = FakeHcom()
    monkeypatch.setattr(asyncio, "create_subprocess_exec", hcom.create_process)

    asyncio.run(HcomBackend(str(tmp_path)).run("agy", "prompt"))

    expected = {k: v for k, v in os.environ.items() if not k.startswith("HCOM") or k == "HCOM_DIR"}
    assert hcom.envs and all(env == expected for env in hcom.envs)
    assert all("HCOM_INSTANCE_NAME" not in env and "HCOM_PROCESS_ID" not in env for env in hcom.envs)
    assert all(env["HCOM_DIR"] == "/tmp/hcom-data" for env in hcom.envs)


def test_timed_out_events_raise_member_timeout(monkeypatch, tmp_path):
    hcom = FakeHcom()
    hcom.timed_out = True
    monkeypatch.setattr(asyncio, "create_subprocess_exec", hcom.create_process)

    with pytest.raises(RuntimeError, match="agy did not reply within 3s"):
        asyncio.run(HcomBackend(str(tmp_path), timeout=3).run("agy", "prompt"))


# --- D1: hcom drives a tool, not a model, so the non-default opencode models are unreachable ---

def test_only_the_default_opencode_model_is_reachable_over_hcom():
    assert HcomBackend.supports("nemotron-lightning") is True
    non_default = {"nemotron-ultra", "muse-spark", "mimo-flash", "big-pickle",
                   "ling-flash", "space-bunny", "longcat-preview"}
    for member in non_default:
        assert HcomBackend.supports(member) is False, member
    # the set and the predicate must not drift apart
    assert non_default == HCOM_EXCLUDED


def test_excluded_opencode_members_are_never_offered_by_members(monkeypatch, tmp_path):
    hcom = FakeHcom()
    hcom.agents = [{"name": "hexmind-opencode", "tool": "opencode", "tag": HcomBackend(str(tmp_path)).tag,
                    "directory": str(tmp_path), "status": "listening"}]
    monkeypatch.setattr(asyncio, "create_subprocess_exec", hcom.create_process)

    members = asyncio.run(HcomBackend(str(tmp_path)).members())

    assert "nemotron-lightning" in members
    assert not HCOM_EXCLUDED & set(members)


def test_excluded_member_error_names_the_limit_and_the_alternative(monkeypatch, tmp_path):
    monkeypatch.setattr(asyncio, "create_subprocess_exec", FakeHcom().create_process)

    with pytest.raises(ValueError) as err:
        asyncio.run(HcomBackend(str(tmp_path))._agent("longcat-preview", str(tmp_path)))

    message = str(err.value)
    assert "hcom cannot drive 'longcat-preview'" in message
    assert "hcom selects a tool, not a model" in message
    assert "--backend direct" in message


def test_startup_notice_lists_what_hcom_will_drop():
    installed = ["claude", "agy", "codex", "nemotron-lightning", "space-bunny", "longcat-preview", "kimi"]

    dropped = hcom_unsupported(installed)

    assert dropped == ["space-bunny", "longcat-preview"]
    assert "nemotron-lightning" not in dropped  # the default model is still reachable

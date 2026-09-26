"""How hexmind talks to agents. Two options, same interface: `await backend.run(agent, prompt) -> str`.

- DirectBackend: hexmind runs each agent's CLI in print mode itself. No hcom needed.
- HcomBackend: (phase 2) agents live in hcom, optionally in visible split terminals.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import shlex
import shutil
import tempfile
import uuid

# Per-agent argv for a one-shot, non-interactive turn. {prompt} is filled in.
# Edits are auto-accepted so agents can actually do work in the room's folder.
DIRECT_CMDS: dict[str, list[str]] = {
    "claude": ["claude", "-p", "{prompt}", "--permission-mode", "acceptEdits"],
    "agy": ["agy", "-p", "{prompt}", "--mode", "accept-edits", "--disable-slash-commands"],
    "codex": ["codex", "exec", "--sandbox", "workspace-write", "--skip-git-repo-check",
              "--output-last-message", "{outfile}", "{prompt}"],
}


def available(members: list[str]) -> list[str]:
    """Members whose CLI is actually installed."""
    return [m for m in members if m in DIRECT_CMDS and shutil.which(DIRECT_CMDS[m][0])]


class DirectBackend:
    def __init__(self, cwd: str, timeout: int = 1800):
        self.cwd = cwd
        self.timeout = timeout

    async def run(self, agent: str, prompt: str, cwd: str | None = None) -> str:
        with tempfile.TemporaryDirectory() as tmp:
            outfile = os.path.join(tmp, "last.txt")
            argv = [a.replace("{prompt}", prompt).replace("{outfile}", outfile) for a in DIRECT_CMDS[agent]]
            proc = await asyncio.create_subprocess_exec(
                *argv, cwd=cwd or self.cwd, stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            try:
                out, err = await asyncio.wait_for(proc.communicate(), self.timeout)
            except asyncio.TimeoutError:
                proc.kill()
                raise RuntimeError(f"{agent} timed out after {self.timeout}s")
            if proc.returncode != 0:
                raise RuntimeError(f"{agent} exited {proc.returncode}: {err.decode(errors='replace')[-500:]}")
            if os.path.exists(outfile):  # codex writes its final message here; stdout is its log
                with open(outfile) as f:
                    return f.read()
            return out.decode(errors="replace")


HCOM_TOOLS = {"claude": "claude", "agy": "antigravity", "codex": "codex"}
HCOM_MEMBERS = {"claude": "claude", "antigravity": "agy", "gemini": "agy", "codex": "codex"}


class HcomBackend:
    """Persistent hcom agents, with each request isolated in its own thread."""

    def __init__(self, cwd: str, timeout: int = 1800):
        self.cwd = os.path.abspath(cwd)
        self.timeout = timeout
        self.tag = "hexmind-" + hashlib.sha256(self.cwd.encode()).hexdigest()[:10]
        self._locks: dict[tuple[str, str], asyncio.Lock] = {}

    async def _command(self, *args: str, cwd: str | None = None, timeout: int | None = None,
                       accepted_returncodes: tuple[int, ...] = (0,)) -> str:
        env = {k: v for k, v in os.environ.items() if not k.startswith("HCOM") or k == "HCOM_DIR"}
        proc = await asyncio.create_subprocess_exec(
            "hcom", *args, cwd=cwd or self.cwd, stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, env=env)
        try:
            out, err = await asyncio.wait_for(proc.communicate(), timeout or self.timeout)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            raise RuntimeError(f"hcom {' '.join(args[:2])} timed out")
        if proc.returncode not in accepted_returncodes:
            detail = err.decode(errors="replace").strip() or out.decode(errors="replace").strip()
            raise RuntimeError(f"hcom {' '.join(args[:2])} exited {proc.returncode}: {detail[-500:]}")
        return out.decode(errors="replace").strip()

    async def _agents(self) -> list[dict]:
        try:
            agents = json.loads(await self._command("list", "--json"))
        except json.JSONDecodeError as e:
            raise RuntimeError("hcom list --json returned invalid JSON") from e
        if not isinstance(agents, list):
            raise RuntimeError("hcom list --json did not return an array")
        return [a for a in agents if isinstance(a, dict)]

    async def members(self) -> list[str]:
        """Model aliases represented by currently available hcom agents."""
        found = {HCOM_MEMBERS[a.get("tool", "").lower()] for a in await self._agents()
                 if a.get("tool", "").lower() in HCOM_MEMBERS}
        return [m for m in HCOM_TOOLS if m in found]

    async def _agent(self, member: str, cwd: str) -> tuple[str, str]:
        if member not in HCOM_TOOLS:
            raise ValueError(f"unsupported hcom member: {member}")
        cwd = os.path.abspath(cwd)
        lock = self._locks.setdefault((member, cwd), asyncio.Lock())
        async with lock:
            tool = HCOM_TOOLS[member]

            def matching(agents: list[dict]) -> list[dict]:
                return [a for a in agents if a.get("tag") == self.tag and a.get("tool") == tool
                        and os.path.abspath(a.get("directory", "")) == cwd]

            agents = matching(await self._agents())
            if not agents:
                await self._command("1", tool, "--headless", "--tag", self.tag, "--dir", cwd,
                                    "--hcom-system-prompt",
                                    f"You are the persistent {member} agent in a Hexmind team. "
                                    "Respond to each incoming Hexmind request with its result.",
                                    timeout=min(self.timeout, 60), accepted_returncodes=(0, 2))

            deadline = asyncio.get_running_loop().time() + min(self.timeout, 60)
            agent = None
            while asyncio.get_running_loop().time() < deadline:
                agents = matching(await self._agents())
                if agents:
                    agent = agents[-1]
                    if agent.get("status") == "blocked":
                        name = agent.get("name", member)
                        message = (
                            f"{member} agent {name} is waiting for approval (usually the folder-trust prompt in a "
                            f"folder that the CLI has never opened). Open it once yourself: "
                            f"`cd {shlex.quote(cwd)} && {member}` and accept, then retry. "
                            f"To look at the prompt: `hcom term {name}`.")
                        try:
                            await self._command("kill", name, timeout=10)
                        except RuntimeError as e:
                            raise RuntimeError(f"{message} Stopping the blocked agent also failed: {e}") from e
                        raise RuntimeError(message)
                    if agent.get("status") in {"listening", "active"}:
                        return agent["name"], agent.get("base_name", agent["name"])
                await asyncio.sleep(0.25)
            if agent:
                raise RuntimeError(f"hcom {member} agent {agent.get('name')} did not become ready "
                                   f"(status: {agent.get('status', 'unknown')})")
            raise RuntimeError(f"hcom did not start a {member} agent for {cwd}")

    async def run(self, agent: str, prompt: str, cwd: str | None = None) -> str:
        agent_name, event_from = await self._agent(agent, cwd or self.cwd)
        thread = f"{self.tag}-{agent}-{uuid.uuid4().hex[:16]}"
        await self._command("send", f"@{agent_name}", "--intent", "request", "--thread", thread,
                            "--from", "hexmind", "--", prompt)
        raw = await self._command("events", "--wait", str(max(1, self.timeout)), "--type", "message",
                                  "--from", event_from, "--thread", thread,
                                  timeout=self.timeout + 5)
        try:
            event = json.loads(raw)
        except json.JSONDecodeError as e:
            raise RuntimeError("hcom events returned invalid JSON") from e
        if isinstance(event, dict) and event.get("timed_out") is True:
            raise RuntimeError(f"{agent} did not reply within {self.timeout}s")
        text = event.get("data", {}).get("text") if isinstance(event, dict) else None
        if not isinstance(text, str):
            raise RuntimeError("hcom event did not contain a message")
        return text

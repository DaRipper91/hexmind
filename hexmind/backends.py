"""How hexmind talks to agents. Two options, same interface: `await backend.run(agent, prompt) -> str`.

- DirectBackend: hexmind runs each agent's CLI in print mode itself. No hcom needed.
- HcomBackend: (phase 2) agents live in hcom, optionally in visible split terminals.
"""
from __future__ import annotations

import asyncio
import os
import shutil
import tempfile

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

    async def run(self, agent: str, prompt: str) -> str:
        with tempfile.TemporaryDirectory() as tmp:
            outfile = os.path.join(tmp, "last.txt")
            argv = [a.replace("{prompt}", prompt).replace("{outfile}", outfile) for a in DIRECT_CMDS[agent]]
            proc = await asyncio.create_subprocess_exec(
                *argv, cwd=self.cwd, stdin=asyncio.subprocess.DEVNULL,
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

"""How hexmind talks to agents. Two options, same interface: `await backend.run(agent, prompt) -> str`.

- DirectBackend: hexmind runs each agent's CLI in print mode itself. No hcom needed.
- HcomBackend: (phase 2) agents live in hcom, optionally in visible split terminals.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import signal
import shlex
import shutil
import tempfile
import urllib.request
import uuid

# Per-agent argv for a one-shot, non-interactive turn. Prompts go over stdin.
# Edits are auto-accepted so agents can actually do work in the room's folder.
DIRECT_CMDS: dict[str, list[str]] = {
    "claude": ["claude", "-p", "--permission-mode", "bypassPermissions"],
    "agy": ["agy", "--input-format", "stream-json", "--output-format", "stream-json",
            "--mode", "accept-edits", "--dangerously-skip-permissions", "--disable-slash-commands"],
    "codex": ["codex", "exec", "--sandbox", "workspace-write", "-a", "never", "--skip-git-repo-check",
              "--output-last-message", "{outfile}", "-"],
    # Free OpenCode Zen models. All 8 confirmed present in `opencode models` on 2026-09-27.
    # Prompts go over stdin, so there is no argv length ceiling. --format json (WS-4) will replace
    # the bare stdout read here with a session-aware event stream.
    "opencode": ["opencode", "run", "--auto", "-m", "opencode/nemotron-3.5-lightning-free"],
    "opencode-ultra": ["opencode", "run", "--auto", "-m", "opencode/nemotron-3-ultra-free"],
    "opencode-muse": ["opencode", "run", "--auto", "-m", "opencode/muse-spark-1.3-contributor-free"],
    "opencode-mimo": ["opencode", "run", "--auto", "-m", "opencode/mimo-v2.6-flash-free"],
    "opencode-pickle": ["opencode", "run", "--auto", "-m", "opencode/big-pickle"],
    "opencode-ling": ["opencode", "run", "--auto", "-m", "opencode/ling-3.0-flash-fin-free"],
    "opencode-bunny": ["opencode", "run", "--auto", "-m", "opencode/space-bunny-free"],
    "opencode-longcat": ["opencode", "run", "--auto", "-m", "opencode/longcat-2.5-preview-free"],
    # file edits allowed without prompting (like claude acceptEdits); shell and other tools stay denied
    "copilot": ["copilot", "-s", "--allow-tool=write"],
    # kimi's -p takes the prompt as an argv token, not stdin -- its only stdin-driven mode is the
    # much heavier ACP protocol, so very large prompts may hit an OS arg-length limit here unlike
    # every other member (see {prompt} substitution in DirectBackend.run).
    "kimi": ["kimi", "-p", "{prompt}", "--output-format", "stream-json"],
}


# Local models served by Ollama. Text in, text out: no tools, no files.
LOCAL_MODELS: dict[str, str] = {"qwen": "qwen2.5-coder:7b", "qwen-large": "qwen2.5-coder:latest"}
OLLAMA_URL = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
MAX_OUTPUT_BYTES = 1_000_000
TERMINATE_GRACE_SECONDS = 1


async def _read_capped(stream: asyncio.StreamReader, limit: int = MAX_OUTPUT_BYTES) -> bytes:
    kept = bytearray()
    while chunk := await stream.read(65536):
        kept.extend(chunk)
        if len(kept) > limit:
            del kept[:len(kept) - limit]
    return bytes(kept)


async def _write_stdin(proc: asyncio.subprocess.Process, payload: bytes) -> None:
    try:
        proc.stdin.write(payload)
        await proc.stdin.drain()
    except (BrokenPipeError, ConnectionResetError):
        pass
    finally:
        proc.stdin.close()


def _signal_group(pid: int, sig: int) -> None:
    try:
        os.killpg(pid, sig)
    except ProcessLookupError:
        pass


async def _terminate_group(proc: asyncio.subprocess.Process) -> None:
    _signal_group(proc.pid, signal.SIGTERM)
    try:
        await asyncio.wait_for(proc.wait(), TERMINATE_GRACE_SECONDS)
    except asyncio.TimeoutError:
        pass
    # A child may have exited while a descendant still holds inherited pipes.
    _signal_group(proc.pid, signal.SIGKILL)
    await proc.wait()

# Both are loadable, but Ollama shares one memory budget between them, so only one stays
# resident at a time: switching local models unloads whichever one was active before it.
_local_lock = asyncio.Lock()
_active_local: str | None = None


def _ollama_models() -> set[str]:
    try:
        with urllib.request.urlopen(f"{OLLAMA_URL}/api/tags", timeout=3) as r:
            return {m["name"] for m in json.load(r).get("models", [])}
    except (OSError, ValueError):
        return set()


def available(members: list[str]) -> list[str]:
    """Members whose CLI is installed, or whose local model is pulled in a running Ollama."""
    pulled = _ollama_models() if any(m in LOCAL_MODELS for m in members) else set()
    return [m for m in members if (m in DIRECT_CMDS and shutil.which(DIRECT_CMDS[m][0]))
            or LOCAL_MODELS.get(m) in pulled
            or (m == "jules" and bool(os.environ.get("JULES_API_KEY")))]


def _ollama_generate(model: str, prompt: str, timeout: int, keep_alive: int | None = None) -> str:
    body = {"model": model, "prompt": prompt, "stream": False, "think": False}
    if keep_alive is not None:
        body["keep_alive"] = keep_alive
    req = urllib.request.Request(f"{OLLAMA_URL}/api/generate", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r).get("response", "")


async def run_local(agent: str, prompt: str, timeout: int) -> str:
    """One Ollama generate call; thinking off so the reply is just the answer.

    Serialized across all local models: if a different one is currently loaded, it's evicted
    first (keep_alive=0, no prompt) so the two never both sit in memory at once.
    """
    global _active_local
    async with _local_lock:
        if _active_local is not None and _active_local != agent:
            try:
                await asyncio.to_thread(_ollama_generate, LOCAL_MODELS[_active_local], "", 10, keep_alive=0)
            except OSError:
                pass  # best-effort: Ollama frees it on its own keep_alive timeout regardless
        try:
            result = await asyncio.to_thread(_ollama_generate, LOCAL_MODELS[agent], prompt, timeout)
        except OSError as e:
            raise RuntimeError(f"{agent} (Ollama {LOCAL_MODELS[agent]}) failed: {e}") from e
        _active_local = agent
        return result


class DirectBackend:
    def __init__(self, cwd: str, timeout: int = 1800):
        self.cwd = cwd
        self.timeout = timeout

    async def run(self, agent: str, prompt: str, cwd: str | None = None,
                  schema: dict | None = None) -> str:
        if agent == "jules":
            from .jules import run as run_jules
            return await run_jules(prompt, cwd or self.cwd)
        if agent in LOCAL_MODELS:
            return await run_local(agent, prompt, self.timeout)
        with tempfile.TemporaryDirectory() as tmp:
            outfile = os.path.join(tmp, "last.txt")
            argv = [a.replace("{outfile}", outfile).replace("{prompt}", prompt) for a in DIRECT_CMDS[agent]]
            if schema is not None and agent == "claude":
                argv.extend(["--json-schema", json.dumps(schema, separators=(",", ":"))])
            elif schema is not None and agent == "agy":
                argv.extend(["--json-schema", json.dumps(schema, separators=(",", ":"))])
            elif schema is not None and agent == "codex":
                schemafile = os.path.join(tmp, "schema.json")
                with open(schemafile, "w") as f:
                    json.dump(schema, f)
                argv.extend(["--output-schema", schemafile])
            proc = await asyncio.create_subprocess_exec(
                *argv, cwd=cwd or self.cwd, stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, start_new_session=True)
            payload = (b"" if agent == "kimi" else
                       (json.dumps({"event": "user", "message": {"content": prompt}}) + "\n").encode()
                       if agent == "agy" else prompt.encode())
            stdin_task = asyncio.create_task(_write_stdin(proc, payload))
            stdout_task = asyncio.create_task(_read_capped(proc.stdout))
            stderr_task = asyncio.create_task(_read_capped(proc.stderr))
            try:
                await asyncio.wait_for(asyncio.gather(proc.wait(), stdin_task, stdout_task, stderr_task),
                                       self.timeout)
            except asyncio.TimeoutError:
                await _terminate_group(proc)
                await asyncio.gather(stdin_task, stdout_task, stderr_task, return_exceptions=True)
                raise RuntimeError(f"{agent} timed out after {self.timeout}s")
            out, err = stdout_task.result(), stderr_task.result()
            if proc.returncode != 0:
                detail = err.decode(errors="replace").strip() or out.decode(errors="replace").strip()
                raise RuntimeError(f"{agent} exited {proc.returncode}: {detail[-500:]}")
            if os.path.exists(outfile):  # codex writes its final message here; stdout is its log
                with open(outfile) as f:
                    return f.read()
            if agent == "agy":
                events = []
                for line in out.decode(errors="replace").splitlines():
                    try:  # agy may print warnings between stream-json events
                        events.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
                result = next((e["result"]["response"] for e in reversed(events)
                               if isinstance(e, dict) and e.get("event") == "result"), None)
                if result is None:
                    raise RuntimeError("agy stream did not contain a result")
                return result
            if agent == "kimi":
                events = []
                for line in out.decode(errors="replace").splitlines():
                    try:
                        events.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
                result = next((e["content"] for e in reversed(events)
                               if isinstance(e, dict) and e.get("role") == "assistant"), None)
                if result is None:
                    raise RuntimeError("kimi stream did not contain an assistant reply")
                return result
            return out.decode(errors="replace")


HCOM_TOOLS = {"claude": "claude", "agy": "antigravity", "codex": "codex", "opencode": "opencode",
              "copilot": "copilot", "jules": "jules", "kimi": "kimi"}
HCOM_MEMBERS = {"claude": "claude", "antigravity": "agy", "gemini": "agy", "codex": "codex",
                "opencode": "opencode", "copilot": "copilot", "jules": "jules", "kimi": "kimi"}


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
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, env=env,
            start_new_session=True)
        stdout_task = asyncio.create_task(_read_capped(proc.stdout))
        stderr_task = asyncio.create_task(_read_capped(proc.stderr))
        try:
            await asyncio.wait_for(asyncio.gather(proc.wait(), stdout_task, stderr_task),
                                   timeout or self.timeout)
        except asyncio.TimeoutError:
            await _terminate_group(proc)
            await asyncio.gather(stdout_task, stderr_task, return_exceptions=True)
            raise RuntimeError(f"hcom {' '.join(args[:2])} timed out")
        out, err = stdout_task.result(), stderr_task.result()
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
        members = [m for m in HCOM_TOOLS if m in found]
        if os.environ.get("JULES_API_KEY"):
            members.append("jules")
        return members

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

    async def run(self, agent: str, prompt: str, cwd: str | None = None,
                  schema: dict | None = None) -> str:
        if agent == "jules":
            from .jules import run as run_jules
            return await run_jules(prompt, cwd or self.cwd)
        if agent in LOCAL_MODELS:  # local models are not hcom agents; call Ollama directly
            return await run_local(agent, prompt, self.timeout)
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

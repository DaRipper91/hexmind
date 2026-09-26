"""Team roster, plan parsing, and the orchestrator that runs a task chain.

Flow for one user message:
  1. lead agent gets the roster + request, answers with JSON: a reply and a task list
  2. tasks run as a dependency graph; everything whose deps are done runs in parallel
  3. lead gets all task outputs and writes the final answer for the user
"""
from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass, field
from typing import Callable

# Who is on the team and what each is good at. The lead reads this to assign work.
ROSTER: dict[str, str] = {
    "claude": "careful multi-file code changes, refactoring, code review, debugging, planning, writing docs",
    "agy": "Google Gemini: very large context reading, deep reasoning, polyglot code generation, web research, UI/frontend work",
    "codex": "OpenAI Codex: fast focused implementation, writing tests, shell scripting and automation",
    "opencode": "NVIDIA Nemotron 3.5 Lightning (Free): fast implementation, refactoring, and general coding",
    "opencode-ultra": "NVIDIA Nemotron 3 Ultra (Free): deep architectural audits and complex logic validation",
    "opencode-muse": "Meta Muse Spark (Free): massive 1M context repo scanning and cross-file documentation analysis",
    "opencode-mimo": "Xiaomi MiMo (Free): low-latency small tasks — quick edits, short scripts, fast second opinions",
    "copilot": "GitHub Copilot CLI: GitHub-aware coding agent: implementation, GitHub workflows/Actions, repo conventions. Can edit files but not run shell commands",
    "qwen": ("local qwen2.5-coder:7b via Ollama: free, private, never hits a quota, but small and slow. TEXT ONLY: "
             "it cannot read or edit files or run commands. Give it only small self-contained text jobs "
             "(summarize, classify, triage, draft short text) and paste everything it needs into the instructions. "
             "Shares one Ollama slot with qwen-large — only one of the two is ever loaded at a time, so pick "
             "whichever one fits the job rather than assigning both in the same room"),
    "qwen-large": ("local qwen2.5-coder:latest via Ollama: same free/private/TEXT-ONLY deal as qwen, but the "
                   "larger build — slower, better for anything qwen would struggle with. Shares one Ollama slot "
                   "with qwen: picking this one unloads qwen if it was warm, and vice versa"),
    "kimi": ("Moonshot AI's Kimi Code: 1M-token context with deep extended thinking (effort defaults to max), "
             "general implementation and second opinions on large-context tasks"),
}

# Members that only see the prompt (no tools). Never lead, never auditor, not rotated into relays.
TEXT_ONLY = {"qwen", "qwen-large"}
# Members that only join with --with NAME. Both run on CPU and starve an 8 GB machine running other
# agents; they also share one Ollama memory slot (see backends.run_local), so only one loads at a time.
OPT_IN = {"qwen", "qwen-large"}


@dataclass
class Task:
    id: str
    title: str
    agent: str
    instructions: str
    depends_on: list[str] = field(default_factory=list)
    status: str = "pending"  # pending | running | done | failed | skipped
    output: str = ""
    cwd: str | None = None    # folder this task works in (None = the room's folder)
    notes: str | None = None  # relay chain notes file; each finished stage is appended to it
    domain: str = "general"   # kind of work, for audit rankings (see auditor.DOMAINS)
    gate: bool = False        # high-impact: an unresolved audit failure blocks dependents
    audit: str = ""           # "" | pass | fixed | disputed
    auditor: str = ""


LEAD_PROMPT = """You are the lead of a team of AI coding agents working in one shared room.
Team members and their strengths:
{roster}

The user said:
{request}

{history}Decide how the team should handle this. Answer ONLY with a JSON object:
{{"reply": "short message to the user about what the team will do (or the full answer if no work is needed)",
  "tasks": [{{"id": "t1", "title": "short title", "agent": "<team member>",
             "instructions": "complete, self-contained instructions", "depends_on": [],
             "domain": "<one of: {domains}>", "gate": false}}]}}

Rules:
- Assign each task to the member best suited to it. Use only members listed above.
- The user may call members by nickname; in the JSON always use the member name (claude, agy, ...).
- Split work into phases with depends_on. Independent tasks run at the same time.
- Tasks that edit the same files must not run in parallel; chain them with depends_on.
- Set "gate": true only for high-impact tasks whose mistakes would break later work (core logic, migrations, security).
- For a simple question or chat, answer directly in "reply" and return "tasks": [].
"""

SYNTH_PROMPT = """You are the lead of an AI agent team. The user asked:
{request}

Your team finished these tasks:
{results}

Write the final answer to the user: what was done, key results, anything that failed or needs their decision. Be concise."""

TASK_PROMPT = """You are {agent}, working as part of an AI agent team led by {lead}.
Overall user request: {request}

Your task ({id}: {title}):
{instructions}
{deps}
Do the task, then reply with a concise report of what you did and the result."""


def extract_json(text: str) -> dict:
    """Pull the first JSON object out of a model reply (models like to wrap it in fences)."""
    decoder = json.JSONDecoder()
    for m in re.finditer(r"\{", text):  # try each '{' until one parses as a whole object
        try:
            obj, _ = decoder.raw_decode(text, m.start())
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            return obj
    raise ValueError("no JSON object in lead reply")


def _as_list(v) -> list:
    """Models sometimes send "t1" instead of ["t1"]."""
    return v if isinstance(v, list) else [v] if v else []


def clip(text: str, n: int = 4000) -> str:
    return text if len(text) <= n else text[:n] + "\n... [truncated]"


def parse_plan(text: str, members: list[str], lead: str) -> tuple[str, list[Task]]:
    """Validate the lead's plan: known agents, known deps, no cycles."""
    data = extract_json(text)
    if "tasks" in data and not isinstance(data["tasks"], list) and data.get("tasks") is not None:
        raise ValueError("tasks field must be a list")
    raw_tasks = data.get("tasks") or []
    tasks = []
    if isinstance(raw_tasks, list):
        for i, t in enumerate(raw_tasks):
            if isinstance(t, str):
                tasks.append(Task(id=f"t{i + 1}", title=t,
                                  agent=lead, instructions=t,
                                  depends_on=[],
                                  domain="general", gate=False))
            elif isinstance(t, dict):
                agent = t.get("agent") if t.get("agent") in members else lead
                tasks.append(Task(id=str(t.get("id") or f"t{i + 1}"), title=t.get("title", "task"),
                                  agent=agent, instructions=t.get("instructions", t.get("title", "")),
                                  depends_on=[str(d) for d in _as_list(t.get("depends_on"))],
                                  domain=str(t.get("domain") or "general"), gate=t.get("gate") is True))
    ids = {t.id for t in tasks}
    if len(ids) != len(tasks):
        raise ValueError("duplicate task ids in plan")
    for t in tasks:
        t.depends_on = [d for d in t.depends_on if d in ids and d != t.id]
    # cycle check: repeatedly peel off tasks whose deps are all peeled
    done: set[str] = set()
    while len(done) < len(tasks):
        ready = {t.id for t in tasks if t.id not in done and set(t.depends_on) <= done}
        if not ready:
            raise ValueError("plan has a dependency cycle")
        done |= ready
    reply = data.get("reply", "")
    if not reply and not tasks:
        raise ValueError("plan has neither reply nor tasks")
    return reply, tasks


Emit = Callable[[str, dict], None]  # (event kind, payload) -> UI


class Orchestrator:
    def __init__(self, backend, members: list[str], lead: str = "claude", emit: Emit | None = None,
                 audit: bool = False, stats=None):
        self.backend = backend
        self.members = members
        self.lead = lead
        self.emit = emit or (lambda kind, data: None)
        self.history: list[tuple[str, str]] = []  # (user msg, final answer)
        self.audit = audit  # runner-up model reviews every task
        self.stats = stats  # auditor.Stats: pass/fail record per model per domain
        from .config import load_nicknames
        self.nicknames: dict[str, str] = load_nicknames()  # model -> user's display name

    def name(self, m: str) -> str:
        """What the user sees: the nickname if one is set, else the model name."""
        return self.nicknames.get(m, m)

    def _roster(self) -> str:
        lines = [f"- {m}" + (f' (the user calls it "{self.nicknames[m]}")' if m in self.nicknames else "")
                 + f": {ROSTER.get(m, 'general purpose')}" for m in self.members]
        if self.stats:
            table = self.stats.table(self.members)
            if table.startswith("|"):  # skip the "no stats yet" placeholder
                lines.append("\nTrack record (tasks that passed peer audit on first try / audited):\n" + table)
        return "\n".join(lines)

    def _history(self) -> str:
        if not self.history:
            return ""
        # ponytail: last 3 exchanges verbatim; summarize older ones if context gets tight
        lines = [f"User: {u}\nTeam: {a[:1500]}" for u, a in self.history[-3:]]
        return "Earlier in this room:\n" + "\n\n".join(lines) + "\n\n"

    async def handle(self, request: str) -> str:
        if request.startswith("/"):
            from .relay import command  # slash commands: /relay, /chains, /help
            reply = await command(self, request)
            self.history.append((request, reply))
            return reply
        self.emit("status", {"agent": self.lead, "state": "planning"})
        from .auditor import DOMAINS
        raw = await self.backend.run(self.lead, LEAD_PROMPT.format(
            roster=self._roster(), request=request, history=self._history(), domains=", ".join(DOMAINS)))
        self.emit("status", {"agent": self.lead, "state": "idle"})
        try:
            reply, tasks = parse_plan(raw, self.members, self.lead)
        except (ValueError, json.JSONDecodeError, AttributeError, TypeError):
            # lead answered in prose instead of JSON: treat it as a direct answer
            reply, tasks = raw.strip(), []
        self.emit("message", {"from": self.lead, "text": reply})
        if not tasks:
            self.history.append((request, reply))
            return reply

        self.emit("plan", {"tasks": tasks})
        await self.run_tasks(request, tasks)

        results = "\n\n".join(f"[{t.id}] {t.title} ({t.agent}, {t.status}):\n{clip(t.output)}" for t in tasks)
        self.emit("status", {"agent": self.lead, "state": "summarizing"})
        final = await self.backend.run(self.lead, SYNTH_PROMPT.format(request=request, results=results))
        self.emit("status", {"agent": self.lead, "state": "idle"})
        self.emit("message", {"from": self.lead, "text": final.strip()})
        self.history.append((request, final))
        return final

    async def run_tasks(self, request: str, tasks: list[Task]) -> None:
        by_id = {t.id: t for t in tasks}
        running: dict[asyncio.Task, Task] = {}

        def launch_ready():
            for t in tasks:
                if t.status != "pending":
                    continue
                deps = [by_id[d] for d in t.depends_on]
                if any(d.status in ("failed", "skipped") for d in deps):
                    t.status = "skipped"
                    self.emit("task", {"task": t})
                elif all(d.status == "done" for d in deps):
                    t.status = "running"
                    self.emit("task", {"task": t})
                    running[asyncio.create_task(self._run_one(request, t, deps))] = t

        launch_ready()
        while running:
            finished, _ = await asyncio.wait(running, return_when=asyncio.FIRST_COMPLETED)
            for f in finished:
                t = running.pop(f)
                try:
                    t.output, t.status = f.result(), "done"
                    if t.notes:
                        with open(t.notes, "a") as nf:
                            nf.write(f"\n## {t.title} ({t.agent})\n\n{t.output.strip()}\n")
                except Exception as e:  # one agent failing must not kill the room
                    t.output, t.status = f"error: {e}", "failed"
                self.emit("task", {"task": t})
            launch_ready()
            # a skip can cascade; keep resolving until nothing changes
            while any(t.status == "pending" and any(by_id[d].status in ("failed", "skipped")
                                                    for d in t.depends_on) for t in tasks):
                launch_ready()

    async def _run_one(self, request: str, t: Task, deps: list[Task]) -> str:
        dep_text = "".join(f"\nResult of {d.id} ({d.title}, by {d.agent}):\n{clip(d.output)}\n" for d in deps)
        prompt = TASK_PROMPT.format(agent=t.agent, lead=self.lead, request=request, id=t.id,
                                    title=t.title, instructions=t.instructions,
                                    deps=("\nInputs from earlier phases:" + dep_text) if deps else "")
        if t.notes:
            prompt += (f"\nThis is one stage of a relay chain. Every earlier stage's full report is in {t.notes}"
                       " — read it first. Hexmind appends your final reply to it; don't edit it yourself.")
        if self.audit and self.stats is not None:
            from .auditor import audited_run
            auditors = [m for m in self.members if m not in TEXT_ONLY]  # auditors must inspect real files
            return await audited_run(self.backend, t, prompt, auditors, self.stats, self.emit)
        return await self.backend.run(t.agent, prompt, cwd=t.cwd)

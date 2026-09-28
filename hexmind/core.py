"""Team roster, plan parsing, and the orchestrator that runs a task chain.

Flow for one user message:
  1. lead agent gets the roster + request, answers with JSON: a reply and a task list
  2. tasks run as a dependency graph; everything whose deps are done runs in parallel
  3. lead gets all task outputs and writes the final answer for the user
"""
from __future__ import annotations

import asyncio
import inspect
import json
import os
import re
from dataclasses import dataclass, field
from typing import Callable

from .models import Registry

# The team roster. GENERATED from hexmind/models.toml — see models.py. Every model has a structured
# entry (best_at, avoid_for, domains, weight); the prose the lead reads is derived from it, so a
# model cannot be described one way here and another way in /models.
REGISTRY = Registry.load()

# Who is on the team and what each is good at. The lead reads this to assign work.
ROSTER: dict[str, str] = REGISTRY.roster()

# Members that can't see local files (qwen: no tools; jules: works on the GitHub copy).
# Never lead, never auditor, not rotated into relays.
TEXT_ONLY = REGISTRY.text_only()
# Members that only join with --with NAME. qwen starves an 8 GB machine; jules spends cloud quota and opens PRs.
OPT_IN = REGISTRY.opt_in()

# A member failure that means "out of quota", not "bad work": hand the task to someone else.
QUOTA_RE = re.compile(r"usage limit|quota|rate.?limit|\b429\b|exceeded your|credit balance|"
                      r"subscription does not have access|out of credits", re.I)

# Lead plans are forced into this shape on CLIs that support structured output.
PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "reply": {"type": "string"},
        "tasks": {"type": "array", "items": {"type": "object", "properties": {
            "id": {"type": "string"}, "title": {"type": "string"}, "agent": {"type": "string"},
            "instructions": {"type": "string"}, "depends_on": {"type": "array", "items": {"type": "string"}},
            "domain": {"type": "string"}, "gate": {"type": "boolean"}},
            "required": ["id", "title", "agent", "instructions", "depends_on"]}},
    },
    "required": ["reply", "tasks"],
}

# Control chars (incl. ESC) and bidi overrides, from repohub core/textsafe.py. Keeps \n and \t.
_UNSAFE = re.compile("[\x00-\x08\x0b\x0c\r\x0e-\x1f\x7f-\x9f\u202a-\u202e\u2066-\u2069\u200e\u200f]")


def clean_text(text: str) -> str:
    """Model output feeds other models' prompts and the TUI: strip anything that can hide or spoof text."""
    return _UNSAFE.sub("", text or "")


@dataclass
class Task:
    id: str
    title: str
    agent: str
    instructions: str
    depends_on: list[str] = field(default_factory=list)
    # pending | running | auditing | revising (set by auditor.audited_run) | done | failed | skipped
    status: str = "pending"
    output: str = ""
    cwd: str | None = None    # folder this task works in (None = the room's folder)
    notes: str | None = None  # relay chain notes file; each finished stage is appended to it
    domain: str = "general"   # kind of work, for audit rankings (see auditor.DOMAINS)
    gate: bool = False        # high-impact: an unresolved audit failure blocks dependents
    audit: str = ""           # "" | pass | fixed | disputed
    auditor: str = ""


@dataclass
class Assembly:
    """The pre-flight negotiation: leader recommends a roster, the user edits it, `/go` hands the
    result back and the leader plans against the team the user actually chose.

    There is one roster, not two. `/add` `/remove` `/sleep` `/wake` edit `orchestrator.members`
    directly, so the proposal is never a second copy of the team that can drift from the live one —
    `recommended` is kept only to show the lead what it asked for and what it got.
    """
    request: str = ""                                # the request the roster is being built for
    recommended: list[str] = field(default_factory=list)  # the leader's pick, kept after /go
    reasons: dict[str, str] = field(default_factory=dict)
    room: list[str] = field(default_factory=list)    # who was in the room when it proposed

    def dropped(self, actual: list[str]) -> list[str]:
        """What the user took out. The lead reviews the disagreement, not just the final list."""
        return [m for m in self.recommended if m not in actual]

    def added(self, actual: list[str]) -> list[str]:
        """What the user put in *since the proposal*, which is not the same as what the lead did
        not ask for: a model that was already in the room when it recommended is not a change the
        user made, and telling the lead it was would be noise on the one call that has to be
        read carefully."""
        return [m for m in actual if m not in self.room]


# Returned by an operation that has already posted its own messages to the room, so the caller does
# not post the same text twice. `execute` and `run_relay` behave this way; making it a value rather
# than a convention is what stops a second copy reaching the user. Lives here, not in relay, because
# core is the lower layer and imports relay lazily.
POSTED = object()

# A task in one of these states means its model is mid-edit, so INVARIANT S-1 applies to it.
# Single source of truth: auditor.audited_run sets `auditing` and `revising`, and the sleep check
# reads this rather than re-listing the states.
BUSY_STATUSES = frozenset({"running", "auditing", "revising"})


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

RECOMMEND_SCHEMA = {
    "type": "object",
    "properties": {
        "members": {"type": "array", "items": {"type": "string"}},
        "reasons": {"type": "object", "additionalProperties": {"type": "string"}},
    },
    "required": ["members"],
}

# The review call is PLAN_SCHEMA unchanged: same plan, but asked against the roster the user
# actually settled on. ASSEMBLY_SCHEMA (chains + skills) is the next step of the plan contract and
# is deliberately not in here — see docs/TEAM-ASSEMBLY.md 4.

RECOMMEND_PROMPT = """You are {lead} of a team of AI coding agents, and the user is deciding who
should be in the room for one request.

The user asked:
{request}

Every model hexmind knows about, and what it is good and bad at:
{roster}

Track record, where there is one:
{stats}

Which members do you want on this? Answer ONLY with a JSON object:
{{"members": ["<name>", ...], "reasons": {{"<name>": "<one line, why this model>"}}}}

Rules:
- Use only names from the list above.
- Prefer the fewest members that cover the work. An idle model costs a process and a session, and a
  specialist you did not need is worse than a generalist that was.
- If the request needs a kind of model that is not on the list, say so in a reason rather than
  picking the nearest thing.
- This is a proposal, not a decision. The user edits it and hands it back.
"""

REVIEW_PROMPT = """You are {lead} of a team of AI coding agents.

You recommended these members for this request:
{recommended}
{reasons}
The user settled on this room instead:
{actual}
{dropped}
Your track record for this request:
{stats}

The user said:
{request}

Plan for the team the user actually chose, not the one you asked for. If dropping a member costs
you something, say what it costs in "reply" before the plan. Then answer ONLY with a JSON object:
{{"reply": "what the team will do, and anything the roster you were given cannot do",
  "tasks": [{{"id": "t1", "title": "short title", "agent": "<team member>",
             "instructions": "complete, self-contained instructions", "depends_on": [],
             "domain": "<one of: {domains}>", "gate": false}}]}}

Rules:
- Assign each task to a member who is actually in the room you were given. Never plan for a model
  the user removed, and never plan for one they never had.
- The user may call members by nickname; in the JSON always use the member name.
- Split work into phases with depends_on. Independent tasks run at the same time.
- Tasks that edit the same files must not run in parallel; chain them with depends_on.
- Set "gate": true only for high-impact tasks whose mistakes would break later work.
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
{where}Do the task, then reply with a concise report of what you did and the result."""


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


class TeamBusy(Exception):
    """A sleep request for a model that is mid-task. See INVARIANT S-1."""


class TeamError(Exception):
    """An invalid team change: unknown model, or a lead that cannot lead."""


class Orchestrator:
    def __init__(self, backend, members: list[str], lead: str = "opencode-ultra", emit: Emit | None = None,
                 audit: bool = False, stats=None, known: list[str] | None = None):
        self.backend = backend
        # `members` is the AWAKE roster and is mutated in place so every consumer (this
        # orchestrator, the TUI and the server, which share the same list object) sees a change
        # immediately. `known` is every model hexmind knows about, awake or not — a sleeping model
        # must keep its registry entry, its stats and its journal, or sleeping would destroy history.
        self.members = members
        self.known = list(known) if known is not None else list(REGISTRY.names())
        self.lead = lead
        self.emit = emit or (lambda kind, data: None)
        self.history: list[tuple[str, str]] = []  # (user msg, final answer)
        self.audit = audit  # runner-up model reviews every task
        self.stats = stats  # auditor.Stats: pass/fail record per model per domain
        from .config import load_nicknames
        self.nicknames: dict[str, str] = load_nicknames()  # model -> user's display name
        self.approve_plans = False  # True: the lead's plan waits for /approve or /discard
        self.assembly: Assembly | None = None  # pending /recommend \u2192 /go negotiation
        self.pending: tuple[str, list[Task]] | None = None  # (request, tasks) awaiting approval
        self.busy: set[str] = set()  # models holding a non-terminal task; enforces INVARIANT S-1
        self.all_tasks: list[Task] = []  # every task this session, for the busy set and /team

    # ---------- team: sleep, wake, lead (plan WS-2, WS-3, WS-10) ----------

    def asleep(self) -> list[str]:
        return [m for m in self.known if m not in self.members]

    def is_awake(self, model: str) -> bool:
        return model in self.members

    def can_sleep(self, model: str) -> tuple[bool, str]:
        """(allowed, reason). The UI disables its control from this rather than offering a
        button that is guaranteed to fail."""
        if model not in self.members:
            return False, f"{self.name(model)} is already asleep"
        if model == self.lead:
            return False, f"{self.name(model)} is the lead — `/lead <model>` first"
        if model in self.busy:
            held = ", ".join(f"{t.id} {t.title}" for t in self.all_tasks
                             if t.agent == model and t.status in BUSY_STATUSES)
            return False, f"{self.name(model)} is working on {held} — it can sleep once that finishes"
        return True, ""

    def sleep(self, model: str) -> str:
        """Put a model to sleep. INVARIANT S-1: refused outright while it holds a live task.

        A model mid-edit is writing real files in the room or in a relay worktree. Interrupting it
        to reclaim resources risks a half-written file and a worktree nobody can trust, and that is
        never worth the memory. There is deliberately no force and no queue: the caller retries
        after the task reaches a terminal state.
        """
        if model not in REGISTRY:
            raise TeamError(f"unknown model '{model}'")
        allowed, reason = self.can_sleep(model)
        if not allowed:
            raise TeamBusy(reason)
        self.members.remove(model)
        self.emit("team", {"action": "sleep", "model": model})
        return f"**{self.name(model)}** is asleep. Its history and journal stay readable — " \
               f"`/wake {model}` brings it back."

    def wake(self, model: str) -> str:
        """Bring a model back into the room. Re-checks the tool is actually available, so a
        model whose CLI was uninstalled cannot be woken into failing tasks."""
        if model not in REGISTRY:
            raise TeamError(f"unknown model '{model}'")
        if model in self.members:
            return f"**{self.name(model)}** is already in the room."
        if model in self.known and model not in REGISTRY.available():
            return f"**{self.name(model)}** cannot be woken: its CLI is not installed or its model " \
                   f"is not available to the provider right now."
        self.members.append(model)
        self.emit("team", {"action": "wake", "model": model})
        return f"**{self.name(model)}** is awake."

    def can_retire(self, model: str) -> tuple[bool, str]:
        """(allowed, reason) for /remove, which is stronger than /sleep: sleep keeps the model
        known so it comes back with `/wake`, retire drops it from this session entirely. It is
        refused for the lead and for a busy model for the same reasons as sleep — INVARIANT S-1 is
        about a model holding a live task, and a lead that is not in the room cannot answer."""
        if model not in self.known:
            return False, f"{self.name(model)} is not in this session"
        if model == self.lead:
            return False, f"{self.name(model)} is the lead — `/lead <model>` first"
        if model in self.busy:
            held = ", ".join(f"{t.id} {t.title}" for t in self.all_tasks
                             if t.agent == model and t.status in BUSY_STATUSES)
            return False, f"{self.name(model)} is working on {held} — it can be retired once that finishes"
        return True, ""

    def add(self, model: str) -> str:
        """Bring a model into this session for the first time: it becomes known *and* awake.

        Distinct from `/wake`, which revives a model that is already known (asleep). `/add` is for a
        model hexmind was not tracking — one discovered by `/scan`, or one registered in models.toml
        after the session started. An opt-in model is the whole point of this command: `--with` is
        how you ask for one at launch, and `/add NAME` is how you ask for one mid-session.

        Availability is re-checked here, not assumed: a model whose CLI is missing must not be
        added into failing tasks, which is the same guard `wake` uses."""
        if model not in REGISTRY:
            # Deliberately a hard boundary. The roster every prompt is generated from is
            # models.toml, so a model with no registry entry has no best_at, no avoid_for and no
            # colour, and adding one at runtime would mean a roster nothing else agrees with.
            # `/scan` finds what is installed; `/profile` is what turns a find into a member.
            raise TeamError(f"unknown model '{model}' — `/scan` finds what is installed, "
                            f"`/profile {model}` is what registers it")
        if model in self.known:
            if model in self.members:
                return f"**{self.name(model)}** is already in the room."
            return f"**{self.name(model)}** is already known and asleep — `/wake {model}` brings it back."
        if model not in REGISTRY.available():
            return f"**{self.name(model)}** cannot be added: its CLI is not installed or its model " \
                   f"is not available to the provider right now."
        self.known.append(model)
        self.members.append(model)
        self.emit("team", {"action": "add", "model": model})
        return f"**{self.name(model)}** is in the room. {REGISTRY.get(model).best_at}."

    def remove(self, model: str) -> str:
        """Take a model out of this session for good: asleep *and* no longer known, so it will not
        appear in `/team`, will not be offered by `/lead`, and `/add` is the only way back.

        Its registry entry, stats and journal are untouched — only this session forgets it, so
        nothing that was learned about the model is lost."""
        if model not in REGISTRY:
            raise TeamError(f"unknown model '{model}'")
        allowed, reason = self.can_retire(model)
        if not allowed:
            raise TeamBusy(reason)
        if model in self.members:
            self.members.remove(model)
        self.known.remove(model)
        self.emit("team", {"action": "remove", "model": model})
        return f"**{self.name(model)}** is out of the session. Its history stays on disk; " \
               f"`/add {model}` brings it back."

    def set_lead(self, model: str) -> str:
        """Change the leader mid-session. `lead` is read fresh at each use, so this is safe
        between turns; a turn already in flight keeps the lead it started with."""
        if model not in REGISTRY:
            raise TeamError(f"unknown model '{model}'")
        if model in TEXT_ONLY:
            raise TeamError(f"'{model}' is text-only (no file or tool access) and can't lead")
        if model not in self.members:
            if model not in REGISTRY.available():
                raise TeamError(f"'{model}' isn't installed, so it can't lead")
            self.members.append(model)  # leading implies being in the room
            if model not in self.known:
                self.known.append(model)  # ...and in this session: /remove can drop a model, and
                # a lead that is not in `known` would be invisible in /team while running the room
            self.emit("team", {"action": "wake", "model": model})
        previous = self.lead
        self.lead = model
        self.emit("team", {"action": "lead", "model": model, "previous": previous})
        return f"**{self.name(model)}** is the lead now" + \
               (f" (was {self.name(previous)})." if previous != model else ".")

    async def ask(self, agent: str, prompt: str, cwd: str | None = None, schema: dict | None = None) -> str:
        """backend.run, passing a JSON schema when the backend supports one; output is always cleaned."""
        if schema is not None and "schema" in inspect.signature(self.backend.run).parameters:
            return clean_text(await self.backend.run(agent, prompt, cwd=cwd, schema=schema))
        return clean_text(await self.backend.run(agent, prompt, cwd=cwd))

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

    # ---------- team assembly: /recommend, /go, /cancel ----------
    def _catalog(self) -> str:
        """Every model hexmind knows, with the strengths the lead routes on — wider than `_roster`,
        which describes the room. A recommendation has to be able to name a model that is not yet
        in it, which is the whole point of asking before the roster is settled."""
        lines = []
        for name in REGISTRY.by_weight([m for m in self.known if m in REGISTRY]):
            m = REGISTRY.get(name)
            lines.append(f"- {name}: {m.best_at} · not for {', '.join(m.avoid_for) or 'nothing in particular'}")
        return "\n".join(lines)

    def _track_record(self, members: list[str]) -> str:
        if not self.stats:
            return "No audit history yet. Judge on best_at and avoid_for alone.\n"
        table = self.stats.table(members)
        return table if table.startswith("|") else "No audit history yet. Judge on best_at and avoid_for alone.\n"

    async def recommend(self, request: str) -> str:
        """Ask the current lead which members it wants for this request. One call, no tools, and it
        changes nothing: the result is a proposal the user edits. The roster is not touched here."""
        if self.lead is None:
            raise TeamError("no lead yet — pick one with /lead NAME first")
        if not request.strip():
            raise TeamError("/recommend needs the request it is building a team for")
        if not self.known:
            raise TeamError("no models registered — check hexmind/models.toml")
        self.assembly = Assembly(request=request.strip(), room=list(self.members))
        self.emit("status", {"agent": self.lead, "state": "planning"})
        try:
            raw = await self.ask(self.lead, RECOMMEND_PROMPT.format(
                lead=self.name(self.lead), request=self.assembly.request,
                roster=self._catalog(), stats=self._track_record(list(self.known))),
                schema=RECOMMEND_SCHEMA)
        finally:
            self.emit("status", {"agent": self.lead, "state": "idle"})
        try:
            data = extract_json(raw)
            members = [m for m in (data.get("members") or []) if m in REGISTRY]
            reasons = {k: v for k, v in (data.get("reasons") or {}).items() if k in REGISTRY}
        except (ValueError, json.JSONDecodeError, AttributeError, TypeError):
            return f"**{self.name(self.lead)}** answered in prose instead of a team. Nothing changed — " \
                   f"try `/recommend` again, or build the room by hand with `/wake` and `/add`."
        if not members:
            return f"**{self.name(self.lead)}** could not name a single usable member for this. " \
                   f"Nothing changed — `/scan` looks for what is installed."
        self.assembly.recommended, self.assembly.reasons = members, reasons
        lines = [f"**{self.name(self.lead)} recommends** for __{request.strip()}__:", ""]
        for m in members:
            lines.append(f"- `{m}`" + (f" — {reasons[m]}" if m in reasons else ""))
        note = ("A proposal, not a decision. `/add` and `/remove` change the room, `/wake` and "
                "`/sleep` park members, then `/go` hands it back for a plan.")
        lines += ["", note]
        return "\n".join(lines)

    async def assemble_go(self):
        """Hand the room the user actually settled on back to the lead, which reviews the
        disagreement and plans against it. Falls back to the ordinary plan path when there is no
        pending assembly, so `/go` is never worse than typing the request."""
        assembly = self.assembly
        if assembly is None:
            return ""
        request, recommended, reasons = assembly.request, list(assembly.recommended), dict(assembly.reasons)
        actual = list(self.members)
        dropped, added = assembly.dropped(actual), assembly.added(actual)
        if not actual:
            self.assembly = None
            return "**The room is empty.** `/wake` or `/add` someone, then `/go` again."
        self.assembly = None  # consumed: a second /go must not re-review a spent assembly
        from .auditor import DOMAINS
        lines = []
        if dropped:
            lines.append(f"You asked for and the user dropped: {', '.join(dropped)}.")
        if added:
            lines.append(f"The user added: {', '.join(added)}.")
        self.emit("status", {"agent": self.lead, "state": "planning"})
        try:
            raw = await self.ask(self.lead, REVIEW_PROMPT.format(
                lead=self.name(self.lead), request=request,
                recommended=", ".join(recommended) or "(nothing)",
                reasons="\n".join(f"  {m}: {r}" for m, r in reasons.items()) + "\n" if reasons else "",
                actual=", ".join(actual),
                dropped=("\n".join(lines) + "\n") if lines else "",
                stats=self._track_record(actual), domains=", ".join(DOMAINS)),
                schema=PLAN_SCHEMA)
        finally:
            self.emit("status", {"agent": self.lead, "state": "idle"})
        try:
            reply, tasks = parse_plan(raw, actual, self.lead)
        except (ValueError, json.JSONDecodeError, AttributeError, TypeError):
            reply, tasks = raw.strip(), []
        if dropped or added:
            review = "\n".join(lines)
            reply = f"**Roster adjusted.** {review}\n\n{reply}" if reply else f"**Roster adjusted.** {review}"
        self.emit("message", {"from": self.lead, "text": reply})
        if not tasks:
            self.history.append((request, reply))
            return POSTED
        if self.approve_plans:
            self.pending = (request, tasks)
            self.emit("message", {"from": "hexmind", "text":
                                  "**Draft plan: nothing runs until you decide.** `/approve` to run it, "
                                  "`/discard` to drop it."})
            self.history.append((request, reply))
            return POSTED
        return await self.execute(request, tasks)

    def cancel_assembly(self) -> str:
        """Abandon the negotiation. The roster is untouched — it was never a copy — and the next
        request plans against the room as it stands."""
        if self.assembly is None:
            return "Nothing to cancel — no team is being assembled."
        who = self.assembly.request
        self.assembly = None
        return f"**Cancelled.** The proposal for _{who}_ is gone. The room is as you left it."

    async def handle(self, request: str) -> str:
        if request.startswith("/"):
            from .relay import command  # slash commands: /relay, /chains, /help
            reply = await command(self, request)
            self.history.append((request, reply))
            return reply
        self.emit("status", {"agent": self.lead, "state": "planning"})
        from .auditor import DOMAINS
        raw = await self.ask(self.lead, LEAD_PROMPT.format(
            roster=self._roster(), request=request, history=self._history(), domains=", ".join(DOMAINS)),
            schema=PLAN_SCHEMA)
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

        if self.approve_plans:
            self.pending = (request, tasks)
            lines = [f"- **{t.id}** → {self.name(t.agent)}: {t.title}" +
                     (f" _(after {', '.join(t.depends_on)})_" if t.depends_on else "") for t in tasks]
            note = "**Draft plan: nothing runs until you decide.** `/approve` to run it, `/discard` to drop it."
            self.emit("message", {"from": "hexmind", "text": note + "\n\n" + "\n".join(lines)})
            self.history.append((request, reply))
            return reply
        return await self.execute(request, tasks)

    async def execute(self, request: str, tasks: list[Task]) -> str:
        """Run an (approved) plan, then have the lead summarize."""
        self.record(tasks)
        self.emit("plan", {"tasks": tasks})
        await self.run_tasks(request, tasks)

        results = "\n\n".join(f"[{t.id}] {t.title} ({t.agent}, {t.status}):\n{clip(t.output)}" for t in tasks)
        self.emit("status", {"agent": self.lead, "state": "summarizing"})
        final = await self.ask(self.lead, SYNTH_PROMPT.format(request=request, results=results))
        self.emit("status", {"agent": self.lead, "state": "idle"})
        self.emit("message", {"from": self.lead, "text": final.strip()})
        self.history.append((request, final))
        return final

    def record(self, tasks: list[Task]) -> None:
        """Add tasks to the session log, once each. A plan is recorded before it runs and run_tasks
        records what it is given, so without the identity check every task would be listed twice —
        and /team, which counts tasks to decide who is busy, would name each id twice over."""
        for t in tasks:
            if not any(known is t for known in self.all_tasks):
                self.all_tasks.append(t)
        self.busy = {t.agent for t in self.all_tasks if t.status in BUSY_STATUSES}

    def record_note(self, t: Task) -> None:
        """Record a finished relay stage in its chain notes file — the file the next stage is told
        to read first, so it has to carry the failures too. Written on success only, a notes file
        reads as a clean run and the next stage reasons from a report that skipped the hole."""
        if not t.notes:
            return
        try:
            with open(t.notes, "a") as nf:
                nf.write(f"\n## {t.title} ({t.agent}) — {t.status}\n\n{t.output.strip()}\n")
        except OSError as e:  # an unwritable notes file must not fail the stage that just finished
            self.emit("message", {"from": "hexmind", "text": f"Could not write the relay notes: {e}"})

    async def run_tasks(self, request: str, tasks: list[Task], on_finish=None) -> None:
        """Run the graph. `on_finish(task)` is called once per task as it reaches a terminal state —
        done, failed, skipped, or cancelled — so a caller can act on stage boundaries (a relay
        isolation check compares the main folder after each stage). Every exit that ends a task goes
        through `_finish`, so a task is never reported twice and never missed."""
        by_id = {t.id: t for t in tasks}
        running: dict[asyncio.Task, Task] = {}
        self.record(tasks)

        def _sync_busy() -> None:
            """Recompute which models hold a live task. INVARIANT S-1 reads this, so it is
            derived from task state rather than tracked separately — the two cannot disagree."""
            self.busy = {t.agent for t in self.all_tasks if t.status in BUSY_STATUSES}

        def _finish(t: Task) -> None:
            self.record_note(t)  # after the status is set: a failed or skipped stage is still history
            _sync_busy()
            self.emit("task", {"task": t})
            if on_finish is not None:
                on_finish(t)

        def launch_ready():
            for t in tasks:
                if t.status != "pending":
                    continue
                deps = [by_id[d] for d in t.depends_on]
                if any(d.status in ("failed", "skipped") for d in deps):
                    t.status = "skipped"
                    _finish(t)
                elif all(d.status == "done" for d in deps):
                    t.status = "running"
                    _sync_busy()
                    self.emit("task", {"task": t})
                    running[asyncio.create_task(self._run_one(request, t, deps))] = t

        try:
            launch_ready()
            while running:
                finished, _ = await asyncio.wait(running, return_when=asyncio.FIRST_COMPLETED)
                for f in finished:
                    t = running.pop(f)
                    try:
                        t.output, t.status = clean_text(f.result()), "done"
                    except Exception as e:  # one agent failing must not kill the room
                        t.output, t.status = f"error: {e}", "failed"
                    _finish(t)
                launch_ready()
                # a skip can cascade; keep resolving until nothing changes
                while any(t.status == "pending" and any(by_id[d].status in ("failed", "skipped")
                                                        for d in t.depends_on) for t in tasks):
                    launch_ready()
        finally:
            # A cancelled turn (the user quit, or the run was interrupted) leaves its tasks still
            # marked running. Recomputing the busy set from that stale status would wedge those
            # models as unsleepable for the rest of the session, and leave the board claiming work
            # is in flight when nothing is. Mark them failed so the truth reaches the UI, and write
            # it to the relay notes too, so a cancelled chain has no silent hole in its record.
            for t in self.all_tasks:
                if t.status in BUSY_STATUSES:
                    t.output = t.output or "cancelled before it finished"
                    t.status = "failed"
                    self.record_note(t)
                    self.emit("task", {"task": t})
                    if on_finish is not None and any(t is mine for mine in tasks):
                        on_finish(t)  # a stage cut off mid-flight can still have left a mess
            _sync_busy()

    def _workspace_block(self, t: Task) -> str:
        """Spell out the file layout for a task that runs in its own folder.

        Without this the isolation is not real. A relay chain's notes file lives in the main
        folder, so every path a stage reads points at a different checkout, and an agent that
        follows one writes to main instead of its worktree. That happened silently once: the chain
        reported success and the changes were in the main checkout, not the isolated one.
        """
        if not t.cwd:
            return ""
        here, root = os.path.abspath(t.cwd), os.path.abspath(self.backend.cwd)
        if here == root:
            return ""  # an ordinary request in the room folder needs no map
        lines = ["", f"Your working directory is {here} — an isolated copy of this repository.",
                 "Create, edit and delete files there only."]
        if t.notes:
            lines.append(f"One exception: this is a relay stage, and the shared notes file "
                         f"{t.notes} is in the main checkout at {root}. Read it first; Hexmind "
                         f"appends your report to it, so do not edit it yourself.")
        lines.append(f"Do not modify anything under {root}, or in any other checkout or worktree "
                     "of this repository.")
        return "\n".join(lines) + "\n"

    async def _run_one(self, request: str, t: Task, deps: list[Task]) -> str:
        dep_text = "".join(f"\nResult of {d.id} ({d.title}, by {d.agent}):\n{clip(d.output)}\n" for d in deps)
        prompt = TASK_PROMPT.format(agent=t.agent, lead=self.lead, request=request, id=t.id,
                                    title=t.title, instructions=t.instructions,
                                    where=self._workspace_block(t),
                                    deps=("\nInputs from earlier phases:" + dep_text) if deps else "")
        if t.notes:
            prompt += (f"\nThis is one stage of a relay chain. Every earlier stage's full report is in {t.notes}"
                       " — read it first. Hexmind appends your final reply to it; don't edit it yourself.")
        tried = {t.agent}
        while True:
            try:
                if self.audit and self.stats is not None:
                    from .auditor import audited_run
                    auditors = [m for m in self.members if m not in TEXT_ONLY]  # auditors must inspect real files
                    return clean_text(await audited_run(self.backend, t, prompt, auditors, self.stats, self.emit))
                return await self.ask(t.agent, prompt, cwd=t.cwd)
            except RuntimeError as e:
                # backends prefix errors with the member name; only the primary's own quota failure hands off
                if not (str(e).startswith(t.agent) and QUOTA_RE.search(str(e))):
                    raise
                spare = self.fallback(t, tried)
                if spare is None:
                    raise
                self.emit("message", {"from": "hexmind", "text":
                          f"{self.name(t.agent)} is out of quota; handing **{t.id}** to {self.name(spare)}."})
                prompt = prompt.replace(f"You are {t.agent},", f"You are {spare},", 1)
                t.agent = spare
                tried.add(spare)
                self.emit("task", {"task": t})

    def fallback(self, t: Task, tried: set[str]) -> str | None:
        """Next-best member for this task's domain that hasn't been tried and can see local files."""
        spares = [m for m in self.members if m not in tried and m not in TEXT_ONLY]
        if not spares:
            return None
        return self.stats.ranked(spares, t.domain)[0] if self.stats else spares[0]

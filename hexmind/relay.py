"""Relay chains: an ordered list of stages, run by several models, optionally as N parallel chains.

A chain comes from one of three places:
  1. a chain file:  ~/.config/hexmind/chains/NAME.toml  or  hexmind/chains/NAME.toml
  2. imported stage definitions: a stage in a chain file can say `from = "<agent file>"`
     (Claude .md agents or Codex .toml agents); its instructions become that stage's prompt
  3. the lead: if NAME isn't a known chain, the whole text is a goal and the lead designs the stages

Room usage:
  /relay NAME|GOAL [-n 3] [--assign rotate|best|pinned] [--workspace shared|worktree] [--end merge|compare|list]
  /chains     list chain files
"""
from __future__ import annotations

import argparse
import os
import shlex
import subprocess
import time
import tomllib
from dataclasses import dataclass
from pathlib import Path

from .core import Task, clip, extract_json

CHAIN_DIRS = [Path.home() / ".config/hexmind/chains", Path(__file__).parent / "chains"]
LABELS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"

# Where agent files live, searched in order when a stage names an agent instead of a path.
# A stage may say `from = "rip-it-apart-recon-mapper.md"` and mean "the one I already wrote",
# which is the common case: agents are per-user, not per-package.
AGENT_DIRS = [Path.home() / ".claude/agents", Path.home() / ".agents/agents",
              Path(".claude/agents"), Path(".agents/agents")]


def resolve_agent_file(ref: str) -> Path | None:
    """Find an agent file given a full path, or a bare filename to look up in AGENT_DIRS.

    A reference that looks like a path (it contains a separator) is never searched for by name:
    if you wrote a path and it is not there, that is an error to report, not a hint to go looking.
    """
    direct = Path(ref).expanduser()
    if direct.is_file():
        return direct
    if "/" in ref or "\\" in ref:
        return None
    for directory in AGENT_DIRS:
        for name in (ref, f"{ref}.md", f"{ref}.toml"):
            candidate = directory / name
            if candidate.is_file():
                return candidate
    return None


@dataclass
class Stage:
    name: str
    instructions: str
    agent: str | None = None  # pinned model, used by --assign pinned
    domain: str = "general"
    gate: bool = False


@dataclass
class Chain:
    name: str
    description: str
    stages: list[Stage]


# ---------- loading ----------

def read_agent_file(path: str) -> str:
    """Instructions from a Claude agent (.md, frontmatter stripped) or Codex agent (.toml)."""
    p = Path(path).expanduser()
    text = p.read_text()
    if p.suffix == ".toml":
        data = tomllib.loads(text)
        return data.get("developer_instructions") or data.get("instructions") or data.get("description", "")
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) == 3:
            return parts[2].strip()
    return text


class BrokenChain(ValueError):
    """A chain file that can't be loaded (bad TOML, no stages, missing `from =` agent file)."""


def load_chain(path: Path) -> Chain:
    try:
        data = tomllib.loads(path.read_text())
    except tomllib.TOMLDecodeError as e:
        raise BrokenChain(f"invalid TOML in {path}: {e}") from e
    stages = []
    for s in data.get("stages", []):
        instr = s.get("instructions", "")
        if s.get("from"):
            found = resolve_agent_file(s["from"])
            if found is None:
                hint = "" if "/" in s["from"] else f" (also looked for a file named this in: " \
                                                       f"{', '.join(str(d) for d in AGENT_DIRS)})"
                raise BrokenChain(f"missing {s['from']}{hint}")
            instr = read_agent_file(str(found))
        stages.append(Stage(s.get("name", f"stage {len(stages) + 1}"), instr, s.get("agent"),
                            s.get("domain", "general"), s.get("gate") is True))
    if not stages:
        raise BrokenChain(f"{path} has no [[stages]]")
    return Chain(data.get("name", path.stem), data.get("description", ""), stages)


def list_chains() -> dict[str, Path]:
    found: dict[str, Path] = {}
    for d in reversed(CHAIN_DIRS):  # user dir listed first wins, so load it last
        if d.is_dir():
            found.update({p.stem: p for p in sorted(d.glob("*.toml"))})
    return found


# ---------- assignment ----------

def assign(chain: Chain, n: int, members: list[str], mode: str, best: list[str] | None = None) -> list[list[str]]:
    """agents[k][i] = model running stage i of chain k."""
    grid = []
    for k in range(n):
        row = []
        for i, st in enumerate(chain.stages):
            if mode == "pinned" and st.agent in members:
                row.append(st.agent)
            elif mode == "best" and best:
                row.append(best[i])
            else:  # rotate: every chain starts on a different model, so all stay busy
                row.append(members[(i + k) % len(members)])
        grid.append(row)
    return grid


def build_tasks(chain: Chain, grid: list[list[str]], goal: str, cwds: list[str], notes: list[str]) -> list[Task]:
    tasks = []
    for k, row in enumerate(grid):
        prev = None
        for i, (st, agent) in enumerate(zip(chain.stages, row)):
            tid = f"{LABELS[k]}{i + 1}"
            tasks.append(Task(id=tid, title=f"{LABELS[k]}·{st.name}", agent=agent,
                              instructions=f"Relay goal: {goal}\n\nStage {i + 1}/{len(chain.stages)} "
                                           f"of chain '{chain.name}' ({st.name}):\n{st.instructions}",
                              depends_on=[prev] if prev else [], cwd=cwds[k], notes=notes[k],
                              domain=st.domain, gate=st.gate))
            prev = tid
    return tasks


# ---------- workspaces ----------

def make_workspaces(root: str, run: str, n: int, mode: str) -> tuple[list[str], list[str]]:
    """Returns (cwd per chain, notes file per chain). Notes live in the main folder's .hexmind/."""
    run_dir = Path(root) / ".hexmind" / "runs" / run
    run_dir.mkdir(parents=True, exist_ok=True)
    (Path(root) / ".hexmind" / ".gitignore").write_text("*\n")  # keep run files out of the user's repo
    notes = [str(run_dir / f"chain-{LABELS[k]}.md") for k in range(n)]
    for k, path in enumerate(notes):
        Path(path).write_text(f"# Chain {LABELS[k]} notes ({run})\n")
    if mode == "shared":
        return [root] * n, notes
    cwds = []
    for k in range(n):
        wt = Path(root) / ".hexmind" / "worktrees" / f"{run}-{LABELS[k]}"
        branch = f"hexmind/{run}-{LABELS[k]}"
        r = subprocess.run(["git", "-C", root, "worktree", "add", "-q", "-b", branch, str(wt)],
                           capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(f"git worktree failed (is {root} a git repo with a commit?): {r.stderr.strip()}")
        cwds.append(str(wt))
    return cwds, notes


# ---------- lead calls ----------

DESIGN_PROMPT = """Design a relay chain for an AI agent team. Goal:
{goal}

Team members: {members}

Break the goal into 3-7 sequential stages. Each stage is done by one agent who reads all
earlier stages' reports, so each stage should build on the last. Answer ONLY with JSON:
{{"name": "short-chain-name", "stages": [{{"name": "short stage name", "instructions": "complete instructions for this stage"}}]}}"""

BEST_PROMPT = """Pick the best team member for each stage of this chain.
Team: {roster}

Stages:
{stages}

Answer ONLY with JSON: {{"agents": ["<member for stage 1>", "<member for stage 2>", ...]}}"""

DESIGN_SCHEMA = {
    "type": "object",
    "properties": {"name": {"type": "string"}, "stages": {"type": "array", "items": {"type": "object", "properties": {
        "name": {"type": "string"}, "instructions": {"type": "string"}}, "required": ["name", "instructions"]}}},
    "required": ["name", "stages"],
}

END_PROMPTS = {
    "merge": "Merge the chains' results into ONE combined result for the user. Findings several chains agree on "
             "are high confidence; flag findings only one chain reported as needing a second look.",
    "compare": "Compare the chains side by side: where they agree, where they disagree, and which chain's "
               "result is strongest and why.",
}

END_WRAPPER = """You are the lead of an AI agent team. {n} relay chain(s) of '{chain}' just ran. Goal: {goal}

Chain notes files (full stage-by-stage reports): {notes}
Work folders: {cwds}

How each stage ended (a failed or skipped stage produced no result, whatever any report claims):
{statuses}

Final stage report of each chain:
{finals}

{instruction}
Be concise; point to files rather than repeating them."""


def dirty_paths(root: str) -> set[str] | None:
    """Tracked-or-untracked paths that differ from HEAD in `root`, as git reports them.

    `.hexmind/` carries its own `.gitignore` of `*`, so the notes files and the per-chain worktrees
    are invisible here — which is exactly what makes this usable as an isolation check: anything
    that shows up was written outside the chain's own folder.

    `None` means "could not tell": a folder that is not a git repo, a git error, or a timeout. An
    empty set means clean, and the two must never look alike — this returning an empty set on any
    failure made a check that could not answer report the same thing as a check that passed.

    `-z` is not optional here. The default porcelain quoting turns a file called `naïve.py` into
    `"na\\303\\257ve.py"`, so the leak was reported under a path that does not exist, and a rename
    came back as one line holding two quoted paths. `-z` prints them NUL-separated and unmunged.
    """
    try:
        out = subprocess.run(["git", "-C", root, "status", "--porcelain", "-z"],
                             capture_output=True, text=True, encoding="utf-8",
                             errors="surrogateescape", timeout=20)
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:  # not a git repo, or git could not read the tree
        return None
    paths, skip = set(), False
    for field in out.stdout.split("\0"):
        if skip:  # a rename/copy's source path, in a field of its own; the destination is the one taken
            skip = False
            continue
        if len(field) < 4:  # "XY path", and the empty field after the final NUL
            continue
        status = field[:2]
        skip = "R" in status or "C" in status  # -z puts the source path in the next field
        paths.add(field[3:])
    return paths


class Isolation:
    """Watch the main folder's git state across a run, one stage at a time.

    Telling a stage which directory is its own is a soft control, so the state is compared rather
    than trusted. One comparison for the whole chain was no good: a breach is then only reported
    once the last stage is done, and the only stage the report could name is the one that did
    nothing wrong. So the comparison runs at every stage boundary, and whatever appeared is
    escalated while the stage it appeared under is still the one the room is waiting on.

    A snapshot git cannot produce is remembered as unknown. `unavailable` means the run could not
    compare the folder's whole state, which is not the same claim as "isolation held".
    """

    def __init__(self, root: str, say):
        self.root, self.say = root, say
        self.seen: set[str] | None = dirty_paths(root)  # the baseline, or None if git could not say
        self.unavailable = self.seen is None
        self.breaches: list[tuple[Task, list[str]]] = []  # (the stage, the paths it was caught by)

    def stage_finished(self, t: Task) -> None:
        now = dirty_paths(self.root)
        if now is None:
            self.unavailable = True
            return
        # With no baseline the first answer git does give is a baseline, not a diff: the folder may
        # have been dirty before the relay started, and that is not this stage's doing.
        fresh = sorted(now - self.seen) if self.seen is not None else []
        self.seen = now
        if not fresh:
            return
        self.breaches.append((t, fresh))
        listing = "\n".join(f"- `{p}`" for p in fresh)
        self.say(f"**ESCALATION: relay stage {t.id} ({t.title}, by {t.agent}) wrote outside its own "
                 f"worktree.**\n\n`--workspace worktree` was supposed to keep this run's changes "
                 f"inside its worktree, but these paths changed in the main folder `{self.root}` "
                 f"while {t.id} was the stage running:\n{listing}\n\nThe stage prompt names each "
                 f"stage's directory, and this check reports it either way — but an agent that "
                 f"ignored both still put its work somewhere the chain did not intend. Inspect "
                 f"before committing anything.")


# ---------- /commands ----------

def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="/relay", add_help=False, exit_on_error=False)
    p.add_argument("target", nargs="+", help="chain name, or a goal for the lead to design a chain for")
    p.add_argument("-n", "--chains", type=int, default=1)
    p.add_argument("--assign", choices=["rotate", "best", "pinned"], default="rotate")
    p.add_argument("--workspace", choices=["shared", "worktree"])
    p.add_argument("--end", choices=["merge", "compare", "list"], default="merge")
    return p


def _parse_relay(args: list[str]):
    """Parse /relay args, with --goal consuming the rest of the line verbatim.

    A goal is a sentence, so it can contain anything — including a word that looks like a flag
    ("print the first line on --once"). Both narrower fixes break on that: nargs="+" swallows
    the real flags that follow, and leaving it single-valued means an unquoted sentence arrives
    as "unrecognized arguments". So everything after --goal is the goal, joined, and the options
    must come before it. That is also how people type it.
    """
    if "--goal" not in args:
        ns = _parser().parse_args(args)
        ns.goal = None
        return ns
    split = args.index("--goal")
    head, tail = args[:split], args[split + 1:]
    if not tail:
        raise ValueError("--goal needs some text after it")
    ns = _parser().parse_args(head)
    ns.goal = " ".join(tail)
    return ns


HELP = """**Commands**
- `/relay NAME|GOAL [-n 3] [--assign rotate|best|pinned] [--workspace shared|worktree] [--end merge|compare|list] [--goal TEXT]`
  run a chain; `x3` works as `-n 3`. Unknown NAME = a goal the lead designs stages for.
- `/chains` list chain files
- `/audit on|off` runner-up model reviews every task (bounded revise loop; `gate = true` tasks block on failure)
- `/ranks` each model's audit track record by domain
- `/drafts on|off` the lead's plan waits for approval before anything runs · `/approve` run it · `/discard` drop it
- `/nick MODEL NAME` give a model a nickname · `/nick MODEL` clear it · `/nick` list
- `/team` the roster: who is awake, who is asleep, and what each model is for
- `/models` every known model, what it is best at, and whether it is installed
- `/model NAME` one model's full card
- `/sleep NAME` put a model to sleep · `/wake NAME` bring it back
- `/lead [NAME|recommend]` show, change, or ask the team who should lead
- `/help` this list"""


def _team_rows(orch) -> list[str]:
    """One line per known model: awake/asleep, busy, and what it is for. Shared by /team and
    /models so the two can never describe the roster differently."""
    from .core import BUSY_STATUSES, REGISTRY

    live = set(REGISTRY.available())
    rows = []
    for name in REGISTRY.by_weight():
        m = REGISTRY.get(name)
        if name in orch.members:
            state = "**lead**" if name == orch.lead else "awake"
            if name in orch.busy:
                held = [t for t in orch.all_tasks if t.agent == name and t.status in BUSY_STATUSES]
                state += f" · working {', '.join(t.id for t in held)}"
        elif name in live:
            state = "asleep"
        else:
            state = "not installed"
        rows.append(f"- `{name}` — {state} · {m.label}: {m.best_at}")
    return rows


async def _cmd_team(orch, args: list[str]) -> str:
    from .core import REGISTRY

    if args and args[0] in REGISTRY:
        return REGISTRY.describe(args[0])
    awake = len(orch.members)
    asleep = len(orch.asleep())
    lines = [f"**Team** — {awake} awake, {asleep} asleep, lead **{orch.name(orch.lead)}**", ""]
    lines += _team_rows(orch)
    lines += ["", "A model that is working cannot be put to sleep until its task finishes. "
              "`/sleep NAME` · `/wake NAME` · `/lead NAME` · `/model NAME`"]
    return "\n".join(lines)


async def _cmd_sleep_wake(orch, args: list[str], sleeping: bool) -> str:
    from .core import REGISTRY, TeamBusy, TeamError

    if not args:
        verb = "/sleep" if sleeping else "/wake"
        return f"Which model? e.g. `{verb} opencode-ling` — `/team` lists them all."
    name = args[0]
    try:
        return orch.sleep(name) if sleeping else orch.wake(name)
    except TeamBusy as e:
        return f"**Not now.** {e}"
    except TeamError as e:
        return f"**{e}** — `/team` lists the known models."


async def _cmd_lead(orch, args: list[str]) -> str:
    from .core import REGISTRY, TeamError

    if not args:
        rows = [f"- `{m}` — {REGISTRY.get(m).label}: {REGISTRY.get(m).best_at}"
                for m in REGISTRY.by_weight(orch.members)]
        return f"**Lead is {orch.name(orch.lead)}.** Change it with `/lead NAME`, " \
               f"or ask the team with `/lead recommend`.\n\n" + "\n".join(rows)
    if args[0] == "recommend":
        return await _lead_recommend(orch)
    try:
        return orch.set_lead(args[0])
    except TeamError as e:
        return f"**{e}**"


RECOMMEND_PROMPT = """You are advising the user of a room of AI agent teammates. \
{lead} is the current lead and is stepping back.

Team members and what each is for:
{roster}

Track record (first-attempt peer-audit results, passed/audited):
{stats}

The lead plans the work, assigns tasks, summarises for the user, and is the one whose \
judgement the room trusts. It does not need to be the strongest coder; it needs to be good \
at decomposition, delegation and honest summarising.

Recommend the best successor. Weigh the track record heavily, but note that a model with no \
audits yet is not proven bad. Answer ONLY with JSON:
{{"recommendation": "<member name>", "reason": "<two sentences, concrete>", "runner_up": "<member name>"}}"""


async def _lead_recommend(orch) -> str:
    """Ask the room who should lead, then tell the user who to promote.

    The current lead is excluded from the candidates: a model asked to name its own successor
    is being asked to grade itself, which is the one judgement its own track record cannot
    inform. The user applies the change with /lead NAME.
    """
    from .core import REGISTRY, TEXT_ONLY, extract_json

    candidates = [m for m in orch.members if m not in TEXT_ONLY and m != orch.lead]
    if not candidates:
        return "There is no one else in the room who can lead — every other member is asleep " \
               "or text-only. `/wake NAME` first."
    # The advisor is the best-tracked member who is NOT the outgoing lead, so the person being
    # replaced is never the one grading the replacement. The lead appears in the prompt as
    # context ("is stepping back") but is not asked.
    advisor = orch.stats.ranked(candidates, "general")[0] if orch.stats else candidates[0]
    roster = "\n".join(f"- {m}: {REGISTRY.get(m).best_at}" for m in candidates)
    table = orch.stats.table(candidates) if orch.stats else "No audit results yet."
    raw = await orch.ask(advisor, RECOMMEND_PROMPT.format(lead=orch.lead, roster=roster, stats=table))
    try:
        data = extract_json(raw)
        pick = data.get("recommendation")
    except Exception:
        pick = None
    # A recommendation may name a model that is currently asleep — promoting it wakes it, and
    # "you should promote opencode-ultra, it is idle but it is the right pick" is a real answer.
    # What cannot be recommended is a text-only model, which can never lead.
    leadable = {m for m in REGISTRY.names() if m not in TEXT_ONLY}
    if pick not in leadable:
        best = orch.stats.ranked(candidates, "general")[0] if orch.stats else candidates[0]
        return (f"**{orch.name(advisor)}** did not name a valid successor, so this is the track "
                f"record's own pick: **{orch.name(best)}**. Apply it with `/lead {best}`.")
    reason = str(data.get("reason", "")).strip()
    runner = data.get("runner_up")
    asleep_note = "" if pick in orch.members else f"\n\n`{pick}` is asleep right now — promoting it wakes it."
    out = (f"Advised by **{orch.name(advisor)}**: **{orch.name(pick)}** should replace "
           f"**{orch.name(orch.lead)}** as lead." + (f" {reason}" if reason else "") + asleep_note)
    if runner in leadable:
        out += f"\n\nRunner-up: **{orch.name(runner)}** — `/lead {runner}` if you'd rather not switch."
    return out + "\n\nThe team is only advising; nothing changes until you run `/lead`."


async def command(orch, text: str) -> str:
    try:
        parts = shlex.split(text)
    except ValueError:  # natural language: "/relay fix the user's bug" has an unpaired quote
        parts = text.split()
    cmd, args = parts[0], parts[1:]
    if cmd == "/chains":
        lines = []
        for n, p in list_chains().items():
            try:
                c = load_chain(p)
                lines.append(f"- **{n}** ({len(c.stages)} stages): {c.description}")
            except BrokenChain as e:
                lines.append(f"- **{n}** (broken: {e})")
        reply = "\n".join(lines) or "No chain files. Add some to ~/.config/hexmind/chains/"
    elif cmd == "/drafts":
        if args and args[0] in ("on", "off"):
            orch.approve_plans = args[0] == "on"
        reply = f"Draft plans are **{'on' if orch.approve_plans else 'off'}**" + (
            ": the lead's plan waits for `/approve` or `/discard`." if orch.approve_plans else ": plans run right away.")
    elif cmd in ("/approve", "/discard"):
        if not orch.pending:
            reply = "No draft plan is waiting."
        else:
            request, tasks = orch.pending
            orch.pending = None
            if cmd == "/discard":
                reply = f"Discarded the draft plan ({len(tasks)} tasks). Nothing ran."
            else:
                return await orch.execute(request, tasks)  # execute posts its own messages
    elif cmd == "/audit":
        if args and args[0] in ("on", "off"):
            orch.audit = args[0] == "on"
        reply = f"Peer audit is **{'on' if orch.audit else 'off'}**."
    elif cmd == "/nick":
        from .config import save_nicknames
        if len(args) >= 2 and args[0] in orch.members:
            orch.nicknames[args[0]] = " ".join(args[1:])
            save_nicknames(orch.nicknames)
        elif len(args) == 1 and args[0] in orch.members:
            orch.nicknames.pop(args[0], None)
            save_nicknames(orch.nicknames)
        elif args:
            orch.emit("message", {"from": "hexmind", "text": f"Unknown model `{args[0]}`. Team: {', '.join(orch.members)}"})
            return "unknown model"
        reply = "**Nicknames**\n" + "\n".join(f"- {m} → **{orch.name(m)}**" if m in orch.nicknames
                                                else f"- {m} _(no nickname)_" for m in orch.members)
    elif cmd in ("/team", "/models", "/model"):
        reply = await _cmd_team(orch, args)
    elif cmd == "/sleep":
        reply = await _cmd_sleep_wake(orch, args, sleeping=True)
    elif cmd == "/wake":
        reply = await _cmd_sleep_wake(orch, args, sleeping=False)
    elif cmd == "/lead":
        reply = await _cmd_lead(orch, args)
    elif cmd == "/ranks":
        table = orch.stats.table(orch.members) if orch.stats else ""
        for m in orch.nicknames:
            table = table.replace(f"| {m} |", f"| {orch.name(m)} ({m}) |")
        reply = table if table.startswith("|") else "No audit results yet. Turn on `/audit on` and give the team work."
    elif cmd == "/relay":
        args = [f"-n{a[1:]}" if a.lower().startswith("x") and a[1:].isdigit() else a for a in args]
        if args and args[0] == "clean":
            # a subcommand, not a chain name — intercept before the lead would try to design
            # a chain called "clean"
            return _relay_clean(orch, args[1:])
        try:
            ns = _parse_relay(args)
        except (argparse.ArgumentError, SystemExit, ValueError) as e:
            # ValueError too: an empty --goal is a ValueError, and it used to escape as a crash
            # instead of being reported like every other bad argument on this line.
            reply = f"Bad /relay arguments: {e}\n\n{HELP}"
        else:
            try:
                return await run_relay(orch, ns)  # run_relay posts its own messages
            except BrokenChain as e:
                reply = f"Chain `{' '.join(ns.target)}` is broken: {e}"
            except (ValueError, RuntimeError, OSError) as e:  # bad lead JSON, git worktree, agent failure
                reply = f"Relay failed: {e}"
    else:
        reply = HELP
    orch.emit("message", {"from": "hexmind", "text": reply})
    return reply


def _run_candidates(root: str) -> list:
    """Every worktree/branch pair under .hexmind, named the way make_workspaces names them.

    Built here rather than in reaping.py so the layout knowledge stays beside the code that
    creates it — if the naming changes, this changes with it instead of quietly finding nothing.
    """
    from .reaping import Candidate

    found = []
    worktrees = Path(root) / ".hexmind" / "worktrees"
    for wt in sorted(worktrees.glob("*")) if worktrees.is_dir() else []:
        name = wt.name
        if "-" not in name:
            continue
        run, _, label = name.rpartition("-")
        found.append(Candidate(run=run, label=label, worktree=wt, branch=f"hexmind/{name}"))
    return found


def _active_runs(root: str) -> set[str]:
    """Runs currently executing, per the marker run_relay writes.

    The marker holds the run id and the pid that owns it, and a run counts as active only while
    that pid is alive. A `finally` was the obvious alternative and is wrong here: it does not run
    on SIGKILL, and `backends.py` kills process groups, so a killed run would leave itself marked
    active forever and /relay clean would skip it permanently.

    A pid that has been reused makes a dead run look active, which is the safe direction to be
    wrong in — we decline to reap something we should have.
    """
    try:
        lines = (Path(root) / ".hexmind" / "active").read_text().split()
    except OSError:
        return set()
    if len(lines) < 2:
        return set()
    run, pid = lines[0], lines[1]
    try:
        os.kill(int(pid), 0)
    except (ValueError, ProcessLookupError, PermissionError, OSError):
        return set()
    return {run}


def _relay_clean(orch, args: list[str]) -> str:
    """`/relay clean` lists; `/relay clean --force` removes what is safe and refuses the rest."""
    from .reaping import ACTIVE, DIRTY, MISSING, SAFE, UNMERGED, classify, remove_one

    force = "--force" in args
    with_notes = "--all" in args
    root = orch.backend.cwd
    try:
        report = classify(root, _run_candidates(root), active_runs=_active_runs(root))
    except Exception as e:  # a folder that is not a git repo at all
        return f"**Cannot inspect relay runs in `{root}`**: {e}"

    by = {c.run: c for c in report.candidates}
    lines = ["**Relay runs**", ""]
    if not report.candidates:
        lines.append("No relay worktrees found. Nothing to clean.")
    for c in sorted(report.candidates, key=lambda c: (c.verdict != SAFE, c.run, c.label)):
        mark = {"safe": "**safe**", "dirty": "⚠️ dirty", "unmerged": "⚠️ unmerged",
                "active": "⏳ active", "missing": "gone"}[c.verdict]
        line = f"- `{c.run}` chain {c.label} — {mark}"
        if c.reason:
            line += f": {c.reason}"
        lines.append(line)

    safe = [c for c in report.candidates if c.verdict == SAFE]
    if not force:
        held = [c for c in report.candidates if c.verdict in (DIRTY, UNMERGED, ACTIVE)]
        lines += ["", f"**{len(safe)}** run(s) could be removed. `/relay clean --force` to do it."]
        if held:
            lines.append(f"**{len(held)}** will be kept, and the reason is above — the dirty ones "
                         f"hold work that exists nowhere else.")
        return "\n".join(lines)

    for c in safe:
        problem = remove_one(root, c)
        if problem:
            report.problems.append(problem)
        else:
            report.removed.append(c)
    lines.append("")
    if report.removed:
        lines.append(f"Removed {len(report.removed)} worktree(s) and branch(es): "
                     + ", ".join(f"`{c.run}`" for c in report.removed))
    else:
        lines.append("Nothing was safe to remove.")
    if with_notes:
        for c in report.removed:
            run_dir = Path(root) / ".hexmind" / "runs" / c.run
            if run_dir.is_dir():
                for f in run_dir.glob("chain-*.md"):
                    f.unlink()
        lines.append("Stage reports deleted (`--all`).")
    else:
        lines.append("Stage reports kept — `/relay clean --all` removes those too.")
    for p in report.problems:
        lines.append(f"⚠️ {p}")
    reply = "\n".join(lines)
    orch.emit("message", {"from": "hexmind", "text": reply})
    return reply


async def run_relay(orch, ns) -> str:
    say = lambda text: orch.emit("message", {"from": "hexmind", "text": text})
    root = orch.backend.cwd
    chains = list_chains()
    target = " ".join(ns.target)
    n = max(1, min(ns.chains, len(LABELS)))

    if len(ns.target) == 1 and target in chains:
        chain = load_chain(chains[target])
        goal = ns.goal or chain.description or chain.name
    else:  # the lead designs the chain
        goal = target + (f"\n{ns.goal}" if ns.goal else "")
        orch.emit("status", {"agent": orch.lead, "state": "designing chain"})
        raw = await orch.ask(orch.lead, DESIGN_PROMPT.format(goal=goal, members=", ".join(orch.members)),
                             schema=DESIGN_SCHEMA)
        orch.emit("status", {"agent": orch.lead, "state": "idle"})
        data = extract_json(raw)
        stages = data.get("stages")
        stages = stages if isinstance(stages, list) else []
        # models sometimes send plain strings instead of stage objects; anything else is dropped
        chain = Chain(str(data.get("name") or "custom"), goal,
                      [Stage(str(s.get("name") or f"stage {i + 1}"), str(s.get("instructions", ""))) if isinstance(s, dict)
                       else Stage(f"stage {i + 1}", s)
                       for i, s in enumerate(x for x in stages if isinstance(x, (dict, str)))])
        if not chain.stages:
            raise ValueError("lead designed an empty chain")

    best = None
    if ns.assign == "best":
        stages = "\n".join(f"{i + 1}. {s.name}: {s.instructions[:300]}" for i, s in enumerate(chain.stages))
        raw = await orch.ask(orch.lead, BEST_PROMPT.format(roster=orch._roster(), stages=stages),
                             schema={"type": "object", "properties": {"agents": {"type": "array", "items": {"type": "string"}}},
                                     "required": ["agents"]})
        picks = extract_json(raw).get("agents")
        picks = picks if isinstance(picks, list) else []
        best = [a if a in orch.members else orch.lead for a in picks] + [orch.lead] * len(chain.stages)
    from .core import TEXT_ONLY
    workers = [m for m in orch.members if m not in TEXT_ONLY] or orch.members
    grid = assign(chain, n, workers if ns.assign == "rotate" else orch.members, ns.assign, best)

    # several chains editing one folder would collide; default them into their own worktrees
    workspace = ns.workspace or ("worktree" if n > 1 and (Path(root) / ".git").exists() else "shared")
    run = time.strftime("%Y%m%d-%H%M%S")
    cwds, notes = make_workspaces(root, run, n, workspace)
    tasks = build_tasks(chain, grid, goal, cwds, notes)
    # /relay clean must not reap a run that is still going. The marker records this pid so a
    # run that was killed goes stale on its own: a `finally` would not survive SIGKILL, and
    # backends.py kills process groups.
    try:
        (Path(root) / ".hexmind" / "active").write_text(f"{run}\n{os.getpid()}\n")
    except OSError:
        pass
    table = "| chain | " + " | ".join(s.name for s in chain.stages) + " |\n|" + "---|" * (len(chain.stages) + 1) + "\n"
    table += "\n".join(f"| {LABELS[k]} | " + " | ".join(orch.name(a) for a in row) + " |" for k, row in enumerate(grid))
    say(f"**Relay `{chain.name}`**: {n} chain(s) × {len(chain.stages)} stages · assign={ns.assign} · "
        f"workspace={workspace}\n\n{table}\n\nNotes: `{Path(notes[0]).parent}`")

    orch.emit("plan", {"tasks": tasks})
    # Isolation is checked, not trusted. The task prompt names each stage's own directory, but a
    # prompt is a soft control: an agent that follows a path out of the shared notes file writes to
    # the main checkout and the chain still reports success. So the main folder's dirty state is
    # compared at every stage boundary — comparing it once at the end reported a breach only after
    # the last stage, attributed to whichever stage happened to be last.
    # Only check when workspace="worktree"; shared mode legitimately writes to the main folder.
    check = Isolation(root, say) if workspace == "worktree" else None
    await orch.run_tasks(goal, tasks, on_finish=check.stage_finished if check else None)
    if check and check.unavailable:
        say(f"**Isolation check unavailable.** `git status` could not report the state of the main "
            f"folder `{root}` at least once during this run, so it cannot claim isolation held — "
            f"treat that as unchecked, not clean. (A folder that is not a git repo, a git error and "
            f"a timeout all look like this.)")
    breaches = check.breaches if check else []
    leaked = sorted({p for _, paths in breaches for p in paths})
    per_chain = [tasks[k * len(chain.stages):(k + 1) * len(chain.stages)] for k in range(n)]
    status = "\n".join(f"- chain {LABELS[k]}: " + ", ".join(f"{t.id} {t.status}" for t in ts)
                       for k, ts in enumerate(per_chain))
    if leaked:  # in the status block too, so the final summary cannot present the run as clean
        blamed = ", ".join(t.id for t, _ in breaches)
        status += f"\n- **isolation breach:** {len(leaked)} path(s) written outside the worktree, by {blamed}"
    if check and check.unavailable:
        status += f"\n- **isolation check unavailable:** git could not read `{root}`; isolation unverified"
    if ns.end == "list":
        final = f"**Relay finished.**\n{status}\n\nFull reports: `{Path(notes[0]).parent}`"
        say(final)
        return final

    finals = "\n\n".join(f"Chain {LABELS[k]}: " + next((f"{t.title} ({t.agent}):\n{clip(t.output, 3000)}"
                                                         for t in reversed(ts) if t.status == "done"), "no stage finished")
                         for k, ts in enumerate(per_chain))
    orch.emit("status", {"agent": orch.lead, "state": f"{ns.end} results"})
    # `finals` is only the last stage that finished, so a stage that was gated off is invisible in
    # it. The statuses go in too, or the summary can call a failed stage a success.
    final = await orch.ask(orch.lead, END_WRAPPER.format(
        n=n, chain=chain.name, goal=goal, notes=", ".join(notes), cwds=", ".join(dict.fromkeys(cwds)),
        statuses=status, finals=finals, instruction=END_PROMPTS[ns.end]))
    orch.emit("status", {"agent": orch.lead, "state": "idle"})
    final = f"{final.strip()}\n\n{status}"
    orch.emit("message", {"from": orch.lead, "text": final})
    return final


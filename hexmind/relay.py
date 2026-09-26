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
import shlex
import subprocess
import time
import tomllib
from dataclasses import dataclass
from pathlib import Path

from .core import Task, clip, extract_json

CHAIN_DIRS = [Path.home() / ".config/hexmind/chains", Path(__file__).parent / "chains"]
LABELS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


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


def load_chain(path: Path) -> Chain:
    data = tomllib.loads(path.read_text())
    stages = []
    for s in data.get("stages", []):
        instr = read_agent_file(s["from"]) if s.get("from") else s.get("instructions", "")
        stages.append(Stage(s.get("name", f"stage {len(stages) + 1}"), instr, s.get("agent"),
                            s.get("domain", "general"), s.get("gate") is True))
    if not stages:
        raise ValueError(f"{path} has no [[stages]]")
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

END_PROMPTS = {
    "merge": "Merge the chains' results into ONE combined result for the user. Findings several chains agree on "
             "are high confidence; flag findings only one chain reported as needing a second look.",
    "compare": "Compare the chains side by side: where they agree, where they disagree, and which chain's "
               "result is strongest and why.",
}

END_WRAPPER = """You are the lead of an AI agent team. {n} relay chain(s) of '{chain}' just ran. Goal: {goal}

Chain notes files (full stage-by-stage reports): {notes}
Work folders: {cwds}

Final stage report of each chain:
{finals}

{instruction}
Be concise; point to files rather than repeating them."""


# ---------- /commands ----------

def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="/relay", add_help=False, exit_on_error=False)
    p.add_argument("target", nargs="+", help="chain name, or a goal for the lead to design a chain for")
    p.add_argument("-n", "--chains", type=int, default=1)
    p.add_argument("--assign", choices=["rotate", "best", "pinned"], default="rotate")
    p.add_argument("--workspace", choices=["shared", "worktree"])
    p.add_argument("--end", choices=["merge", "compare", "list"], default="merge")
    p.add_argument("--goal", help="extra goal/context when target is a chain name")
    return p


HELP = """**Commands**
- `/relay NAME|GOAL [-n 3] [--assign rotate|best|pinned] [--workspace shared|worktree] [--end merge|compare|list] [--goal TEXT]`
  run a chain; `x3` works as `-n 3`. Unknown NAME = a goal the lead designs stages for.
- `/chains` list chain files
- `/audit on|off` runner-up model reviews every task (bounded revise loop; `gate = true` tasks block on failure)
- `/ranks` each model's audit track record by domain
- `/nick MODEL NAME` give a model a nickname · `/nick MODEL` clear it · `/nick` list
- `/help` this list"""


async def command(orch, text: str) -> str:
    parts = shlex.split(text)
    cmd, args = parts[0], parts[1:]
    if cmd == "/chains":
        loaded = {n: load_chain(p) for n, p in list_chains().items()}
        reply = "\n".join(f"- **{n}** ({len(c.stages)} stages): {c.description}"
                          for n, c in loaded.items()) or "No chain files. Add some to ~/.config/hexmind/chains/"
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
    elif cmd == "/ranks":
        table = orch.stats.table(orch.members) if orch.stats else ""
        for m in orch.nicknames:
            table = table.replace(f"| {m} |", f"| {orch.name(m)} ({m}) |")
        reply = table if table.startswith("|") else "No audit results yet. Turn on `/audit on` and give the team work."
    elif cmd == "/relay":
        args = [f"-n{a[1:]}" if a.lower().startswith("x") and a[1:].isdigit() else a for a in args]
        try:
            ns = _parser().parse_args(args)
        except (argparse.ArgumentError, SystemExit) as e:
            reply = f"Bad /relay arguments: {e}\n\n{HELP}"
        else:
            reply = await run_relay(orch, ns)
            return reply  # run_relay already posted its messages
    else:
        reply = HELP
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
        raw = await orch.backend.run(orch.lead, DESIGN_PROMPT.format(goal=goal, members=", ".join(orch.members)))
        orch.emit("status", {"agent": orch.lead, "state": "idle"})
        data = extract_json(raw)
        chain = Chain(data.get("name", "custom"), goal,
                      [Stage(s.get("name", f"stage {i + 1}"), s.get("instructions", ""))
                       for i, s in enumerate(data.get("stages", []))])
        if not chain.stages:
            raise ValueError("lead designed an empty chain")

    best = None
    if ns.assign == "best":
        stages = "\n".join(f"{i + 1}. {s.name}: {s.instructions[:300]}" for i, s in enumerate(chain.stages))
        raw = await orch.backend.run(orch.lead, BEST_PROMPT.format(roster=orch._roster(), stages=stages))
        picks = extract_json(raw).get("agents", [])
        best = [a if a in orch.members else orch.lead for a in picks] + [orch.lead] * len(chain.stages)
    grid = assign(chain, n, orch.members, ns.assign, best)

    # several chains editing one folder would collide; default them into their own worktrees
    workspace = ns.workspace or ("worktree" if n > 1 and (Path(root) / ".git").exists() else "shared")
    run = time.strftime("%Y%m%d-%H%M%S")
    cwds, notes = make_workspaces(root, run, n, workspace)
    tasks = build_tasks(chain, grid, goal, cwds, notes)

    table = "| chain | " + " | ".join(s.name for s in chain.stages) + " |\n|" + "---|" * (len(chain.stages) + 1) + "\n"
    table += "\n".join(f"| {LABELS[k]} | " + " | ".join(orch.name(a) for a in row) + " |" for k, row in enumerate(grid))
    say(f"**Relay `{chain.name}`**: {n} chain(s) × {len(chain.stages)} stages · assign={ns.assign} · "
        f"workspace={workspace}\n\n{table}\n\nNotes: `{Path(notes[0]).parent}`")

    orch.emit("plan", {"tasks": tasks})
    await orch.run_tasks(goal, tasks)

    per_chain = [tasks[k * len(chain.stages):(k + 1) * len(chain.stages)] for k in range(n)]
    status = "\n".join(f"- chain {LABELS[k]}: " + ", ".join(f"{t.id} {t.status}" for t in ts)
                       for k, ts in enumerate(per_chain))
    if ns.end == "list":
        final = f"**Relay finished.**\n{status}\n\nFull reports: `{Path(notes[0]).parent}`"
        say(final)
        return final

    finals = "\n\n".join(f"Chain {LABELS[k]}: " + next((f"{t.title} ({t.agent}):\n{clip(t.output, 3000)}"
                                                         for t in reversed(ts) if t.status == "done"), "no stage finished")
                         for k, ts in enumerate(per_chain))
    orch.emit("status", {"agent": orch.lead, "state": f"{ns.end} results"})
    final = await orch.backend.run(orch.lead, END_WRAPPER.format(
        n=n, chain=chain.name, goal=goal, notes=", ".join(notes), cwds=", ".join(dict.fromkeys(cwds)),
        finals=finals, instruction=END_PROMPTS[ns.end]))
    orch.emit("status", {"agent": orch.lead, "state": "idle"})
    final = f"{final.strip()}\n\n{status}"
    orch.emit("message", {"from": orch.lead, "text": final})
    return final

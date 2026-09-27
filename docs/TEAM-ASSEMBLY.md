# Team Assembly — pick the leader, build the team, then work

Plan for the pre-flight phase: choose the leader, let it recommend a roster, let you edit that
roster, then hand it back and let it plan against the team you actually chose.

This supersedes the `--lead` default in `WS-3`. It exists because a hardcoded default lead both
crashes (see §1) and quietly overrides the roster with one the user never agreed to.

---

## 1. Why the default lead has to go

Two separate failures, one cause.

**It crashes.** `--lead` defaults to a model that may not be installed:

```python
if args.lead not in members:
    sys.exit(f"lead '{args.lead}' is not available (installed members: ...)")
```

With the default set to `opencode-ultra`, anyone without the `opencode` CLI cannot start
hexmind at all. This shipped in `a77322b`, unannounced, in a commit about something else.

**Changing it can crash at runtime.** `Orchestrator.set_lead()` emits a `team` event, and the
TUI handler for that event calls `apply_size()` and `build_table()`, which `query_one` the task
table and the team pane. Called before the app is mounted — which is exactly when a startup
leader prompt would fire — those raise. A startup flow that changes the lead *will* hit this
unless the emit is made mount-safe.

**And it is the wrong default anyway.** The lead is the one role with no defensible automatic
answer: it is the model that plans, delegates, and speaks for the room. Every other member is
selected per task, from evidence. The lead should be chosen by the person who owns the room.

**Replacement:** no default at all in the interactive path. The user picks, every launch.
`--lead` stays for `--once`, the server and scripts, where nobody is there to be asked.

---

## 2. Scan on demand, not at launch

`Registry.available()` currently does three things, and only the first is cheap:

| check | cost |
| :--- | :--- |
| `shutil.which(cli)` per member | microseconds |
| `opencode models` (subprocess) | ~1–2 s |
| `GET /api/tags` (Ollama) | up to 3 s timeout |

So launch does the cheap part only, and `/scan` does the rest.

```
launch   which(cli) per member            → who could be here
/scan    + `opencode models` + ollama tags → who is actually here, exactly
```

`--scan` on the command line does the same before the room opens, for scripts.

### Scanned models are *discovered*, not *curated*

A scan can turn up models `models.toml` has never heard of — that is the point of scanning. So
the registry grows a second kind of member:

| | curated (`models.toml`) | discovered (a scan) |
| :--- | :--- | :--- |
| `best_at`, `avoid_for` | authored | **empty** |
| `domains` | authored | empty |
| in `/team` and `/models` | yes, with its card | yes, marked `no profile` |
| routable by the lead | yes | **yes, but blind** |
| `weight` | authored | default |

An undiscovered model is registered and usable, but the lead is told explicitly that it has no
guidance for it:

> `opencode/some-new-model` — discovered by a scan, no profile in models.toml. I have no
> `best_at` or `avoid_for` for it. Tell me what it is for, or `/profile NAME` to record it.

That is the honest failure mode, and it is what keeps R7 intact: you cannot misuse a model
whose strengths nobody has written down, because the program says so out loud instead of
guessing. `/profile NAME best_at=… avoid_for=… domains=…` writes the entry to
`~/.config/hexmind/models.toml` so it becomes curated from then on.

---

## 3. The flow

```
launch ──> pick the leader            (mandatory, interactive; no default)
       ──> you type a request
       ──> leader RECOMMENDS a roster  (nothing runs)
       ──> you edit it: /add /remove /sleep /wake /model
       ──> you send it back: /go
       ──> leader REVIEWS your roster against its recommendation
       ──> leader plans, and may request chains and skills
       ──> work runs
```

The key change: **the first request produces a proposal, not a plan.** Nothing executes until
you confirm. That is what makes "the user can fully edit the team" meaningful rather than
decorative.

### States

```python
@dataclass
class Assembly:
    """The pre-flight negotiation. Persists across turns until /go or /cancel."""
    leader: str = ""
    request: str = ""              # the request the roster is being built for
    recommended: list[str] = field(default_factory=list)   # leader's pick, with reasons
    reasons: dict[str, str] = field(default_factory=dict)
    confirmed: bool = False         # True once the user has handed the roster back
    applied: bool = False           # the leader has reviewed it and produced a plan
```

`recommended` is kept after confirmation on purpose: the leader's review step needs to say
*what you dropped and why that matters* — "you removed `opencode-longcat`, which I asked for
because this touches eleven files; the plan below is narrower as a result."

### Commands

| command | effect |
| :--- | :--- |
| `/lead` / `/lead NAME` | pick or show the leader (unchanged, plus the startup prompt) |
| `/scan` | full enumeration, adds discovered members, reports what appeared |
| `/profile NAME k=v …` | promote a discovered model to curated in the user config |
| `/recommend` | (re)ask the leader who it wants, for the current request |
| `/team` | the roster: awake, asleep, busy, and each model's card (WS-10) |
| `/go` | hand the roster to the leader; it reviews and then plans |
| `/cancel` | abandon the assembly; the next request starts fresh |

`/add`, `/remove`, `/sleep`, `/wake` and `/model` already exist and now also edit the
proposal's live roster, so there is no second copy of the team to drift.

### The two leader calls

**Recommend** — cheap, one call, no tools:

```
You are {leader}. The user asked: {request}
Available: {registry table, each with best_at / avoid_for / domains}
Track record: {stats table}

Which members do you want on this? Prefer the fewest that cover the work: an idle
model costs a process and a session, and a specialist you did not need is worse than
a generalist that was.
Answer ONLY with JSON:
{"members": ["<name>", ...], "reasons": {"<name>": "<one line>"}}
```

**Review** — after `/go`, one call, still no tools, and it sees the *disagreement*:

```
You recommended: {recommended}
The user settled on: {members}   (dropped: {dropped})
Your track record for this request's domain: {stats}

Plan for the team the user actually chose. If dropping someone costs you
something, say what. Then answer ONLY with JSON:
{"reply": ..., "tasks": [...], "chains": [...], "skills": [...]}
```

The second call is the one the user described as "review which models the user chose, and will
start assigning tasks". It is a separate call from the recommend step on purpose: the lead
should not plan against a roster it did not get.

---

## 4. The plan contract grows

`PLAN_SCHEMA` currently returns `reply` + `tasks`. The lead now needs three more outputs, per
§3's second call:

```python
ASSEMBLY_SCHEMA = {
    "type": "object",
    "properties": {
        "reply": {"type": "string"},
        "tasks":  {"type": "array", "items": TASK},          # unchanged shape
        "chains": {"type": "array", "items": {
            "goal": {"type": "string"},
            "n": {"type": "integer"},
            "assign": {"enum": ["rotate", "best", "pinned"]},
            "why": {"type": "string"}}},
        "skills": {"type": "array", "items": {
            "action": {"enum": ["use", "create", "edit"]},
            "name": {"type": "string"},
            "why": {"type": "string"}}},
    },
    "required": ["reply", "tasks"],
}
```

- **`chains`** become `/relay` invocations, reusing the existing machinery — `run_relay` already
  takes a namespace. A lead-requested chain is a normal chain with a recorded provenance line
  ("requested by {lead} for {request}"), so `/ranks` and the audit treat it like any other.
- **`skills`** become directives, not silent behaviour. `use` injects a skill's path into the
  named task's prompt. `create` and `edit` are **not** executed silently: they are proposed to
  the user with the file path and the diff intent, because a model writing skills into your
  skill directory is a privileged action. That request is where `opencode-muse` earns its
  registry entry — skill and agent authoring is its documented specialty.

Anything the lead asks for that the current team cannot do is reported, not silently dropped:
"this needs a `ui` specialist and none is awake" is a finding, and the fix is `/wake`.

---

## 5. The leader role skill

A `SKILL.md` — or an agent definition — that gives any model the leader role, so the role
travels with the team instead of being a property of one vendor's CLI. Written once, read by
whichever model holds the lead.

`.claude/skills/hexmind-lead/SKILL.md`, covering:

1. **Review the roster before planning.** Say what dropping a member costs. Never silently plan
   for a team you did not get.
2. **Assign the fewest members that cover the work.** An idle model costs a process, a session
   and, on a small machine, memory. A specialist you did not need is worse than a generalist
   that was.
3. **Prefer a chain to four tasks** when the stages are sequential and each builds on the last
   — that is what `/relay` is for, and it parallelises across chains.
4. **Chain work that edits the same files serially.** Parallel tasks must not touch the same
   file; `depends_on` or separate chains, never both.
5. **Ask for a skill when you keep re-explaining something**, and say whether it should be
   `use`, `create` or `edit`. Never assume a skill exists.
6. **Route by `best_at` and respect `avoid_for`.** That is what they are for. A model with no
   profile is a known unknown — say so.
7. **Set `gate: true`** on migrations, core logic and anything whose failure would be silently
   wrong rather than loudly broken.
8. **Report honestly.** A failed task, a missing member, an unmet requirement — the lead's
   summary is the only thing the user is guaranteed to read.

Per the registry, `opencode-muse` (Muse Spark 1.3) is the model documented for agent-skill
authoring and rule engineering, so it should author this, and `opencode-ultra` review it. That
is `opencode-team` with two stages.

---

## 6. Where the code goes

| piece | home | why there |
| :--- | :--- | :--- |
| `Assembly` dataclass | `core.py`, on the orchestrator | the roster already lives there |
| recommend / review prompts + schema | `core.py` next to `LEAD_PROMPT` | all other prompts are there |
| `/scan`, `/profile` | `models.py` | it is a registry operation |
| `/go`, `/cancel`, `/recommend` | `relay.py` `command()` | with every other command |
| startup leader picker | `tui.py` | it is a modal, like `HelpScreen` and `TaskScreen` |
| the skill | `.claude/skills/hexmind-lead/SKILL.md` | auto-loaded by every member, any vendor |

`set_lead()`'s emit must become mount-safe first (§1), or the startup picker crashes the app
it is being used to fix.

### Surfaces

| surface | leader choice | assembly |
| :--- | :--- | --- |
| TUI | mandatory modal picker | full flow, `/go` in the chat |
| `--once` | `--lead` only; error if absent | skipped — one shot, no negotiation to have |
| `--serve` | `--lead`, changeable via REST | full flow over the WebSocket |

`--once` deliberately does **not** assemble a team. A script wants the work done, and a
mandatory prompt would break every caller. That is the one place the old default behaviour has
to survive, as an explicit `--lead` requirement rather than a silent default.

---

## 7. Risks

| risk | mitigation |
| :--- | :--- |
| the startup picker blocks a TUI user who just wants to type | make it one keypress (`Enter` takes the first, `l` picks another) and never a modal that must be answered before the chat is usable |
| a two-call plan doubles latency on the first request | the recommend call is cheap and tool-free; `/go` is where the real work starts |
| the lead plans for a roster that changed under it | the review call receives both rosters and the diff, and `/go` is the only thing that starts work |
| `skills: create` becomes a backdoor | never executed silently; always proposed with path and intent |
| a scan pulls in dozens of junk models | discovered members are marked `no profile` and sort below curated ones by weight |
| `opencode models` costs 1–2 s | only on `/scan`, never at launch |
| the assembly goes stale (user wanders off) | `/cancel` clears it; a new request resets it; the leader is told the roster is a proposal, not a fact |

---

## 8. Build order

| step | depends on | delivers |
| :--- | :--- | :--- |
| 1 | — | mount-safe `set_lead`; drop the default lead; `--lead` required for `--once` |
| 2 | 1 | `Assembly` + `/go`, `/cancel`, `/recommend`, recommend/review calls |
| 3 | 1 | `set_lead` never crashes; startup picker modal |
| 4 | — | `/scan` + discovered/curated split + `/profile` |
| 5 | 2 | `ASSEMBLY_SCHEMA` with `chains` and `skills`; chain + skill directives |
| 6 | — | `.claude/skills/hexmind-lead/SKILL.md`, authored by `opencode-muse`, reviewed by `opencode-ultra` |
| 7 | — | `/relay clean` (WS-12), so the chains this flow requests do not accumulate worktrees forever |

Steps 2, 4 and 6 are independent of each other. Step 3 must not land before step 1.

Step 6 is deliberately last: the skill should describe a lead that exists, not one that is
planned.

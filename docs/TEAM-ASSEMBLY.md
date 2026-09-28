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

### Scanned models are a *catalogue*, not members

A scan can turn up models `models.toml` has never heard of — that is the point of scanning. Measured
on this machine, `opencode models` returns 101 ids and Ollama adds 21 more, against 16 curated
entries. Most of the finds **cannot do the job**:

```
google/gemini-2.5-flash-image          ← returns an image, cannot edit a file
openai/gpt-image-1.5                  ← same
google/gemini-2.5-pro-preview-tts      ← text to speech
google/deep-research-max-preview      ← a research agent, not a coder
```

So a scan writes a **catalogue** — a cache at `~/.local/share/hexmind/catalogue.json` — and changes
no registry entry at all. `/profile` is the one deliberate act that turns a find into a member.
The alternative considered, registering finds as no-profile members the lead routes to blind, was
rejected on the arithmetic: 122 rows of which ~90 cannot edit a file, in `/team`, in every prompt,
and in the audit ranking, with a "no profile" branch needed in six places.

| | curated (`models.toml`) | in the catalogue (a find) | promoted (`/profile`) |
| :--- | :--- | :--- | :--- |
| in the registry | yes | **no** | yes |
| in `/team` | yes | no | yes |
| routable by the lead | yes | no | yes |
| `best_at` | authored | — | **you write it** |

`/profile NAME best_at="…"` writes a real entry to `~/.config/hexmind/models.toml` — the overlay
that already exists, already wins per-table, and is already documented in the bundled file. Nothing
in the backends changes: `DIRECT_CMDS` is generated from the registry and the opencode family is
uniform (`opencode run --auto -m <id>`), so promoting a model is a TOML row, not a code edit.

**`best_at` is required.** It is the routing signal — the line the lead reads when deciding who
gets a task — and a member without one is a name in `/team` that nothing can be assigned to. The
refusal says so, and points at `/found`.

A promoted member is `opt_in` (so a launch never silently gains one) and weighted one below the
lowest curated entry (so `by_weight` cannot prefer a find over a hand-chosen member).

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

## 4. The plan contract grows — **built**

`PLAN_SCHEMA` returned `reply` + `tasks`. `ASSEMBLY_SCHEMA` adds `chains` and `skills`; `reply` and
`tasks` are the *same* schema object, so a lead that ignores the new fields produces the plan it
always did, and every existing prompt, model and test keeps working.

```python
ASSEMBLY_SCHEMA = {
    "type": "object",
    "properties": {
        "reply": {"type": "string"},
        "tasks":  PLAN_SCHEMA["properties"]["tasks"],   # unchanged, the same object
        "chains": {"type": "array", "items": {
            "goal": {"type": "string"}, "n": {"type": "integer"},
            "assign": {"enum": ["rotate", "best", "pinned"]}, "why": {"type": "string"}}},
        "skills": {"type": "array", "items": {
            "action": {"enum": ["use", "create", "edit"]}, "name": {"type": "string"},
            "task": {"type": "string"}, "why": {"type": "string"}}},
    },
    "required": ["reply", "tasks"],
}
```

**One deviation from the sketch above:** `skill.task`. The prose says a `use` directive injects a
skill's path "into the named task's prompt", which needs a task to name. With no field, the only
unambiguous reading is *every* task in the plan — occasionally right, usually not. So `task` is
optional: named, it applies to that one task; omitted, to the whole plan.

Both plan-producing calls use it: the ordinary `handle()` path and the `/go` review.

- **`chains`** become `/relay` invocations through the existing `run_relay`, one call per goal, with
  `n` copies. `run_relay` takes a `provenance` string that is written into each chain's notes
  header, so a lead-requested chain is an ordinary chain that happens to record who asked for it —
  `/ranks`, the audit and `/relay clean` need to know nothing about who asked. Chains run *after* the
  task list, and their outcomes go into the lead's synthesis, because the synthesis is the one thing
  the user is guaranteed to read.
- **`skills` → `use`** injects the skill's path into the task prompt, after checking it is actually
  installed (project `.claude/skills/NAME/SKILL.md` before `~/.claude/skills/`). A `use` for a skill
  nobody has is a **finding**, not a dead path in a prompt the model cannot read.
- **`skills` → `create` / `edit`** are **proposed and never executed**. The request comes back with
  its path and its intent and you decide. A model writing into your skill directory is a privileged
  action, and a plan that quietly performs one is a plan you would not have approved.

**Findings are the point.** `parse_directives` validates everything up front and returns a
`Directives` with a `findings` list, so a malformed chain, an unknown `assign`, a task that is not
in the plan, or a skill that cannot be used is reported in the room in the same turn. A request that
vanishes is worse than one that is refused, because the lead's summary is what you read.

**Drafts own their directives.** With `/drafts on`, a plan's chains and skills are stashed with it,
previewed before you decide, and `/approve` runs them. `/discard` drops them and says how many. The
alternative — approving a task list and silently dropping the chain that was shown next to it — would
run a different plan than the one on screen.

`n` is clamped to 1–5. Unlimited copies of a chain is a fork-bomb of somebody's machine.

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

### The other way to do it (Option B, kept for the switch)

**Option A — what shipped.** No lead means a modal picker and nothing else happens. One candidate
is chosen for you, `Esc` declines, and a request typed after declining re-opens the picker instead
of running with no lead. Costs one keypress, and it never hands the room to a model you did not
pick.

**Option B — the alternative, deliberately not built.** The picker is a *non-blocking* notice in
the chat with the same list, and the first request falls back to the highest-weighted installed
model that can lead. No modal, nothing to dismiss, `/lead NAME` whenever you like.

The reason A won: with B, the first plan the room produces is written by a model nobody chose, and
it is the plan the user is most likely to trust, because it is the one that came back first. A
silent fallback is only honest if it is loud, and making it loud enough to be honest costs the
same attention as the modal. B is still the right call for a room that is *watched* rather than
used — a second window, a phone mirror of a session already running — where a modal would be an
obstruction and the fallback is only ever a convenience.

To switch: replace `HexmindApp.ask_lead` with a `self.say` that names the fallback model, and let
`on_input_submitted` call `set_lead(first)` before `handle`. Nothing else in the room knows how the
lead was chosen, because `set_lead` is the only door — which is the reason both options cost the
same to swap.

---

## 7. Risks

| risk | mitigation |
| :--- | :--- |
| the startup picker blocks a TUI user who just wants to type | shipped: one candidate is chosen automatically, declining is one `Esc` and re-asks on the next request, and every command still answers while there is no lead. If it still gets in the way, Option B above is the documented switch |
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
| 2 | 1 | `Assembly` + `/go`, `/cancel`, `/recommend`, recommend/review calls — **done** |
| 3 | 1 | `set_lead` never crashes; startup picker modal — **done** |
| 4 | — | `/scan` + discovered/curated split + `/profile` |
| 5 | 2 | `ASSEMBLY_SCHEMA` with `chains` and `skills`; chain + skill directives |
| 6 | — | `.claude/skills/hexmind-lead/SKILL.md`, authored by `opencode-muse`, reviewed by `opencode-ultra` |
| 7 | — | `/relay clean` (WS-12), so the chains this flow requests do not accumulate worktrees forever |

Steps 2, 4 and 6 are independent of each other. Step 3 must not land before step 1.

**Steps 2 and 3 are built** (the `--serve --timeout` fix and `/add` `/remove` came with them).
Step 4 (`/scan`, `/profile`) is the next piece and is what makes `/add` useful for a model
`models.toml` has never heard of: `/add` refuses a model with no registry entry on purpose, because
the roster every prompt is generated from *is* `models.toml`.

What step 2 shipped, and one deliberate difference from the design above: the `Assembly` keeps a
snapshot of **who was in the room when the lead proposed** (`Assembly.room`). `dropped` is
recommended-minus-room; `added` is room-minus-*that snapshot*, not room-minus-recommended —
otherwise every member that was already awake would be reported to the lead as something the user
chose, which is noise on the one call that has to be read carefully.

`ASSEMBLY_SCHEMA` (chains + skills, §4) is not built. `/go` uses `PLAN_SCHEMA` unchanged: the
lead reviews the roster and plans, and a lead that wants a chain says so in its reply.

Step 6 is deliberately last: the skill should describe a lead that exists, not one that is
planned.

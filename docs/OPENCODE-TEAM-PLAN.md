# Hexmind — Opencode Team Plan

Planning document. Written 2026-09-27 against commit `0897b1c` + the
`docs/model-updates.md` rename.

**Baseline:** `107 passed, 1 skipped` (Python 3.14.7, textual 8.2.7).

## Goal

Make the eight free `opencode/*` models first-class, simultaneously-working team
members — each holding its own session in the room — with live team management,
user-chosen leadership, and in-app model documentation.

| # | Requirement |
| :--- | :--- |
| R1 | Multiple opencode models working at once, **each owning a session** in the room |
| R2 | Add / remove models **without interrupting** the chat session |
| R3 | User can pick the leader |
| R4 | User can **ask the team** who should be leader |
| R5 | Favour opencode models over the rest |
| R6 | Add the report's local Ollama models |
| R7 | See a report-style description of each model in-app (avoid misusing "best at") |
| R8 | The **plan itself** is audited continuously — double-checked until it is finished |
| R9 | Models can be **woken / put to sleep** from one control surface; the **leader recommends** which to sleep when the team is over-provisioned |
| R10 | A working model **cannot be slept** until its task finishes — hard rule, no override |
| R11 | Every model **journals what it did after each turn**; the leader, the user, and other models can all read those journals |

---

## Verified Findings (2026-09-27)

Everything below was checked against the live CLI and source, not assumed.

### The 8 free models are all available right now

`opencode models` returns exactly 8 `opencode/*` entries, matching the report
one-for-one:

```
opencode/big-pickle                      opencode/nemotron-3.5-lightning-free
opencode/ling-3.0-flash-fin-free         opencode/nemotron-3-ultra-free
opencode/longcat-2.5-preview-free        opencode/space-bunny-free
opencode/mimo-v2.6-flash-free           opencode/muse-spark-1.3-contributor-free
```

Hexmind wires **6** of these (`backends.py:28-33`). **Missing: Space Bunny and
LongCat2.5** — both available, both trivial to add.

**`opencode models` is a validation endpoint.** Hexmind currently guesses whether a
model exists and fails opaquely at runtime. This command makes real validation possible.

### `opencode run` already supports everything R1 needs

From `opencode run --help`:

| Flag | Enables |
| :--- | :--- |
| `-s, --session <id>` | **resume a specific session** — the core of R1 |
| `-c, --continue` | continue the last session |
| `--fork` | branch a session when work diverges |
| `--attach <url>` | attach to a persistent opencode server |
| `--format json` | **raw JSON event stream** → live output |
| `-f, --file <path>` | **attach files** → vision, without rearchitecting |
| `--variant <e>` | provider-specific reasoning effort |
| `--thinking` | show thinking blocks |
| `--pure` | disable external plugins (reproducibility) |

None of this is used today. Hexmind spawns a **cold** `opencode run` per task and
discards stdout, so every model forgets everything between tasks.

### Six confirmed defects this plan fixes

| # | Defect | Location |
| :--- | :--- | :--- |
| D1 | `HCOM_TOOLS` has a single `"opencode"` entry, so `opencode-ultra/-muse/-mimo/-pickle/-ling` raise `unsupported hcom member` — **5 of 6 opencode members are dead in `--backend hcom`** | `backends.py:213`, `backends.py:269` |
| D2 | Ollama name mismatch → member silently never joins, no error (`available()` is an exact set lookup) | `backends.py:104` |
| D3 | `"think": False` hardcoded, defeating the installed `deepseek-r1-1.5b` | `backends.py:109` |
| D4 | `opencode-muse` roster text describes **LongCat2.5's** specialty — repo-scan work routes to the wrong model | `core.py:24` |
| D5 | No `/lead`, `/models`, `/add`, or `/remove` command exists at all | `relay.py` |
| D6 | `Task.status` + `AGENT_COLOR` hardcode the member list; a new model gets no colour | `core.py:84`, `tui.py:22` |

### RESOLVED: prompt delivery is stdin — no arg-length ceiling

Tested 2026-09-27 against the real CLI:

```
$ printf 'Reply with exactly: PONG' | opencode run --auto -m opencode/nemotron-3.5-lightning-free
PONG                                    # exit 0
```

**stdin works.** `backends.py:151-168` is correct as written; opencode does **not** inherit
the OS arg-length ceiling that `kimi` is subject to. Large relay prompts and stage
instructions are safe. (The docs declare the message as positional argv, but both paths
work — stdin is the one to use.)

### RESOLVED: the event schema, and session memory works

`--format json` emits one JSON object per line. Verified shape:

| event | payload |
| :--- | :--- |
| `step_start` | `sessionID` |
| `text` | `part.text` ← **the model's reply lives here** |
| `step_finish` | `part.reason`, `part.tokens.total` |

**Session memory confirmed working.** A session created with prompt "Reply with exactly:
PONG", then resumed with `-s <id>` and asked what it had been told to reply with, returned
`PONG`. R1's core mechanism is sound.

Text extraction is therefore: `part["text"]` on `type == "text"`, and `sessionID` is present
on **every** event, so capture is trivial.

### HAZARD: sessions are directory-bound, and violating this HANGS

Resuming a session from a **different directory** does not error. It **hangs**:

```
$ cd /tmp/elsewhere && opencode run --format json -s ses_f1bf… 
[EXIT CODE: 124]        # 120s timeout
--- bytes: 0            # zero output
```

`opencode session list --format json` confirms why — every session records its origin:

```json
{ "id": "ses_f1bf…", "projectId": "global", "directory": "/tmp/oc-probe" }
```

**Design rule (must be enforced in code, not convention):**

> A session ID may only ever be passed to a `cwd` identical to the one it was created in.
> Key sessions by `(model, directory)`, never by model alone.

This is not theoretical. `relay.py:125-144` gives every parallel chain its own git worktree,
and `--cwd` lets the user point the room anywhere. A per-model-only session key would hand a
worktree a session belonging to the main repo and hang the task for the full 30-minute
`DirectBackend` timeout with nothing on screen. **Add a test that asserts a cross-directory
session id is rejected before the subprocess is spawned.**

### Additional CLI surfaces found in the docs

| Command | Why it matters here |
| :--- | :--- |
| `opencode serve` + `run --attach <url>` | Documented as the way to **avoid MCP cold-boot on every run**. With 8 models × many tasks this is the single biggest latency win. Promotes the "optional tier-2" of WS-4a to a serious candidate. |
| `opencode session list --format json` | Session recovery. If Hexmind loses a session id, it can re-derive it by `directory`. |
| `opencode session delete <id>` | Cleanup for `/reset`. |
| `opencode export <id>` | Inspect exactly what a session did — useful for the audit trail. |
| `opencode stats --models` | Per-model token/cost breakdown → feeds the `/models` view and reveals free-tier pressure. |
| `opencode db path` | Sessions live in a local SQLite db. |
| `--title` | Label sessions per model/room for legible `session list`. |
| `OPENCODE_DISABLE_AUTOCOMPACT` | Long sessions are **auto-compacted** — old detail is silently summarized away. Bounds the cost of long-lived sessions, and is a gotcha when a model "forgets" something it was told. |

### Side finding: the opencode members' real skill path

`OPENCODE_DISABLE_CLAUDE_CODE_SKILLS` implies opencode loads skills from `~/.claude/skills`
— which **does** exist. So the `file:///home/daripper/.agents/skills/…` links in
`model-updates.md` are a secondary route; the skills opencode members actually use are the
ones under `~/.claude/skills/`.

Whether the `.agents` path itself resolves is **machine state, not a durable fact**: it was
absent when first checked, present minutes later in a `find`, and gone again by the next
command, while `~/.claude` mtime moved in between. Something on this machine manages that
directory actively. Don't "fix" it by moving files.

Also: **do not pass `--pure`** to opencode members — it disables external plugins, which
would cut the team off from the very skills the report is built around.

---

## WS-1 · Model Registry — the foundation

Everything else depends on this. One structured source of truth replacing the
hand-maintained `ROSTER` prose that caused D4.

**New:** `hexmind/models.py`, `hexmind/models.toml`
(override at `~/.config/hexmind/models.toml` — mirrors the existing `chains/` pattern).

```toml
[models.opencode-ultra]
cli        = "opencode"
model      = "opencode/nemotron-3-ultra-free"
tier       = "cloud"            # cloud | local
opt_in     = false
text_only  = false
domains    = ["architecture", "implementation", "review", "security"]
best_at    = "system architecture, ADRs, security audits, concurrency tuning"
avoid_for  = "typos, one-liners, markdown formatting"
think      = false
variant    = "high"
weight     = 100               # preference; higher = favoured (R5)
fallback_for = []              # e.g. deepseek-r1 covers opencode-ultra offline
color      = "blue"
footprint  = "cloud · heavy CoT"

[models.deepseek]
cli      = "ollama"
model    = "deepseek-r1-1.5b"  # exact name from /api/tags
tier     = "local"
domains  = ["debugging", "review"]
think    = true                # fixes D3
verify   = "ollama"            # how to check availability
```

**API:**

```python
class Registry:
    def members(self, *, include_opt_in=False) -> list[str]
    def get(self, name) -> Model
    def describe(self, name) -> str            # report-style card (R7)
    def matrix(self, live=True) -> str         # report-style table (R7)
    async def detect(self) -> list[str]       # validate via `opencode models` + ollama tags
    def roster_prose(self) -> str              # generated → D4 can never recur
```

**Fixes:** D2 (normalise before comparing; warn on near-miss), D4 (prose is generated),
D6 (`AGENT_COLOR` reads `color`), and makes R5/R6/R7 declarative instead of hardcoded.

**Also:** `available()` becomes `await registry.detect()` — `asyncio.to_thread` around the
blocking `urllib` / `shutil.which` calls, so runtime re-detection never stalls the event loop.

---

## WS-2 · Live Team Management (R2)

Add/remove members mid-session without interrupting the chat.

**New commands:**

| Command | Behaviour |
| :--- | :--- |
| `/models` | the report-style matrix, live availability, current team marked (R7) |
| `/model <name>` | detail card: best_at, avoid_for, domains, footprint, live stats (R7) |
| `/add <name>` | bring a model in; re-runs `registry.detect()` |
| `/remove <name>` | send it home |
| `/pull <name>` | `ollama pull` for a local model, then add it |

**Why this is cheap:** `Orchestrator.members` is a plain list, and `HexmindServer` passes
the *same list object* into the orchestrator (`server.py:91,111`). In-place mutation
propagates to every consumer automatically — `_roster()`, `parse_plan()`, auditor
selection, `fallback()`, relay rotation, and the server status payload all read
`self.members` live.

**Safety rule (the "without interrupting" requirement):** snapshot `members` at turn
start; a plan already in flight keeps its own snapshot so removing a model mid-run cannot
orphan a running task. New turns see the new roster.

**Also:** removing the current lead must be blocked or require `/lead` first; removing a
model with a `running` task must warn.

---

## WS-3 · Leader Control (R3, R4)

| Command | Behaviour |
| :--- | :--- |
| `/lead` | show current leader + track record |
| `/lead <model>` | switch leader live (R3) |
| `/lead recommend` | **ask the team** who should lead (R4) |

`orch.lead` is already a plain attribute read at each use site
(`core.py:243,245,320,276`), so switching is safe mid-session. The TUI must refresh
`#team` and `sub_title` on change — `refresh_team()` already handles this.

**`/lead recommend` — two stages:**

- **v1 (cheap):** one call to the current lead, briefed on every member's
  `best_at`/`domains` plus their `Stats` record, asked to recommend a successor with
  reasons. Returns a ranked shortlist.
- **v2 (the real feature):** a genuine parallel consultation — every non-lead member is
  asked independently "who should lead this room?", run through the existing task graph
  (`run_tasks`), then votes are **weighted by each voter's own `general`-domain track
  record**. Ties break on `Stats`.

v2 is the honest version of "ask the team": a single model can be flattered or sycophantic,
but a weighted panel of independent opinions cannot be talked into one answer. It reuses
`run_tasks` unchanged, so it costs almost no new machinery.

**Default lead:** `opencode-ultra` (Nemotron 3 Ultra) — the report's architecture and
planning model. Makes R5 true from first launch.

---

## WS-4 · Opencode Sessions & Live Output (R1) — the core ask

The centrepiece. Today six opencode models *do* run in parallel as separate processes,
but each is a **cold, one-shot, throwaway process** with no memory and no live output.

### 4a. Session persistence (the "each owns sessions" requirement)

1. Switch opencode members to `--format json`.
2. Capture `sessionID` (present on every event); store `self.sessions[(model, directory)] -> id`
   in the orchestrator, persisted to `~/.local/share/hexmind/sessions.json`.
3. On that model's next turn **in that same directory**, pass `-s <id>` so it resumes its own
   context — it remembers what it already did in this room.
4. Use `--fork` when a task diverges from the session's line of work, so the parent context
   stays clean.
5. `--title` per session so `opencode session list` is legible.

**The key MUST be `(model, directory)`, never model alone** — sessions are directory-bound
and a cross-directory id **hangs with zero output** (see HAZARD above). Add a guard that
refuses to pass a session id whose recorded directory differs from the task's `cwd`, plus a
regression test. `opencode session list --format json` gives recovery if an id is ever lost.

**Escalation to a shared server:** `opencode serve` + `run --attach <url>` is the documented
way to skip MCP cold-boot on every run. With 8 models and many tasks per run, that overhead
is the dominant per-task cost. Design `DirectBackend` so the transport (spawn-per-call vs.
attach) is swappable, but land `-s` first — it is the part that delivers R1.

### 4b. Live output

`--format json` gives an event stream. Introduce a new emit kind, `delta`, and render it
in the TUI so a model visibly works instead of going silent for up to 30 minutes.
This also fixes the review finding that `agy`/`kimi` already parse stream-json and throw
it away — one `DeltaSink` abstraction serves all three.

### 4c. Complete the team

✅ **Done** — all 8 free models are now in `ROSTER`/`DIRECT_CMDS`/`AGENT_COLOR` as
`opencode`, `-ultra`, `-muse`, `-mimo`, `-pickle`, `-ling`, `-bunny`, `-longcat`.
The three drifted descriptions were corrected at the same time (D4). Still missing:
**persistent sessions** (4a) and **live output** (4b), which are what make the eight
genuinely co-resident rather than merely present.

### 4d. Fix hcom (D1)

Either give each opencode model its own `HCOM_TOOLS` entry, or declare opencode
**direct-only** and say so in `--backend hcom` output rather than failing at task time.

**Now 8 members are affected, not 6.** Still latent — `opencode run` self-serves — but it
blocks the `--attach` transport in 4a.

---

## WS-5 · Preference Weighting (R5)

"Favour opencode models" is currently impossible to express: `fallback()` sorts purely
by Laplace score (`core.py:352`) and relay rotation is plain round-robin
(`relay.py:103`).

- `weight` field in the registry (R5).
- `fallback()` sorts by `(weight, stats score)` — a free model that also audits well wins.
- Relay rotation gains `--prefer opencode|balanced`, and a weighted variant that avoids
  running one model twice in a row when alternatives exist.
- `available()` ordering puts preferred members first so the TUI and lead prompt lead
  with them.
- `/models` shows weight and a "preferred" marker, so the bias is visible not hidden.

---

## WS-6 · Local Models (R6)

Add the report's 6 local engines to the registry. Current reality from
`/api/tags`: **4 are not installed, 2 use names Ollama doesn't report.**

| Report | Installed as | Action |
| :--- | :--- | :--- |
| `qwen3:4b` | — | registry entry, `needs pull` |
| `phi3:mini` | `phi3-mini:latest` | normalise |
| `moondream:latest` | — | registry entry; vision deferred (§below) |
| `deepseek-r1:1.5b` | `deepseek-r1-1.5b:latest` | normalise + `think = true` (**D3**) |
| `qwen2.5-coder:1.5b` | — | registry entry, `needs pull` |
| `samantha-mistral:latest` | — | registry entry, `needs pull` |

Also surface the **9 installed models the report never mentions** — notably
`deepseek-coder-v2:16b` and `deepseek-coder:6.7b`, which beat the report's recommended
1.5B model for code work, and `nomic-embed-text`, which is the natural fix for the
flat 3-exchange history in `core.py:230`.

**Keep `_local_lock`** (`backends.py:88`) — serialising local models is correct on an 8 GB
Asahi. The registry should make the eviction visible rather than silent.

**Vision — defer, but cheaply.** `moondream` needs image input, which the text-only
`/api/generate` path cannot express. But `opencode run -f <file>` **can** attach an image
to a cloud model. So the report's "snap a photo → read the pinouts" flow is achievable
through WS-4 with no interface change. Note it in the registry as the cheap path; leave
Ollama vision for later.

---

## WS-7 · Descriptions UI (R7)

The point is to stop a user handing a 1.5B model an architecture task. Three surfaces,
one data source (the registry, not the markdown):

1. **`/models`** — the report's comparison matrix rendered as a Markdown table in chat:
   model, tier, footprint/latency, best_at, live status, weight. Instant, reuses `say()`.
2. **`/model <name>`** — detail card: best_at, **avoid_for**, domains, footprint,
   fallbacks, live `Stats` row. `avoid_for` is the field that prevents misuse.
3. **TUI modal** — a `ModelScreen` beside the existing `HelpScreen`/`TaskScreen`
   (`tui.py:49,66`): a `DataTable` of models with a detail pane, `?`-key reachable,
   consistent with the current modal pattern.
4. **Server** — `GET /api/models` and `GET /api/models/{name}`.

Keyboard-navigable, with an accessible label on every control, per `AGENTS.md`.

---

## WS-8 · Standing Plan Audit (R8)

The plan gets audited the way the code does — continuously, not once at the end.

### Two auditors, two different failure modes

| Model | Catches | Why it is the right tool |
| :--- | :--- | :--- |
| `opencode-ultra` (Nemotron 3 Ultra) | **Wrong** — bad reasoning, missed failure modes, contradictory phases | Report disposition is adversarial *by construction*: "force chain-of-thought analysis on edge cases and failure modes **before** generating implementation code" |
| `opencode-longcat` (LongCat2.5) | **Missing** — requirements never addressed, silent omissions | The only free model that ingests plan + full diff + relevant source in one context, and its guideline already demands "line-by-line citations for every synthesized finding" |

An audit missing either is half an audit: Ultra finds errors in what was reasoned, LongCat
finds what was never considered.

### Mechanism: a persistent traceability matrix

Not a conversational review — a **table**, re-derived each phase and **diffed against the
previous phase's table**:

| Req | Status | Evidence | Verdict |
| :--- | :--- | :--- | :--- |
| R1 sessions | ✅ | `backends.py:28`, `core.py:47` | ultra: gap — no cwd guard |
| D1 hcom | 🔴 | — | longcat: no evidence line exists |

Three defect classes fall out for free:

- **Regression** — a row marked ✅ whose evidence line has since been deleted.
- **Theatre** — a row whose status never changed across phases. Probably not real work.
- **Omission** — a requirement with no evidence row at all. The failure mode that survives
  a purely conversational review, because nothing ever looks for it.

Matrix lives at `~/.local/share/hexmind/plan-audit.json`, keyed by plan file hash so a
rewritten plan resets the baseline deliberately rather than silently.

### Rule that must not be forgotten: no self-review

**If `opencode-ultra` is the default lead (WS-5), then Ultra auditing the plan is a model
reviewing its own reasoning.** This is the same trap the Antigravity section correctly
identifies for builders ("a builder should never approve its own work"), and it applies
symmetrically to planners.

**Enforce:** the auditor set excludes the current lead, and substitutes in when leadership
changes. Encode as an assertion in `audited_plan()` plus a test — not as a convention.

### Surfaces

| Surface | Behaviour |
| :--- | :--- |
| `/audit-plan` | run both auditors in parallel now, return the matrix + verdict |
| `hexmind/chains/plan-audit.toml` | reusable relay chain: `ultra` pre-audit → `longcat` coverage → `ultra` post-critique |
| Phase gate | after each phase, the matrix is re-derived and diffed automatically |
| `GET /api/plan-audit` | server equivalent |

Reuses `run_tasks` unchanged — the same fan-out that powers `/lead recommend`. This is a
pattern pointed at a requirements matrix, not new machinery.

---

## WS-9 · The Leader as Roster Advisor (R9)

The lead watches for **over-provisioning** and proposes who to sleep.

### The signal

16 members are available. Each awake opencode model is a live process, and once WS-4 lands,
a **parked session** — real cost on an 8 GB Asahi. Waking all 16 to execute a 3-task plan
is waste. The lead proposes the smallest roster that still covers the work:

1. **Idle depth** — N awake but only M tasks in flight, M ≪ N.
2. **Domain redundancy** — several awake models hold pending tasks in the *same* domain;
   their work could be consolidated onto one.
3. **Staleness** — a model has held no task for K rounds.

Output is a proposal, never an action: *"sleep `opencode-mimo` and `opencode-ling` — no open
task touches `ui` or quant work; consolidate `t3` onto `opencode-pickle`."*

### The rule that makes this safe

> #### ⛔ INVARIANT S-1 — A working model cannot be put to sleep.
>
> If a model holds a task in `running`, `auditing`, or `revising`, a sleep request is
> **refused**, not queued and not deferred. The request only succeeds once the model reaches
> `done`, `failed`, or `skipped`.
>
> There is no override, no `--force`, and no "sleep anyway". The model is mid-edit in a real
> folder or a relay worktree; interrupting it to reclaim resources is how you get a
> half-written file, a corrupted worktree, and a task whose output describes work that was
> never finished. Reclaiming resources is never worth an inconsistent repo.
>
> **Enforce in code, not in the UI:** `Orchestrator.sleep_model()` raises unless every task
> assigned to that model is terminal. The `/team` control surface (WS-10) disables the Sleep
> control for a busy row and shows *why*, rather than offering a button that fails.
>
> **The same invariant governs reassignment:** only `pending` tasks may move between models.
> `running` is untouchable for the same reason.

| Task state | May the model be slept? | May the task be reassigned? |
| :--- | :--- | :--- |
| `pending` | ✅ yes | ✅ yes |
| `running` / `auditing` / `revising` | ⛔ **no — INVARIANT S-1** | ⛔ **no** |
| `done` / `failed` / `skipped` | ✅ yes | n/a |

A leader proposal that would sleep a busy model is **not made** — it is deferred to the next
task boundary. See WS-9 for the full proposal rules.

### Three-step loop, and it is not advisory-only

```
leader proposes  →  auditor validates coverage  →  user applies (one action)
```

The middle step is WS-8 doing real work. **LongCat checks that sleeping a model does not
remove coverage the plan still requires** — *"you proposed sleeping `opencode-mimo`, but
WS-7 is a UI workstream and no other awake member covers `ui`."* Without that check, the
leader will happily propose a roster that cannot finish the job.

Advisory with one-keystroke apply, never automatic. Auto-sleeping a model the plan depends
on — or one that just got handed a gated task — is hostile and hard to recover from.

---

## WS-10 · One Control Surface (`/team`)

R2, R3, R7 and R9 all want the same thing: **one place** to see the team and change it.
Scattering them across `/models`, `/add`, `/remove`, `/lead`, `/sleep` gives the user five
places to look and no consistent mental model.

**Converge them on a single `/team` modal**, opened with `?`-style key or command, with the
chat commands kept as keyboard shortcuts *into* that modal:

```
┌─ Team ─────────────────────────────────────────────┐
│  model              state      domains      stats  │
│ ▸ opencode-pickle   ● running  impl,tests   7/8    │
│   opencode-ultra    ○ asleep   arch,review  5/6    │
│   opencode-mimo     ○ asleep   ui           -      │
├────────────────────────────────────────────────────┤
│ [Sleep] [Wake] [Lead] [Audit] [Plan] [Close]      │
└────────────────────────────────────────────────────┘
```

- **Every row is interactive** — toggle sleep, promote to leader, open the description card.
- Sleep/wake and leader selection are **the same kind of click**, which is what R9 asks for.
- Sleeping shows the parked session id and lets you resume it (WS-4 synergy: a sleeping
  model has *parked its memory*, not discarded it).
- Keyboard-navigable with an accessible label on every control, per `AGENTS.md`.
- REST equivalent: `GET /api/team`, `POST /api/team/{model}/{sleep|wake|lead}`.

Chat commands remain (`/models`, `/lead`, `/audit-plan`, `/sleep`) because they are faster
for scripted and headless use — they just all route to the same underlying state changes.

### Sleep is a state, not a deletion

A sleeping model must be **known but inactive**, not forgotten:

| Concern | Sleeping behaviour |
| :--- | :--- |
| `orch.members` | removed → excluded from roster prose, lead assignment, auditor picks, `fallback()`, relay rotation |
| Registry | **retained** → `/models` shows it asleep with its `best_at` and live `Stats` intact |
| Session | **parked**, keyed `(model, directory)` → waking resumes its memory (WS-4) |
| **Journal** | **retained and still readable** (WS-11) — you lose the model's *process*, not its *record* |
| Leader | cannot be slept; must be reassigned first |
| Busy model | ⛔ refused outright — **INVARIANT S-1** |

This is why `members` (active) and the registry (known) must be separate concepts — today
they are the same list, and collapsing "asleep" into "removed" would lose the stats history
and the parked session. The journal is what makes sleeping *safe*: a sleeping model still
has a readable account of everything it did.

---

## WS-11 · Per-Model Work Journals (R11)

Every model writes a plain-text journal of what it did, after every turn. The leader, the
user, and the other models can all read them.

### Why this is not just logging

Today a task sees only its **declared dependencies'** final output, clipped to 4000 chars
(`core.py:319`, `clip()`). A journal is a different thing: the running narrative of what the
team has actually done, including work that **failed, was revised, or was done by a model
outside this task's dependency chain**. Three concrete gains:

- A task can learn from a sibling's dead end instead of rediscovering it.
- The lead plans against what happened, not against what was reported.
- **The audit workstream (WS-8) gets evidence for free** — a journal is a per-model,
  per-turn trace with timestamps, which is exactly the `Evidence` column of the traceability
  matrix.

It also completes the sleep story: a model can be parked and forgotten, and its record
survives.

### Location and format

Reuse the established scratch convention — relay already writes
`.hexmind/runs/<run>/chain-<X>.md` behind `.hexmind/.gitignore` = `*` (`relay.py:126-129`).

```
.hexmind/journal/<run>/<model>.md        # one file per model, appended in turn order
```

Append-only Markdown, one `##` section per turn: turn index, task id + title, status, and
the model's own report. Same gitignore protection, so nothing leaks into the user's commits.

### Who writes it — and why it can't be the model's job alone

**Hexmind appends automatically** after each turn, from the turn's output, exactly as
`core.py:306-308` already does for relay notes. This guarantees the journal exists even if
the model ignores its instructions, gets truncated, or crashes.

The prompt *also* tells the model its journal path and invites it to add detail — richer
notes, what it tried and abandoned, what it would do differently. Best-effort enrichment on
top of a guaranteed floor. **Never** depend on the model to maintain its own record.

### Who reads it

| Reader | How |
| :--- | :--- |
| **Leader** | a digest of every model's journal tail injected into `LEAD_PROMPT` — it plans with the team's real history |
| **Other models** | journals of adjacent/completed work injected into `TASK_PROMPT`, so a task benefits from siblings' findings |
| **User** | `/journal` and `/journal <model>` in chat; a pane in the `/team` modal (WS-10) |
| **Auditors** | WS-8 reads journals as evidence for the traceability matrix |
| **Server** | `GET /api/journal`, `GET /api/journal/{model}` |

### The constraint that decides the design: journals grow

A journal is unbounded by nature, and it is being injected into *other models' prompts* —
which are already carrying task instructions, dependency outputs, and the roster. Injecting
a whole journal is a context bomb and a cost problem.

**Therefore: digest, never full text.**

- Inject only the **tail** — the most recent K turns per model, K small (start at 3).
- Keep a **per-model one-line running summary** (latest status + last action) that is always
  in the roster, so the lead knows *that* a model worked even when the detail is trimmed.
- Budget it explicitly: a fixed character cap on the journal block in any prompt, and a
  test asserting the cap holds as journals grow.
- `STEP-2` the full text behind `/journal <model>` for the user, who can always read more
  than a model gets.

`nomic-embed-text` is already installed and is a natural future answer to "find the one turn
in t1's 400-line journal that's about auth" — worth noting, not worth building now.
---

## WS-12 · Reap relay worktrees (`/relay clean`)

`make_workspaces` (`relay.py:125`) creates a git worktree **and** a branch per chain, named
`hexmind/<run>-<X>`, and nothing ever removes either. Every `/relay` therefore leaves behind
1.7 MB and a branch, permanently. Three relay runs had accumulated before this was noticed.

### Why this is a safety feature, not housekeeping

Cleaning up is exactly where a tool destroys work by accident, and this project has already come
close. Committing an audit chain's fixes with `git add` naming only the source files left the
tests behind in the worktree. The branch had **0 unmerged commits** — the standard check says
safe — and deleting it would have destroyed the only copy of the regression tests for two shipped
fixes. It was caught only by diffing the worktree's working tree against `main`, which nothing was
doing.

So the rule: **never trust a commit-graph check alone.** Uncommitted work is invisible to it by
definition, and a relay worktree is exactly where uncommitted work lives.

### Commands

| command | effect |
| :--- | :--- |
| `/relay clean` | list every run with its verdict and what would be lost. Changes nothing |
| `/relay clean --force` | remove the runs that are safe, refuse the rest, and say why |
| `/relay clean --all` | also drop `<run>/chain-*.md` notes — they are the audit trail, so opt-in |

Listing first is not friction. A destructive command whose failure mode is silent data loss
should cost one extra keypress.

### Verdicts

For each run under `.hexmind/runs/`, four checks in order; the first failure decides:

| verdict | condition | action |
| :--- | :--- | :--- |
| **active** | named in `.hexmind/active`, written by `run_relay` on start and cleared in a `finally` | skip |
| **unmerged** | `git log main..<branch>` is non-empty | skip, and name the commits |
| **dirty** | the worktree has modified or untracked files | skip, and **name the files** |
| **safe** | none of the above | eligible |

The dirty check is the one that matters, and it must list the offending paths. A bare "skipped:
dirty" leaves the user unable to act, which is precisely how the tests nearly got lost. Print
them, so the listing can be pasted straight into a diff.

The active marker is a file rather than a process check because guessing from `ps` is fragile: a
chain can sit between stages, and a killed run leaves no process but a live-looking worktree.

### Use the safe git invocations, not the forceful ones

```python
git worktree remove <path>   # no --force: git itself refuses a dirty worktree
git branch -d <branch>       # -d, never -D: git itself refuses an unmerged branch
git worktree prune
```

The force variants are what turned a near-miss into a real loss when done by hand
(`git worktree remove --force` bypasses the dirty check that would have saved the tests). The
built-in guards already encode the two rules that matter; this command's job is to never override
them and to explain refusals in the user's terms.

`git branch -d` is also a genuine second opinion: it re-checks mergedness at delete time, so a run
that gained a commit between the listing and the `--force` is still caught.

### Where it lives

`relay.py`, beside `make_workspaces` — the module that creates the mess, so the naming scheme and
the cleanup cannot drift apart. Purely a filesystem and git operation: no model is consulted and
nothing runs.

### Tests

- a clean, fully merged run is removed, and both the worktree and the branch go
- a run with an unmerged commit is kept, and the commit is named
- **a worktree with uncommitted changes is kept and the changed paths are named** — the
  regression that matters
- an untracked file counts as dirty
- a run marked active is never touched, even when otherwise clean
- a dirty worktree is left registered, so `git worktree list` still agrees
- `--all` keeps the notes by default and drops them only when asked

---

## Phasing

| Phase | Workstream | Delivers | Depends on |
| :--- | :--- | :--- | :--- |
| **P0** | ~~verify stdin~~ ✅ · WS-1 | registry; D2, D4, D6 fixed | — |
| **P1** | WS-7 + WS-2 + WS-10 | `/team` control surface, `/models`, `/model`, sleep/wake, `/add`, `/remove`, `/pull` (R2, R7, R9) | P0 |
| **P2** | WS-3 | `/lead`, live leader switch, `/lead recommend` (R3, R4) | P0 |
| **P3** | WS-4 | sessions keyed `(model, dir)`, live output, hcom fix (R1) | P0 |
| **P4** | WS-5 | preference weighting, default lead `opencode-ultra` (R5) | P1, P2 |
| **P5** | WS-6 | local models, `think` flag (R6) | P0 |
| **P6** | WS-8 | plan-audit chain, `/audit-plan`, phase-gate matrix (R8) | P1, P2 |
| **P7** | WS-9 | leader's over-provisioning advisor (R9) | P3, P6 |
| **P8** | WS-11 | per-model journals, digests into prompts, `/journal` (R11) | P1 |
| **P9** | WS-12 | `/relay clean` — reap finished runs, refuse dirty ones (P1) | relay runs |

P1 and P2 are independent and can run in parallel. Nothing before P0 should start — the
registry is what makes the rest declarative instead of hardcoded.

**P3 must include the cross-directory session guard and its test on day one** — it is a
30-minute silent hang, not a cosmetic bug.

**WS-10 merges into P1 deliberately.** Building `/team` last would mean building the sleep
toggle, the leader picker, and the description cards three separate times in three
different widgets, then reconciling them. One surface, built once, with the chat commands
acting as shortcuts into it.

**P6 gates P7.** The roster advisor's proposal must be coverage-checked by the plan auditor
before it reaches you — otherwise the leader will confidently propose a roster that cannot
finish the plan.

**P8 is independent but cheap once P1 exists**, and it makes INVARIANT S-1 safer to enforce:
the journal is the record that survives a model being parked.

## Risks

| Risk | Mitigation |
| :--- | :--- |
| ~~Prompt delivery stdin vs argv~~ | ✅ **Resolved** — stdin works, no arg ceiling |
| Session id used against the wrong `cwd` | ✅ Root-caused: hangs, exit 124, zero output. Enforce `(model, directory)` keying + a pre-spawn guard + regression test |
| `--format json` event schema undocumented | ✅ **Resolved** — `text` → `part.text`; `sessionID` on every event. Pin both in a test |
| MCP cold-boot on every `opencode run` | `opencode serve` + `--attach` as the transport upgrade in P3/P4 |
| Long sessions silently compacted | `OPENCODE_DISABLE_AUTOCOMPACT` awareness; `/reset` for a clean context |
| 8 free models share a rate limit | `QUOTA_RE` fallback (`core.py:51`) becomes load-bearing. `opencode stats --models` to watch pressure. Consider a shared token bucket in the registry |
| Open sessions hold RAM/CPU | **WS-9 is the direct mitigation** — sleep over-provisioned models rather than capping them |
| Leader audits its own plan | Enforce auditor ≠ lead as an assertion + test (WS-8), not a convention |
| Consolidating a `running` task corrupts a worktree | **Pending-only reassignment**, enforced in code (WS-9) |
| Sleeping a model the plan depends on | Coverage check by the plan auditor before any sleep is applied (WS-8 → WS-9) |
| Registry scope creep | Freeze the field set in P0. New fields need a stated use case |

## Open Questions for the User

1. ~~Prompt delivery~~ — **resolved: stdin.**
2. ~~Session scope~~ — **resolved.** Recommendation below; needs your sign-off.
3. ~~Cloud models beyond the free 8~~ — **resolved: free 8 only.**
4. **`/lead recommend` weight** — should the current leader be allowed to vote on its own
   successor?

---

## Appendix A · Session scope, explained (Question 2)

### What a session actually is

An OpenCode session is one model's **persistent conversation memory**. It stores the full
message history for that model. When Hexmind passes `-s <id>`, the model *continues that
conversation* — it remembers everything already said.

Today Hexmind passes no `-s`, so **every task is a brand-new empty session**. A model
assigned three tasks in a row has zero memory of tasks one and two. That is the gap R1 closes.

So the question is: **how long should a model's memory of a room last?**

### Option A — "Survive" (one session per model, indefinitely)

One long-lived session per model, kept on disk and resumed days later.

- **For:** maximum continuity. Ask "what did we decide about the CSV export last week?" and it knows.
- **Against:** unbounded context growth — slower and more expensive over time, and eventually
  the model is navigating stale context from a project you abandoned. A session from an old
  unrelated project can quietly contaminate judgment on a new one.
- **Decisive problem:** this is **not actually possible.** Sessions are bound to their
  directory (verified above). A single global session would be pinned to whichever folder it
  was born in, and resuming it anywhere else **hangs forever**. Option A is ruled out by the
  tool, not by taste.

### Option B — "Reset per room" (fresh session each time you launch Hexmind)

Launch `hexmind` in a folder → every model starts fresh. Close and reopen → clean slate.

- **For:** context always matches the work in front of you; no cross-project contamination; predictable cost and latency.
- **Against:** no cross-day memory. Come back tomorrow and the team has forgotten the whole project.

### Option C — Survive, scoped to the project, resettable ← **recommended**

Key sessions by `(model, directory)`, persist them across launches, and add `/reset`.

- **For:** continuity *within* a project, which is the continuity you actually want — "we discussed this yesterday" still works. Pairs correctly with the directory binding we verified. `/reset` is the escape hatch when context goes stale or a model starts citing decisions you no longer want.
- **Against:** slightly more state to manage; a long-lived session still gets auto-compacted by opencode, so very old detail fades (which is arguably correct).

### Why C

Option A is technically impossible. Between A and B, the real question is whether you want
the team to remember a project **across days** or only **within a sitting** — and the
directory binding means the honest unit of memory is the *project folder*, not the model.
C is the only option that gives cross-day continuity where it's meaningful (per project)
without ever risking a cross-directory hang.

It also degrades gracefully: `/reset` gives you B on demand, per model, without restarting
the room.

**One design note either way:** because opencode auto-compacts long sessions
(`OPENCODE_DISABLE_AUTOCOMPACT`), a "surviving" session won't grow forever — old turns get
summarized away. That is a feature here: it bounds cost. But it does mean a model may
eventually paraphrase rather than quote something from long ago. `/reset` is the clean fix
when that matters.

---

## Model Selection & Operational Execution Assignment

> **Decision by Antigravity (Google DeepMind Agentic Coding Assistant):**
> Evaluated the 8 free Opencode endpoints against the requirements, failure modes, and lifecycle of this plan. Designated specialized roles across a 3-stage lifecycle, formalized as an executable Hexmind agent chain with custom skill sets.

### 1. Plan Review & Architectural Audit Model (Pre-Build)
* **Assigned Model:** `opencode/nemotron-3-ultra-free` (Nemotron 3 Ultra)
* **Rationale:** As a heavy chain-of-thought reasoner specialized in system architecture, security threat modeling, and formal review (`system-design`, `plan-reviewer`, `ruthless-refactorer`), it is uniquely suited to probe failure modes, memory limits (Asahi 8GB constraint), and concurrency bounds in this document before code is written.
* **Dispatch Command:**
  ```bash
  opencode run --model opencode/nemotron-3-ultra-free \
    -f docs/model-updates.md \
    -f docs/OPENCODE-TEAM-PLAN.md \
    "Perform a rigorous technical audit of these two documents. Focus on architecture feasibility, failure modes, concurrency on 8GB RAM, and any missing edge cases in Phase 0 (P0) and Phase 1 (P1)."
  ```

### 2. Autonomous Builder & Implementation Model (Construction)
* **Assigned Model:** `opencode/big-pickle` (Big Pickle)
* **Rationale:** Built for unrelenting, zero-fluff test-driven execution ("Ralph Mode"). It will not stall on failing tests or produce half-finished placeholders; it drives implementation from failing tests to green suites (`code-implementer`, `test-driven-development`, `ralph-mode`).
* **Dispatch Command:**
  ```bash
  opencode run --model opencode/big-pickle \
    -f docs/OPENCODE-TEAM-PLAN.md \
    "Execute Phase 0 (P0) from docs/OPENCODE-TEAM-PLAN.md. Create hexmind/models.toml and hexmind/models.py with full test coverage in tests/test_models.py. Ensure all existing 107 tests continue to pass."
  ```

### 3. Post-Build Critic & Code Auditor (Verification)
* **Primary Code Critic:** `opencode/nemotron-3-ultra-free` (Nemotron 3 Ultra)
* **Full-Diff Compliance Auditor:** `opencode/longcat-2.5-preview-free` (LongCat 2.5 Preview)
* **Rationale:** A builder should never approve its own work. Big Pickle drives code to pass tests, but Nemotron 3 Ultra acts as the skeptical, adversarial senior reviewer inspecting AST safety, contract regressions, and edge cases. Meanwhile, LongCat 2.5 ingests the entire git diff against the plan in a single turn to verify 100% requirement coverage (R1–R7, D1–D6).
* **Dispatch Commands:**
  ```bash
  # Step A: LongCat verifies full plan compliance across the entire diff
  git diff main > /tmp/hexmind_implementation.diff
  opencode run --model opencode/longcat-2.5-preview-free \
    -f docs/OPENCODE-TEAM-PLAN.md \
    -f /tmp/hexmind_implementation.diff \
    "Verify that every requirement (R1-R7) and defect (D1-D6) in the plan is addressed in this diff with zero missing implementations."

  # Step B: Nemotron 3 Ultra executes adversarial AST code & security audit
  opencode run --model opencode/nemotron-3-ultra-free \
    -f hexmind/models.toml \
    -f hexmind/models.py \
    -f tests/test_models.py \
    "Act as an adversarial, ruthless code reviewer. Scrutinize this implementation for edge cases, silent failure modes, type mismatches, and memory/performance bottlenecks on 8GB RAM."
  ```

### 4. Hexmind Agent Chain Definition (`hexmind/chains/opencode-team.toml`)
The Opencode models must construct this workflow into a permanent, reusable Hexmind agent chain definition at `hexmind/chains/opencode-team.toml`:

```toml
name = "opencode-team"
description = "Autonomous Opencode team pipeline: Nemotron audit -> Pickle TDD build -> LongCat diff inspection -> Nemotron critique"

[[stages]]
name = "pre-audit"
agent = "opencode-ultra"
instructions = "Audit the feature spec and plan for architecture risks, concurrency bottlenecks, and Asahi 8GB RAM constraints. Output an approved execution contract."

[[stages]]
name = "tdd-build"
agent = "opencode-pickle"
instructions = "Implement the approved contract using strict Test-Driven Development (TDD). Write failing tests first, write code, run pytest, iterate until green. Match surrounding code style."

[[stages]]
name = "compliance-check"
agent = "opencode-longcat"
instructions = "Ingest the full repository diff against the specification. Verify all requirements and defect fixes are present. Report any missing implementations."

[[stages]]
name = "post-critique"
agent = "opencode-ultra"
instructions = "Conduct an adversarial code and security review of the diff. Scrutinize edge cases, error handling, and silent fallbacks. Approve only when production-ready."
```

### 5. Tailored Skill Sets for Each Model in the Chain
The Opencode models (specifically leveraging `opencode/muse-spark-1.3-contributor-free`, the prompt/skill engineering specialist) must generate a dedicated capability skill pack for each participating model, conforming to standard `SKILL.md` format:

1. **For `opencode-ultra` (Pre-Audit & Post-Critique):**
   * **`plan-architectural-auditor`**: Guidelines for stress-testing technical plans, memory ceilings, and failure cascades.
   * **`adversarial-code-critic`**: Checklists for finding silent drops, type mismatches, race conditions, and unhandled exceptions.
2. **For `opencode-pickle` (TDD Builder):**
   * **`autonomous-tdd-builder`**: Conventions for writing pytest fixtures, atomic commits, and relentless test-driven iterations without human intervention.
3. **For `opencode-longcat` (Compliance Inspector):**
   * **`monorepo-diff-compliance`**: Prompts and heuristics for cross-referencing multi-file diffs against tabular requirements matrices.
4. **For `opencode-muse` (Meta-Author):**
   * **`skill-chain-synthesizer`**: Automated skill generator that compiles model capabilities into valid Hexmind chain and skill files.

### 6. Model Role Summary Matrix

| Stage | Selected Opencode Model | Operational Specialty | Supporting Model |
| :--- | :--- | :--- | :--- |
| **1. Pre-Audit** | **`opencode/nemotron-3-ultra-free`** | Deep CoT analysis, failure-mode stress testing, architecture review | `opencode/longcat-2.5-preview-free` *(context)* |
| **2. Build** | **`opencode/big-pickle`** | Relentless full-stack TDD execution, tests-first implementation, no hand-waving | `opencode/nemotron-3.5-lightning-free` *(fast fixes)* |
| **3. Post-Audit** | **`opencode/nemotron-3-ultra-free`** | Adversarial code review, security, AST scrutiny, contract verification | `opencode/longcat-2.5-preview-free` *(diff compliance)* |
| **Meta-Authoring**| **`opencode/muse-spark-1.3-contributor-free`** | Standardized `SKILL.md` skill sets and chain definition authoring | `opencode/space-bunny-free` *(lateral ideation)* |



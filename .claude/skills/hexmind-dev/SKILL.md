---
name: hexmind-dev
description: Conventions, invariants and traps for working on the Hexmind codebase. Use when editing anything under hexmind/ — especially the model registry, the relay/audit pipeline, the orchestrator's team state, or the Textual TUI. Covers the generated-roster invariant, INVARIANT S-1, the test commands, and the opencode traps that cause silent hangs.
---

# Working on Hexmind

Hexmind is a multi-model agent orchestrator: a lead model plans a task graph, tasks fan out
across different AI CLIs, a peer auditor reviews each task, and per-domain audit verdicts
decide who gets assigned what. Read `README.md` for behaviour and `docs/OPENCODE-TEAM-PLAN.md`
for the roadmap.

## Layout

| file | responsibility |
| :--- | :--- |
| `models.toml` / `models.py` | **the source of truth for the roster.** All 16 members as structured fields |
| `core.py` | `Task`, `Orchestrator`, plan parsing, the task graph, team state (sleep/wake/lead) |
| `relay.py` | chain loading, `from =` resolution, stage assignment, all `/commands` |
| `auditor.py` | domains, verdict parsing, the bounded revise loop, `Stats` rankings |
| `backends.py` | `DirectBackend`, `HcomBackend`, Ollama local models, process-group cleanup |
| `tui.py` | the Textual room: responsive layout, task board, modals |
| `server.py` | headless FastAPI + WebSocket daemon (`--serve`, needs the `server` extra) |
| `jules.py` | the Google Jules cloud member (works on the GitHub copy, not your tree) |
| `reaping.py` | classifying a relay run's worktree as safe / dirty / unmerged / active, for `/relay clean` |
| `qt/widget.py` | the same room as a `QWidget` (`hexmind.qt.HexmindWidget`, needs the `qt` extra). One brain with the TUI — a turn goes through the same `Orchestrator` |

## Commands

```sh
python3 -m pytest tests -q          # full suite, ~2 min. Run this, not just the file you touched.
python3 -m pytest tests/test_x.py -q # one file
```

A fresh `.venv` cannot run the suite until the extras are installed — `test_server.py` needs
`fastapi`/`httpx2` and `test_qt.py` needs PySide6:

```sh
uv pip install --python .venv/bin/python -e ".[qt,server,dev]"
QT_QPA_PLATFORM=offscreen ./.venv/bin/python -m pytest tests -q
```

**363 tests pass.** The 14 Qt tests `importorskip` when PySide6 is absent, so the suite is green
either way — but that also means a green run can mean "the widget was never exercised".

There is no committed lint config despite a `.ruff_cache` existing, and ~139 findings are
pre-existing and tolerated. Match surrounding style; do not add a formatter config without being
asked. What matters is the **delta**: `python3 -m ruff check .` before and after, and land no new
findings.

## Invariants — breaking these breaks the product

**The roster is generated. Never hand-edit prose about a model.**
`core.ROSTER` comes from `REGISTRY.roster()`, which composes `best_at` and `avoid_for` from
`models.toml`. If you need to change how a model is described, edit `models.toml`. Adding a
hand-maintained dict is how `opencode-muse` came to be described with another model's specialty
and nothing caught it. `test_roster_is_generated_from_the_registry_not_hand_written` guards this.

**INVARIANT S-1: a model holding a live task cannot be put to sleep.** No force, no queue.
Enforced in `Orchestrator.sleep()`, not the UI. Use `can_sleep()` to get `(allowed, reason)` so a
control can be disabled with the reason in its tooltip. Only `pending` tasks may be reassigned.
A model mid-edit is writing real files in the room or in a relay worktree; a half-written file is
never worth the memory.

**The busy set is derived, never tracked.** `Orchestrator.busy` is recomputed from task status via
`BUSY_STATUSES`. Two sources of truth would eventually disagree, and the disagreement either
wedges a model awake forever or interrupts a live edit. `BUSY_STATUSES` is the single list — add
`auditing`/`revising` there, never inline.

**`members` is the awake roster; `known` is every model.** `members` is mutated in place because
the TUI, the server and the Qt widget share that list object. A sleeping model must stay in `known`
or it loses its registry entry, its stats and its journal. `/remove` is the one verb that drops a
model from `known` — so anything that puts a model back into `members` (notably `set_lead`) must
restore `known` too, or the room is led by a model `/team` cannot see.

**A registry change at runtime must go through `models.publish()`.** `REGISTRY`, `ROSTER`,
`TEXT_ONLY`, `OPT_IN`, `DIRECT_CMDS`, `LOCAL_MODELS` and `AGENT_COLOR` are all computed **once, at
import**, and four modules hold them by name (`from .core import ROSTER`). `models.publish()`
reloads and mutates every one **in place**, which is the only thing that works: rebinding a global
would leave the importers holding the old value. A member that is in the registry but missing from
those snapshots is *worse* than one that is absent — it appears in `/models`, has no line in the
lead's roster, and raises `KeyError: DIRECT_CMDS[name]` the first time a task routes to it. This is
what `/profile` uses.

**There is one roster.** `/add` `/remove` `/sleep` `/wake` edit `orchestrator.members` directly. The
team-assembly flow keeps only a snapshot to diff against — never a second copy of the team to drift
from the live one.

## opencode traps

**Sessions are directory-bound, and violating that HANGS.** Resuming a session id from a different
cwd does not error — it hangs until timeout with zero output. So sessions must be keyed
`(model, directory)`, never model alone. This is live: `/relay -n > 1` gives each chain its own
git worktree. (WS-4 has not landed yet, so no session support exists — but do not reintroduce
per-model keys when it does.)

**`opencode run` reads its prompt from stdin**, verified. So there is no argv length ceiling,
unlike `kimi`, whose `-p` takes the prompt as an argv token.

**Do not pass `--pure`** to an opencode member: it disables external plugins, which cuts the team
off from the skills it depends on.

**Only the default `opencode` model is reachable over hcom.** hcom picks a *tool*, not a model,
so the seven non-default opencode models cannot be told apart there. `HCOM_EXCLUDED` is derived
from the registry; keep it that way.

**The opencode family is uniform, so its argv is generated** from the registry
(`DIRECT_CMDS.update(...)`). The bespoke CLIs (claude, agy, codex, copilot, kimi) keep
hand-written argv because their protocols genuinely differ.

## Relay and audit pipeline

- `gate = true` on a stage means an unresolved audit failure **fails the stage and skips its
  dependents** — that is the point. Do not gate a stage whose dependents you still want to run.
- Gate enforcement only happens when peer audit is on. Without `--audit` the gates are inert.
- `from =` in a chain file takes a bare filename (searched in `~/.claude/agents/`,
  `~/.agents/agents/`, `./.claude/agents/`, `./.agents/agents/`) or a full path, which must exist
  as written. A path-shaped ref is never searched for by name.
- Only self-contained chains are bundled in `hexmind/chains/`. Chains importing a user's agent
  files live in `docs/examples/chains/`.

## TUI conventions

- Breakpoints: `NARROW=80`, `SHORT=18`, `TINY=10`. Layout changes must survive all three.
- `RichLog` never re-wraps written lines, so on a width change the chat is cleared and replayed
  from `self.history` with an explicit width.
- `TaskTable._on_click` moves the cursor on a single tap because `DataTable` otherwise needs two.
- Modals are `ModalScreen` with their own CSS and a `VerticalScroll` so they fit a short terminal.
- Always run the **full** suite. `tests/test_mobile_tui.py` asserts no widget overflows the
  terminal width, and a new control in a narrow-mode bar will break it at 40 columns.

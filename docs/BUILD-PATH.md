# Build Path Map

Where every planned operation actually stands. Re-derived 2026-09-28 against `main` at `ed0db64`
(**pushed**), **619 tests passing** (60 of them Qt, offscreen; runs across all surfaces with
`.[qt,server,dev]`).

Derived from the commit history and the code, not from intention, and **re-checked rather than
carried forward** — which is how the previous version came to claim `/add` and `/remove` worked when
neither command existed. Where a workstream is partly built, it says which half.

The design documents are [`OPENCODE-TEAM-PLAN.md`](file:///home/daripper/Projects/hexmind/docs/OPENCODE-TEAM-PLAN.md) (the original R1–R11
requirements), [`TEAM-ASSEMBLY.md`](file:///home/daripper/Projects/hexmind/docs/TEAM-ASSEMBLY.md) (the pre-flight flow), and the [Flagship GUI Roadmap](file:///home/daripper/Projects/hexmind/docs/plans/2026-09-28-gui-flagship-roadmap.md) (Phases 0–9).
This file is the state; those are the reason.

Legend: **DONE** shipped · **PART** part built, gap named · **TODO** not started · **BLOCKED** cannot
proceed until something else lands.

---

## Phase status

| phase | workstream | status | note |
| :--- | :--- | :--- | :--- |
| P0 | WS-1 registry | **DONE** | `models.toml` + `models.py`; `ROSTER` generated; D2/D4/D6 closed |
| P0 | verify stdin | **DONE** | stdin confirmed, no arg ceiling |
| P1 | WS-2 team management | **PART** | all four verbs work; only the duplicate `backends.available()` / `Registry.available()` is left |
| P1 | WS-7 descriptions | **PART** | `/models` `/model NAME` cards exist; no browsable modal |
| P1 | WS-10 `/team` surface | **DONE** | `TeamScreen` built by the `opencode-team` chain, INVARIANT S-1 in the UI |
| P2 | WS-3 leader control | **DONE** | `set_lead` + `/lead` + `/lead recommend` + the startup `LeadPicker` modal all land |
| P3 | WS-4 sessions | **TODO** | feasibility proven (`-s`, `sessionID`, cwd hazard); nothing built |
| P4 | WS-5 preference weighting | **PART** | `weight` + `by_weight()` exist; `fallback()` and relay rotation still ignore them |
| P5 | WS-6 local models | **PART** | registry supports `verify = "ollama"`; **none of the report's 6 added**; `think` unwired |
| P6 | WS-8 plan audit | **PART** | the `audit` chain shipped; the **traceability matrix and `/audit-plan` did not** |
| P7 | WS-9 roster advisor | **TODO** | `/lead recommend` is adjacent but is not the over-provisioning advisor |
| P8 | WS-11 journals | **TODO** | nothing built |
| P9 | WS-12 `/relay clean` | **DONE** | `reaping.py`; pushed, and used for real: it reaped the merged chain's worktree and kept the stage reports |
| P10 | Qt front-end suite (`hexmind.qt`) | **DONE** | `HexmindWidget` (embeddable), `HexmindWindow` (`hexmind-gui` standalone workbench), `TaskGraphView` DAG visualizer, `CommandPalette`, `TimelinePanel`, `StatsPanel`; worker-threaded, zero style pollution; unblocks Aether's Room tab |
| P11 / F0 | Security & Reliability (11 tasks) | **DONE** | Loopback `127.0.0.1` default, token auth for REST/WS, restricted CORS, directive validation, gate warning, Jules branch detection, corrupt stats recovery, turn serialization (see [2026-09-28-hexmind-fixes.md](file:///home/daripper/Projects/hexmind/docs/plans/2026-09-28-hexmind-fixes.md)) |

Team Assembly steps 1–7 in `TEAM-ASSEMBLY.md`: **steps 1–5 DONE** — no default lead, mount-safe
emits, the startup `LeadPicker`, the `Assembly` flow (`/recommend` → edit the room → `/go` →
`/cancel`), and `/scan` `/found` `/profile` as the catalogue the roster is edited from. **Step 6**
(the `hexmind-lead` skill) is **TODO** and is the next engine thing; step 7 (`/relay clean`, which the plan
listed as part of this flow) shipped separately as WS-12.

---

## DONE

| operation | where | commit |
| :--- | :--- | --- |
| all 8 free opencode models as members | `core.py` `backends.py` `tui.py` | `e50f94b` |
| roster generated from structured data | `models.py` `models.toml` | `349d860` |
| `opencode-team` build pipeline | `chains/opencode-team.toml` | `850c70c` |
| `from =` resolves agent names; user chains unbundled | `relay.py` | `a992eaf` |
| sleep / wake / lead with **INVARIANT S-1** | `core.py` | `ed2d5e9` |
| `TeamScreen` modal roster | `tui.py` | `9bb18f4` |
| `--goal` takes a whole sentence | `relay.py` | `6c3a5d8` `9b28cd4` |
| `--timeout` flag | `__main__.py` | `c8ce397` |
| `hexmind-dev` skill | `.claude/skills/` | `c8ce397` |
| `fix-review` chain | `chains/fix-review.toml` | `c8ce397` |
| `audit` chain, two reviewers | `chains/audit.toml` | `ca5ea3b` |
| failed relay stages reach the notes file | `core.py` | `cc529e9` |
| `--once` says why a task failed | `__main__.py` | `cc529e9` |
| synthesis cannot contradict the board | `relay.py` | `cc529e9` |
| 40-column tab bar overflow | `tui.py` | `cc529e9` |
| workspace map in the task prompt | `core.py` | `0275073` `a77322b` |
| isolation check (chain-scoped) | `relay.py` | `a77322b` `c6f4fad` |
| hcom opencode exclusion is honest | `backends.py` | `349d860` |
| no default lead; mount-safe emits | `__main__.py` `tui.py` | `272a50c` |
| two recovered regression tests | `tests/` | `6995055` `ccc2f2d` |
| `/relay clean` | `reaping.py` `relay.py` | `87b8f91` |
| isolation check per stage, not per chain | `relay.py` `core.py` | `79a57ce` |
| a check that could not tell says "unavailable", never "clean" | `relay.py` | `79a57ce` |
| non-ASCII and renamed paths survive the isolation check | `relay.py` | `79a57ce` |
| empty `--goal` is bad arguments, not a crash | `relay.py` | `79a57ce` |
| task sheet button overflow (real threshold, 14 cols) | `tui.py` | `79a57ce` |
| `--timeout` reaches the backend (coverage gap, now covered) | `tests/test_cli.py` | `79a57ce` |
| self-expiring pid marker for active runs | `relay.py` | `63f6297` |
| `app.lead` cannot go stale (one source of truth) | `tui.py` | `877ded4` |
| README visual system: 6 Mermaid diagrams, animated audit, 2 real demo GIFs, style board | `README.md` `docs/` | `877ded4` |
| **startup `LeadPicker`** — a room with no lead blocks until one is chosen | `tui.py` | `7c71fd2` |
| `--serve` honours `--timeout` (it was accepted and ignored) | `server.py` `__main__.py` | `ddb2085` |
| `/add` and `/remove` — the roster changes at runtime | `core.py` `relay.py` | `ddb2085` |
| **team assembly** — `/recommend` → edit the live room → `/go`, `/cancel` | `core.py` `relay.py` | `ddb2085` |
| `/scan` catalogues what is installed; `/found` browses it | `models.py` `relay.py` | `8d9ffe9` |
| `/profile` promotes one find to a member, `best_at` required | `models.py` `relay.py` | `8d9ffe9` |
| **Qt front-end** — `hexmind.qt.HexmindWidget`, embeddable, worker-threaded | `hexmind/qt/` | `f60566c` |
| the documented smoke line works standalone (app + thread teardown) | `hexmind/qt/widget.py` | `4d7aae6` |
| **`server` extra** — a clean install no longer has a broken `--serve` | `pyproject.toml` | `b18412f` |
| **`dev` extra** — a fresh `.venv` can finally run the whole suite | `pyproject.toml` | `b18412f` |
| `ASSEMBLY_SCHEMA` — chains become real `/relay` runs; `use` injects a skill, `create`/`edit` are proposed and never written | `core.py` `relay.py` | `ddaf390` |
| chain provenance recorded in the chain notes | `relay.py` | `ddaf390` |
| tests can no longer write the real `~/.config` (session-wide redirect) | `tests/conftest.py` | `f60566c` |
| the `Registry.available` instance-shadow trap is closed | `tests/conftest.py` | `f60566c` |
| **2026-09-28 audit fixes (11 tasks)** — server bind/auth/CORS, approve directives, gate warning, parse_plan findings, Qt audit checkbox, turn serialization, Jules branch detection, corrupt stats, quota-reassign, example chain paths, TUI/Qt low-risk | see `docs/plans/2026-09-28-hexmind-fixes.md` | `0d5755f`..`4fb60e3` |

---

## IN PROGRESS

**Nothing.** The `fix-review` chain is merged (`79a57ce` → `9bb93f9`) and its worktree reaped. No
chain is running and no workstream is mid-edit.

Three sessions' worth of work landed since the last re-derivation: the assembly flow and
`ASSEMBLY_SCHEMA`, the scan/profile catalogue, and the Qt front-end. All of it is in DONE below.

## PART — the named gap in each

**WS-2** **Done, apart from the duplicate `available()`.** Four verbs, one shape, one refusal
path: `/sleep` parks a session and is reversible, `/wake` revives it, `/add` brings in a model this
session never had (one added to `models.toml` after launch, or excluded at start), and `/remove`
forgets it for the session while leaving its registry entry, stats and nickname alone. Both
refusals come from the orchestrator (`can_sleep`, `can_retire`) and the UI disables the control
from the same answer, so a command and a click cannot disagree.

`/add` deliberately refuses a model with no registry entry, and says so: the roster every prompt is
generated from is `models.toml`, so a model with no entry has no `best_at`, no `avoid_for` and no
colour, and admitting one at runtime would build a roster nothing else agrees with. `/scan` finds
what is installed; `/profile` is what turns a find into a member.

Setting a lead now also restores `known`, not just `members` — `/remove` can drop a model, and a
lead missing from `known` would be running the room while being invisible to `/team`.

*Remaining: `backends.available()` and `Registry.available()` are two functions with overlapping
jobs. Both are read by `/scan` and `/profile` now, so this is the last item in WS-2.*

**WS-3** **Done.** `set_lead`, `/lead`, `/lead recommend` and the startup `LeadPicker` modal all
land. A session opened without a lead blocks on the picker until one is chosen (one candidate is
chosen for you, and declining re-asks on your next request rather than letting it through with no
lead). The non-blocking alternative is documented in `TEAM-ASSEMBLY.md` §6, unbuilt on purpose.

**WS-5** `weight` is data with no consumer. `fallback()` sorts by Laplace score alone; relay
rotation is still plain round-robin. *Gap: use it in both.*

**WS-6** the registry can describe a local model but no local model is described. All six of the
report's engines are absent, the `think` flag is still hardcoded `False` in `backends.py:109`, and
the Ollama name-normalisation defect is documented but unfixed in `Registry.available()`.
*Gap: six entries, `think`, normalisation.*

**WS-7** `/models` and `/model NAME` print cards to the chat. There is no browsable modal, so
discovering a model's `avoid_for` costs a command. *Gap: optional; the chat card answers R7.*

**WS-8** the `audit` chain reviews code ranges. The **traceability matrix — re-derived per phase and
diffed, which is what catches regressions, theatre and omissions — does not exist.** `/audit-plan`
does not exist. *Gap: the mechanism, not the reviewers.*

---

## TODO, in dependency order

| # | operation | blocked by | why now |
| :--- | :--- | :--- | :--- |
| 1 | ~~startup leader picker~~ | — | **done** `7c71fd2`: `LeadPicker`; `/lead` with no lead says so |
| 2 | ~~per-stage isolation check~~ | — | **done** `79a57ce`: escalates between stages and names the one that did it |
| 3 | ~~`Assembly` + `/go` `/cancel` `/recommend`~~ | — | **done**: the lead proposes, the user edits the live room, `/go` makes it review the disagreement and plan against what it was given |
| 3a | ~~`/add` `/remove` — change the roster at runtime~~ | — | **done**: `Orchestrator.add`/`remove`; a model with no registry entry is refused and pointed at `/scan` `/profile` |
| 4 | ~~`/scan` + discovered-vs-curated + `/profile`~~ | — | **done**: a scan writes a catalogue and no registry entry; `/profile` promotes one find, `best_at` required |
| 5 | ~~`ASSEMBLY_SCHEMA` with chains + skills~~ | — | **done**: chains become real `/relay` runs with a provenance line; `use` injects a skill path, `create`/`edit` are proposed and never written; findings are reported |
| 6 | `hexmind-lead` skill (`opencode-muse` authors, `opencode-ultra` reviews) | nothing | **next.** A document, not code: the lead exists now, so describing the role is no longer premature |
| 7 | reconcile the two `available()` functions | — | `/scan` and `/profile` both read `Registry.available()`; make the registry's the real one and delete the duplicate |
| 8 | WS-9 roster advisor | WS-8 | needs the coverage check (TODO 8b) to be safe |
| 9 | WS-11 journals | P1 (done) | unblocked; makes sleeping safe *and* records the work |
| 10 | WS-4 sessions — the big one | nothing | 3–4 h of concurrency and event parsing; the cwd hazard needs its guard on day one |
| 11 | WS-6 remainder: 6 local models, `think`, normalisation | nothing | independent. `/scan` now surfaces the 21 Ollama tags the registry never described, so this has visible input |
| 12 | WS-5 remainder: weight in `fallback()` and rotation | nothing | independent; `/profile` sets a weight below the curated floor, so the field has a new producer |
| 8b | WS-8 remainder: the traceability matrix and `/audit-plan` | P1, P2 (done) | unblocked, and it is the gate on TODO 8 |
| 13 | Aether: flip `room = ["hexmind"]` → `["hexmind[qt]"]` | **not ours** | Aether's own two lines. The widget ships; this is the last step to remove its placeholder |

**The pre-flight area is closed.** The lead proposes a roster, you edit the live one with
`/add` `/remove` `/sleep` `/wake`, and `/go` makes the leader plan against the room you actually
settled on — told what it dropped and what that costs. `/scan` and `/profile` are how a model this
session has never heard of becomes one, deliberately. `ASSEMBLY_SCHEMA` lets the lead ask for a
chain (run for real) or a skill (injected), while `create`/`edit` come back to you as proposals.

What is left of it is one document: the **`hexmind-lead` skill** (design §5), which describes a lead
that now exists.

---

## Risks carried forward

| risk | state |
| :--- | --- |
| merge conflict on `relay.py` with the chain | **happened, resolved.** Only `tests/test_relay.py` actually conflicted; `relay.py` auto-merged with all three work sets intact. The real risk was a *silent* one: the chain's rewrite dropped two imports a main-side test needed, which compiles and then fails at runtime |
| isolation check is after-the-fact | per-stage fix landed, but it is still detection, not prevention — a genuine jail would need a filesystem sandbox |
| `--serve --timeout N` was silently ignored | **fixed.** `run_server` and `HexmindServer` take the timeout and hand it to the backend; the test covers argv → main → run_server → backend with only uvicorn stopped |
| `/add` and `/remove` did not exist | **fixed.** Both built, so the roster changes at runtime and `/scan` has something to add to |
| shared-mode relays get **zero** isolation verification | unresolved trade-off; the current gate is a blunt disable |
| a test wrote the developer's real `~/.config/hexmind/models.toml` and broke a test in another file | **fixed structurally.** Every writable user path is redirected at a temp dir for the whole session. Both this and the next row now have tests that fail with the fix removed |
| `monkeypatch.setattr(REGISTRY, "available", …)` leaves an instance shadow that silently defeats later class-level patches | **fixed.** An autouse fixture clears it around every test; `available_models` is the supported way to pin availability |
| **two sessions editing this repo at once** | happened once: another session rewrote `AGENT_REPORT.md` and added `docs/AETHER-INTERFACE.md` mid-turn. Its file was committed, its report edits left alone, and the report section appended rather than merged. Worth reconciling before the next commit that touches it |
| Aether's placeholder is still up until Aether installs the extra | open, and **not ours to fix** — `Aether/pyproject.toml:16` still says `room = ["hexmind"]` |
| `Stats` is one or two samples deep | `opencode-ultra` is 0/2 on architecture. The rankings are a prior, not evidence yet |
| audit chain ignored "read-only" and edited `main` | prompt-level control is worthless; only the after-the-fact check caught it |

---

## Flagship GUI Roadmap (Phases 0–9)

The project's desktop GUI surface is organized into 10 phases governed by the [D3F Master Implementation Handbook](file:///home/daripper/Projects/hexmind/docs/handbooks/PONYTAIL-MASTER-HANDBOOK.md) and detailed plans in `docs/plans/`:

| Phase | Title | Status | Scope & Deliverables | Document |
| :--- | :--- | :--- | :--- | :--- |
| **0** | **Foundation & Fixes** | **DONE** | 11 audit reliability fixes, loopback 127.0.0.1 default, token auth for REST/WS, restricted CORS, 619 tests passing | [`2026-09-28-hexmind-fixes.md`](file:///home/daripper/Projects/hexmind/docs/plans/2026-09-28-hexmind-fixes.md) |
| **1** | **Frame & Foundation** | **DONE** | Native `HexmindWindow` (`hexmind-gui`), menus (File, Room), shortcuts (F5, Ctrl+K, Ctrl+Q, Ctrl+O), status bar | [`2026-09-28-gui-flagship-roadmap.md`](file:///home/daripper/Projects/hexmind/docs/plans/2026-09-28-gui-flagship-roadmap.md) |
| **2** | **Live Wire** | **READY** | Reactive signal bus (`turnState`, `taskChanged`, `teamChanged`), in-place DAG node updates via preserved `update_task` | [`2026-09-28-gui-flagship-roadmap.md`](file:///home/daripper/Projects/hexmind/docs/plans/2026-09-28-gui-flagship-roadmap.md) |
| **3** | **The Foundry** | **READY** | Prompt editor, draft plan inspector, template library, multi-turn review | [`2026-09-28-gui-feature-forge.md`](file:///home/daripper/Projects/hexmind/docs/plans/2026-09-28-gui-feature-forge.md) |
| **4** | **Battleground** | **READY** | Split-pane peer audit view, diff viewer, escalation modal | [`2026-09-28-gui-flagship-roadmap.md`](file:///home/daripper/Projects/hexmind/docs/plans/2026-09-28-gui-flagship-roadmap.md) |
| **5** | **Roster & Identity** | **READY** | Visual roster management, model capability badges, member details | [`2026-09-28-gui-ux-ideas.md`](file:///home/daripper/Projects/hexmind/docs/plans/2026-09-28-gui-ux-ideas.md) |
| **6** | **Timeline & History** | **READY** | Execution waterfall (`TimelinePanel`), turn replay slider, session log | [`2026-09-28-gui-feature-forge.md`](file:///home/daripper/Projects/hexmind/docs/plans/2026-09-28-gui-feature-forge.md) |
| **7** | **Analytics & Scorecard**| **READY** | Domain audit matrix, pyqtgraph performance charts (`StatsPanel`), export | [`2026-09-28-gui-flagship-roadmap.md`](file:///home/daripper/Projects/hexmind/docs/plans/2026-09-28-gui-flagship-roadmap.md) |
| **8** | **Command Center** | **READY** | `CommandPalette` 2.0 (fuzzy search, custom actions via preserved `set_commands`), DAG tools via preserved `select_task`, `fit`, `clear` | [`PONYTAIL-MASTER-HANDBOOK.md`](file:///home/daripper/Projects/hexmind/docs/handbooks/PONYTAIL-MASTER-HANDBOOK.md) |
| **9** | **Polish & Ship** | **READY** | Dark pastel design system, desktop alerts via preserved `notify.py`, native PyInstaller distribution | [`2026-09-28-gui-flagship-roadmap.md`](file:///home/daripper/Projects/hexmind/docs/plans/2026-09-28-gui-flagship-roadmap.md) |

### Preserved Roadmap Assets Invariant
Static code audits (such as [`docs/audits/PONYTAIL-2026-09-28.md`](file:///home/daripper/Projects/hexmind/docs/audits/PONYTAIL-2026-09-28.md)) must **never** strip the following hooks as dead code:
1. `hexmind/qt/palette.py: set_commands` & `Command.haystack` (Phase 8: Palette 2.0 / P10)
2. `hexmind/qt/graph.py: select_task, fit, clear` (Phase 8: Wiring Diagram / P13)
3. `hexmind/notify.py` (Phase 9: Come-back notifications via KDE Connect)
4. `hexmind/qt/graph.py: update_task` (Phase 2: Live Wire in-place node update)


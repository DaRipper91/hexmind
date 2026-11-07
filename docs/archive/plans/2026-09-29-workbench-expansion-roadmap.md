# 🌌 Hexmind Workbench Expansion Roadmap 🌌

---

> 🌌 **D3F Master Handbook**
>
> **Scope:** Core engineering, Textual TUI, and Qt GUI
>
> **Relationship to prior docs:** This roadmap extends the completed GUI flagship work and the GUI batch roadmap into a broader workbench plan that covers the shared core, the terminal room, and the desktop workbench together.
>
> **Directive:** 🛡️ Zero Hallucination — every concrete reference below maps to code that exists today in the repository. Anything that does **not** have a first-class hook yet is marked as a planned architectural addition rather than described as already present.

---

## 📖 Part 1 — User Manual

### 1.1 Overview

Hexmind already has three meaningful surfaces:

- a shared orchestration core centered on [`hexmind/core.py`](file:///home/daripper/Projects/hexmind/hexmind/core.py), [`hexmind/backends.py`](file:///home/daripper/Projects/hexmind/hexmind/backends.py), [`hexmind/auditor.py`](file:///home/daripper/Projects/hexmind/hexmind/auditor.py), and [`hexmind/relay.py`](file:///home/daripper/Projects/hexmind/hexmind/relay.py)
- a Textual terminal room in [`hexmind/tui.py`](file:///home/daripper/Projects/hexmind/hexmind/tui.py)
- a Qt workbench spread across [`hexmind/qt/app.py`](file:///home/daripper/Projects/hexmind/hexmind/qt/app.py), [`hexmind/qt/widget.py`](file:///home/daripper/Projects/hexmind/hexmind/qt/widget.py), [`hexmind/qt/settings.py`](file:///home/daripper/Projects/hexmind/hexmind/qt/settings.py), [`hexmind/qt/health.py`](file:///home/daripper/Projects/hexmind/hexmind/qt/health.py), [`hexmind/qt/chat.py`](file:///home/daripper/Projects/hexmind/hexmind/qt/chat.py), and [`hexmind/qt/models.py`](file:///home/daripper/Projects/hexmind/hexmind/qt/models.py)

This roadmap turns the current recommendation backlog into a single execution plan covering:

- **9 core engineering initiatives**
- **10 TUI initiatives**
- **13 GUI initiatives**

That is **32 planned work items**, followed by **3 exploratory opportunities** that are promising but should be treated as opt-in follow-ons rather than the mainline backlog.

### 1.2 Why this roadmap is cross-surface

Some improvements are front-end local, but many are not:

- a stronger event model improves TUI, GUI, and server clients at once
- better failure taxonomy improves both room messaging and desktop diagnostics
- a command catalog can power slash commands, the Qt palette, and future docs or remote clients
- persistent replay data unlocks both desktop replay tooling and terminal postmortem workflows

The plan therefore groups work into tracks, not only by file location.

### 1.3 Track overview

| Track | Scope | Initiative IDs | Goal |
|---|---|---|---|
| **Track A** | Shared core and architecture | C1–C9 | Reduce drift, improve typing, and unlock future surfaces cleanly |
| **Track B** | Textual TUI | T1–T10 | Make the terminal room faster, clearer, and more capable for heavy users |
| **Track C** | Qt GUI | G1–G13 | Make the desktop workbench easier to set up, read, and operate |
| **Track D** | Exploratory follow-ons | X1–X3 | High-value ideas that should be validated after the main backlog |

---

## 🔧 Part 2 — Technical Manual

### 2.1 Invariants this roadmap must preserve

1. **One Brain Rule:** Room behavior continues to come from shared orchestration logic, not duplicated TUI/Qt rules.
2. **Embed Invariant:** `HexmindWidget` remains an embeddable widget, and global Qt styling stays in `HexmindWindow` or the host.
3. **Generated Roster Rule:** Model capability prose still comes from the registry/model metadata pipeline rather than hand-maintained UI descriptions.
4. **INVARIANT S-1:** A model holding a live task cannot be put to sleep; no UI roadmap item may undermine `Orchestrator.can_sleep()` / `sleep()`.
5. **Shared Config Rule:** Saved defaults continue to flow through `hexmind/config.py`.
6. **Preserved Hooks Rule:** Planned work must not remove roadmap hooks explicitly preserved in `qt/palette.py`, `qt/graph.py`, or `notify.py`.

### 2.2 Current code anchors

The roadmap below intentionally maps to surfaces that already exist:

| Concern | Existing code anchor |
|---|---|
| Event emission | `Orchestrator.emit(...)` in `core.py`; `_Room._emit(...)` in `qt/widget.py`; server broadcast path in `server.py` |
| Saved config | `config.py`, `qt/settings.py`, `qt/app.py`, `__main__.py` |
| TUI room state | `HexmindApp` in `tui.py` |
| Qt room state | `_Room` + `HexmindWidget` in `qt/widget.py` |
| Palette actions | `qt/palette.py` and `HexmindWidget._refresh_palette_commands()` |
| Health scan | `qt/health.py` and the Settings-hosted trigger in `qt/settings.py` |
| Direct chat | `qt/chat.py` |
| Model inspection | `qt/models.py` |
| Stats and timeline | `qt/stats.py`, `qt/timeline.py` |
| Notifications | `notify.py` and tray wiring in `qt/app.py` |

### 2.3 Current gaps the roadmap must acknowledge honestly

These ideas are valid, but the current tree does **not** already contain a full subsystem for them:

- no durable session journal or replay module
- no central typed event schema; payloads are still ad hoc dicts
- no shared slash-command registry
- no QDockWidget-based desktop layout system
- no explicit “phase” object for task grouping in the TUI; task grouping would need to derive from ids/dependencies

Roadmap items in those areas must therefore begin with enabling architecture, not with a UI-only patch.

---

## 💻 Part 3 — Developer Guide

## Track A — Shared Core and Architecture

### C1 — Unified event schema

**Goal:** Standardize lifecycle events shared by the orchestrator, TUI, GUI, and server.

**Current anchors**
- `core.py` emits `message`, `status`, `plan`, `task`, and `team`
- `qt/widget.py` bridges those emits to Qt signals
- `server.py` already packages events for remote consumers

**Planned work**
- define a shared event contract for room lifecycle payloads
- normalize status/task/message/team payload shapes
- make new front-ends consume the same semantics

**Why now**
- every other surface enhancement becomes easier if the payload model stops drifting

### C2 — Typed event dataclasses

**Goal:** Replace loose dict payloads with typed models where possible.

**Current anchors**
- `Emit = Callable[[str, dict], None]` in `core.py`
- `_Room._emit()` in `qt/widget.py`

**Planned work**
- introduce typed structures for message/task/status/plan/audit/chunk events
- keep adapters thin for TUI, Qt, and server

**Gap note**
- this is an architectural addition; the current tree does not already expose typed event objects

### C3 — Persistent session journal

**Goal:** Record turns, task transitions, and audit outcomes in durable replayable form.

**Current anchors**
- `Orchestrator.history` stores only final `(user, final answer)` tuples in memory
- comments in `core.py` mention journal readability, but there is no journal module

**Planned work**
- write a structured append-only session log
- capture event stream, not only final summaries
- make logs safe to read without live agents

**Gap note**
- this is a genuine missing subsystem, not a thin wrapper over existing state

### C4 — Smarter error taxonomy

**Goal:** Separate quota/auth/timeout/tool/parse/filesystem failures so surfaces can recover better.

**Current anchors**
- `TeamBusy`, `TeamError` in `core.py`
- broad user-facing failures in `qt/chat.py`, `qt/models.py`, and `qt/widget.py`
- quota and audit-specific recovery logic already appears in `core.py`

**Planned work**
- define error categories and recovery hints
- use them consistently in room messages, health checks, and direct/probe flows

### C5 — Capability descriptors per model

**Goal:** Expose registry-derived capability facts in a reusable form.

**Current anchors**
- `REGISTRY`, `ROSTER`, `TEXT_ONLY`, `OPT_IN` in `core.py`
- registry-backed metadata already drives `qt/models.py`

**Planned work**
- add structured capability descriptors for tool/file/edit/lead/audit suitability
- consume them in scheduling hints and surface messaging

### C6 — Config versioning and migration

**Goal:** Make config growth safe as settings and workspace state expand.

**Current anchors**
- `config.py` currently reads/writes TOML sections without schema migration

**Planned work**
- add schema versioning
- add migration behavior for future room/server/gui settings growth

### C7 — Shared command catalog

**Goal:** Replace duplicated command vocabulary with one authoritative registry.

**Current anchors**
- `qt/palette.py` already models commands as data
- `HexmindWidget` builds a literal slash-command list
- relay/team command behavior lives in `relay.py` and shared orchestration flows

**Planned work**
- centralize command metadata: name, aliases, hint, availability, category
- generate palette content, help surfaces, and future remote docs from it

**Gap note**
- current command behavior is distributed; this needs deliberate consolidation

### C8 — Metrics and tracing hooks

**Goal:** Capture timings and flow metrics beyond audit pass/fail stats.

**Current anchors**
- `auditor.Stats` tracks pass/fail by model/domain
- `qt/widget.py` already measures turn duration for the turn meter
- `qt/health.py` captures latency during health scan

**Planned work**
- add per-turn, per-task, per-backend timing hooks
- track retries, reassignments, and cancellation events
- feed future UX and ranking improvements

### C9 — Session replay mode

**Goal:** Inspect old sessions without live agents attached.

**Current anchors**
- `Orchestrator.history` gives only a minimal in-memory summary
- the server and room event flows already define the shape of what a future replay would need

**Planned work**
- build a replay reader on top of persistent journal data
- support post-run inspection without requiring active backends

**Gap note**
- replay depends on durable journaling first; there is no standalone replay substrate in the current tree

## Track B — Textual TUI

### T1 — Transcript and detail find bar

**Goal:** Add full find workflow to the TUI.

**Current anchors**
- `tui.py` has no equivalent of the Qt `Ctrl+F` transcript search

**Planned work**
- add find UI and hit navigation for transcript and task detail
- preserve narrow-terminal behavior

### T2 — Pinned task detail

**Goal:** Let users hold one task open while the rest of the room continues updating.

**Current anchors**
- `write_task(...)` in `tui.py`
- current detail view is driven by table selection

**Planned work**
- add a pinned/locked detail mode
- stop live row navigation from replacing a user-pinned inspection target

### T3 — Task filters and scopes

**Goal:** Make larger task sets easier to read.

**Current anchors**
- `TaskTable` and task rendering in `tui.py`

**Planned work**
- filter by status, model, audit result, dependency readiness, or failure state
- expose quick toggles that still work at narrow widths

### T4 — Derived task grouping / phase collapse

**Goal:** Reduce noise in long plans by collapsing logical groups.

**Current anchors**
- task list and dependency model already exist

**Planned work**
- derive groups from dependency layers, ids, or chain stage structure
- allow collapse/expand behavior in the task board

**Gap note**
- the current core does not expose explicit phase objects; grouping must be derived or added

### T5 — Inline task recovery actions

**Goal:** Make failure recovery faster from the keyboard.

**Current anchors**
- team/task actions already exist elsewhere conceptually via commands

**Planned work**
- surface retry, inspect, reassign, and copy-output paths directly from the selected task context

### T6 — Better compact/mobile terminal mode

**Goal:** Improve usability on very narrow or short terminals.

**Current anchors**
- `NARROW`, `SHORT`, `TINY` breakpoints in `tui.py`
- existing narrow-mode replay and modal handling

**Planned work**
- make compact mode more intentional rather than only responsive fallback
- enlarge high-value controls and reduce concurrent visual clutter

### T7 — Faster roster operations

**Goal:** Reduce the cost of team changes in the terminal.

**Current anchors**
- `TeamScreen` in `tui.py` already exposes sleep/wake/lead affordances

**Planned work**
- add stronger keyboard-first actions, hints, and maybe nickname editing

**Reference correction**
- this is an enhancement to an existing roster control, not a brand-new roster feature

### T8 — Transcript timestamps and role badges

**Goal:** Make long sessions easier to parse after the fact.

**Current anchors**
- `history` and chat rendering in `tui.py`

**Planned work**
- optionally add timestamps and clearer user/lead/worker/auditor labelling
- preserve re-wrap behavior on resize

### T9 — Live streaming pane for the TUI

**Goal:** Bring the GUI’s live output idea to the terminal room.

**Current anchors**
- Qt already has `liveOutput` in `_Room` and `LivePane` hosted by `HexmindWidget`
- TUI does not yet consume per-line live output

**Planned work**
- route backend streaming into a terminal-side live pane or modal
- make it optional to avoid noise on low-height terminals

### T10 — Escalation inbox

**Goal:** Make “needs you” items impossible to miss.

**Current anchors**
- escalations currently appear inline in chat in the TUI

**Planned work**
- add a dedicated queue, hotkey, or filter for unresolved human-required events

## Track C — Qt GUI

### G1 — Active vs saved settings clarity

**Goal:** Make Settings scope obvious.

**Current anchors**
- `SettingsPage` in `qt/settings.py`
- saved/default refresh behavior in `qt/app.py`

**Planned work**
- distinguish “saved defaults for future sessions” from “current-window behavior refreshed from saved settings”

### G2 — Agent Health as a first-class workspace

**Goal:** Move from aggregate status to inspectable diagnostics.

**Current anchors**
- `HealthScanner` in `qt/health.py`
- current trigger and summary label inside `SettingsPage`

**Planned work**
- promote health to a real workspace or substantial panel
- show model, availability, auth, latency, and actionable hints

### G3 — Room status strip

**Goal:** Expand the current top bar into a richer persistent room summary.

**Current anchors**
- `leadBox`, `auditBox`, `status`, and `turnMeter` already exist in `qt/widget.py`

**Planned work**
- extend the existing top-row controls into a more coherent at-a-glance strip

**Reference correction**
- this is not a greenfield feature; the current widget already has partial status-strip behavior

### G4 — First-run onboarding

**Goal:** Turn the first launch into a guided setup flow.

**Current anchors**
- `SettingsPage`
- `HexmindWindow`
- shared config loading in `config.py`

**Planned work**
- detect no-config / first-run state
- guide the user through lead/roster/health/start choices

### G5 — Quick rail actions

**Goal:** Put high-frequency actions next to navigation.

**Current anchors**
- `BenchRail` in `qt/rail.py`
- actions currently live mostly in menus and Settings

**Planned work**
- add refresh team, check health, open config, and reset-layout actions to the rail shell

### G6 — Safer settings editing

**Goal:** Add editor-grade protection to the Settings workspace.

**Current anchors**
- `SettingsPage.save()`, `reload()`, and reset/open helpers in `qt/settings.py`

**Planned work**
- dirty-state tracking
- revert/discard flow
- unsaved-change warning before destructive refresh/navigation

### G7 — Direct Line discoverability

**Goal:** Make the purpose of Direct Line obvious to non-expert users.

**Current anchors**
- `DirectLine` already exists in `qt/chat.py`
- it already exposes “Ask” and “Ask another”

**Planned work**
- improve copy, empty states, labels, and framing

**Reference correction**
- this is a discoverability improvement to an existing feature, not the creation of direct chat

### G8 — Calibration Rack affordances

**Goal:** Make model inspection feel operational, not passive.

**Current anchors**
- `CalibrationRack` already has model inspection plus a single-model probe

**Planned work**
- add compare, open file, copy path, and related utility actions

**Reference correction**
- the current rack is already more than a static viewer because the probe flow exists today

### G9 — Task detail pinning and split focus

**Goal:** Stop task inspection from being overwritten by unrelated updates.

**Current anchors**
- `detail` browser and task-selection handling in `qt/widget.py`
- graph selection hooks already exist

**Planned work**
- allow pinning/locking of task detail
- preserve live graph/task updates around a pinned inspection target

### G10 — Better empty and error states

**Goal:** Make every workspace answer “what next?”

**Current anchors**
- `SettingsPage`, `DirectLine`, `CalibrationRack`, and the planned health workspace

**Planned work**
- replace passive labels and blank states with clear CTAs and recovery text

### G11 — Config editing shortcuts

**Goal:** Make config-heavy workflows faster.

**Current anchors**
- open-config helpers already exist in `qt/settings.py` and `qt/app.py`

**Planned work**
- add copy path, export snapshot, import snapshot, reveal folder, and section-level reset paths

**Reference correction**
- “open config file/folder” is already implemented; this initiative extends, rather than introduces, config shortcuts

### G12 — Visual system feedback

**Goal:** Make success/warning/error treatment consistent across the desktop workbench.

**Current anchors**
- theme token system in `qt/theme.py`
- current status labels in Settings, Direct Line, Calibration Rack, and the main room

**Planned work**
- standardize visual feedback semantics and reuse them across workspaces

### G13 — Dockable GUI panes

**Goal:** Let advanced users reshape the workbench around their current task.

**Current anchors**
- the current shell uses `BenchRail`, `QSplitter`, and `QTabWidget`
- graph, timeline, stats, live output, and task detail already exist as separate visual surfaces

**Planned work**
- evaluate a controlled move toward dockable panes for detail-heavy workflows
- preserve the current simple default layout for first-run clarity

**Gap note**
- this is a larger shell evolution because no `QDockWidget` framework exists in the current window today

## Track D — Exploratory Follow-ons

### X1 — OSC 8 hyperlinks in terminal surfaces

**Why it matters**
- TUI users could click file paths, docs, or issue references directly in modern terminals

**Current anchors**
- the TUI already uses terminal-specific clipboard behavior (`OSC 52` in `tui.py`)

**Reality check**
- useful and plausible, but terminal compatibility detection should ship with it

### X2 — Terminal capability detection

**Why it matters**
- the TUI could adapt to hyperlink, emoji, mouse, truecolor, or constrained SSH environments more intentionally

**Current anchors**
- `FORCE_ASCII` and breakpoint logic already show the TUI cares about terminal constraints

### X3 — Richer Qt layout persistence

**Why it matters**
- full workspace restoration is a large perceived-quality upgrade

**Current anchors**
- `HexmindWidget` already persists splitter state and current right-tab index through `QSettings`
- `HexmindWindow` already persists geometry through `config`

**Reality check**
- deeper persistence is a natural extension of existing behavior, not a speculative mismatch

---

## 📋 Part 4 — Reference Audit and Gap Review

This section is the roadmap’s self-review against the existing code, so it stays honest.

### 4.1 Corrections applied to earlier wording

1. **Room status strip:** not a brand-new surface. `qt/widget.py` already has a lead selector, audit toggle, status label, and turn meter. The roadmap now frames this as an expansion of the existing top bar.
2. **Calibration Rack affordances:** not a pure-inspector feature. `qt/models.py` already includes a live single-model probe.
3. **Direct Line discoverability:** not the creation of direct chat. `qt/chat.py` already supports direct chat and comparison responses.
4. **Config shortcuts:** opening `config.toml` and its folder already exists in the Settings workspace and window menus. The roadmap now treats this as an extension to import/export/copy/reveal/reset operations.
5. **Roster quick actions in the TUI:** not a missing team UI. `TeamScreen` already exists; the roadmap targets faster operations and richer keyboard affordances instead.

### 4.2 Known architectural gaps

These roadmap items still require enabling work because there is no complete implementation substrate yet:

- **C1 / C2:** current event emission is ad hoc and stringly typed
- **C3 / C9:** no durable journal or replay module exists yet
- **C7:** no single command registry currently owns slash commands and palette entries
- **T4:** task grouping does not have a first-class phase model yet
- **future docking-oriented GUI ideas:** the current Qt shell uses `BenchRail`, `QSplitter`, and `QTabWidget`, not `QDockWidget`

### 4.3 Areas that are already partially ahead of the roadmap

Some current code is stronger than a casual backlog description would suggest:

- Qt already has:
  - turn cancellation
  - a live turn meter
  - transcript search
  - live output tabbing
  - graph, timeline, and stats tabs
  - splitter/right-tab layout persistence
- the TUI already has:
  - a dedicated team roster screen
  - compact-mode breakpoints
  - clipboard integration for task output copying

That means future docs should avoid understating what is already shipped.

---

## 📚 Part 5 — Recommended Delivery Order

### 5.1 Highest-value sequence

1. **C1–C2** — shared event and typing cleanup
2. **G2, G4, G6, G10** — health, onboarding, settings safety, empty/error states
3. **T1, T2, T3, T10** — terminal search, pinned detail, filters, escalation handling
4. **C4, C7, C8** — failures, command catalog, metrics
5. **G3, G5, G8, G9, G11, G12, G13** — richer workbench polish
6. **T4–T9** — heavier terminal workflow improvements
7. **C3, C5, C6, C9** — journaling, capability descriptors, config migration, replay
8. **X1–X3** — exploratory polish once the core backlog is stable

### 5.2 Lowest-risk starting batch

If the goal is to improve the product fastest with minimal architectural risk, start with:

- **G2** Agent Health workspace
- **G6** Safer settings editing
- **G10** Better empty and error states
- **T1** Transcript/detail search in the TUI
- **T2** Pinned task detail in the TUI

---

## 🔍 Part 6 — Initiative Ledger

| ID | Area | Initiative | Existing anchor | Status |
|---|---|---|---|---|
| C1 | Core | Unified event schema | `core.py`, `qt/widget.py`, `server.py` | ⏳ Planned |
| C2 | Core | Typed event dataclasses | `core.py`, `qt/widget.py` | ⏳ Planned |
| C3 | Core | Persistent session journal | `core.py` history only | ⏳ Planned |
| C4 | Core | Smarter error taxonomy | `core.py`, `qt/chat.py`, `qt/models.py`, `qt/widget.py` | ⏳ Planned |
| C5 | Core | Capability descriptors per model | `core.py`, registry-backed metadata | ⏳ Planned |
| C6 | Core | Config versioning and migration | `config.py` | ⏳ Planned |
| C7 | Core | Shared command catalog | `qt/palette.py`, `qt/widget.py`, `relay.py` | ⏳ Planned |
| C8 | Core | Metrics and tracing hooks | `auditor.py`, `qt/widget.py`, `qt/health.py` | ⏳ Planned |
| C9 | Core | Session replay mode | future journal-backed replay | ⏳ Planned |
| T1 | TUI | Transcript/detail find bar | `tui.py` | ⏳ Planned |
| T2 | TUI | Pinned task detail | `tui.py` | ⏳ Planned |
| T3 | TUI | Task filters and scopes | `tui.py` | ⏳ Planned |
| T4 | TUI | Derived task grouping / phase collapse | `tui.py`, task dependencies | ⏳ Planned |
| T5 | TUI | Inline task recovery actions | `tui.py` | ⏳ Planned |
| T6 | TUI | Better compact/mobile mode | `tui.py` breakpoints | ⏳ Planned |
| T7 | TUI | Faster roster operations | `TeamScreen` in `tui.py` | ⏳ Planned |
| T8 | TUI | Transcript timestamps and role badges | `tui.py` transcript/history | ⏳ Planned |
| T9 | TUI | Live streaming pane | Qt `LivePane` as precedent | ⏳ Planned |
| T10 | TUI | Escalation inbox | TUI chat escalation flow | ⏳ Planned |
| G1 | GUI | Active vs saved settings clarity | `qt/settings.py`, `qt/app.py` | ⏳ Planned |
| G2 | GUI | Agent Health workspace | `qt/health.py`, `qt/settings.py`, `qt/app.py` | ⏳ Planned |
| G3 | GUI | Room status strip expansion | `qt/widget.py` top bar | ⏳ Planned |
| G4 | GUI | First-run onboarding | `qt/app.py`, `qt/settings.py`, `config.py` | ⏳ Planned |
| G5 | GUI | Quick rail actions | `qt/rail.py`, `qt/app.py` | ⏳ Planned |
| G6 | GUI | Safer settings editing | `qt/settings.py` | ⏳ Planned |
| G7 | GUI | Direct Line discoverability | `qt/chat.py` | ⏳ Planned |
| G8 | GUI | Calibration Rack affordances | `qt/models.py` | ⏳ Planned |
| G9 | GUI | Task detail pinning and split focus | `qt/widget.py`, `qt/graph.py` | ⏳ Planned |
| G10 | GUI | Better empty/error states | `qt/settings.py`, `qt/chat.py`, `qt/models.py` | ⏳ Planned |
| G11 | GUI | Config editing shortcuts | `qt/settings.py`, `qt/app.py` | ⏳ Planned |
| G12 | GUI | Visual system feedback | `qt/theme.py` plus workspaces | ⏳ Planned |
| G13 | GUI | Dockable GUI panes | current `QSplitter`/`QTabWidget` shell | ⏳ Planned |
| X1 | Explore | OSC 8 hyperlinks | `tui.py` terminal-specific behavior precedent | 🔬 Explore |
| X2 | Explore | Terminal capability detection | `tui.py` ASCII/breakpoint handling precedent | 🔬 Explore |
| X3 | Explore | Richer Qt layout persistence | `qt/widget.py`, `qt/app.py` | 🔬 Explore |

### 6.1 Related roadmap documents

This roadmap complements:

- [Flagship GUI Roadmap](file:///home/daripper/Projects/hexmind/docs/plans/2026-09-28-gui-flagship-roadmap.md)
- [GUI Batch Roadmap — Next 12 Phases](file:///home/daripper/Projects/hexmind/docs/plans/2026-09-29-gui-batch-roadmap.md)
- [GUI UX & Visual System](file:///home/daripper/Projects/hexmind/docs/plans/2026-09-28-gui-ux-ideas.md)
- [GUI Feature Forge](file:///home/daripper/Projects/hexmind/docs/plans/2026-09-28-gui-feature-forge.md)

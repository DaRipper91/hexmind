# 🌌 Hexmind GUI Batch Roadmap — Next 12 Phases 🌌

---

> 🌌 **D3F Master Handbook**
>
> **Source Basis:** Existing GUI roadmap and current Qt implementation in `hexmind/qt/`
>
> **Relationship to prior docs:** This document is a forward-looking execution roadmap that extends the completed Flagship GUI Roadmap with the next 12 GUI improvements, grouped into implementation batches.
>
> **Directive:** 🛡️ Zero Hallucination — this roadmap names only surfaces that already exist in the repository (`HexmindWindow`, `BenchRail`, `SettingsPage`, `HealthScanner`, `DirectLine`, `CalibrationRack`, task board/detail surfaces, and shared config handling). Where implementation shape is proposed rather than already present, it is called out as planned work.

---

## 📖 Part 1 — User Manual

### 1.1 Overview

The first Flagship GUI Roadmap (`Phase 0` through `Phase 9`) established the standalone Qt workbench:

- the host window in [`hexmind/qt/app.py`](file:///home/daripper/Projects/hexmind/hexmind/qt/app.py)
- the navigation shell in [`hexmind/qt/rail.py`](file:///home/daripper/Projects/hexmind/hexmind/qt/rail.py)
- the settings workspace in [`hexmind/qt/settings.py`](file:///home/daripper/Projects/hexmind/hexmind/qt/settings.py)
- agent health checks in [`hexmind/qt/health.py`](file:///home/daripper/Projects/hexmind/hexmind/qt/health.py)
- direct chat in [`hexmind/qt/chat.py`](file:///home/daripper/Projects/hexmind/hexmind/qt/chat.py)
- model inspection in [`hexmind/qt/models.py`](file:///home/daripper/Projects/hexmind/hexmind/qt/models.py)

This roadmap defines the **next 12 GUI phases**, organized into **4 implementation batches**. The aim is not to invent new subsystems first, but to make the current workbench clearer, safer, and more fluent in daily use.

### 1.2 What this roadmap covers

The 12 phases correspond to the 12 proposed GUI improvements:

1. Settings active-vs-saved clarity
2. Agent Health as a first-class workspace
3. Room status strip
4. First-run onboarding
5. Quick actions in the rail
6. Safer settings editing
7. Direct Line discoverability
8. Calibration Rack affordances
9. Task detail pinning and split focus
10. Better empty and error states
11. Config editing shortcuts
12. Visual system feedback

### 1.3 Batch overview

| Batch | Theme | Roadmap phases | Covers proposals | Goal |
|---|---|---:|---|
| **Batch A** | Settings UX & configuration trust | 1–4 | 1, 6, 11, 12 | Make Settings feel safe, explicit, and operationally clear |
| **Batch B** | Health, onboarding, and first-run success | 5–7 | 2, 4, 10 | Help users get from launch to a working team without confusion |
| **Batch C** | Workbench navigation and room awareness | 8–10 | 3, 5, 7 | Make the GUI easier to read and faster to operate during active use |
| **Batch D** | Deep work surfaces | 11–12 | 8, 9 | Improve model inspection and task-focused execution workflows |

---

## 🔧 Part 2 — Technical Manual

### 2.1 Non-negotiable engineering constraints

All 12 phases must continue to obey the existing GUI invariants:

1. **Embed Invariant:** `HexmindWidget` remains embeddable and must not assume ownership of the host window or application styling.
2. **One Brain Rule:** Orchestrator rules stay in core modules; Qt presents truth, it does not recreate it.
3. **Host Isolation Invariant:** Application-wide styling belongs in `HexmindWindow` or the host application, never in `HexmindWidget`.
4. **Shared Config Rule:** Persistent room/server/notification defaults continue to flow through `hexmind/config.py`.
5. **Preserved Hooks Rule:** Reserved roadmap hooks in `palette.py`, `graph.py`, and `notify.py` must remain intact.

### 2.2 Delivery strategy

These phases should be implemented **batch by batch**, not as one monolithic GUI rewrite.

- **Batch A** is the lowest-risk, highest-confidence start because it builds on the now-existing Settings workspace.
- **Batch B** should follow because it improves first-run success and diagnostics.
- **Batch C** tightens the shell and interaction model once users can trust the setup flow.
- **Batch D** comes last because it touches the most workflow-specific UI and benefits from the earlier clarity work.

### 2.3 Validation rule

Each phase should ship with Qt tests and preserve the full suite:

```bash
QT_QPA_PLATFORM=offscreen python3 -m pytest tests -q
python3 -m ruff check .
```

The repo already tolerates existing unrelated ruff findings, so the operational requirement is still: **introduce no new findings in touched files**.

---

## 💻 Part 3 — Developer Guide

## Batch A — Settings UX & Configuration Trust

### Phase 1 — Active vs saved settings clarity

**Goal:** Make it explicit which controls affect future sessions and which can change current-window behavior.

**Primary surfaces**
- `hexmind/qt/settings.py`
- `hexmind/qt/app.py`

**Planned work**
- Add a clearly visible note or banner separating:
  - defaults written to `config.toml`
  - current-window behavior refreshed from saved settings
- Distinguish “applies to new sessions” from “applies after save/reload”
- Ensure success messages reflect the actual scope of the change

**Acceptance**
- A user can tell, without reading source, whether a setting is session-default state or active-window state.

### Phase 2 — Safer settings editing

**Goal:** Prevent accidental loss of edits and make Settings behave like a real workbench editor.

**Primary surfaces**
- `hexmind/qt/settings.py`
- `hexmind/qt/app.py`

**Planned work**
- Add dirty-state tracking
- Add explicit **Save**, **Revert**, and unsaved-changes messaging
- Warn before leaving Settings or reloading values when there are unsaved edits

**Acceptance**
- Unsaved edits are visible and recoverable.

### Phase 3 — Config editing shortcuts

**Goal:** Make configuration operations faster for advanced users.

**Primary surfaces**
- `hexmind/qt/settings.py`
- `hexmind/qt/app.py`

**Planned work**
- Add shortcuts such as:
  - copy config file path
  - copy config directory path
  - reveal config directory
  - export config snapshot
  - import config snapshot
  - reset one section without resetting all settings

**Acceptance**
- A user no longer has to leave the GUI just to perform routine config-file operations.

### Phase 4 — Visual system feedback

**Goal:** Standardize success, warning, and error presentation across workbench surfaces.

**Primary surfaces**
- `hexmind/qt/settings.py`
- `hexmind/qt/health.py`
- `hexmind/qt/app.py`
- `hexmind/qt/theme.py`

**Planned work**
- Define reusable visual treatment for:
  - success
  - warning
  - blocking error
  - informational state
- Apply the same status semantics in Settings, Health, and follow-on workspaces

**Acceptance**
- Similar states look and read the same way everywhere in the GUI.

## Batch B — Health, Onboarding, and First-Run Success

### Phase 5 — Agent Health as a first-class workspace

**Goal:** Promote health from a single command/status line into a browsable diagnostic workspace.

**Primary surfaces**
- `hexmind/qt/health.py`
- `hexmind/qt/rail.py`
- `hexmind/qt/app.py`

**Planned work**
- Introduce a dedicated workspace or panel for health results
- Show structured columns such as:
  - model
  - CLI availability
  - auth readiness
  - latency
  - actionable hint
- Preserve non-blocking scan behavior

**Acceptance**
- A user can identify exactly which agent is unavailable and why.

### Phase 6 — First-run onboarding

**Goal:** Turn a cold start into a guided setup instead of an implicit expert-only flow.

**Primary surfaces**
- `hexmind/qt/app.py`
- `hexmind/qt/settings.py`
- `hexmind/qt/rail.py`

**Planned work**
- Detect absence of a user config or a minimally configured first run
- Open the workbench in a guided setup state
- Present a simple checklist:
  - pick roster
  - choose lead
  - run health check
  - start room

**Acceptance**
- A new user can get to a working GUI session without already knowing the configuration model.

### Phase 7 — Better empty and error states

**Goal:** Make every workspace answer “what should I do next?”

**Primary surfaces**
- `hexmind/qt/settings.py`
- `hexmind/qt/chat.py`
- `hexmind/qt/models.py`
- future health workspace

**Planned work**
- Replace passive blank states with contextual CTA-based empty states
- Make error states specific and recoverable
- Cover at least:
  - no health scan yet
  - no direct conversation yet
  - no custom config yet
  - no selected model or task

**Acceptance**
- Blank or partial states always guide the user toward a next action.

## Batch C — Workbench Navigation and Room Awareness

### Phase 8 — Room status strip

**Goal:** Make active room state readable at a glance.

**Primary surfaces**
- `hexmind/qt/app.py`
- `hexmind/qt/widget.py`

**Planned work**
- Add a persistent strip summarizing:
  - lead
  - audit state
  - working directory
  - current turn state
  - elapsed turn time
- Use existing room/orchestrator signals instead of inventing duplicate state

**Acceptance**
- Core room state is visible without hunting across multiple panes.

### Phase 9 — Quick actions in the rail

**Goal:** Put global workbench actions where they are faster than menu traversal.

**Primary surfaces**
- `hexmind/qt/rail.py`
- `hexmind/qt/app.py`

**Planned work**
- Add compact rail-level actions for:
  - refresh team
  - check health
  - open config
  - reset layout
- Keep the navigation shell compact and keyboard-friendly

**Acceptance**
- Routine operations are accessible in one click from anywhere in the workbench.

### Phase 10 — Direct Line discoverability

**Goal:** Make the single-model chat purpose obvious to first-time users.

**Primary surfaces**
- `hexmind/qt/chat.py`
- `hexmind/qt/rail.py`
- `hexmind/qt/app.py`

**Planned work**
- Clarify the label, subtitle, or empty-state copy for Direct Line
- Explain that it is a one-model conversation path, distinct from orchestrated room turns
- Preserve the existing roadmap identity while improving user comprehension

**Acceptance**
- Users understand Direct Line without needing roadmap vocabulary.

## Batch D — Deep Work Surfaces

### Phase 11 — Calibration Rack affordances

**Goal:** Make model inspection feel operational instead of passive.

**Primary surfaces**
- `hexmind/qt/models.py`
- `hexmind/config.py`

**Planned work**
- Add practical actions such as:
  - probe model
  - open `models.toml`
  - copy model/config path
  - compare selected models
- Preserve the rule that persistent model metadata lives in config/registry flows, not ad hoc Qt-only state

**Acceptance**
- Calibration Rack becomes a toolbench for model tuning, not just a viewer.

### Phase 12 — Task detail pinning and split focus

**Goal:** Support deeper task inspection during busy turns.

**Primary surfaces**
- `hexmind/qt/widget.py`
- `hexmind/qt/graph.py`

**Planned work**
- Allow a task detail view to remain pinned while the user navigates transcript, board, or graph
- Support split-focus browsing so task inspection is not overwritten by unrelated UI updates
- Preserve live task/graph updates and existing preserved graph hooks

**Acceptance**
- A user can hold one task in view while continuing to inspect other room activity.

---

## 📋 Part 4 — Standard Operating Procedures (SOP)

### SOP-1: Batch execution order

1. Implement **Batch A** first.
2. Ship **Batch B** after Settings semantics are stable.
3. Ship **Batch C** once onboarding and health states are trustworthy.
4. Ship **Batch D** last, after the workbench shell and empty-state language have settled.

### SOP-2: Testing per phase

For each phase:

1. Add or update `tests/test_qt_*.py`.
2. Verify offscreen behavior:
   ```bash
   QT_QPA_PLATFORM=offscreen python3 -m pytest tests/test_qt_*.py -q
   ```
3. Re-run the full suite before landing:
   ```bash
   QT_QPA_PLATFORM=offscreen python3 -m pytest tests -q
   ```

### SOP-3: Documentation maintenance

When a phase lands:

1. Update this roadmap’s status table.
2. Update the Qt front-end section of `README.md` if user-visible capabilities changed.
3. Keep the completed Flagship Roadmap as historical baseline; do not overwrite it with future-phase planning.

---

## 📚 Part 5 — Glossary

| Term | Definition |
| :--- | :--- |
| **Batch A** | Settings-focused quality and trust work around saved defaults and config operations. |
| **Batch B** | Health, onboarding, and first-run support work to reduce setup friction. |
| **Batch C** | Navigation and room-state improvements that make the workbench faster to operate. |
| **Batch D** | Higher-focus workflow surfaces for model tuning and task investigation. |
| **Status strip** | A persistent room summary band showing active execution context. |
| **Split focus** | Holding task detail in view while navigating other workbench surfaces. |

---

## 🔍 Part 6 — Reference Guide

### 6.1 Phase ledger

| Phase | Batch | Milestone | Key files | Primary deliverable | Status |
| :---: | :---: | :--- | :--- | :--- | :---: |
| **1** | **A** | Active vs saved settings clarity | `qt/settings.py`, `qt/app.py` | Clear scope messaging for saved vs active state | ⏳ Planned |
| **2** | **A** | Safer settings editing | `qt/settings.py`, `qt/app.py` | Dirty-state save/revert flow | ⏳ Planned |
| **3** | **A** | Config editing shortcuts | `qt/settings.py`, `qt/app.py` | Faster file/path/import/export operations | ⏳ Planned |
| **4** | **A** | Visual system feedback | `qt/theme.py`, `qt/settings.py`, `qt/health.py` | Consistent success/warn/error language | ⏳ Planned |
| **5** | **B** | Agent Health workspace | `qt/health.py`, `qt/rail.py`, `qt/app.py` | Structured diagnostic workspace | ⏳ Planned |
| **6** | **B** | First-run onboarding | `qt/app.py`, `qt/settings.py`, `qt/rail.py` | Guided setup flow | ⏳ Planned |
| **7** | **B** | Better empty/error states | `qt/settings.py`, `qt/chat.py`, `qt/models.py` | Recovery-oriented CTAs across surfaces | ⏳ Planned |
| **8** | **C** | Room status strip | `qt/app.py`, `qt/widget.py` | Always-visible room execution summary | ⏳ Planned |
| **9** | **C** | Quick actions in the rail | `qt/rail.py`, `qt/app.py` | Global actions reachable in one click | ⏳ Planned |
| **10** | **C** | Direct Line discoverability | `qt/chat.py`, `qt/rail.py`, `qt/app.py` | Clearer one-model chat framing | ⏳ Planned |
| **11** | **D** | Calibration Rack affordances | `qt/models.py` | Action-oriented model tooling | ⏳ Planned |
| **12** | **D** | Task detail pinning & split focus | `qt/widget.py`, `qt/graph.py` | Persistent task inspection workflow | ⏳ Planned |

### 6.2 Relationship to existing roadmap docs

This document complements, but does not replace:

- [Flagship GUI Roadmap](file:///home/daripper/Projects/hexmind/docs/plans/2026-09-28-gui-flagship-roadmap.md)
- [GUI UX & Visual System](file:///home/daripper/Projects/hexmind/docs/plans/2026-09-28-gui-ux-ideas.md)
- [GUI Feature Forge](file:///home/daripper/Projects/hexmind/docs/plans/2026-09-28-gui-feature-forge.md)

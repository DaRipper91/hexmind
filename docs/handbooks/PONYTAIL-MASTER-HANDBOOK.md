# 🌌 Hexmind GUI Flagship — Master Agent Implementation Handbook 🌌

---

> 🌌 **Hexmind Engineering & Implementation Master Handbook**
>
> **Authority Level:** High — Canonical Guide for Autonomous Agents & Developers
> **Scope:** Full Flagship GUI Evolution (`Phase 0` through `Phase 9`), Architectural Invariants, Safe Refactoring, and Asset Preservation
> **Primary Source References:** 
> - [`docs/plans/2026-09-28-gui-flagship-roadmap.md`](file:///home/daripper/Projects/hexmind/docs/plans/2026-09-28-gui-flagship-roadmap.md)
> - [`docs/plans/2026-09-28-gui-ux-ideas.md`](file:///home/daripper/Projects/hexmind/docs/plans/2026-09-28-gui-ux-ideas.md)
> - [`docs/plans/2026-09-28-gui-feature-forge.md`](file:///home/daripper/Projects/hexmind/docs/plans/2026-09-28-gui-feature-forge.md)
> - [`docs/plans/2026-09-28-hexmind-fixes.md`](file:///home/daripper/Projects/hexmind/docs/plans/2026-09-28-hexmind-fixes.md)
> - [`docs/audits/PONYTAIL-2026-09-28.md`](file:///home/daripper/Projects/hexmind/docs/audits/PONYTAIL-2026-09-28.md)

---

## 📖 Part 1 — Handbook Mission & Architecture Overview

### 1.1 The Purpose of This Handbook
The original Ponytail audit performed an isolated static scan of the codebase and flagged anything without an existing caller as "dead code." In an evolving project, however, **unhooked code often represents pre-built infrastructure for planned roadmap features**. Deleting those constructs causes immediate data loss and rework.

This handbook bridges that gap. It is an **actionable, end-to-end execution guide for AI agents and human engineers** to complete the `hexmind-gui` Flagship Roadmap. It explicitly defines:
1. **Preserved Assets:** Hooks that must **not** be deleted because they serve upcoming roadmap phases.
2. **Safe Pre-Flight Cuts:** Genuine dead code and abandoned prototype debt that can be pruned safely.
3. **Phase-by-Phase Implementation Playbook:** Exact technical specifications, signal flow, UI layout, and test requirements for Phases 0 through 9.

### 1.2 System Architecture
Hexmind unites disparate AI CLI processes (`claude`, `agy`, `codex`, `opencode`, `kimi`, `jules`, etc.) into a cohesive team through a layered architecture:

```
┌────────────────────────────────────────────────────────────────────────┐
│                        PRESENTATION LAYER                              │
│   • Textual TUI (`tui.py`)                                             │
│   • FastAPI/WebSocket Headless Server (`server.py`)                    │
│   • Flagship Desktop Workbench (`hexmind/qt/app.py` & `widget.py`)      │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ Qt Signals & Event Emitters
┌───────────────────────────────────▼────────────────────────────────────┐
│                        ORCHESTRATION LAYER                             │
│   • Orchestrator Core (`core.py`): Task graph, turn loop, consensus   │
│   • Relay Engine (`relay.py`): Multi-stage sequential handoffs         │
│   • Peer Auditor (`auditor.py`): Disagreement scoring & ledger         │
│   • Configuration System (`config.py`): Shared TOML defaults (Phase 1) │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ Subprocess CLI Invocation
┌───────────────────────────────────▼────────────────────────────────────┐
│                         EXECUTION LAYER                                │
│   • Model Registry (`models.py`, `models.toml`): 16 CLI members        │
│   • Execution Backends (`backends.py`): DirectBackend, HcomBackend     │
│   • External Bridges: Jules API (`jules.py`), Notify (`notify.py`)     │
└────────────────────────────────────────────────────────────────────────┘
```

### 1.3 Core Architectural Invariants (The "Bench Rules")
When implementing roadmap features, agents must strictly uphold:
* **Rule 1 (Real CLIs, Zero Raw APIs):** All LLM interactions execute via installed local CLIs. Never introduce direct HTTP API calls to Anthropic, OpenAI, or Google.
* **Rule 2 (Single Source of Truth):** The orchestrator in `core.py` owns task execution and writes to the reliability ledger (`Stats`). Views (`HexmindWidget`, `StatsPanel`) are strictly read-only observers.
* **Rule 3 (The Embed Rule):** `HexmindWidget` must remain a standalone, embeddable `QWidget` that requires only Qt and the orchestrator. Subsystem frames (Settings, Health, Model Manager) live on the outer shell (`QMainWindow` in `qt/app.py` or `BenchRail`).
* **Rule 4 (Measured Sublime Aesthetic):** No generic dark themes (e.g., `qdarkstyle` is forbidden). Adhere strictly to the color tokens, contrast rules (≥ 4.5:1), and typography in `hexmind/qt/theme.py`.

---

## 🛡️ Part 2 — Audit Reconciliation: Preserved Assets vs. Safe Cuts

Before executing new roadmap phases, agents must clean technical debt **without touching planned hooks**.

### 2.1 Preserved Assets Registry (DO NOT DELETE)
The following constructs were flagged in the Ponytail audit as "never called" or "tests-only", but are **mandatory roadmap assets**. Agents must preserve them:

| Symbol / File | Location | Roadmap Need | Reason to Preserve |
| :--- | :--- | :--- | :--- |
| **`CommandPalette.set_commands`** | [`hexmind/qt/palette.py:63`](file:///home/daripper/Projects/hexmind/hexmind/qt/palette.py#L63) | **Phase 8 (P10)** | Called whenever `teamChanged` fires so the command palette updates its slash commands dynamically. |
| **`TaskGraphView.select_task`** | [`hexmind/qt/graph.py:314`](file:///home/daripper/Projects/hexmind/hexmind/qt/graph.py#L314) | **Phase 8 (P13)** | Required for interactive graph selection: clicking a graph node highlights and reveals task details in the drawer. |
| **`TaskGraphView.fit`** | [`hexmind/qt/graph.py:320`](file:///home/daripper/Projects/hexmind/hexmind/qt/graph.py#L320) | **Phase 8 (P13)** | Required for "Fit to View" DAG auto-centering on canvas resize or turn start. |
| **`TaskGraphView.clear`** | [`hexmind/qt/graph.py:328`](file:///home/daripper/Projects/hexmind/hexmind/qt/graph.py#L328) | **Phase 0 / 8** | Required when resetting room state or starting a new turn. |
| **`notify.py` (KDE Connect)** | [`hexmind/notify.py`](file:///home/daripper/Projects/hexmind/hexmind/notify.py) | **Phase 9 (Forge)** | Required for "Come-back pings": background tray notifications and mobile phone buzz when turns finish or need `/approve`. |
| **`TaskGraphView.update_task`** | [`hexmind/qt/graph.py:260`](file:///home/daripper/Projects/hexmind/hexmind/qt/graph.py#L260) | **Phase 2 (Live Wire)** | Evaluated for in-place live status updates (`running`, `passed`, `failed`) during turn execution without redrawing the entire DAG. |

---

### 2.2 Approved Safe Pre-Flight Cleanups
The following 14 items are verified dead code or obsolete prototype debt that can be safely refactored or deleted:

```
[APPROVED CUTS]
├── pyproject.toml
│   └── Drop unused optional deps: qtawesome, qdarkstyle, numpy (pyqtgraph imports its own)
├── hexmind/jules.py
│   └── Drop unused send_message() and hardcode AUTO_CREATE_PR in create_session()
├── hexmind/relay.py & hexmind/core.py
│   └── Consolidate duplicate _AUDIT_WORDS into core._AUDIT_TRUE_WORDS / _AUDIT_FALSE_WORDS
├── hexmind/qt/widget.py
│   └── Collapse identical slash and non-slash branches in _submit()
├── hexmind/server.py
│   ├── Inline single-line _task_to_dict() at call sites
│   └── Delete unused pydantic model ChainRunRequest
├── hexmind/core.py
│   ├── Remove JSONDecodeError from parse_directives except tuple (subclass of ValueError)
│   ├── Drop unused Directives.__bool__()
│   └── Drop defensive inspect.signature schema check in Orchestrator.ask()
├── hexmind/models.py
│   ├── Delete Registry.matrix (abandoned terminal table generator)
│   └── Delete unused prototype helpers: Registry.detect(), members(), Model.is_local
├── hexmind/backends.py
│   └── Delete unused HcomBackend.members()
├── hexmind/reaping.py
│   └── Delete unused Report.counts
└── hexmind/qt/graph.py
    └── Delete unused 15-line wrapper GraphPanel (widget.py uses TaskGraphView directly)
```

---

## 🚀 Part 3 — Step-by-Step Roadmap Execution Playbook

---

### Phase 0: Honest Instruments & First-Run Fixes
* **Target Objective:** Eliminate misleading UI indicators and restore broken baseline actions.

#### Task 0.1: Lead Combo True State (P1)
* **Problem:** On initial launch without `--lead`, the combo defaults to showing the first team member instead of an unassigned state.
* **Implementation:**
  1. Add placeholder entry `"(no lead — parallel turn)"` as index 0 when `self.lead is None`.
  2. In `refresh_team()` ([`hexmind/qt/widget.py:310`](file:///home/daripper/Projects/hexmind/hexmind/qt/widget.py#L310)), update the combo without overwriting an active lead.
  3. Ensure selecting index 0 passes `lead=None` to the room.

#### Task 0.2: Peer Audit Initial Checkbox State (P2)
* **Problem:** Checkbox does not reflect orchestrator startup audit state.
* **Implementation:**
  1. In `widget.py:348`, initialize `self.auditCheck.setChecked(bool(self.audit))`.
  2. Wire `self.auditCheck.toggled` to `self._room.orch.set_audit(checked)` (protected by `_orch_lock`).

#### Task 0.3: Checkbox Visual Indicators in Dark Theme (P3)
* **Problem:** Standard QCheckBox checkmarks are nearly invisible against dark backgrounds.
* **Implementation:**
  1. In `hexmind/qt/theme.py`, update `QCheckBox::indicator` styles with explicit high-contrast check SVG / stroke colors (`ACCENT_TEAL = #4EC9B0`).

#### Task 0.4: Connect Command Palette Menu Action (P11)
* **Problem:** Menu bar action for Command Palette sits disabled.
* **Implementation:**
  1. In `hexmind/qt/app.py`, connect `action_palette.triggered` to `self.room.open_palette()`.

---

### Phase 1: Shared Configuration Subsystem (`config.py`)
* **Target Objective:** Unify CLI, headless server, and GUI under a shared, validated TOML configuration file at `~/.config/hexmind/config.toml`.

#### Technical Specification:
* **File:** Create [`hexmind/config.py`](file:///home/daripper/Projects/hexmind/hexmind/config.py)
* **Schema:**
  ```toml
  [room]
  lead = ""                  # default lead model ID or empty
  members = ["claude", "agy", "codex", "kimi"]
  audit = true               # default peer audit toggle
  theme = "measured-dark"    # UI theme

  [server]
  host = "127.0.0.1"
  port = 8765
  token = ""

  [notifications]
  phone_buzz = false         # KDE Connect ping via notify.py
  threshold_seconds = 30     # only notify if turn took longer than 30s
  ```
* **Required Functions:**
  - `load_config(path: Path | None = None) -> dict[str, Any]`
  - `save_section(section: str, data: dict[str, Any], path: Path | None = None) -> None`
  - `get_defaults() -> RoomDefaults` (validated dataclass ready for `argparse`)
* **Integration Points:**
  - `hexmind/__main__.py`: Merge saved defaults with CLI arguments (explicit CLI flags always take precedence).
  - `hexmind/server.py`: Load server host/port/token defaults.
  - `hexmind/qt/app.py`: Read room defaults on startup and save window geometry on close.

---

### Phase 2: Live Wire & Hand Brake (Real-Time Control)
* **Target Objective:** Provide visible feedback during long-running turns and allow cancellation of individual tasks or the entire turn.

#### Task 2.1: Bridge Dropped `status` Events (P4)
* The orchestrator emits status events (`thinking`, `running tool`, `evaluating`). Bridge these through `_Room._emit` to Qt Signal `turnProgress(model, status_text)`.

#### Task 2.2: Live Turn Meter (`qt/widget.py`)
* Display an active timer badge next to the status label:
  ```
  [● claude · planning · 0:42] [Stop ■]
  ```
* Implemented using a lightweight `QTimer` started on `turnState(True)` and stopped on `turnState(False)`.

#### Task 2.3 & 2.4: Hand Brake (Cancellation)
* **Process Group Termination:** Update `backends.py:DirectBackend` to launch model CLIs in dedicated process groups (`os.setsid`).
* When cancel is triggered:
  1. Send `SIGTERM` to the process group.
  2. Grace period of 1.5s, then escalate to `SIGKILL`.
* **GUI Stop Button:** A dedicated Stop button next to `sendButton` that calls `self._room.cancel_turn()`.
* **Server Parity:** Add `POST /api/turn/cancel` to `server.py`.

---

### Phase 3: The Bench Rail (Navigation Shell)
* **Target Objective:** Transform `hexmind-gui` into a multi-workspace workbench without breaking the embeddable `HexmindWidget`.

#### Architecture:
```
┌──┬────────────────────────────────────────────────────────────────────┐
│  │ [ Room: Project Alpha ] [ + ]             [ Direct Line ] [ Rack ] │
│  ├────────────────────────────────────────────────────────────────────┤
│  │                                                                    │
│B │                                                                    │
│E │                    ACTIVE WORKSPACE VIEW                           │
│N │               (HexmindWidget / CalibrationRack /                   │
│C │                    DirectLine / SettingsView)                      │
│H │                                                                    │
│  │                                                                    │
│R │                                                                    │
│A │                                                                    │
│I │                                                                    │
│L ├────────────────────────────────────────────────────────────────────┤
│  │ ⚙️ Settings   |   🩺 Instrument Check   |   Status: Ready          │
└──┴────────────────────────────────────────────────────────────────────┘
```
* **Location:** Implemented in `hexmind/qt/app.py` surrounding `QStackedWidget`.
* **Dock Tabs:**
  - `Room`: Primary chat and orchestration workbench (`HexmindWidget`).
  - `Direct Line`: 1:1 chat interface.
  - `Calibration Rack`: Model manager and live roster tuner.
  - `Settings`: General configuration.

---

### Phase 4: The Bench Settings Screen
* **Target Objective:** Direct GUI interface for `hexmind/config.py`.
* **Panels:**
  1. **Roster Defaults:** Checkbox list of available models to include in default teams.
  2. **Audit & Autonomy:** Default lead selection, default peer audit state, automatic PR creation toggle.
  3. **Theme & Contrast:** Dark / Light / High-Contrast mode switcher; typography scaling slider.
  4. **Notifications:** Toggle KDE Connect (`notify.py`) pings and turn duration threshold.

---

### Phase 5: Instrument Check & First Light (Diagnostics)
* **Target Objective:** Self-diagnostic screen verifying installed CLI tools, permissions, and network availability.
* **Component:** `hexmind/qt/health.py`
* **Checks:**
  - Scan for each model CLI in `$PATH` (`claude`, `agy`, `codex`, `opencode`, `kimi`, `jules`).
  - Detect versions (`--version`) and measure ping response latency.
  - Verify Termux / Android vs Linux host environment (`is_termux()`).
  - Show green / yellow / red status badges next to each model in the roster.

---

### Phase 6: Calibration Rack (Model Manager)
* **Target Objective:** Visual inspection and configuration for `models.toml`.
* **Features:**
  1. Inspect context window, cost tier, supported modalities, and family groupings.
  2. **Single-Model Probe:** A "Test Query" prompt box to run a one-off probe against any model CLI to verify its current availability and output formatting without starting a team turn.

---

### Phase 7: Direct Line (1:1 Model Chat)
* **Target Objective:** Bypass the orchestrator for quick single-model queries.
* **Implementation:**
  - Stripped-down conversational view communicating directly with `backends.run_model(model_id, prompt)`.
  - **"Ask Another" Comparator:** A button to re-send the prompt to a secondary model and display their responses side-by-side.

---

### Phase 8: Polish, Finishing & Preserved Hook Activation
* **Target Objective:** Activate the preserved hooks and complete the visual polish.

#### Task 8.1: Palette 2.0 (Connecting Preserved `set_commands`)
* In `hexmind/qt/palette.py`, activate [`set_commands(commands)`](file:///home/daripper/Projects/hexmind/hexmind/qt/palette.py#L63).
* Connect `_Room.teamChanged` → `CommandPalette.set_commands` with updated `/model`, `/lead`, and `/ask` entries.

#### Task 8.2: Graph Interaction (Connecting Preserved `select_task` & `fit`)
* In `hexmind/qt/graph.py`, wire node click events:
  - Clicking a node triggers `select_task(task_id)`, updating the task detail panel.
  - Double-clicking or pressing `F` triggers `fit()`, smoothly fitting the DAG bounding rect into view.

#### Task 8.3: Detail Drawer (P7, P15)
* Selected tasks remain pinned in the detail view even as subsequent tasks complete and stream messages into the main transcript.

#### Task 8.4: Accessibility & Contrast (WCAG AA Compliance)
* Run automated headless tests asserting contrast ratio ≥ 4.5:1 across all panels on light and dark themes.

---

### Phase 9: Flagship Backlog (Feature Forge Integration)

#### Feature 9.1: Come-Back Pings (Activating Preserved `notify.py`)
* **Trigger:** When turn execution time exceeds `threshold_seconds` (default: 30s) or when an audit escalation occurs (`auditor.py:277`).
* **Execution:** Call `notify.ping(title, message)` in a background worker thread (`QThreadPool`).
* **Desktop & Phone:** Emits a desktop notification and vibrates paired phone via KDE Connect.

---

## 🛠️ Part 4 — Standard Operating Procedures (SOPs) for Agents

### SOP-1: Pre-Flight Debt Pruning Protocol
1. **Target:** Apply only the 14 approved cuts in §2.2.
2. **Safety Rule:** Never delete `set_commands`, `select_task`, `fit`, `clear`, or `notify.py`.
3. **Execution:**
   - Apply edits via targeted diffs.
   - Run tests: `pytest tests/`
   - Assert all tests pass before proceeding to feature development.

### SOP-2: Phase Implementation & Verification Protocol
1. **Read Task Spec:** Review the specific phase task in `docs/plans/2026-09-28-gui-flagship-roadmap.md`.
2. **Draft Test First:** Create or extend corresponding test module in `tests/test_qt_*.py`.
3. **Implement Feature:** Respect the embed rule (`HexmindWidget` remains standalone; shell features live in `app.py`).
4. **Run Headless Suite:**
   ```bash
   QT_QPA_PLATFORM=offscreen pytest tests/test_qt_*.py
   ```
5. **Format & Lint:**
   ```bash
   ruff check hexmind/ tests/
   ```

### SOP-3: UI Styling & Theme Rules
1. Never hardcode colors using hex values inside widgets.
2. Always import color tokens from `hexmind.qt.theme`:
   - `INK_NORMAL`, `INK_MUTED`, `BG_CANVAS`, `BG_PANEL`, `ACCENT_TEAL`, `ACCENT_AMBER`, `ACCENT_CORAL`.
3. Support dynamic theme switching by listening to `themeChanged`.

---

## 📊 Part 5 — Acceptance & Progress Ledger

| Phase | Core Component | Key Files | Preserved Hook / Requirement | Status |
| :---: | :--- | :--- | :--- | :---: |
| **Pre-Flight** | Debt Cleanup | `jules.py`, `relay.py`, `pyproject.toml` | Apply safe cuts; preserve F2, F5, F9 | ⏳ Pending |
| **Phase 0** | Honest Instruments | `qt/widget.py`, `qt/theme.py`, `qt/app.py` | Lead combo, audit box, checkbox SVG | ⏳ Pending |
| **Phase 1** | Shared Config | `config.py`, `__main__.py`, `server.py` | TOML persistence across CLI & GUI | ⏳ Pending |
| **Phase 2** | Live Wire & Hand Brake | `backends.py`, `qt/widget.py`, `server.py` | Turn meter, process group kill | ⏳ Pending |
| **Phase 3** | Bench Rail | `qt/app.py`, `qt/rail.py` | Multi-view navigation shell | ⏳ Pending |
| **Phase 4** | Bench Settings | `qt/settings.py` | Visual config management | ⏳ Pending |
| **Phase 5** | Instrument Check | `qt/health.py` | CLI availability diagnostics | ⏳ Pending |
| **Phase 6** | Calibration Rack | `qt/models.py`, `models.toml` | Model manager & test query | ⏳ Pending |
| **Phase 7** | Direct Line | `qt/chat.py` | 1:1 conversation view | ⏳ Pending |
| **Phase 8** | Polish & Finishing | `qt/palette.py`, `qt/graph.py` | Wire `set_commands`, `select_task`, `fit` | ⏳ Pending |
| **Phase 9** | Come-Back Pings | `notify.py`, `qt/app.py` | Wire `notify.ping()` to turn completion | ⏳ Pending |

---

*This handbook is the governing specification for all autonomous agent implementations on Hexmind. Follow its sequence strictly, respect the preserved assets, and verify each milestone with regression tests.*

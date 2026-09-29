# 🌌 Hexmind GUI Flagship Roadmap — Master Handbook 🌌

---

> 🌌 **D3F Master Handbook**
>
> **Source Document:** [`docs/plans/2026-09-28-gui-flagship-roadmap.md`](file:///home/daripper/Projects/hexmind/docs/plans/2026-09-28-gui-flagship-roadmap.md)
>
> **Chain Stages:** 🧊 Architect ✓ · 🦄 SME ✓ · 👾 Auditor ✓ · 🌌 UX Writer ✓
>
> **Directive:** 🛡️ Zero Hallucination — every fact is traceable to the source document. Where the source is silent, the gap is marked explicitly.
>
> **Roadmap Scope:** 10 Phases (`Phase 0` through `Phase 9`), Architectural Invariants, and Implementation Specifications

---

## 📖 Part 1 — User Manual

### 1.1 Overview & Roadmap Scope
The Hexmind GUI Flagship Roadmap is the authoritative blueprint for transitioning `hexmind-gui` from a prototype debug console into a production-grade multi-agent desktop workbench. 

### 1.2 Core Architectural Decisions
Four foundational design decisions govern the entire roadmap:
* **Decision 1 (Shared Config — `D1`):** Configuration is centralized in a shared, human-editable TOML file at `~/.config/hexmind/config.toml` loaded by the CLI (`hexmind`), headless server (`--serve`), and desktop GUI (`hexmind-gui`).
* **Decision 2 (Direct Line — `D2`):** A dedicated 1:1 conversational view that communicates directly with individual model CLIs, bypassing orchestrator task planning for fast queries.
* **Decision 3 (Instrument Check — `D3`):** An in-app health and diagnostic matrix scanning system paths for installed model CLIs, verifying credentials and execution status.
* **Decision 4 (Calibration Rack — `D4`):** A visual model manager for inspecting and tuning model parameters in `~/.config/hexmind/models.toml`.

```
┌────────────────────────────────────────────────────────────────────────┐
│                        FLAGSHIP ROADMAP OVERVIEW                       │
├────────────────────────────────────────────────────────────────────────┤
│  Phase 0: Honest Instruments (P1, P2, P3, P11)                         │
│  Phase 1: Shared Config Subsystem (config.py, D1)                      │
│  Phase 2: Live Wire and Hand Brake (Turn meter, task cancellation, P4) │
│  Phase 3: The Bench Rail (Navigation shell & multi-workspace layout)   │
│  Phase 4: The Bench Settings (UI for config.py)                        │
│  Phase 5: Agent Health & First Light (Diagnostic scanner, D3)          │
│  Phase 6: Model Manager & Calibration Rack (models.toml tuning, D4)    │
│  Phase 7: Direct Line (1:1 chat & side-by-side comparison, D2)         │
│  Phase 8: Polish & Preserved Hook Activation (P7, P8, P10, P12, P13)   │
│  Phase 9: Flagship Backlog (Feature forge integrations)                │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 🔧 Part 2 — Technical Manual

### 2.1 The Build Guide & Engineering Rules
1. **The Embed Invariant:** `HexmindWidget` must remain a standalone, embeddable `QWidget` that depends only on Qt and the orchestrator. Subsystem frames live on `QMainWindow` or `BenchRail`.
2. **One Brain Rule:** Presentation components never duplicate orchestrator rules. Logic belongs in `core.py`, `relay.py`, `auditor.py`, or `config.py`.
3. **Contrast Compliance:** All panels must achieve a contrast ratio ≥ 4.5:1 against `palette().text().color()`.
4. **Preserved Hooks Invariant:** Do not delete pre-built methods intended for upcoming roadmap phases:
   - `CommandPalette.set_commands` (Phase 8: Palette 2.0 / P10)
   - `TaskGraphView.select_task`, `fit`, `clear` (Phase 8: Interactive Wiring Diagram / P13)
   - `notify.py` (Phase 9: KDE Connect come-back pings)
   - `TaskGraphView.update_task` (Phase 2: Live Wire in-place node update)

---

## 💻 Part 3 — Developer Guide

### Phase 0 — Honest Instruments & First-Run Fixes
* **Task 0.1: Lead Combo True State (P1):** Add placeholder entry `"(no lead — parallel turn)"` as index 0 when `self.lead is None`.
* **Task 0.2: Peer Audit Initial State (P2):** Call `self.auditCheck.setChecked(bool(self.audit))` during initialization in `widget.py`.
* **Task 0.3: Checkbox Indicators on Dark Theme (P3):** Update `hexmind/qt/theme.py` with high-contrast checkmark styling.
* **Task 0.4: Connect Command Palette Menu (P11):** Connect `action_palette.triggered` to `self.room.open_palette()` in `app.py`.

---

### Phase 1 — Shared Config (`config.py`)
Centralized configuration engine at `~/.config/hexmind/config.toml`.
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
* **Integration:** CLI flags always override saved configuration defaults.

---

### Phase 2 — Live Wire and Hand Brake
* **Task 2.1: Bridge Dropped `status` Events (P4):** Bridge orchestrator status events (`planning`, `evaluating`) through `_Room._emit` to Qt Signal `turnProgress(model, status_text)`.
* **Task 2.2: Live Turn Meter:** Render elapsed turn timer badge: `[● claude · planning · 0:42]`.
* **Task 2.3 & 2.4: Hand Brake (Process Group Kill):**
  - Launch model CLIs in dedicated process groups (`os.setsid`).
  - On cancellation, send `SIGTERM` followed by `SIGKILL` after 1.5s grace period.
  - Expose red Stop button next to Send to cancel the active turn.
* **Task 2.5: Server Cancellation Endpoint:** Expose `POST /api/turn/cancel` on `server.py`.

---

### Phase 3 — The Bench Rail
* Multi-workspace navigation shell in `hexmind/qt/app.py` hosting a 56px left dock with tabs:
  - **Room:** Primary chat and orchestration canvas (`HexmindWidget`).
  - **Direct Line:** 1:1 conversation view.
  - **Calibration Rack:** Model manager.
  - **Settings:** Preferences interface.

---

### Phase 4 — Settings Page
* Graphical interface for `~/.config/hexmind/config.toml` managing default roster, peer audit defaults, theme selection, and notification thresholds.

---

### Phase 5 — Agent Health & First Light (D3)
* **Component:** `hexmind/qt/health.py`
* Diagnostic scanner detecting CLI presence in `$PATH`, execution latency, declared credential readiness,
  and safe provider auth status where the installed CLI documents a read-only command.
* Auth checks are explicitly allowlisted (`claude auth status`, `codex login status`, and
  `opencode auth list`); unsupported providers are reported as **not checked** rather than invoking
  login, help, or model-inference commands.

---

### Phase 6 — Calibration Rack (D4)
* Visual inspector for `models.toml` displaying token limits, pricing tiers, and family classifications. Includes single-model test probe box.

---

### Phase 7 — Direct Line (D2)
* 1:1 conversation interface communicating directly with individual models, featuring an "Ask Another" side-by-side response comparator.

---

### Phase 8 — Polish & Preserved Hook Activation
* **Task 8.1 (P10):** Activate [`CommandPalette.set_commands`](file:///home/daripper/Projects/hexmind/hexmind/qt/palette.py#L63) on `teamChanged`.
* **Task 8.2 (P13):** Wire [`TaskGraphView.select_task`](file:///home/daripper/Projects/hexmind/hexmind/qt/graph.py#L314) and [`fit`](file:///home/daripper/Projects/hexmind/hexmind/qt/graph.py#L320) for interactive node selection and view centering.
* **Task 8.3 (P7, P15):** Pin selected task detail in collapsible drawer.
* **Task 8.4 (P8):** Add in-transcript Ctrl+F find bar with hit navigation.
* **Task 8.5 (P12):** Assert WCAG AA contrast compliance across all themes.

---

### Phase 9 — Flagship Backlog
* **Come-Back Pings:** Wire [`hexmind/notify.py`](file:///home/daripper/Projects/hexmind/hexmind/notify.py) to background completion events via `QSystemTrayIcon`.
* **Live Tap:** Line-by-line stream-json rendering in dedicated `LivePane`.
* **Audit Courtroom:** Multi-round disagreement history view.

---

## 📋 Part 4 — Standard Operating Procedures (SOP)

### SOP-1: Implementing a Roadmap Phase Task
1. Read the task specification in Part 3.
2. Write unit tests under `tests/test_qt_*.py`.
3. Implement code conforming to the Embed Invariant and theme tokens.
4. Verify execution headless:
   ```bash
   QT_QPA_PLATFORM=offscreen pytest tests/test_qt_*.py
   ```

---

## 📚 Part 5 — Glossary

| Term | Definition |
| :--- | :--- |
| **`D1–D4`** | The four core architectural decisions (Shared Config, Direct Line, Instrument Check, Calibration Rack). |
| **`Embed Invariant`** | Rule mandating that `HexmindWidget` remains fully standalone and usable outside `HexmindWindow`. |
| **`The Bench Rail`** | 56px left-docked navigation bar switching workspaces via `QStackedWidget`. |
| **`Live Wire`** | Active status streaming and elapsed turn timer badge. |
| **`Hand Brake`** | Process-group-level cancellation system for interrupting runaway agents. |

---

## 🔍 Part 6 — Reference Guide

### 6.1 Master Roadmap Phase & Task Ledger

| Phase | Milestone Name | Key Files | Primary Deliverable | Status |
| :---: | :--- | :--- | :--- | :---: |
| **0** | Honest Instruments | `qt/widget.py`, `qt/theme.py` | Fix P1, P2, P3, P11 baseline UI bugs | ✅ Complete |
| **1** | Shared Config | `config.py`, `__main__.py` | Centralized TOML settings engine | ✅ Complete |
| **2** | Live Wire & Hand Brake | `backends.py`, `qt/widget.py` | Turn meter & process group kill | ✅ Complete |
| **3** | Bench Rail | `qt/app.py`, `qt/rail.py` | Multi-view navigation shell | ✅ Complete |
| **4** | Settings Page | `qt/settings.py` | Visual configuration manager | ✅ Complete |
| **5** | Agent Health | `qt/health.py` | Binary, credential, latency, and allowlisted auth diagnostics | ✅ Complete |
| **6** | Calibration Rack | `qt/models.py` | Model inspector & test probe | ✅ Complete |
| **7** | Direct Line | `qt/chat.py` | 1:1 chat & Ask-Another arena | ✅ Complete |
| **8** | Polish & Finishing | `qt/palette.py`, `qt/graph.py` | Wire `set_commands`, `select_task`, `fit` | ✅ Complete |
| **9** | Flagship Backlog | `notify.py`, `qt/live.py`, `qt/timeline.py` | Come-back pings, Live Tap streaming, audit history | ✅ Complete |

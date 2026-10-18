# 🌌 Hexmind GUI Feature Forge — Master Handbook 🌌

---

> 🌌 **D3F Master Handbook**
>
> **Source Document:** [`docs/plans/2026-09-28-gui-feature-forge.md`](file:///home/daripper/Projects/hexmind/docs/plans/2026-09-28-gui-feature-forge.md)
>
> **Chain Stages:** 🧊 Architect ✓ · 🦄 SME ✓ · 👾 Auditor ✓ · 🌌 UX Writer ✓
>
> **Directive:** 🛡️ Zero Hallucination — every fact is traceable to the source document. Where the source is silent, the gap is marked explicitly.
>
> **Classification:** Ideation & Architecture Expansion Reservoir

---

## 📖 Part 1 — User Manual

### 1.1 Overview & The "One Brain" Invariant
This handbook documents the Feature Forge architectural proposals for expanding `hexmind-gui`. The GUI is structured as a `QMainWindow` ([`hexmind/qt/app.py`](file:///home/daripper/Projects/hexmind/hexmind/qt/app.py)) wrapping an embeddable [`HexmindWidget`](file:///home/daripper/Projects/hexmind/hexmind/qt/widget.py). It drives the core `Orchestrator` across four foundational signals: `message`, `taskChanged`, `teamChanged`, and `turnState`.

> 🧠 **Architectural Note:** The fundamental principle governing all feature forge expansions is: **The orchestrator already produces more truth than the GUI can see. The flagship move is to widen that pipe (new emit kinds, keeping handles on running tasks), never to duplicate orchestration logic in Qt.**

### 1.2 Non-Negotiable Engineering Constraints
1. **Host-Safe Styling:** The widget must never restyle its host window; stylesheets remain strictly isolated.
2. **Zero New External Dependencies:** Features utilize built-in Python standard library components and existing PySide6 capabilities (e.g. `QSystemTrayIcon`, `PySide6.QtWebSockets`).
3. **Untouched Terminal TUI:** Enhancements to shared core modules must preserve backwards compatibility with `hexmind/tui.py`.

---

## 🔧 Part 2 — Technical Manual

### 2.1 Subsystem Expansion Matrix
The forge organizes features across three complexity tiers:

```
┌────────────────────────────────────────────────────────────────────────┐
│                        WEEKEND-SCALE (HIGH LEVERAGE)                   │
│   • Hand Brake: Per-task cancellation & live reassignment              │
│   • Come-Back Pings: Tray presence & mobile buzz via notify.py        │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
┌───────────────────────────────────▼────────────────────────────────────┐
│                        SUBSYSTEM-SCALE (WORKBENCHES)                   │
│   • Live Tap: Real-time agent thought streaming (stream-json / chunks) │
│   • Relay Runs Desk: Multi-stage workspace diffs & chain adoption      │
│   • Draft Plan Workbench: Graph-based plan editing before execution    │
│   • Audit Courtroom: Multi-round debate thread & diff inspection       │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
┌───────────────────────────────────▼────────────────────────────────────┐
│                    SWING-FOR-THE-FENCE (PLATFORM)                      │
│   • Protocol Abstraction: Local, Remote (WS), and Session Replay       │
│   • Mission Control: Multi-repository tabs with fleet quota awareness │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 💻 Part 3 — Developer Guide

### 3.1 Weekend-Scale Features

#### 1. Hand Brake (Task-Level Cancellation & Reassignment)
* **Problem:** A 4-task turn has 1 stuck agent (e.g. codex looping). Today the user must wait up to 30 minutes (`DirectBackend(timeout=1800)`) or terminate the entire process.
* **Architecture:**
  - `core.py`: Retain active task futures in an orchestrator `running` dictionary. Add `cancel_task(task_id, reassign_to=None)`.
  - `backends.py`: Call `_terminate_group` on `asyncio.CancelledError`.
  - `widget.py`: Expose task row right-click context menu ("Stop task", "Reassign to claude"). Add a global red Stop button next to Send.
  - `server.py`: Expose parity endpoint `POST /api/cancel`.

#### 2. Come-Back Pings (Activating `notify.py`)
* **Problem:** Terminal users sit at the shell, but GUI users minimize the window during long turns.
* **Architecture:**
  - Wire existing [`hexmind/notify.py`](file:///home/daripper/Projects/hexmind/hexmind/notify.py) to background completion events: turn finished (`turnState(False)`), audit escalation (`auditor.py:277`), draft plan awaiting approval (`core.py:830`), or quota exhaustion.
  - `app.py` instantiates `QSystemTrayIcon`. If the window is inactive, invokes `notify.ping()` via `QThreadPool` to ring desktop notifications and send a KDE Connect mobile buzz.

---

### 3.2 Subsystem-Scale Workbenches

#### 3. Live Tap (Streaming Agent Output)
* **Problem:** `DirectBackend.run` buffers complete stdout (`_read_capped`), hiding partial replies.
* **Architecture:**
  - Introduce `on_event(agent, event)` in `DirectBackend`. Read line-by-line while maintaining JSON stream parsing.
  - Orchestrator emits `chunk` events (`emit("chunk", {"task": id, ...})`).
  - Introduce `LivePane` widget in Qt containing a 2000-block ring buffer to render streaming thought processes.

#### 4. Relay Runs Desk (Harvesting & Adopting Worktrees)
* **Problem:** `run_relay` generates worktree branches and markdown reports (`relay.py:998`), but lacks visual comparison and branch merging tools.
* **Architecture:**
  - Create `qt/runs.py` providing a chain stage browser and `QPlainTextEdit` diff view.
  - Expose `reaping.adopt(root, candidate)` to safely merge the chosen chain branch into `main` after verifying git cleanliness.

#### 5. Draft Plan Workbench (Visual Plan Modification)
* **Problem:** When `approve_plans` is enabled, the plan arrives as plain text requiring `/approve` or `/discard`.
* **Architecture:**
  - Display the pending plan inside `TaskGraphView` as an interactive draft.
  - Allow users to drag/reassign tasks to different models, toggle `gate:true`, or delete tasks before clicking Approve.
  - Wire through `Orchestrator.revise_pending(edits) -> list[str] findings`.

#### 6. Audit Courtroom (Full Disagreement Timeline)
* **Problem:** `audited_run` discards intermediate audit iterations, preserving only the final verdict.
* **Architecture:**
  - Emit each intermediate audit round: `emit("audit", {task, round, auditor, passed, issues, output})`.
  - Add `qt/courtroom.py` showing side-by-side diffs between primary output and auditor revisions using Python's `difflib`.

---

### 3.3 Swing-For-The-Fence Platform Shifts

#### 7. The Room as a Protocol (Local, Remote, Replay)
* Decouple `HexmindWidget` from local thread execution. Implement a unified `RoomSource` interface supporting:
  - **Local:** In-process `_Room` thread.
  - **Remote:** Connect to `hexmind --serve` over WebSocket (`QWebSocket` with token auth).
  - **Replay:** Load `.hexmind/sessions/*.jsonl` session journals with a scrubber slider.

#### 8. Mission Control (Multi-Room Fleet Awareness)
* Host multiple repository rooms in tabs (`qt/mission.py`).
* Introduce `hexmind/fleet.py` to track cross-room CLI occupancy and global quota limits in real time.

---

### 3.4 Deliberately Excluded Concepts
* **Jules Desk:** Interactive messaging (`jules.send_message`) is omitted; Jules CLI is designed for autonomous batch PR creation.
* **Embedded Terminal Emulator:** Embedding `hcom term` into Qt was rejected to avoid heavy terminal dependencies.
* **External Dark Themes:** 3rd-party themes (`qdarkstyle`) are rejected in favor of the native "Measured Sublime" design system.

---

## 📋 Part 4 — Standard Operating Procedures (SOP)

### SOP-1: Implementing a Forge Feature
1. **Core First:** Implement required data structures and public functions in `hexmind/core.py`, `relay.py`, or `backends.py`.
2. **Signal Exposure:** Add new emit types in `_Room._emit` ([`hexmind/qt/widget.py`](file:///home/daripper/Projects/hexmind/hexmind/qt/widget.py)).
3. **UI Implementation:** Create self-contained widgets in `hexmind/qt/` without modifying outer host stylesheets.
4. **Regression Verification:** Run tests headless:
   ```bash
   QT_QPA_PLATFORM=offscreen pytest tests/test_qt_*.py
   ```

---

## 📚 Part 5 — Glossary

| Term | Definition |
| :--- | :--- |
| **`Hand Brake`** | Architecture for cleanly interrupting in-flight tasks and killing child process groups. |
| **`Come-Back Ping`** | Desktop tray notification and mobile phone buzz triggered when long tasks complete. |
| **`Live Tap`** | Real-time streaming display of agent thought processes and tool calls. |
| **`Relay Desk`** | UI workspace for reviewing, comparing, and merging competing relay worktrees. |
| **`Audit Courtroom`** | Threaded visual history of auditor disagreements, issues, and intermediate diffs. |

---

## 🔍 Part 6 — Reference Guide

### 6.1 Feature Complexity & Dependency Blueprint

| Feature | Scale | Core Modules Touched | Qt Modules Added | New Deps |
| :--- | :---: | :--- | :--- | :---: |
| **Hand Brake** | Weekend | `core.py`, `backends.py` | `qt/widget.py` | None |
| **Come-Back Pings** | Weekend | `notify.py`, `core.py` | `qt/app.py` | None |
| **Live Tap** | Subsystem | `backends.py`, `core.py` | `qt/live.py` | None |
| **Relay Runs Desk** | Subsystem | `relay.py`, `reaping.py` | `qt/runs.py` | None |
| **Draft Plan Workbench** | Subsystem | `core.py`, `auditor.py` | `qt/graph.py` | None |
| **Audit Courtroom** | Subsystem | `auditor.py`, `core.py` | `qt/courtroom.py` | None |
| **Room as Protocol** | Platform | `server.py`, `journal.py` | `qt/remote.py`, `replay.py` | None |
| **Mission Control** | Platform | `fleet.py` | `qt/mission.py` | None |

# 🌌 Hexmind GUI UX & Visual System — Master Handbook 🌌

---

> 🌌 **D3F Master Handbook**
>
> **Source Document:** [`docs/plans/2026-09-28-gui-ux-ideas.md`](file:///home/daripper/Projects/hexmind/docs/plans/2026-09-28-gui-ux-ideas.md)
>
> **Chain Stages:** 🧊 Architect ✓ · 🦄 SME ✓ · 👾 Auditor ✓ · 🌌 UX Writer ✓
>
> **Directive:** 🛡️ Zero Hallucination — every fact is traceable to the source document. Where the source is silent, the gap is marked explicitly.
>
> **Design Philosophy:** "Measured Sublime" — Dark Lab Instrument Bench

---

## 📖 Part 1 — User Manual

### 1.1 The Soul of Hexmind GUI
The Hexmind GUI is built on the **"Measured Sublime"** design philosophy (`docs/design-philosophy.md`, encoded in [`hexmind/qt/theme.py`](file:///home/daripper/Projects/hexmind/hexmind/qt/theme.py)). It evokes an instrument bench in a darkened research laboratory:
* **Purposeful Color:** Six distinct hues, each mapped to a single semantic meaning.
* **Glow as State:** A glow indicates a live process; motion is reserved exclusively for active background computation.
* **Controlled Asymmetry:** Each view deliberately breaks the strict grid once to provide visual focus.
* **The Embed Invariant:** One brain, multiple front-ends. The GUI strictly presents orchestration truth; it never re-implements team rules or forces styles upon external hosts (such as Aether).

### 1.2 Layout Evolution: The Bench Metaphor
The application layout evolves from a single-room debug console into a multi-screen instrument workbench:
* **The Bench Rail:** A 56px navigation rail anchored to the left of the main window hosting workspace icons.
* **The Room Canvas:** A high-contrast terminal transcript paired with an interactive task dependency DAG ("Wiring Diagram").
* **The Bench Drawer:** A collapsible slide-out drawer housing task inspection details without obstructing conversation flow.

---

## 🔧 Part 2 — Technical Manual

### 2.1 The Semantic Color Architecture (`theme.py`)
All UI components strictly utilize semantic color tokens from the palette. Direct hex coding in widgets is forbidden.

| Token | Hex Value | Semantic Function |
| :--- | :---: | :--- |
| **`SUBSTRATE`** | `#12151c` | Deepest canvas background |
| **`BG_PANEL`** | `#181c26` | Card and panel backgrounds |
| **`INK_NORMAL`** | `#e6edf7` | High-contrast primary text |
| **`INK_MUTED`** | `#8b9cb3` | Secondary text, labels, and timestamps |
| **`ACCENT_TEAL`** | `#4ec9b0` | Healthy status, verified tasks, passing audits |
| **`ACCENT_AMBER`** | `#dcdcaa` | Warning states, in-flight turns, lead badges |
| **`ACCENT_CORAL`** | `#f44747` | Critical failures, rejected audits, stop controls |
| **`ACCENT_VIOLET`**| `#c586c0` | Structural controls, active rail items, command palette |

> ⚠️ **Watch Out:** Never use generic dark packages (e.g. `qdarkstyle`). Its rounded grey-on-grey aesthetic washes out semantic contrast. Use the stylesheet defined in `hexmind/qt/theme.py`.

### 2.2 Host-Safe Contrast Invariant (P12)
When embedded in light-themed host environments (such as Aether under Fusion light):
* Panels must derive foreground colors from `palette().text().color()` rather than static light constants.
* Automated tests must assert a contrast ratio of at least **4.5:1** (WCAG AA).

---

## 💻 Part 3 — Developer Guide

### 3.1 The Four Flagship Screens

#### 1. Model Manager: "The Calibration Rack"
* **Structure:** Master-detail split view.
  - **Left (List):** Filterable list of all models registered in `hexmind/models.toml`.
  - **Right (Inspector):** Form displaying context limits, token cost tiers, supported modalities, and family tags.
  - **Bottom (Test Strip):** Live single-model probe box to fire isolated prompt queries without initiating an orchestrator team turn.
* **Storage:** Persists edits to `~/.config/hexmind/models.toml`, never modifying the bundled repository copy.

#### 2. 1:1 Direct Chat: "Direct Line"
* **Structure:** Minimalist conversational interface connecting directly to an isolated CLI model.
* **Features:**
  - Bypasses orchestrator task planning for fast ad-hoc queries.
  - Includes **"Ask Another"** comparison: resends the active prompt to a secondary model and places outputs side-by-side.

#### 3. Agent CLI Health: "Instrument Check"
* **Structure:** Diagnostic status matrix scanning system binaries (`claude`, `agy`, `codex`, `opencode`, `kimi`, `jules`).
* **Indicators:**
  - Green / Yellow / Red availability badges based on binary existence and execution latency.
  - Environment badge (Termux / Native Linux detection).

#### 4. System Settings: "The Bench Settings"
* **Structure:** Multi-tab preferences window configuring defaults in `~/.config/hexmind/config.toml`.
* **Panels:** Default team roster, default lead model, peer audit toggle, theme selection, and KDE Connect notification preferences.

---

### 3.2 Real-Time Feedback: "Live Wire"
* **Turn Meter:** Displays elapsed execution time alongside the active model status: `[● claude · planning · 0:42]`.
* **Pulse Indicators:** Status glyphs on the active task in the graph view glow subtly during execution (`theme.is_live`).

### 3.3 Quick Navigation: "Palette 2.0"
* Activated via `Ctrl+K`. Displays all 23 slash commands, model switches, and navigation destinations.
* Dynamically refreshes via [`set_commands`](file:///home/daripper/Projects/hexmind/hexmind/qt/palette.py#L63) on `teamChanged` events.

---

## 📋 Part 4 — Standard Operating Procedures (SOP)

### SOP-1: Verifying Offscreen UI Rendering
Validate Qt UI changes without requiring an active X11/Wayland display server:
```bash
QT_QPA_PLATFORM=offscreen pytest tests/test_qt_*.py -v
```

### SOP-2: Automated Contrast Validation
Assert panel contrast compliance across both light and dark themes:
```python
def test_contrast_compliance(qapp):
    from hexmind.qt.theme import calculate_contrast_ratio, INK_NORMAL, SUBSTRATE
    ratio = calculate_contrast_ratio(INK_NORMAL, SUBSTRATE)
    assert ratio >= 4.5, f"Contrast ratio {ratio} fails WCAG AA requirement"
```

---

## 📚 Part 5 — Glossary

| Term | Definition |
| :--- | :--- |
| **`The Bench Rail`** | 56px primary navigation rail docked to the left window margin. |
| **`Calibration Rack`** | Visual configuration inspector and test harness for model CLI definitions. |
| **`Direct Line`** | Isolated 1:1 chat window communicating with a single agent process. |
| **`Instrument Check`** | System diagnostic screen probing installed CLI binaries and permissions. |
| **`Live Wire`** | Real-time visual feedback system streaming active turn progress and elapsed time. |

---

## 🔍 Part 6 — Reference Guide

### 6.1 The 17 Observed UX Defects (P1–P17)

| ID | Problem Description | Severity | Target Module |
| :---: | :--- | :---: | :--- |
| **P1** | Lead combo defaults to first member when lead is None | High | `hexmind/qt/widget.py:593` |
| **P2** | Peer audit checkbox starts unchecked when audit is enabled | High | `hexmind/qt/widget.py:330` |
| **P3** | Checkbox checkmarks invisible in dark theme | High | `hexmind/qt/theme.py` |
| **P4** | Orchestrator lead-status events dropped by Qt bridge | High | `hexmind/qt/widget.py:492` |
| **P5** | Input line locked during turns with no cancellation option | Med-High | `hexmind/qt/widget.py:491` |
| **P6** | Transcript lacks speaker identity badges and timestamps | Medium | `hexmind/qt/widget.py:502` |
| **P7** | Task detail panel overwritten by incoming chat messages | Medium | `hexmind/qt/widget.py:508` |
| **P8** | Search finds only first match without next/previous cycle | Low-Med | `hexmind/qt/widget.py:382` |
| **P9** | Model nicknames ignored in favor of raw CLI identifiers | Low-Med | `hexmind/qt/widget.py:595` |
| **P10** | Palette thin, stale, and misses slash command definitions | Medium | `hexmind/qt/palette.py` |
| **P11** | Command palette menu action disabled on startup | Low | `hexmind/qt/app.py:95` |
| **P12** | Light host embedding causes white-on-white text disappearance | High | `hexmind/qt/graph.py` |
| **P13** | Graph DAG encodes status by color alone with no arrowheads | Medium | `hexmind/qt/graph.py:172` |
| **P14** | PyQtGraph drops axis category labels at normal window sizes | Medium | `hexmind/qt/stats.py:254` |
| **P15** | Transcript, search, and detail panes share cramped space | Low-Med | `hexmind/qt/widget.py:432` |
| **P16** | Initial startup with no agents exits with critical error dialog | Medium | `hexmind/qt/app.py:202` |
| **P17** | GUI lacks CLI flag parity (timeout, approve-plans, backend) | Medium | `hexmind/qt/app.py:162` |

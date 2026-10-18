# UI/UX Audit — Textual TUI and Qt Frontend

- **Date:** 2026-09-29
- **Task:** t3 (read-only UI/UX audit, no code changes)
- **Scope:** `hexmind/tui.py` (840 lines) and the whole `hexmind/qt/` package
  (16 source files + 11 test files).
- **Method:** source read end to end, every claim re-verified against the live
  tree (grep + executed repro where possible), baseline test run captured before
  any judgement. Nothing in this document is taken from a prior report on trust.
- **Deliverable:** findings + a proposed atomic upgrade list (`UI-1`…`UI-14`).
  No source file was modified by this task.

## 0. Baseline

```
cd /home/daripper/Projects/hexmind && python3 -m pytest tests -q
1 failed, 723 passed, 3 skipped in 207.34s   (full log: /tmp/opencode/hexmind-baseline.txt)
```

The single failure is `tests/test_qt_chat.py::test_direct_line_asks_primary_and_another`
(`assert '' == 'big-pickle: answer'`). It predates this task and is **not owned by
the UI audit** — see §6.

## 1. How the audit was scored

Each AGENTS.md UI/UX rule was checked against both front-ends:

| # | Rule | TUI | Qt |
|---|------|-----|----|
| 1 | Existing notification system, no `alert`/`confirm` | ✅ `self.notify` | ⚠️ no toast; `QMessageBox` only in `app.py`/`settings.py` |
| 2 | Live state reflects immediately | ✅ | ✅ |
| 3 | Settings persist from day one | ✅ (view/layout in CSS classes) | ✅ `QSettings` `qt/split`, `qt/right` |
| 4 | Keyboard operable + accessible labels | ⚠️ operable, but **footer hides every key hint** | ⚠️ labels excellent, **no visible focus ring** |
| 5 | Every list/table has an empty state | ❌ task board | ❌ task table |
| 6 | Long async shows a loading indicator | ⚠️ no turn-in-progress spinner | ✅ input disabled + Stop + turn meter |
| 7 | Narrow screens stack vertically | ✅ tested at 3 breakpoints | ❌ fixed horizontal splitter, no `resizeEvent` |
| 8 | Collapsible state remembered | n/a | ✅ splitter/drawer persisted |
| 9 | Destructive action needs confirmation | ❌ `action_clear` | ❌ `_clear_transcript` (settings discard ✅) |

## 2. Findings — Textual TUI (`hexmind/tui.py`)

### 2.1 Navigation
- Five modal screens (`HelpScreen` L49, `TaskScreen` L66, `ModelCardScreen` L129,
  `TeamScreen` L152, `LeadPicker` L340), all `align: center middle`, all reachable
  from dedicated actions. Escape/back handling is tested
  (`tests/test_tui.py:220`, `:547`).
- Chat/Tasks is a tab pair (`set_view` L662) with a click **and** `v` path; the
  focused widget follows the view (L668) — good.
- **F-1 (medium): every binding is hidden.** All 11 `Binding(...)` declarations
  are `show=False` (L173–175, L366–367, L508–513). Textual's `Footer()` (L554)
  only renders bindings with `show=True`, so the footer bar is permanently blank
  while `q`/`c`/`v`/`t`/`?` all work. The `?` → `HelpScreen` path exists but is
  undiscoverable. This is the single largest discoverability gap in the TUI.

### 2.2 Empty states
- ✅ Team roster: `#team-empty` → "No models registered — check
  hexmind/models.toml." (L209–210), tested at `test_tui.py:207`.
- ✅ Lead picker: "No model can lead…" (L575), tested at `test_tui.py:547`.
- ✅ Task detail: "(no output yet)" (L836).
- ❌ **F-2 (medium): task board has no empty state.** `build_table()` (L650–660)
  clears the `DataTable`, re-adds columns, and adds zero rows when
  `self.tasks` is empty — the user sees a bare column header. Violates rule 5.

### 2.3 Loading / long operations
- ⚠️ **F-3 (low): no turn-in-progress indicator.** While a turn runs the chat
  says only "Team is busy — queued…" for *subsequent* input (L729); the roster
  line does show `busy`/`idle` counts (L809), but nothing marks the current turn
  as in flight (no spinner, no elapsed time, no Stop affordance). Cross-refs
  backlog item **26** (already filed — do not re-file).

### 2.4 Keyboard & accessibility
- ✅ Every roster control carries an accessible label + tooltip
  (`test_tui.py:373`), and the `show=False` bindings are still *operable*.
- ⚠️ `q` = quit with no confirmation (L509) — acceptable for a TUI, noted only
  because the Qt side does confirm on `app.py` close events.
- ❌ **F-4 (medium): `action_clear` (L838–840) clears the whole transcript with
  no confirmation.** It is bound to `c` and is destructive. Rule 9.

### 2.5 Theme tokens
- ✅ No raw hex in `tui.py`; colours come from module constants and Rich styles.

### 2.6 Responsive
- ✅ Strongest part of the TUI. Breakpoints `NARROW=80 / SHORT=18 / TINY=10`
  drive a tabbed narrow view, chat reflow with history replay, and table column
  recompute (`columns()` feeding `build_table`). `.tiny` hides Header/Footer
  (L488). All of it is covered by `tests/test_mobile_tui.py` (12 tests: layout
  matrix, tap targets, wrap, single-key bindings, resize reflow, view
  persistence). No action required.

## 3. Findings — Qt frontend (`hexmind/qt/`)

### 3.1 Navigation
- Left `rail.py` → workspaces, right tab widget (`widget.py` L521–535), Ctrl+K
  `palette.py`. Rail buttons and palette entries have accessible names and
  placeholder states (`test_qt_rail.py:59`, `:86`; `test_qt_palette.py:69`,
  `:174`). Search next/prev (P8) and turn cancellation (P5) from the 2026-09-28
  P-list are **already fixed** in this tree — do not re-propose.

### 3.2 Empty states
- ✅ Stats panel: "empty ledger shows the empty message and no rows"
  (`test_qt_stats.py:313`).
- ✅ Palette empty query (`test_qt_palette.py:174`), calibration rack
  (`test_qt_models.py:67`).
- ❌ **F-5 (medium): the Tasks table has no empty state.** `widget.py:446`
  `_table(TASK_COLUMNS, "Tasks")` starts at zero rows and rows are only
  inserted as tasks arrive (L747–756). Before any run, the tab is a bare grid.

### 3.3 Loading
- ✅ Best-in-class: input disabled during a turn, a Stop button with its own
  styled state (`theme.py` L148–156), and a turn meter (L411) — all covered by
  tests. No action required.

### 3.4 Keyboard & accessibility
- ✅ `setAccessibleName` is applied across every panel (40+ call sites:
  `widget.py`, `chat.py`, `models.py`, `graph.py`, `live.py`, `palette.py`,
  `rail.py`, `model_selector.py`) and is asserted by
  `test_qt.py:277 test_accessible_names_are_set_so_a_screen_reader_has_something`.
- ✅ WCAG AA contrast is asserted by a test.
- ❌ **F-6 (high): there is no visible focus indicator for anything except text
  inputs.** `theme.py` has exactly one `:focus` rule (L127: `QLineEdit`,
  `QPlainTextEdit`, `QTextEdit`, `QSpinBox`). `QPushButton`, `QTabBar::tab`,
  `QListWidget`, `QTreeWidget` and `QTableWidget` have `:hover`/`:checked`
  states but **no `:focus` rule at all** — a keyboard-only user tabbing through
  the workbench cannot see where focus is. This is the most consequential
  accessibility defect found in either front-end. There is no focus-ring test
  file (`test_qt_accessibility.py` does not exist).

### 3.5 Theme tokens
- ❌ **F-7 (medium): `graph.py` hardcodes hex colours** — L155
  (`#5fd68a #f2686b #39d0d8 #6b7a94`), L163 (`#e8b04b #5a6577`), L169
  (`#e6edf7`). This violates the shared "theme tokens only — no hardcoded hex
  colours in views" convention and will not follow a future palette change.

### 3.6 Notifications / confirmations
- ⚠️ **F-8 (medium): the widget has no toast mechanism.** `QMessageBox` exists
  only in the standalone host `app.py` and the `settings.py` discard dialog
  (L285–292, ✅ correct use of the established confirmation mechanism). Panels
  fall back to per-panel `QLabel` status strings (`agentdeck_panel.py:199/323`,
  `chat.py:110`, `health.py:41`). When embedded in Aether there is no
  `statusBar()` to fall back on, so "Copied task output"-class events would be
  silent. Rule 1 asks for a project notification system — there isn't one yet.
- ❌ **F-9 (medium): `_clear_transcript` (L882–886), bound to Ctrl+L (L571),
  clears the transcript with no confirmation.** Rule 9.

### 3.7 Responsive
- ❌ **F-10 (high for embedding): no vertical stacking at narrow widths.**
  The main layout is a fixed horizontal `QSplitter` (`widget.py:538`) and
  neither `widget.py` nor any panel implements `resizeEvent`. Worse,
  `agentdeck_panel.py:31` imposes `setMinimumWidth(600)`, which sets a hard
  floor: embedding `HexmindWidget` in a pane narrower than ~600 px will force
  horizontal clipping instead of reflowing. The TUI solves the same problem at
  NARROW=80 with a tabbed view; the Qt side has no equivalent. Rule 7.

### 3.8 Embedding rule
- ✅ One-way embedding respected: no `aether` import anywhere in `hexmind/`.

## 4. Confirmed defects (reproduced by execution this session)

### D-1 — `hexmind/qt/agentdeck_panel.py` cannot even be imported
```
$ python3 -c "import hexmind.qt.agentdeck_panel"
  File ".../hexmind/qt/agentdeck_panel.py", line 24, in AgentdeckPanel
    itemActivated = pyqtSignal(object)  # Item
NameError: name 'pyqtSignal' is not defined
```
Three distinct faults in one file:
1. `pyqtSignal` is never imported from `QtCore` (line 24).
2. `QApplication` is used (~L270) but never imported.
3. A class-body `from hexmind.qt.theme import (...)` (L42–45) with the comment
   "injected by host at runtime" — a module-level import inside a class body
   does not bind into the class namespace.

**Reachability:** `widget.py:531–535` calls `_load_agentdeck_items()` and, when
`agentdeck` *is* importable, does `from .agentdeck_panel import AgentdeckPanel`
**unguarded**. On a machine with `agentdeck` installed, `HexmindWidget.__init__`
crashes. On this machine `import agentdeck` fails, so the guard at
`widget.py:95–102` masks the bug — it is dormant here, not absent. No test
references `AgentdeckPanel`. Backlog item **43** (read-only agentdeck tab
parity) is written as if the tab works; it does not.

### D-2 — Hardcoded hex in `graph.py` (F-7)
Confirmed at L155, L163, L169 by grep (3 matches, all in status/dependency
colour helpers).

### D-3 — No focus rule for buttons/lists/tabs (F-6)
Confirmed by grep: `theme.py` has exactly one `:focus` selector (L127, inputs
only); `QPushButton`'s state rules are `:hover`/`:pressed`/`:checked`/`:disabled`
only.

## 5. Proposed atomic upgrades

Ordered by (defect severity × how little they disturb existing architecture).
Each is deliberately small enough to be one PR with its own test. Cross-ref
column prevents duplicate filing against the existing backlogs.

| ID | Proposal | Files | Test to add | Cross-ref |
|----|----------|-------|-------------|-----------|
| **UI-1** | Fix `agentdeck_panel.py`: import `pyqtSignal`/`QApplication` from `QtCore`/`QtWidgets`; move the `theme` import to module level. Then **guard** the tab creation at `widget.py:533` (`try/except` + `console`-free fallback to no-tab) so a broken panel can never take `HexmindWidget` down. | `qt/agentdeck_panel.py`, `qt/widget.py` | `test_qt_agentdeck.py::test_widget_survives_a_broken_agentdeck_panel` (monkeypatch the import to raise, assert `HexmindWidget` still builds) | **new** — backlog 43 assumes it works |
| **UI-2** | Add focus-ring rules to the shared stylesheet: `QPushButton:focus`, `QTabBar::tab:focus`, `QListWidget::item:focus`, `QTreeWidget::item:focus`, `QTableWidget::item:focus` using the existing VIOLET accent, plus `QAbstractItemView { outline: none }` to kill the platform default. | `qt/theme.py` | new `tests/test_qt_accessibility.py`: assert the stylesheet string contains a `:focus` selector for each of those five classes | rule 4; no existing backlog item |
| **UI-3** | Replace the three hardcoded hex sites in `graph.py` with tokens from `qt/theme.py` (add status tokens alongside the existing palette constants). | `qt/graph.py`, `qt/theme.py` | extend the existing contrast test to cover graph status colours | **dup risk:** convention stated in AGENTS.md; no filed item |
| **UI-4** | Empty state for the task board in **both** front-ends: a single placeholder row ("No tasks yet — send a goal to start a run") in Qt's `tasks` table and a `#tasks-empty` `Static` in the TUI's `build_table()` when `self.tasks` is empty. | `qt/widget.py`, `tui.py` | `test_qt.py::test_an_empty_task_table_says_so` + `test_tui.py::test_an_empty_task_board_says_so` | batch roadmap line 227 ("contextual CTA-based empty states") — **same phase, coordinate** |
| **UI-5** | Confirm before clearing: reuse `QMessageBox.question` (as `settings.py:285` already does) in `widget.py:882`, and `self.push_screen` + a modal confirm in `tui.py:838` (`action_clear`). | `qt/widget.py`, `tui.py` | `test_qt.py::test_clear_transcript_asks_first` (patch `QMessageBox.question`), `test_tui.py::test_clear_asks_first` | rule 9; **new** |
| **UI-6** | TUI footer hints: flip the six primary bindings (help/team/tasks/quit/clear/input) to `show=True` so `Footer()` is not blank; keep the `j`/`k` cursor bindings hidden. | `tui.py` | `test_tui.py::test_the_footer_shows_the_primary_key_hints` (assert footer text contains `?`) | rule 4; **new** |
| **UI-7** | Turn-in-progress indicator in the TUI: reuse the existing busy line (L809) with an animated `Spinner` + elapsed seconds + a visible Stop binding while `orch` is mid-turn. | `tui.py` | `test_tui.py::test_a_running_turn_shows_progress` | **dup: backlog item 26 — do not file separately, attach UI-7 to it** |
| **UI-8** | Qt toast host: a lightweight non-modal `ToastHost` (`QFrame` + `QTimer`, token-styled) owned by `HexmindWidget`, exposed as a `notificationRequested(str, str)` signal so an embedding host (Aether) can forward it to its own toast system. Panels emit instead of writing per-panel status labels. | new `qt/toast.py`, `qt/widget.py` | `test_qt_toast.py` (signal fires, auto-dismisses, token colours) | rule 1; **new** |
| **UI-9** | Narrow-width stacking: `HexmindWidget.resizeEvent` switches the horizontal `QSplitter` to a vertical orientation below 720 px (mirroring the TUI's NARROW breakpoint scaled to px), and **drop** `setMinimumWidth(600)` in `agentdeck_panel.py` in favour of a scroll area. | `qt/widget.py`, `qt/agentdeck_panel.py` | `test_qt.py::test_the_splitter_stacks_vertically_when_narrow` | rule 7; **new** — depends on UI-1 landing first (same file) |
| **UI-10** | Persist the task-detail drawer open/closed and the table density setting alongside the existing `qt/split` / `qt/right` keys. | `qt/widget.py` | extend `tests/test_qt_settings.py` (2 new tests) | settings backlog item **42** — attach, don't re-file |
| **UI-11** | First-run empty state: when the roster is empty, show a CTA panel ("No models registered — edit models.toml →") with a button that opens the config folder, replacing the bare table. | `qt/widget.py` | `test_qt.py::test_first_run_offers_the_config_cta` | batch roadmap phase for empty states; **coordinate with UI-4** |
| **UI-12** | Port the TUI's accessible-label test pattern to Qt: one test asserting *every* focusable child of `HexmindWidget` has a non-empty `accessibleName()` or visible text. Catches future panels that forget labels. | new `tests/test_qt_accessibility.py` | (is the test) | complements existing `test_qt.py:277` |
| **UI-13** | Flag — do **not** edit — the stale line "`hexmind/…` No Qt front-end yet" in `~/Projects/AGENTS.md`. That file is a protected agent-instruction file; the owner must fix it via `init-agent-rules.sh`. Raised here because it actively misdirects future agents (this task's own premise was based on it). | (none) | n/a | **dup: backlog item 50** (doc drift) — reference, don't re-file |
| **UI-14** | Add a `?`-equivalent discoverability cue in Qt: bind `F1`/`?` on `HexmindWidget` to the same command palette that Ctrl+K opens, so the two front-ends teach the same gesture. | `qt/widget.py` | `test_qt_palette.py::test_question_mark_opens_the_palette` | **new** |

### Suggested sequencing
1. **UI-1** (it is a crash, not a preference) → then UI-9 on the same file.
2. **UI-2** + **UI-12** together (focus ring + the test that keeps it).
3. **UI-4**, **UI-5**, **UI-6** — small, independent, immediately visible.
4. **UI-3**, **UI-8**, **UI-10**, **UI-11**, **UI-14** as capacity allows.
5. **UI-7** only via backlog item 26; **UI-13** only via backlog item 50.

## 6. Explicitly not owned by this task

- `tests/test_qt_chat.py::test_direct_line_asks_primary_and_another` — the sole
  baseline failure. It is a direct-line output assertion, unrelated to any
  finding above; recorded so the next agent does not attribute it to t3.
- Roster generation, INVARIANT S-1 (no sleeping busy model), and the model
  registry were not audited — out of scope for a UI/UX pass.

## 7. Conventions any implementer must respect

- **One-way embedding:** Aether imports `hexmind.qt.HexmindWidget`; hexmind
  never imports Aether. UI-8's signal exists precisely so the host can own the
  toast instead of hexmind reaching out.
- **Theme tokens only** — UI-3 is the fix for the existing violation; new code
  must not add hex to views.
- The QApplication owner (`qt/app.py`) applies the stylesheet; embedded hosts
  may not, so UI-2's focus rules must be defined in the shared stylesheet string
  *and* be safe when absent.
- **Established confirmation mechanism:** modal screen (TUI) /
  `QMessageBox.question` (Qt). UI-5 uses both as-is.
- Breakpoints: TUI `NARROW=80 / SHORT=18 / TINY=10` (columns, not pixels);
  UI-9 introduces the Qt pixel equivalent and should document it in
  `hexmind-dev`'s skill notes when implemented.
- Test command: `python3 -m pytest tests -q`.

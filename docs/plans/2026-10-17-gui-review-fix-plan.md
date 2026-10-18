# hexmind GUI: review fix plan (design + a11y + code reviews + critic, clean pass)

> **Implement task-by-task, in phase order, one commit per task.** Task 1.1 (C-1) is the blocker: "Select Team… → OK" in the room self-deadlocks the GUI thread. The probe `team_deadlock` hangs until killed (exit 124), and the only test for that path (`tests/test_qt.py:218`) passes because it swaps the lock for a re-entrant `MagicMock`. Fix that test in the same commit, before anything else touches `widget.py`.

**Context:** This plan covers the PySide6 suite under `hexmind/qt/` (`hexmind-gui`) and merges three independent reviews:
- `.audit/gui/design.md` (D-1..D-25)
- `.audit/gui/a11y.md` (A-1..A-15)
- `.audit/gui/code.md` (C-1..C-17)

The critic pass in `.audit/gui/critic.md` verified 50 findings, corrected 6 and dropped 1. Two corrections matter for implementation:
- D-15's proposed border token `#3a4660` is **2.06:1** and still fails, so use `#636e88`.
- A-9's SLATE `#6e7c96` fails on PANEL, so use `#7686a0`.

Probes live in `.audit/gui/` and run like this:
`H=$(mktemp -d); HOME=$H PYTHONPATH=. QT_QPA_PLATFORM=offscreen timeout 20 /usr/bin/python3 .audit/gui/probe_code.py <probe>`.

Suite baseline: **725 passed / 2 failed / 727 collected**. The 2 failures are the ling-flash tests in `tests/test_team.py`. They are environmental, so do not chase them.

**Rules that apply to every task (from AGENTS.md):**
- `HexmindWidget` must never call `QApplication.setStyleSheet` or touch the app palette. All QSS goes in `theme.stylesheet()`.
- Do not delete the preserved hooks: `palette.set_commands` and `Command.haystack`; `graph.select_task`, `fit`, `clear` and `update_task`; `notify.py`.
- Run the **full** suite after every task.
- Land no new ruff findings.

Size: **S** ≤ 30 lines incl. test · **M** ≤ 150 · **L** larger.

---

## Phase 1 — crashes, hangs, data loss

### Task 1.1 — Stop `_on_team_saved` deadlocking on `_orch_lock`, and replace the masking test

**Findings:** C-1 · **Size:** S · **Depends on:** none (do first)

**Problem:** `hexmind/qt/widget.py:825-827` holds the non-reentrant `threading.Lock` while it calls `orch.emit("team", …)`.
- `_Room` is a QObject with GUI-thread affinity, so `teamChanged` is delivered directly.
- The chain is `_emit` (`:176`) → `refresh_team` (`:336`) → `snapshot` (`:382`) → `_Room.snapshot` (`:278`).
- That last call takes `with self._orch_lock` again, so the GUI thread deadlocks on itself.
- `tests/test_qt.py:218-233` replaces the lock with a `MagicMock`, which is re-entrant, so the test passes.

**Change:**
1. In `_on_team_saved`, shrink the critical section to the mutation only:
   ```python
   with self._room._orch_lock:
       self._room.orch.members = team
   self._room.orch.emit("team", {"action": "set", "models": team})
   ```
   Keep the trailing `self.refresh_team()`. It is now redundant but harmless, so remove it if the emit already redraws.
2. Delete `test_team_save_serializes_with_orch_lock`.

**Test:** add `test_team_save_does_not_deadlock` in `tests/test_qt.py`:
- Use the real lock and arm `faulthandler.dump_traceback_later(10, exit=True)`.
- Call `widget._on_team_saved({"claude": True, "agy": True}, ["claude", "agy"])`, then cancel the watchdog.
- Assert `not widget._room._orch_lock.locked()`.
- Assert the Team table lists both models.

Before the fix this test hangs and the watchdog kills it.

**Verification:** `pytest tests/test_qt.py -q`; probe `team_deadlock` exits 0.

---

### Task 1.2 — Lock lead, team and audit controls during a turn, and make a refused lead change visible

**Findings:** C-4, C-17 (unlocked `orch.audit` write) · **Size:** S · **Depends on:** 1.1

**Problem:** `_on_turn_state` (`widget.py:612-635`) disables only `input` and `sendButton`. That leaves three controls live mid-turn:
- **Lead box.** Picking a lead sets `self.lead` and the combo text, but `change_lead` (`:208-215`) silently returns while `_turn_in_flight`. The UI then says `codex` while `orch.lead` is still `claude`. This is fake success.
- **Team save.** It can drop a busy model from `members` mid-turn, which bypasses INVARIANT S-1.
- **Peer audit checkbox.** `_on_audit_toggle` (`:384-387`) writes `orch.audit` without the lock.

**Change:**
1. In `_on_turn_state`, add `self.leadBox.setEnabled(not busy)`, `self.teamButton.setEnabled(not busy)` and `self.auditBox.setEnabled(not busy)`.
2. In `_Room.change_lead`, when it refuses, emit `self.message.emit("hexmind", "Lead change ignored: a turn is running.")` and `self.teamChanged.emit()`. The second emit makes the combo snap back. This covers the palette `lead:` path, which bypasses the disabled combo.
3. Wrap the `orch.audit` write in `with self._room._orch_lock:`.

**Test:** in `tests/test_qt.py`:
- Call `widget._on_turn_state(True)` and assert all three controls are disabled.
- Set `widget._room._turn_in_flight = True`, call `widget._room.change_lead("agy")`, then `pump()`.
- Assert the transcript contains "Lead change ignored" and `widget.leadBox.currentText() == widget._room.orch.lead`.

**Verification:** probe `lead_during_turn` prints `leadBox enabled: False`.

---

### Task 1.3 — Make `_Room.submit` honest: no echo when the line is dropped, and no wedge after close

**Findings:** C-5, C-15 · **Size:** S · **Depends on:** none

**Problem:**
- `_submit` (`widget.py:583-596`) echoes `you: …` before `submit()` (`:198-206`) silently drops a line while a turn is in flight.
- `_pending` (`:151, 201-203, 211-213`) is appended to but never drained, and the `run()` comment (`:192`) says it is drained.
- After `close()`, `submit()` sets `_turn_in_flight = True`. Then `run_coroutine_threadsafe` raises `RuntimeError: Event loop is closed`, which leaves the flag stuck.

**Change:**
1. `submit(text) -> bool`:
   - Return `False` if `self._loop is None or self._loop.is_closed()` or a turn is in flight.
   - Otherwise schedule the line, set `_turn_in_flight = True` only after the schedule succeeds, and return `True`.
2. Give `change_lead` the same early return.
3. Delete `_pending` and the stale drain comment. `wait_until_ready` runs in `__init__`, so the loop exists before any caller.
4. In `_submit`, echo only on `True`. Otherwise call `_on_message("hexmind", "Busy: try again when the turn ends.")`.

**Test:**
- Set `_turn_in_flight = True`, call `widget._submit("/team")`, and assert the transcript has no `you: /team` and does have `Busy`.
- `widget.close()`, then `widget._room.submit("x") is False`, and `_turn_in_flight is False`.

**Verification:** probes `submit_during_turn` and `submit_after_close` show no echo and no raise.

---

### Task 1.4 — Cancel in-flight tasks when the room stops, so agent CLIs are not orphaned

**Findings:** C-3 · **Size:** M · **Depends on:** 1.3

**Problem:**
- `_Room.stop` (`widget.py:252-272`) only calls `loop.stop()`, and then `run()` (`:187-193`) closes the loop.
- The `orch.handle` task is never cancelled.
- `DirectBackend` kills its `start_new_session=True` process group **only** in `except asyncio.CancelledError` (`backends.py:230`), so the child CLIs outlive the GUI.
- Probe `orphan` showed the child pid still alive after `widget.close()`, plus `Task was destroyed but it is pending!`.

**Change:**
1. In `stop()`, when the loop is running, schedule this coroutine instead of a bare `loop.stop`:
   ```python
   async def _shutdown():
       tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
       for t in tasks: t.cancel()
       await asyncio.gather(*tasks, return_exceptions=True)
       asyncio.get_running_loop().stop()
   asyncio.run_coroutine_threadsafe(_shutdown(), loop)
   ```
2. In `run()`, call `self._loop.run_until_complete(self._loop.shutdown_asyncgens())` before `close()`.
3. Raise `wait(3000)` to at least `_terminate_group`'s grace period plus 1 s. Read the constant from `backends.py`.
4. `_handle`'s `finally` emits signals. Guard those emits with `try/except RuntimeError` for the "Signal source has been deleted" case seen in the probe.

**Test:** in `tests/test_qt.py`:
- Build a backend whose `run` does `try: await asyncio.sleep(30) except asyncio.CancelledError: cancelled.set(); raise`.
- Submit a line, wait until the turn is in flight, then `widget.close()`.
- Assert `cancelled.is_set()`.

Before the fix the flag is never set.

**Verification:** probe `orphan` reports no surviving child; there is no "Task was destroyed" warning.

---

### Task 1.5 — Stop Direct Line and Calibration Rack threads from aborting the process on close

**Findings:** C-2 · **Size:** M · **Depends on:** none

**Problem:**
- `ChatThread(..., self)` (`chat.py:147`) and `ProbeThread(..., self)` (`models.py:140`) are children of their pages.
- `HexmindWindow.closeEvent` (`app.py:311-322`) only closes the room.
- When the window is destroyed while either thread is running, that is a `qFatal`. Probe `chat_close` exits 134.
- `_default_chat` blocks for up to 1800 s inside `asyncio.run`, so the window is wide and a plain `wait()` would hang the quit.

**Change:**
1. In both thread classes, run the runner on a loop the thread owns, so a cancellation can kill the CLI's process group through `DirectBackend`'s `CancelledError` path:
   - If `inspect.iscoroutinefunction(self._runner)`, call `self._loop = asyncio.new_event_loop()` and `self._task = self._loop.create_task(self._runner(...))`, then `run_until_complete`.
   - Otherwise call the runner synchronously, as today.
   - Make `_default_chat` and `_default_probe` `async def` (drop the `asyncio.run`).
2. Add `shutdown(timeout_ms=5000)` to each thread: `loop.call_soon_threadsafe(task.cancel)` if a task exists, then `self.wait(timeout_ms)`.
3. Add `DirectLine.shutdown()` and `CalibrationRack.shutdown()`, which delegate to the live thread if there is one.
4. Call both from `HexmindWindow.closeEvent` before `self.room.close()`.

**Test:** in `tests/test_qt_chat.py`:
- Inject an `async def runner(model, prompt): await asyncio.sleep(30)`, call `ask`, then `page.shutdown()`.
- Assert `not page._chat_thread.isRunning()` within 6 s.

Add the same test to `tests/test_qt_models.py` for the probe.

**Verification:** probe `chat_close` exits 0.

---

### Task 1.6 — Isolate QSettings in the test suite so tests stop writing the real `~/.config/hexmind/room.conf`

**Findings:** C-9 · **Size:** S · **Depends on:** none (do before 3.4, whose layout assertions need a clean split state)

**Problem:**
- `widget.py:556` saves the splitter state and tab index through `QSettings("hexmind", "room")`. That follows the real `$HOME`, and `tests/conftest.py:31-58` redirects only `config.PATH`.
- `pytest tests/test_qt.py` touched the real `room.conf`. That is how `00-main.png` inherited a 239|604 split from a test.
- The `except Exception:` blocks at `:566` and `:902` swallow failures silently.

**Change:**
1. In `_hermetic_home`, add:
   ```python
   try:
       from PySide6.QtCore import QSettings
       for fmt in (QSettings.Format.NativeFormat, QSettings.Format.IniFormat):
           QSettings.setPath(fmt, QSettings.Scope.UserScope, str(home / ".config"))
   except ImportError:
       pass
   ```
2. Replace the two silent excepts with `logger.exception("room layout restore/save failed")`. `logger` already exists at `widget.py:56`.

**Test:** `test_qsettings_is_hermetic` in `tests/test_qt.py` asserts `QSettings("hexmind", "room").fileName()` starts with the `_hermetic_home` path.

**Verification:** `stat ~/.config/hexmind/room.conf` is unchanged across a full suite run.

---

### Task 1.7 — "Restore defaults" must not write to disk; honour `SettingsPage(config_path=…)`

**Findings:** C-7 · **Size:** S · **Depends on:** none

**Problem:**
- `settings.py:300-321`: the docstring says "without writing to disk", but `save_enabled_to_config(...)` at `:306` rewrites `[models]` straight away.
- `save_enabled_to_config` and `load_enabled_from_config` always use `config.PATH`. They ignore `self._config_path` (`settings.py:46, 306, 342, 418, 465`; `model_selector.py:388-403`).

**Change:**
1. Delete line 306. Persist `_enabled_models` only in `save()`.
2. Pass `self._config_path` through to `get_enabled_models` and `save_enabled_models`. Both already accept `path`.

**Test:** in `tests/test_qt_settings.py`:
- Build a page with `config_path=tmp/"c.toml"`, call `reset_to_defaults()`, and assert neither `tmp/"c.toml"` nor `config.PATH` changed (compare mtime or contents).
- After `save()`, assert `[models]` is in `tmp/"c.toml"`.

**Verification:** probe `settings_reset_writes` prints `disk changed …: False`.

---

### Task 1.8 — Enabling or disabling models marks Settings dirty, and Revert restores it

**Findings:** C-8 · **Size:** S · **Depends on:** 1.7 (same file, adjacent code)

**Problem:** `_capture_state` (`settings.py:233-245`) has no `enabled` key. Toggling a model that is not in the team therefore leaves `is_dirty == False`, and Save stays disabled. `revert` also leaves `_enabled_models` changed.

**Change:**
1. Add `"enabled": tuple(sorted(k for k, v in self._enabled_models.items() if not v))` to `_capture_state`.
2. Have `_apply_state` and `revert` rebuild `_enabled_models` from it.

**Test:** disable a non-team model, then assert `page.is_dirty` and that Save is enabled. Call `revert()` and assert the model is enabled again.

**Verification:** probe `settings_enabled_only_dirty` prints `dirty=True`.

---

### Task 1.9 — Prompt before quitting with unsaved settings

**Findings:** C-16 · **Size:** S · **Depends on:** 1.5 (same `closeEvent`)

**Problem:** `HexmindWindow.closeEvent` (`app.py:311-322`) accepts the close while the Settings page is dirty. `settings_page._confirm_discard` already exists and is not used here.

**Change:** at the top of `closeEvent`:
```python
if self.settings_page.is_dirty and not self.settings_page._confirm_discard("quit"):
    event.ignore()
    return
```

**Test:** in `tests/test_qt_app.py`, make Settings dirty and monkeypatch `_confirm_discard` to return `False`. Then `window.close()` returns `False` and the window is still visible. With `True`, the window closes.

**Verification:** probe `settings_close_dirty` shows the close was ignored.

---

### Task 1.10 — Make `agentdeck_panel.py` importable, and keep a broken panel from killing the room

**Findings:** C-6 · **Size:** S · **Depends on:** none

**Problem:**
- `agentdeck_panel.py` raises `NameError` on import because of these undefined names:
  - `pyqtSignal` at `:24` and `:27`
  - `INK_DIM` at `:72` and `:107`
  - `STATE_HUE` at `:171`
  - `QApplication` at `:270`
- Ruff reports this as 6× F821.
- `widget.py:531-535` imports the panel outside a `try`. Today `_load_agentdeck_items` fails first, so the panel never loads. The day agentdeck exports `load`, `HexmindWidget()` raises.

**Change:**
1. Use `from PySide6.QtCore import Signal` and rename `pyqtSignal` to `Signal`.
2. Import `INK_DIM` and `STATE_HUE` from `.theme`. Import `QApplication`.
3. Wrap `widget.py:533-535` in `try/except Exception: logger.exception(...)`, like the other optional panels.
4. The dead favourites and details actions and the Ctrl+K collision go to "needs decision".

**Test:**
- `test_agentdeck_panel_imports`: `importlib.import_module("hexmind.qt.agentdeck_panel")` succeeds.
- `test_room_survives_agentdeck_panel_error`: monkeypatch `_load_agentdeck_items` to return `(True, [])` and `AgentdeckPanel` to raise. `HexmindWidget()` still constructs.

**Verification:** probe `agentdeck_on` constructs without error; `ruff check hexmind/qt/agentdeck_panel.py` has no F821.

---

### Task 1.11 — Rename HealthScanner's shadowing `finished` signal

**Findings:** C-14 · **Size:** S · **Depends on:** none

**Problem:**
- `health.py:37` declares `finished = Signal(list)`, which shadows `QThread.finished`.
- It is emitted inside `run()` (`:57`), and `settings.py:485` connects `deleteLater` to it. The QThread can be deleted while it is still unwinding.
- An abort was reproduced only with a widened window, so the natural crash is unverified, but the fix is one line.

**Change:**
1. Rename the signal to `results_ready = Signal(list)`.
2. In `settings.py:484-486`, connect `_show_health` to `results_ready`. Connect `deleteLater` and the `_health_scanner = None` reset to the built-in `finished`.

**Test:** in `tests/test_qt_health.py`, run a scanner with a stub check and wait on `QThread.finished`. Assert `results_ready` fired once and the thread is no longer running before `deleteLater`.

**Verification:** probe `health_race` exits 0.

---

### Task 1.12 — Direct Line output fidelity: escape HTML, label the model actually asked, use the room's cwd

**Findings:** C-17 (chat bullets) · **Size:** S · **Depends on:** 1.5 (same files)

**Problem:**
- `chat.py:141` and `:156-158` pass prompt and model output to `QTextBrowser.append` as raw HTML, so `<tags>` in code vanish.
- The reply label reads the **current** combo text, not the model that was actually asked.
- `chat.py:54` and `models.py:45` use `DirectBackend(os.getcwd())`, which ignores the room's `--cwd`. opencode sessions are bound to their directory.

**Change:**
1. Wrap the prompt and both outputs in `html.escape(...).replace("\n", "<br>")`.
2. Store `primary` and `comparison` on the page when the request starts, and use them in `_show_results`.
3. Give `DirectLine` and `CalibrationRack` a `cwd` parameter. `app.py:64-65` passes `cwd`. The default runners close over it.

**Test:** with a runner that returns `"<b>x</b> & <script>"`, the transcript's `toPlainText()` contains that literal string. Change the combo mid-request and the label still names the original model.

**Verification:** `pytest tests/test_qt_chat.py tests/test_qt_models.py -q`.

---

## Phase 2 — keyboard and accessibility blockers

### Task 2.1 — Release the Tab key from every table

**Findings:** A-1 · **Size:** S · **Depends on:** none

**Problem:** `QTableWidget` defaults to `tabKeyNavigation=True`. Tab and Shift+Tab therefore cycle between cells forever, and only Ctrl+F gets out. The room's Tab chain dead-ends in the Team table. Five tables are affected:
- `widget.py:916`
- `timeline.py:297`
- `stats.py:349`
- `model_selector.py:72`
- `agentdeck_panel.py:78`

**Change:** add `table.setTabKeyNavigation(False)` after each of the five constructors. Arrow keys still move between cells.

**Test:** in `tests/test_qt.py`, give the Team table focus and send `QTest.keyClick(table, Qt.Key_Tab)`, then assert `QApplication.focusWidget() is not table`. Add one test per other table file, or a parametrized test across the panels.

**Verification:** `.audit/gui/a11y_probe2.py` leaves the table on the first Tab.

---

### Task 2.2 — Keyboard selection fills Task detail; Enter activates

**Findings:** A-3 · **Size:** S · **Depends on:** none

**Problem:** `widget.py:447-448` connects only `itemDoubleClicked` and `itemClicked`. Down, Return and Space fire only `currentItemChanged`, so a keyboard user never sees Task detail.

**Change:**
1. Add `self.tasks.currentItemChanged.connect(lambda cur, _prev: cur is not None and self._on_task_selected(cur))`.
2. Add `self.tasks.itemActivated.connect(self._on_task_activated)` and drop `itemDoubleClicked`. On most styles a double-click emits `itemActivated`; check the existing tests.

**Test:** inject one task through `_on_task`, call `widget.tasks.setCurrentCell(0, 1)`, and assert `widget.detail.toPlainText()` contains the task id.

**Verification:** `pytest tests/test_qt.py -q`.

---

### Task 2.3 — Visible focus distinct from hover

**Findings:** A-2, D-14 · **Size:** S · **Depends on:** 2.4 (it uses the new `CONTROL_EDGE` token)

**Problem:** these controls show no visible focus at all:
- Checkboxes: `theme.py:257-259` sets `QCheckBox:focus { outline: none; }` and nothing replaces it.
- Room tabs: there is no `QTabBar::tab:focus` rule.
- Rail buttons: there is no `QToolButton` rule anywhere.
- Tables: barely visible.

`a11y_focus.py` counted 0 changed pixels for both checkboxes, the tab bar and a rail button. Separately, hover (`:176`, plus the combo and checkbox hover rules) uses the same violet border as focus (`:196-199`, `:233-236`).

**Change** (in `theme.stylesheet()`):
1. Make hover borders `INK_DIM` instead of `VIOLET` for `QPushButton:hover` and `QCheckBox::indicator:hover`. Violet now means focus.
2. Add these rules:
   - `QCheckBox::indicator:focus { border: 2px solid VIOLET; }`
   - `QTabBar::tab:focus { border-bottom: 2px solid VIOLET; }`
   - `QToolButton:focus { border: 2px solid VIOLET; }`
   - `QTableView:focus, QTreeView:focus, QListView:focus { border: 2px solid VIOLET; }`
   - `QTableView::item:focus { border: 1px solid CYAN; }`

**Test:** in a new `tests/test_qt_theme.py`, parse `stylesheet()` and assert:
- each of the selectors above is present;
- no `:hover` block contains `VIOLET`.

Also run `.audit/gui/a11y_focus.py`: every probed widget shows more than 0 changed pixels.

**Verification:** re-shot `00-main.png`. Focus on Select Team now differs from hover.

---

### Task 2.4 — Contrast tokens: control borders, selection text, faint captions, SLATE

**Findings:** A-4, A-8, A-9, D-15 (values corrected by the critic) · **Size:** S · **Depends on:** none

**Problem:**
- `PANEL_EDGE #1c2436` is 1.25:1 against SUBSTRATE and is used for every control border, checkbox box and scrollbar handle (`theme.py:152, 171, 193, 212, 243, 255, 302, 308`). WCAG 1.4.11 needs 3:1.
- Selected text is INK on VIOLET, 2.71:1 (`:155-156, 221-222`).
- `INK_FAINT` is 3.30:1 and is used for 11 px text.
- `SLATE` is 4.24 on PANEL and 4.48 on SUBSTRATE.

**Change:**
1. Add `CONTROL_EDGE = "#636e88"` (3.81 / 3.61 / 3.41 on SUBSTRATE / PANEL / GRID). Use it for the borders of `QLineEdit`, `QPlainTextEdit`, `QTextBrowser`, `QTextEdit`, the spinboxes, `QPushButton`, `QComboBox` and `QCheckBox::indicator`, and for the scrollbar handles. Keep `PANEL_EDGE` for seams: tables, panes, splitters, the status bar and the tab-pane frame.
2. Change `selection-color` to `{SUBSTRATE}` (6.08:1).
3. Set `INK_FAINT = "#7d8899"` (5.42 / 5.13 / 4.85).
4. Set `SLATE = "#7686a0"` (5.26 / 4.98 / 4.71). Do **not** use `#6e7c96`, which is 4.37 on PANEL. Do **not** use `#3a4660` as a border, which is 2.06.

**Test:** in `tests/test_qt_theme.py`, add a pure-Python WCAG ratio helper. Assert:
- `INK`, `INK_DIM`, `INK_FAINT` and `SLATE` are ≥ 4.5 on each of `SUBSTRATE`, `PANEL` and `GRID`;
- `CONTROL_EDGE` is ≥ 3.0 on each of them;
- the selection pair is ≥ 4.5.

This test fails on today's tokens.

**Verification:** `/usr/bin/python3 .audit/gui/contrast.py` has no FAIL rows apart from the exempt disabled text.

---

### Task 2.5 — Room focus order matches the screen; rail first

**Findings:** A-7 · **Size:** S · **Depends on:** 2.1

**Problem:**
- `leadBox`, `auditBox` and the labels are created without a parent, while `teamButton` is created with `self` (`widget.py:393-405`). As a result, Select Team comes before Lead in the Tab chain.
- The rail, which sits furthest left, comes last in the chain.

**Change:**
1. In `_build_ui`, create every widget with `self` as parent, in visual order.
2. In `HexmindWindow.__init__`, set the order explicitly: rail buttons → `room.leadBox` → `teamButton` → `auditBox`. Use `QWidget.setTabOrder(rail.buttons["Settings"], room.leadBox)`, and so on.

**Test:** walk `nextInFocusChain()` from `room.leadBox` and assert the next focusable widgets are `teamButton`, then `auditBox`, then `transcript`.

**Verification:** `.audit/gui/a11y_probe3.py` prints a chain that starts with the rail.

---

### Task 2.6 — Command palette restores focus on close

**Findings:** A-10 (medium confidence offscreen; confirm on desktop) · **Size:** S · **Depends on:** none

**Problem:** `palette.py:166-176, 250` call `self.close()` without restoring the previous `focusWidget()`. After Esc, focus is `None`.

**Change:**
1. In `open_palette`, set `self._return_to = QApplication.focusWidget()`.
2. Override `closeEvent` (or `hideEvent`) so that, if `self._return_to` is still alive (check with `shiboken6.isValid`), it calls `setFocus(Qt.FocusReason.PopupFocusReason)`.

**Test:** in `tests/test_qt_palette.py`, focus `room.input`, open the palette, press Esc, and assert `QApplication.focusWidget() is room.input`.

**Verification:** test passes offscreen. Recheck once on KDE.

---

### Task 2.7 — Accessible names contain the visible label; labels get buddies and mnemonics

**Findings:** A-11, A-12 · **Size:** S · **Depends on:** none

**Problem:**
- Some accessible names don't contain the visible label (WCAG 2.5.3). For example, "Notify after" is announced as "Notification threshold seconds" (`settings.py:78`).
- The full list: `chat.py:72, 75, 97`; `settings.py:61, 68, 75, 78`; `models.py:86`.
- `QLabel("Lead:")` (`widget.py:415`) and the `"Ask"` and `"Ask another"` labels (`chat.py:80, 82`) have no buddy.

**Change:**
1. Start each name with the visible text: "Notify after (seconds)", "Enable peer audit by default", "Send a completion ping", "Select Team…", "Run probe", "Ask: primary model", "Ask another: comparison model".
2. Drop `setAccessibleName` from checkboxes and buttons whose own text already says it.
3. Label buddies: `lead_label = QLabel("&Lead:", self)` then `lead_label.setBuddy(self.leadBox)`. Do the same for "&Ask" and "Ask a&nother".

**Test:** for each listed control, assert `accessibleName()` (or `text()` when the name is empty) starts with the visible label. Assert `lead_label.buddy() is widget.leadBox`.

**Verification:** `.audit/gui/a11y_probe.py` §3 shows no `buddy=None` for those labels.

---

## Phase 3 — layout and visual structure

### Task 3.1 — Rail sized from content, with a styled checked state

**Findings:** D-1, A-6, C-12 · **Size:** M · **Depends on:** 2.3 (same QSS area, `QToolButton:focus`)

**Problem:**
- `rail.py:31` sets `setFixedWidth(56)`, which elides "Direct Line" to "Dir…ine" and "Calibration Rack" to "Ca…ck". Those labels need 83 px and 120 px including padding.
- There is no `QToolButton` QSS, so the checked "Room" is a barely lighter navy (`rail-crop.png`).
- Margins and spacing are 0 (`:50-55`).

**Change:**
1. Replace the fixed width with `fm = self.navigation.fontMetrics()`, then `self.navigation.setFixedWidth(max(fm.horizontalAdvance(n) for n in self.page_names) + 32)`.
2. Call `button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)`.
3. Set `navigation_layout.setContentsMargins(8, 12, 8, 12)` and `setSpacing(4)`.
4. Call `self.navigation.setObjectName("benchRail")`.
5. Add the `#benchRail QToolButton` normal, `:hover` and `:checked` rules from D-1 to `theme.stylesheet()`. The checked rule uses `color: VIOLET; border-left: 2px solid VIOLET`. Do not set any style on the widget itself (AGENTS.md).

**Test:** in `tests/test_qt_rail.py`:
- for every button, `button.width() >= button.fontMetrics().horizontalAdvance(button.text())`;
- `"#benchRail QToolButton:checked"` is in `theme.stylesheet()`.

Today the first assertion fails for 3 of the 4 buttons.

**Verification:** probe `layout` shows width ≥ needs for every rail button. Re-shot `00-main.png`.

---

### Task 3.2 — Left column: transcript and detail in a vertical splitter, detail collapsed until a task is chosen

**Findings:** C-10, D-3, D-2 (transcript and detail placeholders), D-9 (stop mirroring into detail) · **Size:** M · **Depends on:** 2.2

**Problem:**
- `transcript` and `detail` both have stretch 1 (`widget.py:541-545`), so the first frame shows two empty 300 px boxes.
- `_on_message` (`:675-679`) copies every message into `detail`.
- `detail_toggle` is a checked `QPushButton`. It renders as a full-width cyan bar (656×52), the loudest element on screen.

**Change:**
1. Put `transcript` and `detail` in a `QSplitter(Qt.Vertical)` in place of the two `addWidget(…, 1)` calls.
2. Call `setSizes([1, 0])` initially.
3. In `_on_task_selected`, open the detail pane if it is collapsed (`sizes()[1] == 0`), using `setSizes([2, 1])`.
4. Delete the mirror block in `_on_message` (`:675-679`).
5. Add placeholders:
   - `transcript.setPlaceholderText("Ask the team anything. The lead plans, members run tasks, verdicts land here.")`
   - `detail.setPlaceholderText("Select a task to read its instructions and output.")`
6. Turn `detail_toggle` into a `QToolButton` with `setAutoRaise(True)` and `setArrowType(Qt.DownArrow)`, flipping to `RightArrow` when collapsed. Put it in `search_row`. It toggles the splitter's lower pane. `tests/test_qt.py:475-478` clicks it, so keep the attribute name and the toggling semantics.

**Test:**
- After `_on_message("claude", "hi")`, `widget.detail.toPlainText() == ""`.
- At 1400×900, `widget.transcript.height() > 2 * widget.detail.height()`.
- `detail_toggle.width() < 200`.

**Verification:** probe `layout` shows transcript height ≫ detail height; re-shot.

---

### Task 3.3 — Top bar: the lead combo stops stretching and the bar stops reflowing on turn start

**Findings:** C-11, D-13, D-12 (spacing) · **Size:** S · **Depends on:** 1.2 (same widgets)

**Problem:**
- `bar.addWidget(self.leadBox, 1)` (`widget.py:415`) makes the combo about 974 px wide.
- `turnMeter` starts at zero width, so Select Team jumps about 215 px when a turn starts.
- "Peer audit" and "ready" read as one phrase.

**Change:**
1. `bar.addWidget(self.leadBox)` (no stretch), plus `self.leadBox.setMinimumContentsLength(16)` and `setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)`.
2. `bar.addStretch(1)` after `auditBox`, then `addSpacing(16)` before `status`.
3. `self.turnMeter.setMinimumWidth(self.turnMeter.fontMetrics().horizontalAdvance("[● opencode-ultra · working · 00:00]"))`.

**Test:**
- At 1400 px, `leadBox.width() < 400`.
- Record `teamButton.x()`, call `_on_turn_state(True)` and `pump()`, and assert `teamButton.x()` is unchanged.

**Verification:** probe `layout` prints a leadBox width under 400.

---

### Task 3.4 — Splitter proportions and a tab bar that fits at 1400 px

**Findings:** C-13, D-5, A-14, D-19 · **Size:** S · **Depends on:** 1.6 (otherwise a stale `qt/split` overrides the sizes in tests)

**Problem:**
- Only `setStretchFactor(0, 1)` is set (`widget.py:549`). The right pane never grows, and at 1000 px it starves the left.
- `QTabBar::tab` has `padding: 8px 14px; min-width: 70px` (`theme.py:131-140`), so six tabs overflow and "Stats" is clipped behind 16×35 px scroll arrows.

**Change:**
1. `split.setStretchFactor(1, 1)` and `left.setMinimumWidth(420)`. When there is no persisted state, `split.setSizes([620, 780])`.
2. Change the tab rule to `padding: 6px 12px` and remove `min-width`.
3. `right.tabBar().setExpanding(False)` and `right.setElideMode(Qt.ElideRight)`.
4. Add `QTabBar QToolButton { min-width: 24px; }` for the cases that still scroll (A-14, target size).

**Test:** at `resize(1400, 900)` with a fresh QSettings, assert the union of `tabRect(i)` for all tabs fits inside `tabBar().width()`, which means the scroll buttons are hidden.

**Verification:** re-shot `00-main.png` and `03-min-size.png`.

---

### Task 3.5 — Empty states for the Tasks, Live Tap and Team tables and the Graph

**Findings:** D-2 (tables and graph) · **Size:** M · **Depends on:** 2.4 (it uses the new `INK_FAINT`)

**Problem:** the blank Tasks, Live Tap and Graph tabs give no hint of what will appear. Only Timeline has an empty state (`timeline.py`), and it is the model to copy.

**Change:**
1. Give `_table` (`widget.py:915`) an optional `empty_text`. Implement it with a small `QTableWidget` subclass whose `paintEvent` draws centred `INK_FAINT` text when `rowCount() == 0`.
2. In `TaskGraphView`, override `drawForeground` the same way when `not self._nodes`. Do not touch `select_task`, `fit`, `clear` or `update_task`.
3. For `LivePane`, use `setPlaceholderText` if it is a text widget (check `live.py`).
4. Copy: "No tasks yet. The lead's plan lands here." / "Task graph appears once the lead plans."

**Test:** an empty table's `empty_text` is set; grab the empty Tasks table and the empty graph and assert some pixel in the centre band differs from the background colour.

**Verification:** re-shot `01-tab-1-Tasks.png` and `01-tab-3-Graph.png`.

---

### Task 3.6 — Real chevrons on combo and spinbox arrows

**Findings:** D-4, D-6 · **Size:** M · **Depends on:** 2.4

**Problem:**
- `theme.py:226-232` draws the combo arrow with the CSS border-triangle trick. Qt paints that as a 5 px grey square.
- `QSpinBox` has its frame styled (`:149-157`) but no `::up-button` or `::down-button` rules, so the step buttons collapse into black slivers.

**Change:**
1. Add `hexmind/qt/icons/chevron-down.svg` and `chevron-up.svg`: 10×10, stroke `INK_DIM`.
2. Make sure `pyproject.toml` package-data ships `qt/icons/*.svg`.
3. In `stylesheet()`, resolve `ICONS = Path(__file__).parent / "icons"` and use `QComboBox::down-arrow { image: url(<ICONS>/chevron-down.svg); width: 10px; height: 10px; }`. Use `as_posix()` for the path.
4. Add the spinbox `::up-button`, `::down-button`, `::up-arrow` and `::down-arrow` rules from D-6, for both `QSpinBox` and `QDoubleSpinBox`.

**Test:** `test_qt_theme.py` checks that every `url(...)` in `stylesheet()` points to an existing file.

**Verification:** 6× crops of the Lead combo and of Server port and Notify after in a re-shot `02-ws-Settings.png`.

---

### Task 3.7 — Settings form: fields at their size hint, aligned labels, bounded page width

**Findings:** D-7, D-8 (full-width health button) · **Size:** S · **Depends on:** 3.6

**Problem:**
- The bare `QFormLayout()` (`settings.py:94-103`) grows its fields to about 1230 px.
- Labels sit top-aligned against vertically centred fields.
- `layout.addWidget(self.health_button)` (`:152`) makes the health button full width.

**Change:**
1. `form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.FieldsStayAtSizeHint)` and `form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)`.
2. Give the line edits and combos `setMinimumWidth(280)` and the spinboxes `setMaximumWidth(160)`.
3. Wrap the page content in a container with `setMaximumWidth(720)`, anchored left.
4. Put the health button in a `QHBoxLayout` with `addStretch()` after it.
5. Grouping into Session, Appearance and Server sections is optional. See "needs decision".

**Test:** at 1400×900, `server_host_input.width() <= 480` and `health_button.width() < 400`.

**Verification:** re-shot `02-ws-Settings.png`.

---

### Task 3.8 — Panel spacing: Stats margins, Timeline columns, Direct Line intro

**Findings:** D-21, D-18 (Direct Line intro stretch only) · **Size:** S · **Depends on:** none

**Problem:**
- `stats.py:315-324` sets `outer.setContentsMargins(0, 0, 0, 0)`, so the summary text touches the pane edge.
- The `ResizeToContents` columns at `timeline.py:377-380` overflow, so the empty table shows a horizontal scrollbar.
- The Direct Line intro box (`chat.py:123-128`, stretch 1) takes 340 px to say three lines.

**Change:**
1. Stats: `outer.setContentsMargins(8, 8, 8, 8)`.
2. Timeline: set the Detail column to `Stretch`, set the Task column to `Interactive` with a default width of 160, and `header.setMinimumSectionSize(64)`.
3. Direct Line: give the intro stretch 0 and a maximum height of 3 lines, and give `outputs` stretch 1.

**Test:**
- Empty Timeline at 600 px wide: `table.horizontalScrollBar().isVisible() is False`.
- The Direct Line output panes are taller than the intro box.

**Verification:** re-shot `01-tab-4-Timeline.png`, `01-tab-5-Stats.png` and `02-ws-Direct_Line.png`.

---

### Task 3.9 — Draw the command palette's frame and pad its hint

**Findings:** D-23 · **Size:** S · **Depends on:** 2.6 (same file)

**Problem:** `palette.py:126-132` puts `WA_TranslucentBackground` on the `QDialog` that carries `#palette`, so the border QSS never paints. The hint label at `:147-156` has no object name and no padding.

**Change:**
1. Move the input, list and hint into an inner `QFrame` named `"palette"`. Rename the dialog's object name to `"paletteDialog"` and keep it translucent.
2. Call `hint.setObjectName("paletteHint")` and add the `#paletteHint` QSS from D-23.

**Test:** in `tests/test_qt_palette.py`, assert `palette.findChild(QFrame, "palette")` exists and contains the input and the list. Grab the open palette and assert the border pixel equals `VIOLET`.

**Verification:** re-shot `16-palette.png`.

---

## Phase 4 — polish

### Task 4.1 — Transcript renders markdown, with speaker colour

**Findings:** D-9 · **Size:** M · **Depends on:** 3.2

**Problem:** `_on_message` (`widget.py:670-672`) does `appendPlainText(f"{label}: {text}")` into a `QPlainTextEdit`. That leaves literal `**` and backticks on screen, and every speaker gets the same ink. `AGENT_COLOR` is never used in the GUI.

**Change:**
1. Make `transcript` a read-only `QTextBrowser`.
2. Call `document().setMaximumBlockCount(2000)`.
3. Per message:
   - Insert a speaker line in `FONT_MONO` and `FONT_SIZE_SMALL`: `VIOLET` for the lead, `AGENT_COLOR.get(who, INK_DIM)` for a member, `INK_DIM` italic for `hexmind`.
   - Then insert the body with `cursor.insertMarkdown(text)`.
   - Import `AGENT_COLOR` by module attribute (`models.AGENT_COLOR`), not by name, so a `publish()` takes effect.
4. `_find_match` already works on `document()`. Keep `toPlainText()` semantics so existing tests pass.

**Test:**
- After `_on_message("claude", "**t1** done")`, `toPlainText()` contains `t1 done` and no `**`.
- The speaker fragment's foreground equals the expected colour.
- Search still finds `t1`.

**Verification:** full suite; re-shot `11-populated-tasks.png`.

---

### Task 4.2 — Task and Team tables show state through `STATE_HUE`, plus a glyph

**Findings:** D-10 · **Size:** S · **Depends on:** 2.4 (new SLATE)

**Problem:** `_on_task` (`widget.py:747-756`) and `_add_row` (`:893-897`) build bare `QTableWidgetItem`s. This contradicts `theme.py:66-68` ("the table … resolve[s] through [STATE_HUE]").

**Change:**
1. Status column: `item.setForeground(QColor(theme.state_hue(task.status)))`, with the text prefixed by `● `.
2. Audit column: map pass, fixed and disputed to GREEN, AMBER and RED.
3. Team "state" column: `lead` is VIOLET, `busy …` is CYAN, `asleep` is SLATE.
4. Store the raw status in `Qt.UserRole` so `_row_of` and tests that read `.text()` keep working, or update those tests.

**Test:** inject a `failed` task and assert `tasks.item(0, 2).foreground().color().name() == theme.state_hue("failed")`.

**Verification:** re-shot `11-populated-tasks.png`.

---

### Task 4.3 — Graph: labels and layout on the incremental path, a fit, and a status glyph

**Findings:** D-11 (medium after critic), A-13 · **Size:** M · **Depends on:** none

**Problem:**
- `update_task`'s add branch (`graph.py:260-295`) places new nodes 10 px apart and never adds a `QGraphicsSimpleTextItem` label.
- It draws edge stubs from (0,0).
- During a turn the graph is a cluster of unlabeled dots. It only becomes labelled when `refresh_team` triggers `set_tasks` at the end of the turn.
- Status is shown by colour only, and nodes are not focusable.

**Change:**
1. In the add branch, after inserting, schedule one debounced `QTimer.singleShot(0, self._relayout)`. `_relayout` re-runs the `set_tasks` layout and reuses existing `Node` instances keyed by id, which preserves the identity the tests require.
2. Call `fit()` at the end of `_relayout`.
3. Draw a one-character status glyph centred in each node: ✓, ✗, … or ◐ by state.
4. `setAccessibleDescription("Task graph. The Tasks tab lists the same tasks for keyboard and screen readers.")`.
5. Keep the public hooks unchanged.

**Test:** in `tests/test_qt_graph.py`:
- `update_task` with 4 new tasks, then process events.
- Every node has a label child.
- No two nodes' bounding rects intersect.
- Node identity is preserved across a status update (the existing assertion still holds).

**Verification:** re-shot `12-populated-graph.png`.

---

### Task 4.4 — Typography tokens: role-based label rules, no off-scale inline sizes, no `line-height`

**Findings:** D-16, A-5 (partial: removing the forced global px size is a decision) · **Size:** S · **Depends on:** 2.4

**Problem:**
- `FONT_SIZE_LARGE` is never used.
- Headings are body text: "Settings", "Registered models" and "Primary response".
- These inline styles use off-scale sizes: `stats.py:277, 280, 289, 348` and `timeline.py:283, 294` (11 px).
- `line-height` (`theme.py:109`) is not a QSS property.

**Change:**
1. Add `QLabel[role="title"]`, `[role="heading"]` and `[role="caption"]` rules to `stylesheet()`, built from `FONT_SIZE_LARGE`, `FONT_SIZE` and `FONT_SIZE_SMALL`.
2. Replace each inline `setStyleSheet` font rule with `setProperty("role", …)`.
3. Delete `line-height`.

**Test:** `grep -rn "font-size: 11px\|setStyleSheet" hexmind/qt/stats.py hexmind/qt/timeline.py` returns nothing. In `test_qt_theme.py`, assert the three role selectors are present.

**Verification:** re-shot `02-ws-Settings.png` and `02-ws-Calibration_Rack.png`.

---

### Task 4.5 — A primary button variant

**Findings:** D-8 · **Size:** S · **Depends on:** 2.3

**Problem:** every `QPushButton` gets the same quiet style (`theme.py:168-175`). Send, Save, Ask and Run probe look exactly like "Open config folder".

**Change:**
1. Add `QPushButton[variant="primary"] { background: VIOLET; color: SUBSTRATE; border-color: VIOLET; font-weight: 600; }`, with `:disabled` falling back to the quiet style.
2. `setProperty("variant", "primary")` on Send (`widget.py:434`), Settings Save, Direct Line Ask, and Run probe.

**Test:** assert those four buttons have `property("variant") == "primary"`, and the selector is in `stylesheet()`.

**Verification:** re-shot.

---

### Task 4.6 — Table headers: left-aligned, no scalloped sections

**Findings:** D-20 · **Size:** S · **Depends on:** none

**Problem:** headers are centred over left-aligned cells (`widget.py:915-924`). Each header section has rounded top corners (`theme.py:290-291`).

**Change:**
1. `table.horizontalHeader().setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)` in `_table`, `timeline.py` and the `stats.py` ledger.
2. Remove the per-section radius.
3. Unifying the casing is a decision.

**Test:** `widget.tasks.horizontalHeader().defaultAlignment()` includes `AlignLeft`.

**Verification:** re-shot.

---

### Task 4.7 — Hue discipline: list padding and row selection

**Findings:** D-24 · **Size:** S · **Depends on:** 2.4

**Problem:**
- `QListWidget` items have no padding: 17 px rows, against 30 px table rows.
- Selected rows use VIOLET text (`theme.py:269-270`), the same hue as the lead, so a selected row and the lead row look alike.
- The checked checkbox is GREEN (`:248-251`). Moving it off green is a decision.

**Change:**
1. Add `QListWidget::item { padding: 6px 10px; }`.
2. Change the selection to `selection-background-color: PANEL_HOVER; selection-color: INK`, with `::item:selected { border-left: 2px solid VIOLET; }`.

**Test:** both rules are in `stylesheet()`. INK on PANEL_HOVER is ≥ 4.5 (add it to the 2.4 ratio test).

**Verification:** re-shot `02-ws-Calibration_Rack.png`.

---

### Task 4.8 — Stats charts: integer ticks and an empty "where the team hurts" chart

**Findings:** D-22 · **Size:** S · **Depends on:** none

**Problem:**
- `_stack_bars` (`stats.py:213-266`) leaves pyqtgraph to pick ticks automatically, so integer counts get 0.5 steps.
- With zero failures, "Where the team hurts" is a solid wall of green.

**Change:**
1. `plot.getAxis("bottom").setTickSpacing(1, 1)` for the count chart.
2. When the total failed count is 0, show the caption "No failures recorded yet." in place of the hurts chart.
3. Normalising both charts to a ratio is a decision.

**Test:** load a ledger with 0 failures and assert the hurts plot is hidden and the caption is visible.

**Verification:** re-shot `01-tab-5-Stats.png`.

---

### Task 4.9 — Remove the stray tick marks between tabs

**Findings:** D-25 (root cause unproven) · **Size:** S · **Depends on:** 3.4

**Change:** add `QTabBar::tab { margin-right: 2px; }`, `QTabBar::tab:!selected { margin-top: 2px; }` and `QTabWidget::tab-bar { left: 8px; }`.

**Test:** none automated. Use a 3× crop of a re-shot `00-main.png`. If the ticks remain, revert the change and note it.

---

### Task 4.10 — Status: one channel, styled, and announced

**Findings:** D-12, A-15 (low confidence, needs Orca) · **Size:** S · **Depends on:** 3.3

**Problem:**
- "ready" and "working…" sit unstyled next to the Peer audit checkbox.
- The window status bar repeats the same status.
- Status changes are never announced. There is no `QAccessible` usage at all (`widget.py:620, 632`).

**Change:**
1. `self.status.setObjectName("roomStatus")`, and add the pill QSS from D-12. CYAN while busy, through a dynamic property plus `style().unpolish/polish`.
2. In `_on_turn_state`, call `QAccessible.updateAccessibility(QAccessibleAnnouncementEvent(self.status, text))`. Guard it with `hasattr(QtGui, "QAccessibleAnnouncementEvent")`.

**Test:** monkeypatch `QAccessible.updateAccessibility` and assert it is called once per state change.

**Verification:** one Orca check on KDE.

---

### Task 4.11 — Log swallowed exceptions in the room

**Findings:** C-17 (swallowed-exception bullet) · **Size:** S · **Depends on:** 1.6 (which already converts two of these)

**Problem:** these blocks hide broken graph, timeline, search, task-detail and panel code without a log line:
- `except Exception: pass` at `widget.py:687-688, 696-697, 743-744, 876-877`
- `hexmind/__init__.py:557`

**Change:** replace each with `logger.exception("…")`, using the existing `logger` (`widget.py:56`). Keep the swallow, because a panel must not take down the room. Only add the log.

**Test:** monkeypatch `widget.graph.set_tasks` to raise, call `_refresh_graph()`, and assert `caplog` has the record.

**Verification:** full suite.

---

## Dependencies at a glance

- **1.1 → 1.2 → 3.3 → 4.10.** These touch the same room toolbar and `_on_turn_state`.
- **1.3 → 1.4.** Both change `_Room.submit` and `stop`.
- **1.5 → 1.9, 1.12.** These touch the same `closeEvent` and the same `chat.py`/`models.py` threads.
- **1.6 → 3.4, 4.11.** 3.4 needs hermetic QSettings for deterministic splitter tests. 4.11 builds on the excepts 1.6 already converts.
- **1.7 → 1.8.** Same `settings.py` state code.
- **2.4 → 2.3, 3.5, 3.6, 4.2, 4.4, 4.7.** These use the new tokens.
- **2.3 → 3.1, 4.5.** Same `QToolButton` and `QPushButton` QSS blocks.
- **2.1 → 2.5.** Focus-order assertions need the trap gone.
- **2.2 → 3.2 → 4.1.** Detail behaviour, then the left-column splitter, then the transcript widget swap.
- **2.6 → 3.9.** Same `palette.py`.
- **3.4 → 4.9.** Same tab QSS.
- Everything else is independent.

## Not doing / needs decision (product calls for the user)

1. **D-17: design board versus `theme.py`.** Hues, fonts (Bricolage, GeistMono, CrimsonPro versus Inter and JetBrains Mono) and motifs (member pills, hexagon) have drifted. Decide which document is canonical before anyone retunes tokens or bundles fonts.
2. **A-5: forced 14 px font and zoom.** Dropping `font-size` from the global `QWidget` rule lets the KDE font setting win (WCAG 1.4.4), and you could add View → Zoom in/out (Ctrl+= / Ctrl+-). Either one changes every layout measured in this plan. Decide before Phase 3 if you want it, or after Phase 4 if not.
3. **C-1 long term: team save through core.** `_on_team_saved` assigns `orch.members` directly, and no core rule applies. Task 1.2 makes this safe by disabling the button mid-turn. A proper `Orchestrator.set_members()` that enforces S-1 is a core API addition.
4. **C-6: Agentdeck panel.** Wire up "Add to Favorites" and `_view_details` (`agentdeck_panel.py:273, 293`) and resolve its Ctrl+K collision with the room palette, or delete the panel. Task 1.10 only makes it importable.
5. **Unify persistence.** Splitter and tab state live in QSettings (`room.conf`), while window geometry lives in `config.toml [gui]`. Merging them means the embeddable widget writes `config.toml` under Aether.
6. **Theme combo** (`settings.py:70-72`). It has one item, saves to `[room].theme`, and nothing reads it. Hide it until a second theme exists?
7. **Remove the Task-detail toggle entirely** (D-3) instead of the small `QToolButton` in 3.2.
8. **Rail style:** a wider text rail (3.1) versus icons with `ToolButtonTextUnderIcon` and short labels. The icons need new SVGs (the icon-design skill).
9. **Settings grouping** into Session, Appearance and Server; **header casing** (D-20); **checked checkbox GREEN → VIOLET** (D-24); **Stats charts as ratios** (D-22); **raised versus recessed surface hierarchy** (D-18, beyond the Direct Line fix).
10. **Rail shortcuts Ctrl+1…4** (A-7 suggestion). Cheap, but they claim global shortcuts.
11. **Not doing:** C-17 palette "flash" at construction (unverified offscreen; re-check on a real desktop first).

## Known coverage gaps

- I did not do a real Wayland/X11 run and no screen reader was used. A-10, A-15, D-25 and the palette flash need a desktop check after their tasks.
- Several tests do not exist yet; tasks 1.1, 1.4, 1.5 and 1.10 add them. Today nothing covers:
  - closing during a Direct Line or probe thread;
  - closing mid-turn with a real child process;
  - the agentdeck tab loading;
  - a team save with the real lock.

## Definition of done

- Every task lands as its own commit, with its regression test.
- No preserved roadmap hook is removed.
- `HexmindWidget` never calls `QApplication.setStyleSheet`.
- The full suite stays at baseline or better, and ruff has no new findings.
- Probes `team_deadlock`, `chat_close` and `orphan` exit 0 with no survivors, and every `.audit/gui/` probe reflects the fixes.
- The shots are re-generated with `.audit/gui/shots.py` and `shots_extra.py` and reviewed against `.audit/gui/shots/`.

## Verification (run after each task, and once at the end)

```sh
QT_QPA_PLATFORM=offscreen python3 -m pytest tests -q      # expect >=725 passed, only the 2 ling-flash failures
python3 -m ruff check .                                   # no NEW findings vs baseline
H=$(mktemp -d); for p in team_deadlock chat_close orphan; do \
  HOME=$H PYTHONPATH=. QT_QPA_PLATFORM=offscreen timeout 20 /usr/bin/python3 .audit/gui/probe_code.py $p; echo "$p exit=$?"; done
/usr/bin/python3 .audit/gui/contrast.py                   # no FAIL rows except exempt disabled text
```

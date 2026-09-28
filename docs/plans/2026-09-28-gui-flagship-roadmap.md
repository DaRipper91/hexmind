# Hexmind GUI Flagship — Roadmap & Build Guide

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (or subagent-driven-development) to implement this plan task-by-task.

**Goal:** Make `hexmind-gui` the flagship front-end: honest, live, controllable, and the one place you configure the whole setup (models, agent CLIs, settings) and talk to any model directly.

**Architecture:**
- **One brain.** Qt only renders and calls into the program. Any new logic is added as a public
  function in `core.py`, `relay.py`, `backends.py`, `config.py`, `models.py` or `auditor.py`, never
  written inside Qt (`hexmind/qt/widget.py:8-11`).
- **Embed rule.** `HexmindWidget` stays the room and nothing more, so Aether can keep embedding it.
  Every new screen is its own embeddable `QWidget`, and `HexmindWindow` (`qt/app.py`) assembles
  them behind a navigation rail (`docs/AETHER-INTERFACE.md` hard rules).

**Tech Stack:** Python 3.12+, PySide6 (plus the optional pyqtgraph, qtawesome and qdarkstyle already
in the `qt` extra), pytest with `QT_QPA_PLATFORM=offscreen`. No new dependencies.

**Sources:** `docs/plans/2026-09-28-gui-feature-forge.md` (technical, "forge"),
`docs/plans/2026-09-28-gui-ux-ideas.md` (UX, "ux"). The problem IDs P1–P17 are listed in ux §2.

---

## Decisions (made with the user, 2026-09-28)

| # | Decision | Consequence |
|---|---|---|
| D1 | **One shared config.** The GUI saves to `~/.config/hexmind/config.toml`. `hexmind`, `--serve` and `hexmind-gui` all read it as their defaults. Command-line flags override it for one run. | Phase 1 builds this before any settings screen exists. |
| D2 | **1:1 chat is separate, with "Send to room".** Each model has its own conversation with history. A chosen message can be posted into the room transcript. | Phase 7. History is replayed into each prompt, which works the same on every CLI. Native session resume is deferred. |
| D3 | **CLI health shows problems and offers safe one-click fixes.** Fixes run in a terminal window you can see, never silently inside the GUI. *(The user didn't choose an option; this was the recommended default. Easy to change.)* | Phase 5. |
| D4 | The model manager writes **only** `~/.config/hexmind/models.toml`, never the bundled file. | Phase 6. "Reset" means deleting the override. |
| D5 | **The TUI is out of scope.** Don't edit `hexmind/tui.py`. The user maintains mobile TUI branches separately. | All phases. |

---

## Roadmap

| Phase | Name | Size | Source | Depends on | Detail level |
|---|---|---|---|---|---|
| 0 | Honest Instruments: fix readings that are wrong today | S | ux P1 P2 P3 P11 | none | **Full steps** |
| 1 | Shared config (D1) | S | decision D1 | none | **Full steps** |
| 2 | Live Wire and Hand brake: see and stop a running turn | M | forge "Live tap" (status part) and "Hand brake"; ux §5 | 0 | **Full steps** |
| 3 | Bench Rail: navigation shell for the new screens | M | ux §3 | 0 | Task spec |
| 4 | Settings page | M | ux §4.4 | 1, 3 | Task spec |
| 5 | Agent health and First Light onboarding | M | ux §4.3, §6.4; D3 | 3 | Task spec |
| 6 | Model manager (Calibration Rack) and single-model call | L | ux §4.1; D4 | 3, 5 | Task spec |
| 7 | Direct Line: 1:1 chat | M | ux §4.2; D2 | 6 (single-model call) | Task spec |
| 8 | Polish: readout transcript, host-safe colour, palette 2.0, graph and stats | M | ux §6, §7; P6–P10, P12–P15 | 3 | Task spec |
| 9 | Flagship extras, one at a time: live output streaming, Come-back pings, Plan workbench, Relay Runs desk, Audit courtroom, Room-as-protocol, Mission control | L each | forge | 2, 3 | Backlog |

**Why this order:**
- **0 and 1 first.** They are cheap, fix wrong readings, and give every later settings screen
  something to save to.
- **2 next.** It is the biggest felt improvement. Turns take minutes, and today they can't be seen
  or stopped.
- **3 before 4–7.** The new screens have no home until the rail exists.
- **6 before 7.** Both need the single-model call path, and the model manager's Test button is its
  smallest consumer.

**How to execute:** Phases 0–2 have complete test-first steps below. For Phases 3–9, run the
`writing-plans` skill on that phase's task spec right before building it, so its steps match the
code as it stands after the earlier phases.

---

## Build guide: conventions for every task

- **Run the tests:** `cd ~/Projects/hexmind && QT_QPA_PLATFORM=offscreen python3 -m pytest -q`.
  The baseline is **619 passed** at `e7d9ba3`. Every task ends with the full suite green.
- **Lint:** `ruff check .`. The baseline is 10 errors. Don't add new ones.
- **Qt tests:**
  - Use the `qapp`, `room` and `pump()` helpers in `tests/test_qt.py:56-86`.
  - `FakeBackend` (`tests/test_qt.py:29`) is the scripted team.
  - Tests never launch a real agent CLI.
- **Config isolation:** `tests/conftest.py` redirects `config.PATH` and `models.USER` to a temp
  HOME for the whole session. New code must read `config.PATH` **at call time**, not as a default
  argument frozen at import (see the trap described in `hexmind/models.py:179-181`).
- **Commits:** one per task, conventional prefix, ending with the attribution line:
  `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- **Live check:** after any change to how an agent CLI is invoked, run the real argv once
  (the `#high` variant bug in `08a3fc0` passed every test and failed every real call).

---

## Phase 0 — Honest Instruments

### Task 0.1: The lead combo stops showing a lead that isn't set (P1)

**Files:**
- Modify: `hexmind/qt/widget.py` (`_on_lead_picked` ~line 485; `refresh_team` ~line 593)
- Test: `tests/test_qt.py`

**Step 1: Write the failing test** (add after `test_a_room_with_no_lead_will_not_send_and_says_why`)

```python
def test_with_no_lead_the_combo_says_so_and_picking_the_first_member_works(room):
    """P1: with no lead the combo showed `claude` as if chosen, and picking `claude` then fired
    nothing because it was already the current text."""
    from hexmind.qt.widget import LEAD_PLACEHOLDER

    widget = room(backend=FakeBackend(), lead=None)
    assert widget.leadBox.currentText() == LEAD_PLACEHOLDER

    widget.leadBox.setCurrentIndex(widget.leadBox.findText("claude"))
    pump(1000)

    assert widget.lead == "claude"
    assert widget.leadBox.findText(LEAD_PLACEHOLDER) == -1, "placeholder must go once a lead exists"
```

**Step 2: Run it and confirm it fails**

Run: `QT_QPA_PLATFORM=offscreen python3 -m pytest tests/test_qt.py -k combo_says_so -q`
Expected: FAIL with `ImportError: cannot import name 'LEAD_PLACEHOLDER'`.

**Step 3: Implement**

At module level in `widget.py`, near `_LIVE_ROOMS`:

```python
# Shown in the lead combo while the room has no lead, so the combo never names someone who isn't.
LEAD_PLACEHOLDER = "Choose a lead…"
```

In `refresh_team`, replace the `if lead in members:` block:

```python
        if lead in members:
            self.leadBox.setCurrentText(lead)
        else:
            self.leadBox.insertItem(0, LEAD_PLACEHOLDER)
            self.leadBox.setCurrentIndex(0)
```

In `_on_lead_picked`, change the guard to:

```python
        if not name or name == self.lead or name == LEAD_PLACEHOLDER:
            return
```

**Step 4: Run it and confirm it passes**, then run the whole of `tests/test_qt.py`. Expected: all pass.

**Step 5: Commit**

```bash
git add hexmind/qt/widget.py tests/test_qt.py
git commit -m "fix(qt): lead combo shows a placeholder instead of a lead that isn't set"
```

### Task 0.2: The Peer audit box starts in the right state (P2)

**Files:** Modify `hexmind/qt/widget.py` (the `__init__` block where `auditBox.stateChanged.connect` is called, ~line 275). Test: `tests/test_qt.py`.

**Step 1: Failing test**

```python
def test_the_audit_box_starts_checked_when_the_room_starts_audited(room):
    """P2: `hexmind-gui --audit` showed the box unchecked while the orchestrator was auditing."""
    widget = room(backend=FakeBackend(), audit=True)
    assert widget._room.orch.audit is True
    assert widget.auditBox.isChecked()
```

**Step 2:** Run it. Expected: FAIL at `assert widget.auditBox.isChecked()`.

**Step 3: Implement.** Put this immediately **before** the `stateChanged.connect` line, so setting
it doesn't fire the handler:

```python
        self.auditBox.setChecked(bool(audit))
```

**Step 4:** Run the test and `tests/test_qt.py`. Expected: pass.

**Step 5:** `git commit -m "fix(qt): peer audit checkbox reflects the room's starting audit state"`

### Task 0.3: Visible checkbox indicators on the dark theme (P3)

**Files:** Modify `hexmind/qt/theme.py` (inside `stylesheet()`, after the `QLineEdit:focus` rule ~line 127). Test: `tests/test_qt_app.py`.

**Step 1: Failing test**

```python
def test_the_theme_draws_checkbox_indicators():
    """P3: with no indicator rule the default box vanished into SUBSTRATE, so 'Peer audit' read as a label."""
    qss = theme.stylesheet()
    assert "QCheckBox::indicator" in qss
    assert "QCheckBox::indicator:checked" in qss
```

**Step 2:** Run it. Expected: FAIL.

**Step 3: Implement**, inside the f-string:

```css
    QCheckBox::indicator {{
        width: 14px; height: 14px;
        border: 1px solid {INK_DIM};
        border-radius: 3px;
        background: {PANEL};
    }}
    QCheckBox::indicator:hover {{ border: 1px solid {VIOLET}; }}
    QCheckBox::indicator:checked {{ background: {VIOLET}; border: 1px solid {VIOLET}; }}
    QCheckBox:focus {{ outline: 1px solid {VIOLET}; }}
```

**Step 4:** Run the tests. Then look at the window once: `timeout 10 hexmind-gui` should show a
visible box next to "Peer audit".

**Step 5:** `git commit -m "fix(qt): draw checkbox indicators on the dark theme"`

### Task 0.4: The palette menu item works instead of sitting greyed out (P11)

**Files:** Modify `hexmind/qt/app.py:93-98`. Test: `tests/test_qt_app.py`.

**Step 1: Failing test** (the `window` fixture in `test_qt_app.py` wraps a `StubRoom`)

```python
def test_the_palette_menu_item_is_enabled(window):
    """P11: a greyed-out item reads as 'unavailable', which undercuts the discoverability it was added for."""
    assert window.palette_action.isEnabled()
```

**Step 2:** Run it. Expected: FAIL.

**Step 3: Implement.** Replace the disabled action with one that calls the widget's own palette, so
there's still only one live `QShortcut`:

```python
        self.palette_action = QAction("Command palette…", self)
        self.palette_action.setShortcut(QKeySequence("Ctrl+K"))
        self.palette_action.setShortcutContext(Qt.ShortcutContext.WidgetShortcut)  # display only; the room's QShortcut fires
        palette = getattr(self.room, "_palette", None)
        self.palette_action.setEnabled(palette is not None)
        if palette is not None:
            self.palette_action.triggered.connect(palette.toggle)
        room_menu.addAction(self.palette_action)
```

The `from PySide6.QtCore import Qt` import is already present (`app.py:25`). This also clears that
file's unused-import lint.

**Step 4:** Run `tests/test_qt_app.py`. If the fixture's `StubRoom` has no `_palette`, give it
`self._palette = SimpleNamespace(toggle=lambda: None)` in the test file.

**Step 5:** `git commit -m "fix(qt): palette menu item opens the palette instead of being greyed out"`

---

## Phase 1 — Shared config (D1)

Target file shape:

```toml
[room]
backend = "direct"
lead = "nemotron-ultra"
without = ["codex"]
with = []
audit = true
approve_plans = false
timeout = 1800

[server]
host = "127.0.0.1"
port = 8765
token = ""          # file is written 0600 because of this

[nicknames]
claude = "Rex"
```

### Task 1.1: `config.load`, `config.save`, `config.save_section` (keep every section)

**Files:** Modify `hexmind/config.py`. Create `tests/test_config.py`.

**Step 1: Failing tests**

```python
"""config.toml: one file, several sections, none of them clobbering the others."""
import os
import stat

from hexmind import config


def test_saving_a_section_keeps_the_others(tmp_path):
    path = str(tmp_path / "config.toml")
    config.save_nicknames({"claude": "Rex"}, path)
    config.save_section("room", {"audit": True, "without": ["codex"], "timeout": 60}, path)
    config.save_nicknames({"claude": "Rex", "agy": "Ada"}, path)

    data = config.load(path)
    assert data["room"] == {"audit": True, "without": ["codex"], "timeout": 60}
    assert data["nicknames"] == {"claude": "Rex", "agy": "Ada"}


def test_the_file_is_private_because_it_can_hold_a_token(tmp_path):
    path = str(tmp_path / "config.toml")
    config.save_section("server", {"token": "s3cret"}, path)
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600


def test_a_corrupt_file_loads_as_empty_instead_of_crashing(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text("[room\nnot toml")
    assert config.load(str(path)) == {}


def test_odd_keys_and_strings_round_trip(tmp_path):
    path = str(tmp_path / "config.toml")
    config.save_nicknames({"weird key": 'quote " and é'}, path)
    assert config.load_nicknames(path) == {"weird key": 'quote " and é'}
```

**Step 2:** Run `python3 -m pytest tests/test_config.py -q`. Expected: FAIL (`load`/`save_section` missing).

**Step 3: Implement.** Replace the body of `config.py` below the imports with:

```python
import logging
import re

logger = logging.getLogger(__name__)

PATH = os.path.expanduser("~/.config/hexmind/config.toml")
_BARE_KEY = re.compile(r"[A-Za-z0-9_-]+")


def load(path: str | None = None) -> dict:
    """The whole file, or {} if it is missing or unreadable (a bad file must not stop the room)."""
    path = path or PATH
    try:
        with open(path, "rb") as f:
            return tomllib.load(f)
    except FileNotFoundError:
        return {}
    except tomllib.TOMLDecodeError as e:
        logger.warning("config: %s is not valid TOML (%s); using defaults", path, e)
        return {}


def save(data: dict, path: str | None = None) -> None:
    """Write every section atomically, mode 0600 (the [server] section can hold a token).

    Values are str/int/bool/list[str]; json.dumps renders each as valid TOML."""
    path = path or PATH
    os.makedirs(os.path.dirname(path), exist_ok=True)
    lines: list[str] = []
    for section, values in data.items():
        if not isinstance(values, dict):
            continue
        lines.append(f"[{section}]")
        for k, v in values.items():
            key = k if _BARE_KEY.fullmatch(k) else json.dumps(k)
            lines.append(f"{key} = {json.dumps(v, ensure_ascii=False)}")
        lines.append("")
    tmp = f"{path}.tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    os.replace(tmp, path)


def save_section(name: str, values: dict, path: str | None = None) -> None:
    data = load(path)
    data[name] = values
    save(data, path)


def load_nicknames(path: str = PATH) -> dict[str, str]:
    return {k: str(v) for k, v in load(path).get("nicknames", {}).items()}


def save_nicknames(nicks: dict[str, str], path: str = PATH) -> None:
    save_section("nicknames", dict(sorted(nicks.items())), path)
```

Keep the module docstring, and update it to say the file now holds `[room]`, `[server]` and
`[nicknames]`. The old `# ponytail: rewrites the whole file` comment goes away, because every
section now survives.

**Step 4:** Run `tests/test_config.py` and `tests/test_nicknames.py` (which patches `__defaults__`,
still compatible). Then the full suite.

**Step 5:** `git commit -m "feat(config): multi-section config.toml with private, atomic writes"`

### Task 1.2: `config.defaults()` gives validated, argparse-ready defaults

**Files:** Modify `hexmind/config.py`. Test: `tests/test_config.py`.

**Step 1: Failing tests**

```python
def test_defaults_map_to_argparse_dests_and_drop_bad_types(tmp_path):
    path = str(tmp_path / "config.toml")
    config.save({"room": {"audit": True, "with": ["qwen"], "timeout": "soon", "lead": "claude"},
                 "server": {"port": 9000, "host": 42}}, path)
    d = config.defaults(path)
    assert d == {"audit": True, "with_": ["qwen"], "lead": "claude", "port": 9000}
```

**Step 2:** Run it. Expected: FAIL.

**Step 3: Implement**

```python
# What each saved setting must look like. Anything else is ignored with a warning, never trusted:
# this file is hand-editable, and a bad value must not turn into a crash or a wrong flag.
ROOM_KEYS: dict[str, type] = {"backend": str, "lead": str, "without": list, "with": list,
                              "audit": bool, "approve_plans": bool, "timeout": int}
SERVER_KEYS: dict[str, type] = {"host": str, "port": int, "token": str}


def _typed(section: str, values: dict, keys: dict[str, type]) -> dict:
    out = {}
    for k, typ in keys.items():
        if k not in values:
            continue
        v = values[k]
        if typ is list:
            ok = isinstance(v, list) and all(isinstance(x, str) for x in v)
        elif typ is int:
            ok = isinstance(v, int) and not isinstance(v, bool)
        else:
            ok = isinstance(v, typ)
        if ok:
            out[k] = v
        else:
            logger.warning("config: ignoring [%s] %s = %r (expected %s)", section, k, v, typ.__name__)
    return out


def defaults(path: str | None = None) -> dict:
    """Saved [room] and [server] settings, keyed by argparse dest (`with` -> `with_`)."""
    data = load(path)
    out = {**_typed("room", data.get("room", {}), ROOM_KEYS),
           **_typed("server", data.get("server", {}), SERVER_KEYS)}
    if "with" in out:
        out["with_"] = out.pop("with")
    return out
```

**Step 4:** Run the tests. **Step 5:** `git commit -m "feat(config): validated argparse defaults from [room] and [server]"`

### Task 1.3: `hexmind` and `--serve` use the saved defaults; flags still win

**Files:**
- Modify `hexmind/__main__.py`. Extract `build_parser()` from `main()`. Switch `--audit` and
  `--approve-plans` to `argparse.BooleanOptionalAction`, so `--no-audit` can turn off a saved `true`.
- Test: `tests/test_cli.py`.

**Step 1: Failing tests**

```python
def test_saved_config_becomes_the_default_and_a_flag_overrides_it():
    from hexmind import config
    from hexmind.__main__ import build_parser

    config.save_section("room", {"audit": True, "lead": "claude", "timeout": 60})
    args = build_parser().parse_args([])
    assert (args.audit, args.lead, args.timeout) == (True, "claude", 60)

    args = build_parser().parse_args(["--no-audit", "--lead", "agy"])
    assert (args.audit, args.lead) == (False, "agy")
```

(`conftest.py` points `config.PATH` at a temp file for the session, so this never touches your real
config. `save_section` resolves `PATH` at call time for exactly this reason.)

**Step 2:** Run it. Expected: FAIL (`build_parser` missing).

**Step 3: Implement**
1. Move every `p.add_argument(...)` in `main()` into `def build_parser() -> argparse.ArgumentParser:`,
   ending with:

   ```python
       from . import config
       p.set_defaults(**config.defaults())
       return p
   ```

2. In `main()`, use `args = build_parser().parse_args()`.
3. Change the two flags to:
   `p.add_argument("--approve-plans", action=argparse.BooleanOptionalAction, default=False, help=...)`
   and the same for `--audit`.
4. `--token` default: `run_server` already falls back to `HEXMIND_TOKEN`. A saved `[server] token`
   now arrives as `args.token`, so there's no extra code.

**Step 4:** Run `tests/test_cli.py`, then the full suite. Then live: `hexmind --help` shows
`--audit, --no-audit`.

**Step 5:** `git commit -m "feat(cli): saved config.toml is the default for hexmind and --serve"`

### Task 1.4: `hexmind-gui` uses the same saved defaults

**Files:** Modify `hexmind/qt/app.py` `build_parser()`. Test: `tests/test_qt_app.py`.

**Step 1: Failing test**

```python
def test_the_gui_reads_the_same_saved_defaults(host):
    from hexmind import config
    config.save_section("room", {"audit": True, "lead": "codex", "without": ["claude"]})
    assert A.main([]) == 0
    assert host.built[-1]["audit"] is True and host.built[-1]["lead"] == "codex"
    assert host.built[-1]["members"] == ["codex"]
```

(The `host` fixture's `available` returns `["claude", "codex"]`.)

**Step 2:** Run it. Expected: FAIL.

**Step 3: Implement.** At the end of `app.build_parser()`:

```python
    from .. import config
    saved = config.defaults()
    # Only the knobs this parser has; --serve's host/port/token mean nothing to a window.
    p.set_defaults(**{k: v for k, v in saved.items() if k in ("lead", "without", "with_", "audit")})
    return p
```

**Step 4:** Run the tests. **Step 5:** `git commit -m "feat(qt): hexmind-gui starts from the saved config"`

---

## Phase 2 — Live Wire and Hand brake

### Task 2.1: Bridge the dropped `status` events (P4)

**Files:** Modify `hexmind/qt/widget.py` (`_Room` signals ~line 118; `_emit` ~line 141). Test: `tests/test_qt.py`.

**Step 1: Failing test**

```python
def test_lead_phases_reach_the_widget(room):
    """P4: the orchestrator reports planning/summarizing, and the bridge dropped them."""
    widget = room(backend=FakeBackend())
    seen = []
    widget._room.statusChanged.connect(lambda agent, state: seen.append((agent, state)))
    widget.input.setText("do it")
    widget.send()
    pump()
    assert ("claude", "planning") in seen, seen
```

**Step 2:** Run it. Expected: FAIL (`statusChanged` missing).

**Step 3: Implement**

```python
    statusChanged = Signal(str, str)  # agent, state — "planning", "summarizing", "idle", …
```

and in `_emit`:

```python
        elif kind == "status":
            self.statusChanged.emit(str(data.get("agent", "")), str(data.get("state", "")))
```

**Step 4:** Run it. If `("claude", "planning")` isn't the exact wording, print `seen` and match the
real state names emitted at `core.py:704,751,806,986`. **Step 5:** Commit.

### Task 2.2: A turn meter: `claude · planning · 0:42`

**Files:** Modify `hexmind/qt/widget.py`. Test: `tests/test_qt.py`.

**Behaviour:**
- `self.status` shows `"{agent} · {state} · {m:ss}"` while busy and `"ready"` when idle.
- A `QElapsedTimer` starts on `turnState(True)`. A 1 s `QTimer` refreshes the label.
- There's no backend change.

**Step 1: Failing test**

```python
def test_the_status_label_names_the_phase_while_busy(room):
    widget = room(backend=FakeBackend())
    widget._on_turn_state(True)
    widget._on_status("claude", "planning")
    assert widget.status.text().startswith("claude · planning · 0:0")
    widget._on_turn_state(False)
    assert widget.status.text() == "ready"
```

**Step 3: Implement** (sketch, complete it to this shape):

```python
    # in __init__, after the room is built:
        self._turn_clock = QElapsedTimer()
        self._phase = ""
        self._tick = QTimer(self, interval=1000, timeout=self._render_status)
        self._room.statusChanged.connect(self._on_status)

    def _on_status(self, agent: str, state: str) -> None:
        self._phase = "" if state == "idle" else f"{self.name_of(agent)} · {state}"
        self._render_status()

    def _render_status(self) -> None:
        if not self._turn_clock.isValid():
            self.status.setText("ready")
            return
        s = self._turn_clock.elapsed() // 1000
        self.status.setText(f"{self._phase or 'working'} · {s // 60}:{s % 60:02d}")
```

- In `_on_turn_state(busy)`: when busy, call `self._turn_clock.start()` and `self._tick.start()`.
  When idle, call `self._turn_clock.invalidate()`, `self._tick.stop()` and set `self._phase = ""`.
  Then call `self._render_status()`.
- `name_of` returns the nickname if one is set, else the id: `self._room.orch.name(agent)`
  (see `core.py:657`). Add it as a one-line method.
- Import `QElapsedTimer` and `QTimer` from `PySide6.QtCore`.

**Step 5:** `git commit -m "feat(qt): live turn meter shows the lead's phase and elapsed time"`

### Task 2.3: The backend kills the agent's process group when a call is cancelled

**Files:** Modify `hexmind/backends.py` `DirectBackend.run` (the `try/except asyncio.TimeoutError` ~line 186). Test: `tests/test_backends.py`.

**Step 1: Failing test** (reuses `FakeProcess` from the timeout test at `tests/test_backends.py:97`)

```python
def test_cancel_kills_and_waits_for_child(monkeypatch, tmp_path):
    """Only the timeout path killed the process group, so a cancelled turn orphaned the agent CLI."""
    proc = FakeProcess((), timeout=True)

    async def create(*args, **kwargs):
        return proc

    monkeypatch.setattr(asyncio, "create_subprocess_exec", create)
    monkeypatch.setattr("hexmind.backends._signal_group", lambda pid, sig: setattr(proc, "killed", True))

    async def go():
        task = asyncio.create_task(DirectBackend(str(tmp_path), timeout=60).run("claude", "p"))
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(go())
    assert proc.killed and proc.waited
```

**Step 2:** Run it. Expected: FAIL (`proc.killed` is falsy).

**Step 3: Implement.** Add a second `except` next to the timeout one:

```python
            except asyncio.CancelledError:
                await _terminate_group(proc)
                await asyncio.gather(stdin_task, stdout_task, stderr_task, return_exceptions=True)
                raise
```

**Step 4:** Run `tests/test_backends.py`. **Step 5:** `git commit -m "fix(backends): kill the agent's process group when a call is cancelled"`

### Task 2.4: Stop button: cancel the whole turn from the GUI

**Files:**
- Modify `hexmind/qt/widget.py`:
  - `_Room.submit` keeps the future, and a new `_Room.cancel()` method uses it.
  - `_handle` reports the stop.
  - The Send button becomes Stop while busy.
- Test: `tests/test_qt.py`.

**Step 1: Failing test**

```python
class SlowBackend(FakeBackend):
    async def run(self, agent, prompt, cwd=None, schema=None):
        if "Answer ONLY with a JSON object" in prompt:
            return self.plan
        await asyncio.sleep(30)
        return "too late"


def test_stop_cancels_a_running_turn_and_the_room_is_usable_again(room):
    widget = room(backend=SlowBackend())
    widget.input.setText("do it")
    widget.send()
    pump(500)
    assert widget.sendButton.text() == "Stop"

    widget.sendButton.click()
    pump(1500)

    assert widget.status.text() == "ready"
    assert "Turn stopped" in widget.transcript.toPlainText()
    assert widget.input.isEnabled()
    assert all(t.status != "running" for t in widget.snapshot()["tasks"].values())
```

**Step 2:** Run it. Expected: FAIL.

**Step 3: Implement**
1. `_Room.__init__`: add `self._turn_future = None`.
2. `_Room.submit`: `self._turn_future = asyncio.run_coroutine_threadsafe(self._handle(text), self._loop)`.
3. Add:

   ```python
       def cancel(self) -> None:
           """Stop the running turn. The orchestrator's `finally` (core.py:1066) marks stranded tasks
           failed and fixes the busy set; the backend kills each agent's process group (Task 2.3)."""
           future = self._turn_future
           if future is not None and not future.done():
               future.cancel()
   ```

4. `_handle`: add `except asyncio.CancelledError: self.message.emit("hexmind", "**Turn stopped.**")`
   before the existing `except Exception`. Don't re-raise, so the existing `finally` still runs.
5. Widget:
   - In `_on_turn_state(busy)`: when busy, set the button text to `"Stop"` and keep it enabled;
     when idle, set it back to `"Send"`. Keep disabling the input while busy.
   - The button's click handler calls `self._room.cancel()` when the text is `"Stop"`, otherwise
     `self.send()`.
   - Bind `Esc` to the same handler while busy (`QShortcut(QKeySequence("Esc"), self)`).

**Step 4:** Run `tests/test_qt.py`, then the full suite. Live check:
- `hexmind-gui`, pick a lead, ask for something slow, click Stop.
- `pgrep -f "claude -p"` finds nothing afterwards.

**Step 5:** `git commit -m "feat(qt): stop a running turn from the GUI"`

### Task 2.5: Stop over the server too (parity)

**Files:**
- Modify `hexmind/server.py`: add `POST /api/cancel`, behind the same auth as other `/api/`
  routes, which cancels the in-flight turn's task.
- Test: `tests/test_server.py`.

Mirror Task 2.4: keep the task handle where the server starts a turn, and cancel it. Tests:
- 401 without a token when one is set;
- 200 plus `{"cancelled": true}` while busy;
- `{"cancelled": false}` when idle.

Commit: `feat(server): POST /api/cancel stops the running turn`.

---

## Phase 3 — Bench Rail (task spec)

**Outcome:** `HexmindWindow` gets a left navigation rail with Room, Direct, Models, Agents, Ledger
and Settings (Ctrl+1…6) over a `QStackedWidget`. `HexmindWidget` itself is unchanged.

**Tasks:**
1. **`qt/rail.py`, `NavRail(QWidget)`:**
   - an item list and a `currentChanged(int)` signal;
   - a status dot per item via `set_dot(index, hue | None)`;
   - accessible names on every item;
   - violet active bar, reusing `theme.VIOLET`.

   Tests: clicking or Ctrl+N changes the index, and dots render.
2. **Window assembly:**
   - `app.HexmindWindow` holds `rail + stack`. The Room page is the existing `HexmindWidget`.
   - The other pages are placeholder `QLabel`s until their phase lands. That's an explicit stub:
     each says "coming in Phase N", never fake data.
   - Existing `test_qt_app.py` tests keep passing.
3. **Move Stats out of the room's tabs** into the Ledger page, reusing `qt/stats.py` as is.
   Keep the room's tab for embedders? **No.** Aether gets `StatsPanel` directly from
   `hexmind.qt`. Update `docs/AETHER-INTERFACE.md` if the exported names change.
4. **Remember the last page** in `QSettings("hexmind", "window")`.

**Done when:**
- the rail switches pages by mouse and keyboard;
- `from hexmind.qt import HexmindWidget` still gives the plain room;
- the full suite is green.

---

## Phase 4 — Settings page (task spec)

**Outcome:** a `SettingsPage(QWidget)` in `qt/settings.py` edits `[room]`, `[server]`,
`[nicknames]` and lists chains, all through `config.py` (Phase 1). No TOML is written from Qt.

**Tasks:**
1. **Room section:**
   - backend radio (direct or hcom);
   - lead combo with the placeholder from Task 0.1;
   - members checklist, with opt-in members marked;
   - audit and approve-plans switches;
   - timeout spinbox with a humanised label.
2. **Where each value came from.** A suffix on each field: `default`, `config.toml`, or
   `this session (flag)`. For that, `config.defaults()` gains a sibling `config.sources()`
   (TDD in `test_config.py`).
3. **Apply now vs next start.**
   - Audit, approve-plans and lead apply to the live room. Go through `/audit on|off`,
     `/drafts on|off` and `change_lead`, which are the command paths, not direct orchestrator writes.
   - Backend and server are marked "applies next start".
   - "Save as default" calls `config.save_section`.
4. **Server section:**
   - host, port, and a masked token with Show, Copy and Generate (`secrets.token_urlsafe(32)`);
   - a warning when the host isn't loopback and there's no token. This mirrors the server's refusal
     from `49e35ca`.
5. **Nicknames table**, via `config.save_nicknames` plus `/nick` for the live room.
6. **Chains list:**
   - bundled and user chains, with a user-override marker;
   - "Duplicate to my chains" copies into `~/.config/hexmind/chains/`;
   - "Open in editor" uses `QDesktopServices`.
   - No chain editor yet; that's Phase 9.
7. **"Equivalent command" footer:** the exact `hexmind …` line for the current form, with a Copy
   button. Put a pure function `config.to_argv(settings) -> list[str]`, TDD'd, in core.

**Done when:**
- settings saved in the GUI change what `hexmind --once` and `--serve` do on the next run;
- a test covers the round trip (GUI saves, then `build_parser().parse_args([])` sees it).

---

## Phase 5 — Agent health and First Light (task spec, D3)

**Outcome:** an `AgentCheck(QWidget)` grid of cards (claude, agy, codex, opencode, copilot, kimi,
ollama), each showing installed, signed in, version and quota. It doubles as the first-run screen.

**Tasks:**
1. **Core: `hexmind/health.py`** (new, no Qt). `probe(cli) -> Health`, where
   `Health(installed, path, version, signed_in: bool | None, quota_note: str | None, fix: list[str] | None)`.
   - Version comes from `<cli> --version`, with a timeout.
   - `signed_in` is `None` ("unknown") unless the CLI offers a cheap, documented check. **Don't
     guess.** Verify each CLI's real command live before encoding it, and record the command
     used in a comment.
   - Quota comes from recent `QUOTA_RE` hits recorded by the orchestrator. Add a small
     `core.recent_quota_hits()` ring buffer.
   - TDD with a fake `shutil.which` and `subprocess.run`.
2. **Run probes off the GUI thread** (a `QThreadPool` worker), when the screen opens and on
   Recheck. Never run them at construction (`widget.py:263-266` explains why).
3. **Safe fixes (D3):**
   - `fix` is an argv such as `["claude", "/login"]` or `["opencode", "auth", "login"]`. Verify
     each command live before encoding it.
   - The "Fix…" button opens it in a visible terminal. Take the terminal from `$TERMINAL`, falling
     back to `kitty`, then `xterm`: `QProcess.startDetached(term, ["-e", *fix])`.
   - The GUI never reads or stores credentials.
4. **Warnings elsewhere:** the rail dot turns amber when any card is signed out or over quota, and
   the Team table gets a `⚠` next to affected members.
5. **First Light:**
   - Replace the "No team available" dead-end dialog (`app.py:202-212`) with the AgentCheck page
     plus install hints and Recheck.
   - When at least one agent is ready, show the 3-step strip: pick a lead (cards), audit on/off,
     starter prompts.
   - Store `first_run_done` in `QSettings`.

**Done when:**
- with every CLI missing, the app opens on First Light instead of exiting;
- a signed-out CLI shows amber, and its Fix button opens a terminal running the verified login
  command.

---

## Phase 6 — Model manager (Calibration Rack) and single-model call (task spec, D4)

**Outcome:** a `ModelRack(QWidget)` master-detail editor over the registry, with override-aware
saves to `~/.config/hexmind/models.toml` and a live Test strip.

**Tasks:**
1. **Core: `models.save_override(name, fields)` and `models.reset_override(name, field=None)`.**
   - Write only changed keys to `models.USER`, using `config.save`'s writer. Factor it into a
     shared `hexmind/tomlw.py` only if a second caller actually needs it.
   - Validate with the registry's existing checks (tier, verify, env), so a bad edit fails in the
     form, not at the next launch. The `opencode-ultra` override crash in `e7d9ba3` is the failure
     mode to test against.
2. **Core: `backends.run_one(agent, prompt, cwd, timeout) -> (text, elapsed_s)`.** A single-model
   call with no orchestrator. It's shared by the Test button (here) and Direct Line (Phase 7).
   TDD with the `FakeProcess` pattern.
3. **List:**
   - status glyph plus word (on, off, opt-in, unavailable), label, id, tier and text-only chips, and
     a weight bar;
   - filters and search.
4. **Detail form**, grouped Identity / Routing / Domains / Mechanics:
   - a `•` marker on overridden fields, plus "Reset field" and "Reset model";
   - a diff preview of the TOML before saving;
   - a **live roster-line preview** from `Model.description`.
5. **`variant` guard:** inline help ("declare only after `opencode run -m id#v` works"), and the
   field stays amber until a Test with that variant passes. This is the `#high` lesson from
   `08a3fc0`.
6. **Test strip:**
   - a prompt (default "Reply with the word OK."), Test, and "Test all enabled", run one after
     another on a worker;
   - a verdict of PASS, FAIL or SLOW, with latency and the raw reply.
7. **Scan import:** list `/scan` finds that aren't in the registry (`models.align_entries`).
   Imports land with `opt_in = true`.
8. **Enable/disable** with an undo toast. You can't disable the current lead.

**Done when:**
- an edit round-trips through the file and a restart;
- a bad edit is refused in the form;
- Test runs the exact argv the room would use.

---

## Phase 7 — Direct Line: 1:1 chat (task spec, D2)

**Outcome:** a `DirectLine(QWidget)` with tabbed per-model conversations, persistent history and
**Send to room**.

**Tasks:**
1. **Core: `hexmind/direct.py`** (no Qt):
   - `Conversation(agent, messages)`;
   - `prompt_for(conv, new_text, budget_chars)` replays history newest-first within a budget
     (TDD the clipping);
   - `save`/`load` to `~/.local/share/hexmind/direct/<agent>.jsonl`.
2. **Send:**
   - calls `backends.run_one` (Phase 6) on a worker;
   - Stop cancels, reusing Task 2.3's process-group kill;
   - a header strip always says "Direct · claude: no plan, no audit, no team".
3. **Send to room:**
   - on a message: "Send to room" posts it into the Room transcript as a `hexmind` note quoting the
     model;
   - "Promote conversation" puts a summary-sized excerpt into the Room input for the user to send.
     It doesn't auto-send.
4. **Entry points:** the rail, "Chat with X" in the right-click menu of Team and Models rows, and
   palette `chat: <model>`.
5. **"Ask another":** re-send the last prompt to a second model and show the two answers side by
   side.

**Done when:** a conversation survives a restart, and a sent-to-room message appears in the room
transcript for the lead's next turn.

---

## Phase 8 — Polish (task spec)

Each item is independent, and each gets a failing test first:
1. **Readout transcript (P6, P9):**
   - `QTextBrowser` with rendered markdown, nickname speaker lines and timestamps;
   - a 2000-block cap;
   - file paths become links that emit `openFileRequested`.
2. **Detail drawer (P7, P15):** a selected task is never overwritten by incoming messages. The
   transcript gets most of the column.
3. **Find bar (P8):** Ctrl+F with next/previous and an `n/m` count.
4. **Host-safe colour (P12):**
   - panels take their text colour from `palette()` instead of fixed `INK*` values;
   - a test renders each panel on a light `QPalette` and asserts a contrast ratio of at least 4.5:1.
5. **Palette 2.0 (P10):** slash commands with `relay.HELP` text, navigation targets and `chat:`;
   `set_commands` is called on `teamChanged`.
6. **Graph (P13):** arrowheads, labels above nodes, status glyphs, fit to view, click-to-select, and
   a live glow via `theme.is_live`.
7. **Stats (P14):** every category label shown, and `3/3` at the end of each bar.
8. **Accessibility:** focus rings on every control, glyph plus word plus colour everywhere, `pt`
   fonts, reduced motion, and live announcements for turn start, end and approval.

---

## Phase 9 — Flagship backlog (from forge; plan each with `writing-plans` when picked)

| Item | Size | One line |
|---|---|---|
| Live output streaming (forge "Live tap", the rest) | M | backend `on_event` callback → `chunk` events → a per-task live pane. agy and kimi already emit stream-json (`backends.py:28-37`) |
| Come-back pings | S | tray icon plus `notify.py` (currently has no caller) on turn end, escalation, a waiting plan and quota handoff, through an `attentionNeeded` signal |
| Plan review card, then Draft plan workbench | S→M | Approve/Discard buttons first, then `Orchestrator.revise_pending(edits)` for editing the plan in the graph |
| Stop one task and reassign | S | `Orchestrator.cancel_task(id, reassign_to)`, reusing the quota-handoff path (`core.py:1135`) |
| Relay Runs desk | M | a run grid, stage reports, a diff per worktree, reaping badges, Adopt/Reap, and a dry-run preview |
| Audit courtroom | M | per-round `audit` events plus a thread view with `difflib` diffs, and override records outside first-attempt stats |
| The room is a protocol | L | a `RoomSource` interface: local, remote (`--serve` over QtWebSockets) and replay (JSONL tee on `emit`) |
| Mission control | L | tabs of rooms plus `hexmind/fleet.py`, which shares CLI occupancy and quota across rooms |

---

## Risks and open questions

- **Signed-in probes (Phase 5).** Not every CLI has a cheap "am I logged in" check. Where it
  doesn't, show `unknown`. Never guess.
- **The TUI** shares `core.py` and `backends.py`. The Phase 2 and 6 core changes are additive, so
  test the TUI suite (`tests/test_tui.py`, `test_mobile_tui.py`) on every phase even though
  `tui.py` isn't touched.
- **Aether.** The Phase 3 rail lives in the window only. Run the smoke line in
  `docs/AETHER-INTERFACE.md` at the end of Phases 3 and 8.
- **Live checks.** Anything that changes an agent argv (Phases 5, 6, 7) needs one real run before
  it's marked done.

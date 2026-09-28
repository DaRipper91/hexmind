# Aether Integration — the interface this repo is being asked to ship

Aether (`~/Projects/Aether`) is a PySide6 host whose three tabs are **Room** (Hexmind),
**Deck** (agentdeck) and Workspace. Deck and Workspace are shipped. **Room is the only
unchecked item on Aether's roadmap**, and it is blocked on one thing from this repo.

## What Aether is waiting on

A Qt front-end module named `hexmind.qt` exposing a widget called `HexmindWidget`:

```
from hexmind.qt import HexmindWidget
```

That import today raises `ModuleNotFoundError` — Hexmind has no `qt` subpackage at all
(its front-end is the Textual TUI in `tui.py`).

## The seam on the Aether side (do not change this)

`aether/ui/views/room.py`:

- `_load_hexmind_widget()` does `from hexmind.qt import HexmindWidget` and returns the class
  (`room.py:15-20`). Import error → placeholder card.
- `RoomView.__init__` instantiates it as `widget_cls(self)` (`room.py:33`).

So the contract is exactly:

1. `hexmind/qt/__init__.py` exports `HexmindWidget`.
2. `HexmindWidget` is a `QWidget` subclass constructible with
   `HexmindWidget(parent: QWidget | None = None)`.
3. Nothing else. The moment the import succeeds, Room stops being a placeholder.

## Hard rules

- **One-way embedding.** Aether imports Hexmind; Hexmind never imports Aether. The widget
  must build and run standalone (like agentdeck's `DeckWidget`); Aether's embedding is
  optional plumbing `RoomView` does.
- **One brain.** The widget is a *presentation layer* over the existing `hexmind` backend
  (`core.py`, `relay.py`, `server.py`), not a second implementation of the team logic. It
  can talk to the TUI's backend through the same classes the TUI uses. Do not fork the
  room state into the Qt layer (this repo's own report says it twice: one roster, one lead).
- **Optional, non-blocking signal surface.** agentdeck's model (see `deck.py:35-36`): the
  widget may expose one or two Qt signals (deck exposes `openRequested(str)`); Aether's
  view will connect them to its `SignalBus` — `open_file_in_editor` and `dock_requested`
  are the two deck uses. Absent signals, the embed still works; they only matter if the
  Hexmind UI wants to open/dock workspace files.

## Packaging changes this repo must make

Hexmind's only dependency today is `textual>=0.80`
(`pyproject.toml` → `dependencies`). PySide6 is not present.

- Add a `qt` extra, keep the base lean:

  ```toml
  [project.optional-dependencies]
  qt = ["PySide6>=6.5"]
  ```

  Pulling PySide6 into base `dependencies` would force it on every Textual TUI user; the
  QT work is strictly opt-in. (Deck's own `agentdeck[qt]` works the same way.)
- **Wheel packaging is explicit in this repo**: `[tool.setuptools] packages = ["hexmind"]`.
  A new `hexmind/qt/` subpackage will silently not ship unless it is added there. This is
  the kind of gap that passes everything locally and fails on a fresh install — verify
  with a clean wheel install, not the editable `.venv`.

Once the `qt` extra exists, the Aether side flips `room = ["hexmind"]`
(`Aether/pyproject.toml:16`) to `room = ["hexmind[qt]"]` and its README follows. That is
Aether's problem, not this repo's — included here so the timing is understood.

## Definition of done for this repo — **all three met**

1. **Offscreen smoke passes.** `HexmindWidget()` constructs, and `HexmindWidget(parent)` works the
   way `RoomView` calls it (`widget_cls(self)`).
2. **The clean wheel includes `hexmind/qt/`.** Verified by building a wheel and listing it:
   `hexmind/qt/__init__.py` and `hexmind/qt/widget.py` are both in the archive, alongside
   `models.toml` and the four chain files.
3. **`tests/test_qt.py` — 13 tests**, offscreen, mirroring Aether's own PySide6 test style, and
   skipped wholesale when PySide6 is absent.

## What shipped

`hexmind/qt/widget.py`, a `HexmindWidget(QWidget)` with:

| surface | notes |
| :--- | :--- |
| transcript | read-only, 2000-block cap; the TUI's chat, without a TUI |
| input + Send | Enter sends; disabled while a turn is in flight, so the room cannot be double-driven |
| task board | the TUI's columns: id, agent, status, audit, title |
| roster | model, state (lead / awake / busy + task ids), domains |
| lead combo | **is** the picker — see below |
| peer-audit toggle | the same `audit` flag the TUI sets |
| `openFileRequested(str)` | the one optional signal, matching `DeckWidget.openRequested` |

**One brain.** The orchestrator, the backends, the registry and `relay.command` are the ones the TUI
and `--once` use, and a turn goes through `Orchestrator.handle` exactly as the TUI drives it. No
team rule is re-implemented; the roster shown is a read of the orchestrator, not a copy.

**Threading.** A turn takes minutes, so `_Room` is a QThread carrying its own asyncio loop and
holding the orchestrator. The widget only ever sends text and lead changes, and everything it
learns back arrives as a Qt signal, which Qt delivers on the GUI thread. `closeEvent` always stops
the thread: a QThread destroyed while running aborts the process, and the tab closing, the app
quitting and the end of every test all go through it.

**The lead combo is the picker, not a modal.** The TUI blocks on `LeadPicker`; a combo box is the
Qt-native equivalent and needs no modal, so sending with no lead set says so and sends nothing,
rather than reaching a backend with no model to ask. Same rule, different shape.

**Cost.** PySide6 is ~240 MB of wheels. It stays behind the `qt` extra — see the packaging section
above — and `tests/test_qt.py` uses `importorskip`, so a TUI-only checkout still runs a green
suite without it.

## Aether's remaining step

Flip `room = ["hexmind"]` to `room = ["hexmind[qt]"]` in `Aether/pyproject.toml:16` and update
Aether's README. `RoomView` itself needs no change: the moment the import succeeds, the placeholder
is gone. The widget defaults to whatever is installed and runnable in the current directory, which
is the same default `--once` and the TUI use.

## Notes

- This is not in `docs/BUILD-PATH.md`; it is a genuinely new leading workstream, not a
  row in that map. Add a row when it gets scheduled.
- Hexmind is currently a TUI-first project with no Qt anywhere; nothing existing needs to
  change to accommodate this except the packaging lines above.
- The TUI keeps working untouched — this is purely additive.
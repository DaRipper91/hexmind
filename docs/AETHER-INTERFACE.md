# Aether Integration — Shipped Interface Contract

[Aether](https://github.com/DaRipper91/Aether) is a PySide6 host whose three tabs are **Room**
(Hexmind), **Deck** (agentdeck) and **Workspace**. All three are shipped and embedding. The
`hexmind.qt` module is implemented, tested (**242 Qt tests pass** across `tests/test_qt*.py`),
and shipped in `hexmind`.

## The Shipped Interface

The Qt front-end module [`hexmind.qt`](../hexmind/qt/__init__.py) exports [`HexmindWidget`](../hexmind/qt/widget.py):

```python
from hexmind.qt import HexmindWidget
```

The import succeeds cleanly when Hexmind is installed with its `qt` extra (`pip install -e ".[qt]"`).

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

## Packaging — shipped

Both of the packaging gaps this doc originally warned about are closed.

- The `qt` extra exists and keeps the base lean. Base `dependencies` is still just
  `textual>=0.80`; the extra is
  `qt = ["PySide6>=6.5", "pyqtgraph>=0.13", "numpy>=1.26", "qtawesome>=1.3", "qdarkstyle>=3.2"]`.
  PySide6 is a ~100 MB download that every Textual TUI user would otherwise be forced to take.
- `[tool.setuptools] packages = ["hexmind", "hexmind.qt"]` — the subpackage is listed explicitly,
  so a new one has to be a deliberate edit rather than a silent omission.
- Aether's `room` extra already reads `room = ["hexmind[qt]"]` (`Aether/pyproject.toml:16`).

**Still verify packaging with a clean wheel install, not the editable `.venv`.** The silent-omission
failure mode this doc describes has already bitten once in this repo.

## Definition of done for this repo — **all three met**

1. **Offscreen smoke passes** — run verbatim, in a subprocess:
   ```
   QT_QPA_PLATFORM=offscreen ./.venv/bin/python -c "from hexmind.qt import HexmindWidget; w = HexmindWidget(); print(w.__class__.__name__)"
   # -> HexmindWidget
   ```
   `HexmindWidget(parent)` also works the way `RoomView` calls it (`widget_cls(self)`).
2. **The clean wheel includes `hexmind/qt/`.** Verified by building a wheel and listing it:
   `hexmind/qt/__init__.py` and `hexmind/qt/widget.py` are both in the archive, alongside
   `models.toml` and the five chain files.
3. **The Qt suite is green** — 242 tests across the eleven `tests/test_qt*.py` modules, offscreen,
   skipped wholesale when PySide6 is absent. `tests/test_qt.py` alone is 29 of them.

   Two things the smoke line needs cannot be true in-process — this suite already owns a
   `QApplication` and always closes its widgets — so it runs as a subprocess test. It failed twice
   before it passed, both times by *aborting* rather than raising, which is Qt's answer to both and
   is undiagnosable from a traceback: no `QApplication` existed, and then a `QThread` was destroyed
   while running when the interpreter ended without a `closeEvent`. The widget now creates an
   application if there is none (keeping a reference, or it would be collected out from under Qt)
   and stops its live rooms from an `atexit` hook.

## What shipped

`hexmind/qt/widget.py`, a [`HexmindWidget(QWidget)`](../hexmind/qt/widget.py) with:

| surface | notes |
| :--- | :--- |
| transcript | read-only, 2000-block cap; the TUI's chat, rendered natively in Qt |
| input + Send | Enter sends; disabled while a turn is in flight, so the room cannot be double-driven |
| task board | the TUI's columns: id, agent, status, audit, title |
| roster | model, state (lead / awake / busy + task ids), domains |
| lead combo | **is** the picker — blocks turn execution if no leader selected |
| peer-audit toggle | the same `audit` flag the TUI sets |
| `openFileRequested(str)` | emitted when a file path is double-clicked in a task title |
| `taskChanged(dict)` | emitted on task state changes (pending, running, auditing, done, failed) |
| `teamChanged(list)` | emitted when the roster changes (sleep/wake/add/remove) |
| `turnState(str)` | emitted on turn transitions (`idle`, `planning`, `executing`, `auditing`, `synthesizing`) |

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

- Tracked as **P10** in [`docs/plans/BUILD-PATH.md`](plans/BUILD-PATH.md).
- Hexmind also ships a standalone desktop window ([`HexmindWindow`](../hexmind/qt/app.py) via `hexmind-gui`).
- The TUI and server keep working untouched — Qt is purely additive.
- The Flagship GUI Roadmap (Phases 0–9) extends this foundation with interactive DAG graph views, command palette, and timeline drawers while preserving the one-way embedding contract.
"""Embeddable Qt front-end: `from hexmind.qt import HexmindWidget` (needs the qt extra, PySide6).

    from hexmind.qt import HexmindWidget
    room = HexmindWidget()
    room.openFileRequested.connect(my_editor.open)   # double-click a path in a task title
    stack.addWidget(room)

Same brain as the Textual TUI and `--once`: the orchestrator, the backends and `relay.command` are
used as they are, and no team rule is re-implemented here. What this module owns is presentation —
the transcript, the task board, the roster, and getting a turn onto a worker thread so the GUI does
not freeze while a model thinks.

Aether (`~/Projects/Aether`) embeds this in its Room tab. The import is one-way: Hexmind never
imports Aether, and this widget runs standalone.
"""
from importlib import import_module

from .widget import HexmindWidget

# Each panel is guarded separately rather than in one try/except. They are presentation only, but they
# fail for different reasons -- graph and timeline need nothing beyond PySide6, stats optionally
# wants pyqtgraph -- so one ImportError should not blank out the others' names.
__all__ = ["HexmindWidget"]

for _module, _names in (
    (".graph", ("GraphPanel", "TaskGraphView")),
    (".timeline", ("TimelinePanel",)),
    (".stats", ("StatsPanel",)),
):
    try:
        globals().update({_name: getattr(import_module(_module, __name__), _name) for _name in _names})
        __all__.extend(_names)
    except Exception:  # pragma: no cover - panels are presentation only
        pass
del _module, _names


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
from .widget import HexmindWidget

__all__ = ["HexmindWidget"]

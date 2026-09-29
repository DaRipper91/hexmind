"""Live turn output for the Room workspace."""
from __future__ import annotations

from PySide6.QtWidgets import QPlainTextEdit


class LivePane(QPlainTextEdit):
    """Read-only line feed for backend output and orchestrator lifecycle events."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setReadOnly(True)
        self.setAccessibleName("Live Tap")
        self.setToolTip("Turn lifecycle and response events as they arrive.")
        self.setMaximumBlockCount(2000)

    def append_event(self, agent: str, line: str) -> None:
        if line:
            self.appendPlainText(f"[{agent or 'team'}] {line}")
            self.verticalScrollBar().setValue(self.verticalScrollBar().maximum())

    def append_message(self, sender: str, text: str) -> None:
        if text:
            self.appendPlainText(f"{sender or 'hexmind'}: {text}")
            self.verticalScrollBar().setValue(self.verticalScrollBar().maximum())


__all__ = ["LivePane"]

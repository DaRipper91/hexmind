"""Direct one-to-one model conversations for the Direct Line workspace."""
from __future__ import annotations

import asyncio
import os
from collections.abc import Callable

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from ..backends import DirectBackend
from ..core import REGISTRY

ChatRunner = Callable[[str, str], str]


class ChatThread(QThread):
    succeeded = Signal(str, str)
    failed = Signal(str)

    def __init__(
        self,
        runner: ChatRunner,
        primary: str,
        comparison: str,
        prompt: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._runner = runner
        self._primary = primary
        self._comparison = comparison
        self._prompt = prompt

    def run(self) -> None:
        try:
            primary = self._runner(self._primary, self._prompt)
            comparison = self._runner(self._comparison, self._prompt) if self._comparison else ""
            self.succeeded.emit(primary, comparison)
        except Exception as exc:  # noqa: BLE001 - direct model failures belong in the transcript
            self.failed.emit(str(exc))


def _default_chat(model: str, prompt: str) -> str:
    backend = DirectBackend(os.getcwd(), timeout=1800)
    return asyncio.run(backend.run(model, prompt))


class DirectLine(QWidget):
    """A direct model chat that never routes through the orchestrator."""

    def __init__(
        self,
        parent: QWidget | None = None,
        chat_runner: ChatRunner | None = None,
    ) -> None:
        super().__init__(parent)
        self.setAccessibleName("Direct Line workspace")
        self._chat_runner = chat_runner or _default_chat
        self._chat_thread: ChatThread | None = None

        self.primary_model = QComboBox(self)
        self.primary_model.setAccessibleName("Primary direct model")
        self.primary_model.addItems(REGISTRY.by_weight())
        self.comparison_model = QComboBox(self)
        self.comparison_model.setAccessibleName("Comparison direct model")
        self.comparison_model.addItem("None")
        self.comparison_model.addItems(REGISTRY.by_weight())

        model_row = QHBoxLayout()
        model_row.addWidget(QLabel("Ask", self))
        model_row.addWidget(self.primary_model)
        model_row.addWidget(QLabel("Ask another", self))
        model_row.addWidget(self.comparison_model)

        self.transcript = QTextBrowser(self)
        self.transcript.setAccessibleName("Direct conversation")
        self.prompt = QLineEdit(self)
        self.prompt.setAccessibleName("Direct prompt")
        self.prompt.setPlaceholderText("Ask one model directly…")
        self.prompt.returnPressed.connect(self.ask)
        self.ask_button = QPushButton("Ask", self)
        self.ask_button.setAccessibleName("Ask direct model")
        self.ask_button.clicked.connect(self.ask)
        input_row = QHBoxLayout()
        input_row.addWidget(self.prompt, 1)
        input_row.addWidget(self.ask_button)

        self.primary_output = QTextBrowser(self)
        self.primary_output.setAccessibleName("Primary model response")
        self.comparison_output = QTextBrowser(self)
        self.comparison_output.setAccessibleName("Comparison model response")
        self.status = QLabel("", self)
        self.status.setAccessibleName("Direct line status")

        outputs = QHBoxLayout()
        primary_box = QVBoxLayout()
        primary_box.addWidget(QLabel("Primary response", self))
        primary_box.addWidget(self.primary_output)
        comparison_box = QVBoxLayout()
        comparison_box.addWidget(QLabel("Comparison response", self))
        comparison_box.addWidget(self.comparison_output)
        outputs.addLayout(primary_box)
        outputs.addLayout(comparison_box)

        layout = QVBoxLayout(self)
        layout.addLayout(model_row)
        layout.addWidget(self.transcript, 1)
        layout.addLayout(outputs, 1)
        layout.addWidget(self.status)
        layout.addLayout(input_row)

    def ask(self) -> None:
        prompt = self.prompt.text().strip()
        if not prompt:
            self.status.setText("Enter a prompt first.")
            return
        if self._chat_thread is not None:
            return
        primary = self.primary_model.currentText()
        comparison = self.comparison_model.currentText()
        comparison = "" if comparison == "None" or comparison == primary else comparison
        self.prompt.clear()
        self.transcript.append(f"<b>You</b><br>{prompt}")
        self.status.setText(f"Waiting for {primary}…")
        self.ask_button.setEnabled(False)
        self.primary_output.clear()
        self.comparison_output.clear()
        self._chat_thread = ChatThread(self._chat_runner, primary, comparison, prompt, self)
        self._chat_thread.succeeded.connect(self._show_results)
        self._chat_thread.failed.connect(self._show_error)
        self._chat_thread.finished.connect(self._chat_finished)
        self._chat_thread.start()

    def _show_results(self, primary: str, comparison: str) -> None:
        self.primary_output.setPlainText(primary)
        self.comparison_output.setPlainText(comparison or "Comparison disabled.")
        self.transcript.append(f"<b>{self.primary_model.currentText()}</b><br>{primary}")
        if comparison:
            self.transcript.append(f"<b>{self.comparison_model.currentText()}</b><br>{comparison}")
        self.status.setText("Response complete.")

    def _show_error(self, message: str) -> None:
        self.status.setText(f"Direct request failed: {message}")

    def _chat_finished(self) -> None:
        if self._chat_thread is not None:
            self._chat_thread.deleteLater()
            self._chat_thread = None
        self.ask_button.setEnabled(True)


__all__ = ["ChatThread", "DirectLine"]

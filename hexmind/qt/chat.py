"""Direct one-to-one model conversations for the Direct Line workspace."""
from __future__ import annotations

import asyncio
import html
import inspect
import logging
import os
from collections.abc import Awaitable, Callable

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

logger = logging.getLogger(__name__)

# A runner may be sync (tests) or async (the real backend). Only an async one can be cancelled.
ChatRunner = Callable[[str, str], "str | Awaitable[str]"]


class RunnerThread(QThread):
    """Runs a model call on its own event loop so the window can cancel it on close.

    A QThread destroyed while running aborts the process, and the default runners block for minutes,
    so a plain wait() would hang the quit instead. Cancelling the task takes DirectBackend's
    CancelledError path, which also kills the agent CLI's process group."""

    def __init__(self, runner: Callable, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._runner = runner
        self._loop: asyncio.AbstractEventLoop | None = None
        self._task: asyncio.Task | None = None
        self._stopping = False

    def _call(self, model: str, prompt: str) -> str:
        if self._stopping:
            raise asyncio.CancelledError
        if not inspect.iscoroutinefunction(self._runner):
            return self._runner(model, prompt)
        loop = self._loop = asyncio.new_event_loop()
        try:
            self._task = loop.create_task(self._runner(model, prompt))
            return loop.run_until_complete(self._task)
        finally:
            self._task = self._loop = None
            loop.close()

    def shutdown(self, timeout_ms: int = 5000) -> bool:
        """Cancel the call in flight and wait for the thread. True if it has finished."""
        self._stopping = True
        loop, task = self._loop, self._task
        if loop is not None and task is not None:
            try:
                loop.call_soon_threadsafe(task.cancel)
            except RuntimeError:  # the call finished and closed its loop meanwhile
                pass
        if self.wait(timeout_ms):
            return True
        logger.warning("%s did not stop within %d ms", type(self).__name__, timeout_ms)
        return False


class ChatThread(RunnerThread):
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
        super().__init__(runner, parent)
        self._primary = primary
        self._comparison = comparison
        self._prompt = prompt

    def run(self) -> None:
        try:
            primary = self._call(self._primary, self._prompt)
            comparison = self._call(self._comparison, self._prompt) if self._comparison else ""
            self.succeeded.emit(primary, comparison)
        except asyncio.CancelledError:
            pass  # the window is closing; nobody is left to show the answer to
        except Exception as exc:  # noqa: BLE001 - direct model failures belong in the transcript
            self.failed.emit(str(exc))


def _default_chat(cwd: str) -> ChatRunner:
    # The room's folder, not the process's: opencode sessions are bound to their directory.
    async def chat(model: str, prompt: str) -> str:
        return await DirectBackend(cwd, timeout=1800).run(model, prompt)
    return chat


def _html(text: str) -> str:
    """Model output is text, not markup: unescaped, any `<tag>` in a code answer just vanished."""
    return html.escape(text).replace("\n", "<br>")


class DirectLine(QWidget):
    """A direct model chat that never routes through the orchestrator."""

    def __init__(
        self,
        parent: QWidget | None = None,
        chat_runner: ChatRunner | None = None,
        cwd: str | None = None,
    ) -> None:
        super().__init__(parent)
        self.setAccessibleName("Direct Line workspace")
        self._chat_runner = chat_runner or _default_chat(cwd or os.getcwd())
        self._asked: tuple[str, str] = ("", "")
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
        self.transcript.setHtml(
            "<b>Direct Line</b><br>"
            "Ask one model directly without routing through the orchestrator.<br><br>"
            "Choose a primary model, optionally pick <i>Ask another</i>, then send a prompt."
        )
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
        self.primary_output.setPlainText("Primary model output will appear here.")
        self.comparison_output = QTextBrowser(self)
        self.comparison_output.setAccessibleName("Comparison model response")
        self.comparison_output.setPlainText("Choose a different comparison model to enable side-by-side output.")
        self.status = QLabel("", self)
        self.status.setAccessibleName("Direct line status")
        self.status.setText("Choose a model and send a direct prompt.")

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
        self._asked = (primary, comparison)
        self.transcript.append(f"<b>You</b><br>{_html(prompt)}")
        self.status.setText(f"Waiting for {primary}…")
        self.ask_button.setEnabled(False)
        self.primary_output.clear()
        self.comparison_output.setPlainText("Waiting for comparison response…" if comparison else
                                            "Comparison disabled for this prompt.")
        self._chat_thread = ChatThread(self._chat_runner, primary, comparison, prompt, self)
        self._chat_thread.succeeded.connect(self._show_results)
        self._chat_thread.failed.connect(self._show_error)
        self._chat_thread.finished.connect(self._chat_finished)
        self._chat_thread.start()

    def _show_results(self, primary: str, comparison: str) -> None:
        self.primary_output.setPlainText(primary)
        self.comparison_output.setPlainText(comparison or "Comparison disabled.")
        # Label with the models actually asked; the combos may have changed while waiting.
        asked_primary, asked_comparison = self._asked
        self.transcript.append(f"<b>{html.escape(asked_primary)}</b><br>{_html(primary)}")
        if comparison:
            self.transcript.append(f"<b>{html.escape(asked_comparison)}</b><br>{_html(comparison)}")
        self.status.setText("Response complete.")

    def _show_error(self, message: str) -> None:
        self.status.setText(f"Direct request failed: {message}")

    def shutdown(self) -> None:
        if self._chat_thread is not None:
            self._chat_thread.shutdown()

    def _chat_finished(self) -> None:
        if self._chat_thread is not None:
            self._chat_thread.deleteLater()
            self._chat_thread = None
        self.ask_button.setEnabled(True)


__all__ = ["ChatThread", "DirectLine", "RunnerThread"]

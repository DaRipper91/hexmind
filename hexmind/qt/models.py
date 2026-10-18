"""Model inspection and probe controls for the Calibration Rack."""
from __future__ import annotations

import asyncio
import os
from collections.abc import Awaitable, Callable

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from ..backends import DirectBackend
from ..core import REGISTRY
from .chat import RunnerThread

ProbeRunner = Callable[[str, str], "str | Awaitable[str]"]


class ProbeThread(RunnerThread):
    succeeded = Signal(str)
    failed = Signal(str)

    def __init__(self, runner: ProbeRunner, model: str, prompt: str, parent: QWidget | None = None) -> None:
        super().__init__(runner, parent)
        self._model = model
        self._prompt = prompt

    def run(self) -> None:
        try:
            self.succeeded.emit(self._call(self._model, self._prompt))
        except asyncio.CancelledError:
            pass  # the window is closing
        except Exception as exc:  # noqa: BLE001 - probe errors belong in the visible result panel
            self.failed.emit(str(exc))


def _default_probe(cwd: str) -> ProbeRunner:
    async def probe(model: str, prompt: str) -> str:
        return await DirectBackend(cwd, timeout=60).run(model, prompt)
    return probe


class CalibrationRack(QWidget):
    """Inspect registry metadata and run a single-model text probe."""

    def __init__(
        self,
        parent: QWidget | None = None,
        probe_runner: ProbeRunner | None = None,
        cwd: str | None = None,
    ) -> None:
        super().__init__(parent)
        self.setAccessibleName("Calibration Rack workspace")
        self._probe_runner = probe_runner or _default_probe(cwd or os.getcwd())
        self._probe_thread: ProbeThread | None = None

        self.models = QListWidget(self)
        self.models.setAccessibleName("Registered models")
        # Only show enabled models
        self.models.addItems(REGISTRY.enabled_names())
        self.models.currentTextChanged.connect(self._show_model)

        self.label_value = QLabel("", self)
        self.family_value = QLabel("", self)
        self.tier_value = QLabel("", self)
        self.domains_value = QLabel("", self)
        self.footprint_value = QLabel("", self)
        self.weight_value = QLabel("", self)
        details = QFormLayout()
        details.addRow("Label", self.label_value)
        details.addRow("Family", self.family_value)
        details.addRow("Tier", self.tier_value)
        details.addRow("Domains", self.domains_value)
        details.addRow("Context / pricing", self.footprint_value)
        details.addRow("Weight", self.weight_value)

        self.probe_input = QLineEdit(self)
        self.probe_input.setAccessibleName("Model probe prompt")
        self.probe_input.setPlaceholderText("Ask this model a short test question…")
        self.probe_button = QPushButton("Run probe", self)
        self.probe_button.setProperty("variant", "primary")
        self.probe_button.clicked.connect(self.run_probe)
        probe_row = QHBoxLayout()
        probe_row.addWidget(self.probe_input, 1)
        probe_row.addWidget(self.probe_button)

        self.probe_output = QTextBrowser(self)
        self.probe_output.setAccessibleName("Model probe output")
        self.probe_output.setPlainText(
            "Select a model, enter a short probe prompt, and run a one-model check here."
        )
        self.status = QLabel("", self)
        self.status.setAccessibleName("Calibration status")
        self.status.setText("Select a model and enter a probe prompt to test it directly.")

        left = QVBoxLayout()
        reg_models_title = QLabel("Registered models", self)
        reg_models_title.setProperty("role", "heading")
        left.addWidget(reg_models_title)
        left.addWidget(self.models)
        right = QVBoxLayout()
        inspector_title = QLabel("Model inspector", self)
        inspector_title.setProperty("role", "heading")
        right.addWidget(inspector_title)
        right.addLayout(details)
        probe_title = QLabel("Single-model probe", self)
        probe_title.setProperty("role", "heading")
        right.addWidget(probe_title)
        right.addLayout(probe_row)
        right.addWidget(self.status)
        right.addWidget(self.probe_output, 1)

        layout = QHBoxLayout(self)
        layout.addLayout(left, 1)
        layout.addLayout(right, 2)
        if self.models.count():
            self.models.setCurrentRow(0)

    def _show_model(self, name: str) -> None:
        if not name:
            return
        model = REGISTRY.get(name)
        self.label_value.setText(model.label)
        self.family_value.setText(model.cli)
        self.tier_value.setText(model.tier)
        self.domains_value.setText(", ".join(model.domains) or "—")
        self.footprint_value.setText(model.footprint or "Not declared in models.toml")
        self.weight_value.setText(str(model.weight))

    def run_probe(self) -> None:
        model = self.models.currentItem()
        prompt = self.probe_input.text().strip()
        if model is None or not prompt:
            self.status.setText("Select a model and enter a probe prompt.")
            return
        if self._probe_thread is not None:
            return
        self.probe_button.setEnabled(False)
        self.status.setText(f"Probing {model.text()}…")
        self.probe_output.clear()
        self._probe_thread = ProbeThread(self._probe_runner, model.text(), prompt, self)
        self._probe_thread.succeeded.connect(self._probe_succeeded)
        self._probe_thread.failed.connect(self._probe_failed)
        self._probe_thread.finished.connect(self._probe_finished)
        self._probe_thread.start()

    def _probe_succeeded(self, text: str) -> None:
        self.probe_output.setPlainText(text)
        self.status.setText("Probe complete.")

    def _probe_failed(self, message: str) -> None:
        self.status.setText(f"Probe failed: {message}")

    def shutdown(self) -> None:
        if self._probe_thread is not None:
            self._probe_thread.shutdown()

    def _probe_finished(self) -> None:
        if self._probe_thread is not None:
            self._probe_thread.deleteLater()
            self._probe_thread = None
        self.probe_button.setEnabled(True)


__all__ = ["CalibrationRack", "ProbeThread"]

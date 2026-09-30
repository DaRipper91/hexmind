"""Model inspection and probe controls for the Calibration Rack."""
from __future__ import annotations

import asyncio
import os
from collections.abc import Callable

from PySide6.QtCore import QThread, Signal
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

ProbeRunner = Callable[[str, str], str]


class ProbeThread(QThread):
    succeeded = Signal(str)
    failed = Signal(str)

    def __init__(self, runner: ProbeRunner, model: str, prompt: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._runner = runner
        self._model = model
        self._prompt = prompt

    def run(self) -> None:
        try:
            self.succeeded.emit(self._runner(self._model, self._prompt))
        except Exception as exc:  # noqa: BLE001 - probe errors belong in the visible result panel
            self.failed.emit(str(exc))


def _default_probe(model: str, prompt: str) -> str:
    backend = DirectBackend(os.getcwd(), timeout=60)
    return asyncio.run(backend.run(model, prompt))


class CalibrationRack(QWidget):
    """Inspect registry metadata and run a single-model text probe."""

    def __init__(
        self,
        parent: QWidget | None = None,
        probe_runner: ProbeRunner | None = None,
    ) -> None:
        super().__init__(parent)
        self.setAccessibleName("Calibration Rack workspace")
        self._probe_runner = probe_runner or _default_probe
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
        self.probe_button.setAccessibleName("Run model probe")
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
        left.addWidget(QLabel("Registered models", self))
        left.addWidget(self.models)
        right = QVBoxLayout()
        right.addWidget(QLabel("Model inspector", self))
        right.addLayout(details)
        right.addWidget(QLabel("Single-model probe", self))
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

    def _probe_finished(self) -> None:
        if self._probe_thread is not None:
            self._probe_thread.deleteLater()
            self._probe_thread = None
        self.probe_button.setEnabled(True)


__all__ = ["CalibrationRack", "ProbeThread"]

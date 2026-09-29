"""The Calibration Rack, offscreen."""
from __future__ import annotations

import sys

import pytest

pytest.importorskip("PySide6", reason="the qt extra is not installed")

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication

from hexmind.qt.models import CalibrationRack


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication(sys.argv[:1])
    yield app


def test_calibration_rack_lists_registry_models(qapp):
    rack = CalibrationRack()

    assert rack.models.count() > 0
    assert rack.models.currentItem() is not None
    assert rack.label_value.text()
    assert rack.family_value.text()
    rack.close()
    rack.deleteLater()


def test_calibration_rack_shows_model_metadata(qapp):
    rack = CalibrationRack()
    rack.models.setCurrentRow(0)

    assert rack.tier_value.text() in {"cloud", "local"}
    assert rack.domains_value.text()
    assert rack.weight_value.text().isdigit()
    rack.close()
    rack.deleteLater()


def test_calibration_rack_probe_uses_selected_model(qapp):
    calls = []

    def runner(model, prompt):
        calls.append((model, prompt))
        return "probe response"

    rack = CalibrationRack(probe_runner=runner)
    rack.probe_input.setText("ping")
    loop = QEventLoop()
    rack.probe_output.textChanged.connect(loop.quit)
    QTimer.singleShot(2_000, loop.quit)
    rack.run_probe()
    loop.exec()

    assert calls == [(rack.models.currentItem().text(), "ping")]
    assert rack.status.text() == "Probe complete."
    rack.close()
    rack.deleteLater()


def test_calibration_rack_rejects_empty_probe(qapp):
    rack = CalibrationRack()
    rack.run_probe()

    assert "Select a model" in rack.status.text()
    rack.close()
    rack.deleteLater()

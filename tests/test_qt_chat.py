"""The Direct Line workspace, offscreen."""
from __future__ import annotations

import sys

import pytest

pytest.importorskip("PySide6", reason="the qt extra is not installed")

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication

from hexmind.qt.chat import DirectLine


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication(sys.argv[:1])
    yield app


def _wait_for_response(line):
    loop = QEventLoop()
    line.primary_output.textChanged.connect(loop.quit)
    QTimer.singleShot(2_000, loop.quit)
    loop.exec()


def test_direct_line_lists_primary_and_comparison_models(qapp):
    line = DirectLine()

    assert line.primary_model.count() > 0
    assert line.comparison_model.itemText(0) == "None"
    line.close()
    line.deleteLater()


def test_direct_line_asks_primary_and_another(qapp):
    calls = []

    def runner(model, prompt):
        calls.append((model, prompt))
        return f"{model}: answer"

    line = DirectLine(chat_runner=runner)
    line.comparison_model.setCurrentIndex(2)
    line.prompt.setText("hello")
    line.ask()
    _wait_for_response(line)

    primary = line.primary_model.currentText()
    comparison = line.comparison_model.currentText()
    assert calls == [(primary, "hello"), (comparison, "hello")]
    assert line.primary_output.toPlainText() == f"{primary}: answer"
    assert line.comparison_output.toPlainText() == f"{comparison}: answer"
    line.close()
    line.deleteLater()


def test_direct_line_rejects_empty_prompt(qapp):
    line = DirectLine()
    line.ask()

    assert "Enter a prompt" in line.status.text()
    line.close()
    line.deleteLater()

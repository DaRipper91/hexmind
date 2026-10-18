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
    assert "directly without routing through the orchestrator" in line.transcript.toPlainText()
    assert "Primary model output will appear here." == line.primary_output.toPlainText()
    assert "Choose a different comparison model" in line.comparison_output.toPlainText()
    assert "Choose a model and send a direct prompt." == line.status.text()
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


def test_shutdown_cancels_a_running_async_request(qapp):
    """Closing the window mid-request used to destroy a running QThread, which aborts the process."""
    import asyncio

    started = []

    async def runner(model, prompt):
        started.append(model)
        await asyncio.sleep(30)
        return "never"

    line = DirectLine(chat_runner=runner)
    line.prompt.setText("hello")
    line.ask()
    thread = line._chat_thread
    deadline = QEventLoop()
    QTimer.singleShot(300, deadline.quit)
    deadline.exec()
    assert started

    line.shutdown()
    assert not thread.isRunning()
    line.close()
    line.deleteLater()


def test_output_is_text_and_labelled_with_the_model_asked(qapp):
    answer = "<b>x</b> & <script>"

    def runner(model, prompt):
        return answer

    line = DirectLine(chat_runner=runner)
    asked = line.primary_model.currentText()
    line.prompt.setText("<i>hi</i>")
    line.ask()
    line.primary_model.setCurrentIndex(line.primary_model.count() - 1)  # changed while waiting
    _wait_for_response(line)

    text = line.transcript.toPlainText()
    assert "<i>hi</i>" in text
    assert answer in text
    assert f"{asked}\n{answer}" in text
    line.close()
    line.deleteLater()


def test_default_runner_uses_the_given_cwd(qapp, monkeypatch):
    from hexmind.qt import chat

    seen = []

    class Backend:
        def __init__(self, cwd, timeout):
            seen.append(cwd)

        async def run(self, model, prompt):
            return "ok"

    monkeypatch.setattr(chat, "DirectBackend", Backend)
    import asyncio

    assert asyncio.run(chat._default_chat("/some/room")("m", "p")) == "ok"
    assert seen == ["/some/room"]

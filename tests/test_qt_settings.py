"""The persisted Settings workspace, offscreen."""
from __future__ import annotations

import sys

import pytest

pytest.importorskip("PySide6", reason="the qt extra is not installed")

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication

from hexmind import config
from hexmind.qt.settings import SettingsPage


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication(sys.argv[:1])
    yield app


@pytest.fixture
def config_path(tmp_path):
    return tmp_path / "config.toml"


@pytest.fixture
def page(qapp, config_path):
    widget = SettingsPage(config_path)
    yield widget
    widget.close()
    widget.deleteLater()


def test_settings_page_loads_schema_defaults(page):
    assert page.members_input.text() == ", ".join(config.RoomDefaults().members)
    assert page.audit_checkbox.isChecked() is config.RoomDefaults().audit
    assert page.theme_selector.currentText() == config.RoomDefaults().theme
    assert page.phone_buzz_checkbox.isChecked() is False
    assert page.threshold_input.value() == 30


def test_settings_page_saves_all_configured_preferences(page, config_path):
    page.members_input.setText("codex, claude")
    page.audit_checkbox.setChecked(False)
    page.phone_buzz_checkbox.setChecked(True)
    page.threshold_input.setValue(90)

    assert page.save() is True
    data = config.load_config(config_path)
    assert data["room"] == {
        "members": ["codex", "claude"],
        "audit": False,
        "theme": "measured-dark",
    }
    assert data["notifications"] == {"phone_buzz": True, "threshold_seconds": 90}
    assert "Changes apply to new GUI sessions" in page.status.text()


@pytest.mark.parametrize("roster, message", [("", "at least one"), ("codex, codex", "unique")])
def test_settings_page_rejects_invalid_rosters(page, roster, message):
    page.members_input.setText(roster)

    assert page.save() is False
    assert message in page.status.text()


def test_settings_page_loads_saved_values(qapp, config_path):
    config.save_section(
        "room",
        {"members": ["kimi"], "audit": False, "theme": "measured-dark"},
        config_path,
    )
    config.save_section(
        "notifications",
        {"phone_buzz": True, "threshold_seconds": 45},
        config_path,
    )

    page = SettingsPage(config_path)

    assert page.members_input.text() == "kimi"
    assert page.audit_checkbox.isChecked() is False
    assert page.phone_buzz_checkbox.isChecked() is True
    assert page.threshold_input.value() == 45
    page.close()
    page.deleteLater()


def test_settings_page_reports_agent_health(page, monkeypatch):
    from hexmind.qt import health

    monkeypatch.setattr(health.shutil, "which", lambda _: "/usr/bin/model")
    monkeypatch.setattr(
        health.subprocess,
        "run",
        lambda *args, **kwargs: health.subprocess.CompletedProcess(args[0], 0),
    )
    loop = QEventLoop()
    page.health_completed.connect(loop.quit)
    QTimer.singleShot(2_000, loop.quit)
    page.check_health()
    loop.exec()

    assert "agents ready" in page.health_status.text()

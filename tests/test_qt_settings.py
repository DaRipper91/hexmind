"""The persisted Settings workspace, offscreen."""
from __future__ import annotations

import sys

import pytest

pytest.importorskip("PySide6", reason="the qt extra is not installed")

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication, QMessageBox

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
    assert page.lead_input.text() == config.RoomDefaults().lead
    assert page.members_input.text() == ", ".join(config.RoomDefaults().members)
    assert page.audit_checkbox.isChecked() is config.RoomDefaults().audit
    assert page.theme_selector.currentText() == config.RoomDefaults().theme
    assert page.server_host_input.text() == config.ServerDefaults().host
    assert page.server_port_input.value() == config.ServerDefaults().port
    assert page.server_token_input.text() == config.ServerDefaults().token
    assert page.phone_buzz_checkbox.isChecked() is False
    assert page.threshold_input.value() == 30
    assert page.save_button.isEnabled() is False
    assert page.revert_button.isEnabled() is False


def test_settings_page_saves_all_configured_preferences(page, config_path):
    page.lead_input.setText("codex")
    page.members_input.setText("codex, claude")
    page.audit_checkbox.setChecked(False)
    page.server_host_input.setText("0.0.0.0")
    page.server_port_input.setValue(9000)
    page.server_token_input.setText("secret")
    page.phone_buzz_checkbox.setChecked(True)
    page.threshold_input.setValue(90)

    assert page.save() is True
    data = config.load_config(config_path)
    assert data["room"] == {
        "lead": "codex",
        "members": ["codex", "claude"],
        "audit": False,
        "theme": "measured-dark",
    }
    assert data["server"] == {"host": "0.0.0.0", "port": 9000, "token": "secret"}
    assert data["notifications"] == {"phone_buzz": True, "threshold_seconds": 90}
    assert "Changes apply to new GUI sessions" in page.status.text()


@pytest.mark.parametrize("roster, message", [("", "at least one"), ("codex, codex", "unique")])
def test_settings_page_rejects_invalid_rosters(page, roster, message):
    page.members_input.setText(roster)

    assert page.save() is False
    assert message in page.status.text()


def test_settings_page_rejects_a_lead_outside_the_default_roster(page):
    page.lead_input.setText("qwen")
    page.members_input.setText("codex, claude")

    assert page.save() is False
    assert "Default lead must be included" in page.status.text()


def test_settings_page_loads_saved_values(qapp, config_path):
    config.save_section(
        "room",
        {"lead": "kimi", "members": ["kimi"], "audit": False, "theme": "measured-dark"},
        config_path,
    )
    config.save_section(
        "server",
        {"host": "192.168.1.5", "port": 8888, "token": "tok123"},
        config_path,
    )
    config.save_section(
        "notifications",
        {"phone_buzz": True, "threshold_seconds": 45},
        config_path,
    )

    page = SettingsPage(config_path)

    assert page.lead_input.text() == "kimi"
    assert page.members_input.text() == "kimi"
    assert page.audit_checkbox.isChecked() is False
    assert page.server_host_input.text() == "192.168.1.5"
    assert page.server_port_input.value() == 8888
    assert page.server_token_input.text() == "tok123"
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


def test_settings_page_can_restore_defaults_without_saving(page):
    page.lead_input.setText("codex")
    page.members_input.setText("codex, claude")
    page.audit_checkbox.setChecked(False)
    page.server_host_input.setText("0.0.0.0")
    page.server_port_input.setValue(9000)
    page.server_token_input.setText("secret")
    page.phone_buzz_checkbox.setChecked(True)
    page.threshold_input.setValue(90)

    page.reset_to_defaults()

    assert page.lead_input.text() == config.RoomDefaults().lead
    assert page.members_input.text() == ", ".join(config.RoomDefaults().members)
    assert page.audit_checkbox.isChecked() is config.RoomDefaults().audit
    assert page.server_host_input.text() == config.ServerDefaults().host
    assert page.server_port_input.value() == config.ServerDefaults().port
    assert page.server_token_input.text() == config.ServerDefaults().token
    assert page.phone_buzz_checkbox.isChecked() is config.NotificationDefaults().phone_buzz
    assert page.threshold_input.value() == config.NotificationDefaults().threshold_seconds
    assert "Restored defaults" in page.status.text()
    assert page.save_button.isEnabled() is False
    assert page.revert_button.isEnabled() is False


def test_settings_page_marks_dirty_and_can_revert_unsaved_changes(page):
    page.server_host_input.setText("0.0.0.0")

    assert page.is_dirty is True
    assert page.save_button.isEnabled() is True
    assert page.revert_button.isEnabled() is True

    page.revert()

    assert page.server_host_input.text() == config.ServerDefaults().host
    assert page.is_dirty is False
    assert page.save_button.isEnabled() is False
    assert page.revert_button.isEnabled() is False
    assert "Reverted unsaved changes" in page.status.text()


def test_settings_page_can_cancel_reload_when_dirty(page, monkeypatch):
    page.server_host_input.setText("0.0.0.0")
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Cancel,
    )

    assert page.reload() is False
    assert page.server_host_input.text() == "0.0.0.0"
    assert page.is_dirty is True
    assert "Keeping unsaved changes" in page.status.text()


def test_settings_page_requests_config_paths_and_bootstraps_missing_file(qapp, config_path):
    page = SettingsPage(config_path)
    opened = []
    opened_dirs = []
    page.config_file_requested.connect(opened.append)
    page.config_directory_requested.connect(opened_dirs.append)

    page.request_open_config_file()
    page.request_open_config_directory()

    assert opened == [str(config_path)]
    assert config_path.exists()
    assert opened_dirs == [str(config_path.parent)]
    page.close()
    page.deleteLater()

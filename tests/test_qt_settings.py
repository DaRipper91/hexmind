"""The persisted Settings workspace, offscreen."""
from __future__ import annotations

import sys

import pytest

pytest.importorskip("PySide6", reason="the qt extra is not installed")

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication, QMessageBox

from hexmind import config
from hexmind.core import REGISTRY
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
    # Lead combo should have "(no lead — parallel turn)" as first item
    assert page.lead_combo.itemText(0) == "(no lead — parallel turn)"
    # Default lead is nemotron-lightning (first free opencode model)
    assert page.lead_combo.currentData() == "nemotron-lightning"
    # Team should default to RoomDefaults
    assert page._team == config.RoomDefaults().members
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
    # Select lead from combo
    idx = page.lead_combo.findData("nemotron-lightning")
    page.lead_combo.setCurrentIndex(idx)
    # Set team directly
    page._team = ["nemotron-lightning", "big-pickle"]
    page._lead = "nemotron-lightning"
    page._populate_lead_combo()
    page._update_team_label()

    page.audit_checkbox.setChecked(False)
    page.server_host_input.setText("0.0.0.0")
    page.server_port_input.setValue(9000)
    page.server_token_input.setText("secret")
    page.phone_buzz_checkbox.setChecked(True)
    page.threshold_input.setValue(90)

    assert page.save() is True
    data = config.load_config(config_path)
    assert data["room"] == {
        "lead": "nemotron-lightning",
        "members": ["nemotron-lightning", "big-pickle"],
        "audit": False,
        "theme": "measured-dark",
        "text_size": "14",
    }
    assert data["server"] == {"host": "0.0.0.0", "port": 9000, "token": "secret"}
    assert data["notifications"] == {"phone_buzz": True, "threshold_seconds": 90}
    assert "Changes apply to new GUI sessions" in page.status.text()


@pytest.mark.parametrize("team, message", [([], "at least one"), (["nemotron-lightning", "nemotron-lightning"], "unique")])
def test_settings_page_rejects_invalid_rosters(page, team, message):
    page._team = team
    page._populate_lead_combo()
    page._update_team_label()

    assert page.save() is False
    assert message in page.status.text()


def test_settings_page_rejects_a_lead_outside_the_default_roster(page):
    page._lead = "deepseek-v4-1-flash-free"
    page._team = ["nemotron-lightning", "big-pickle"]
    page._populate_lead_combo()
    page._update_team_label()

    assert page.save() is False
    assert "Default lead must be included" in page.status.text()


def test_settings_page_loads_saved_values(qapp, config_path):
    config.save_section(
        "room",
        {"lead": "nemotron-ultra", "members": ["nemotron-ultra"], "audit": False, "theme": "measured-dark"},
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

    # Lead should be nemotron-ultra
    idx = page.lead_combo.findData("nemotron-ultra")
    assert idx >= 0
    assert page.lead_combo.currentIndex() == idx
    # Team should be nemotron-ultra
    assert page._team == ["nemotron-ultra"]
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
    page._lead = "nemotron-lightning"
    page._team = ["nemotron-lightning", "big-pickle"]
    page._populate_lead_combo()
    page._update_team_label()

    page.audit_checkbox.setChecked(False)
    page.server_host_input.setText("0.0.0.0")
    page.server_port_input.setValue(9000)
    page.server_token_input.setText("secret")
    page.phone_buzz_checkbox.setChecked(True)
    page.threshold_input.setValue(90)

    page.reset_to_defaults()

    # Default lead is nemotron-lightning, not "(no lead)"
    assert page.lead_combo.currentData() == "nemotron-lightning"
    assert page._team == config.RoomDefaults().members
    assert page.audit_checkbox.isChecked() is config.RoomDefaults().audit
    assert page.server_host_input.text() == config.ServerDefaults().host
    assert page.server_port_input.value() == config.ServerDefaults().port
    assert page.server_token_input.text() == config.ServerDefaults().token
    assert page.phone_buzz_checkbox.isChecked() is config.NotificationDefaults().phone_buzz
    assert page.threshold_input.value() == config.NotificationDefaults().threshold_seconds
    assert "Restored defaults" in page.status.text()


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

def test_restore_defaults_writes_nothing_until_save(page, config_path):
    """reset_to_defaults said "without writing to disk" and then rewrote [models] immediately --
    into config.PATH, ignoring the page's own config_path."""
    from pathlib import Path

    def snapshot(p):
        p = Path(p)
        return p.read_bytes() if p.exists() else None

    before = (snapshot(config_path), snapshot(config.PATH))
    page.reset_to_defaults()
    assert (snapshot(config_path), snapshot(config.PATH)) == before

    page.save()
    assert "[models]" in Path(config_path).read_text()


def test_disabling_a_model_outside_the_team_is_dirty_and_revertible(page):
    outsider = next(name for name in page._enabled_models if name not in page._team)
    enabled = dict(page._enabled_models, **{outsider: False})

    page._on_team_saved(enabled, list(page._team))
    assert page.is_dirty
    assert page.save_button.isEnabled()

    page.revert()
    assert page._enabled_models[outsider] is True
    assert not page.is_dirty


def test_text_size_round_trips_and_rejects_junk(page, config_path):
    page.text_size_selector.setCurrentIndex(page.text_size_selector.findData("18"))
    assert page.is_dirty
    assert page.save()
    assert config.get_defaults(config_path).text_size == "18"

    config.save_section("room", {"text_size": "huge"}, config_path)
    assert config.get_defaults(config_path).text_size == config.RoomDefaults().text_size


def test_settings_form_layout_bounds_at_1400(page, qapp):
    """Task 3.7: Settings form fields do not stretch across full width at 1400x900."""
    page.resize(1400, 900)
    page.show()
    qapp.processEvents()

    assert page.server_host_input.width() <= 480
    assert page.health_button.width() < 400

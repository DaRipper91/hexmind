"""Persisted preferences for the standalone Hexmind workbench."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from .. import config
from ..core import REGISTRY
from .model_selector import ModelSelectorDialog, load_enabled_from_config, save_enabled_to_config
from .health import HealthScanner


class SettingsPage(QWidget):
    """Edit the shared TOML defaults without owning the active Room."""

    saved = Signal()
    health_completed = Signal()
    config_file_requested = Signal(str)
    config_directory_requested = Signal(str)
    dirty_changed = Signal(bool)

    def __init__(self, config_path: str | Path | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._config_path = config_path
        self._loaded_state: dict[str, object] = {}
        self._dirty = False
        self._tracking_dirty = True
        self.setAccessibleName("Settings workspace")

        # Load enabled models and team from config
        self._enabled_models = load_enabled_from_config()
        self._team = config.get_defaults(self._config_path).members
        self._lead = config.get_defaults(self._config_path).lead

        title = QLabel("Settings", self)
        title.setAccessibleName("Settings heading")

        # Lead selector - combo box populated from enabled models
        self.lead_combo = QComboBox(self)
        self.lead_combo.setAccessibleName("Default lead")
        self.lead_combo.setToolTip("Who plans the work and writes your answer. Nothing runs without one.")
        self._populate_lead_combo()

        # Team selector - button opens ModelSelectorDialog
        self.team_button = QPushButton("Select Team…", self)
        self.team_button.setAccessibleName("Select default team")
        self.team_button.setToolTip("Choose which enabled models are in the default roster")
        self.team_button.clicked.connect(self._open_team_selector)
        self.team_label = QLabel(self._format_team_label(), self)
        self.team_label.setAccessibleName("Default roster preview")

        self.audit_checkbox = QCheckBox("Enable peer audit by default", self)
        self.audit_checkbox.setAccessibleName("Default peer audit")

        self.theme_selector = QComboBox(self)
        self.theme_selector.setAccessibleName("Theme")
        self.theme_selector.addItem("measured-dark")

        self.phone_buzz_checkbox = QCheckBox("Send a completion ping", self)
        self.phone_buzz_checkbox.setAccessibleName("Completion notification")

        self.threshold_input = QSpinBox(self)
        self.threshold_input.setAccessibleName("Notification threshold seconds")
        self.threshold_input.setRange(0, 86_400)
        self.threshold_input.setSuffix(" seconds")

        self.server_host_input = QLineEdit(self)
        self.server_host_input.setAccessibleName("Server host")

        self.server_port_input = QSpinBox(self)
        self.server_port_input.setAccessibleName("Server port")
        self.server_port_input.setRange(1, 65_535)

        self.server_token_input = QLineEdit(self)
        self.server_token_input.setAccessibleName("Server token")
        self.server_token_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.server_token_input.setPlaceholderText("Optional unless serving off localhost")

        form = QFormLayout()
        form.addRow("Default lead", self.lead_combo)
        form.addRow("Default roster", self._team_row())
        form.addRow("", self.audit_checkbox)
        form.addRow("Theme", self.theme_selector)
        form.addRow("Server host", self.server_host_input)
        form.addRow("Server port", self.server_port_input)
        form.addRow("Server token", self.server_token_input)
        form.addRow("", self.phone_buzz_checkbox)
        form.addRow("Notify after", self.threshold_input)

        self.status = QLabel("", self)
        self.status.setAccessibleName("Settings status")
        self.reload_button = QPushButton("Reload from disk", self)
        self.reload_button.clicked.connect(lambda: self.reload())
        self.defaults_button = QPushButton("Restore defaults", self)
        self.defaults_button.clicked.connect(self.reset_to_defaults)
        self.revert_button = QPushButton("Revert unsaved changes", self)
        self.revert_button.setEnabled(False)
        self.revert_button.clicked.connect(self.revert)
        self.open_config_button = QPushButton("Open config.toml", self)
        self.open_config_button.clicked.connect(self.request_open_config_file)
        self.open_config_dir_button = QPushButton("Open config folder", self)
        self.open_config_dir_button.clicked.connect(self.request_open_config_directory)
        self.save_button = QPushButton("Save settings", self)
        self.save_button.setEnabled(False)
        self.save_button.clicked.connect(self.save)
        buttons = QHBoxLayout()
        buttons.addWidget(self.reload_button)
        buttons.addWidget(self.defaults_button)
        buttons.addWidget(self.revert_button)
        buttons.addWidget(self.open_config_button)
        buttons.addWidget(self.open_config_dir_button)
        buttons.addStretch()
        buttons.addWidget(self.save_button)

        layout = QVBoxLayout(self)
        layout.addWidget(title)
        layout.addWidget(
            QLabel(
                "These preferences apply when a new Hexmind GUI session starts. "
                "They do not replace the active Room's team or audit state.",
                self,
            )
        )
        layout.addLayout(form)
        layout.addWidget(self.status)
        layout.addLayout(buttons)
        self.health_status = QLabel("", self)
        self.health_status.setAccessibleName("Agent health")
        self.health_button = QPushButton("Check agent health", self)
        self.health_button.setAccessibleName("Check agent health")
        self.health_button.clicked.connect(self.check_health)
        layout.addWidget(self.health_button)
        layout.addWidget(self.health_status)
        layout.addStretch()
        self._connect_dirty_inputs()
        self.reload()

    def _team_row(self) -> QWidget:
        """Create a widget containing the team button and label."""
        container = QWidget(self)
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.team_button)
        layout.addWidget(self.team_label, 1)
        return container

    def _populate_lead_combo(self) -> None:
        """Populate lead combo with enabled models."""
        self.lead_combo.blockSignals(True)
        self.lead_combo.clear()
        self.lead_combo.addItem("(no lead — parallel turn)", "")
        for name in REGISTRY.enabled_names():
            if self._enabled_models.get(name, True):
                model = REGISTRY.get(name)
                self.lead_combo.addItem(f"{model.label} ({name})", name)
        # Select current lead
        idx = self.lead_combo.findData(self._lead)
        if idx >= 0:
            self.lead_combo.setCurrentIndex(idx)
        self.lead_combo.blockSignals(False)

    def _format_team_label(self) -> str:
        """Format the team label for display."""
        if not self._team:
            return "(empty — click Select Team…)"
        enabled_team = [m for m in self._team if self._enabled_models.get(m, True)]
        if not enabled_team:
            return "(all disabled — click Select Team…)"
        if len(enabled_team) <= 3:
            labels = [REGISTRY.get(m).label for m in enabled_team]
            return ", ".join(labels)
        return f"{len(enabled_team)} models: {REGISTRY.get(enabled_team[0]).label}, {REGISTRY.get(enabled_team[1]).label}, …"

    def _update_team_label(self) -> None:
        self.team_label.setText(self._format_team_label())

    def _open_team_selector(self) -> None:
        dialog = ModelSelectorDialog(
            current_enabled=self._enabled_models,
            current_team=self._team,
            current_lead=self._lead,
            parent=self,
        )
        dialog.saved.connect(self._on_team_saved)
        dialog.exec()

    def _on_team_saved(self, enabled: dict[str, bool], team: list[str]) -> None:
        self._enabled_models = enabled
        self._team = team
        self._populate_lead_combo()
        self._update_team_label()
        self._on_form_edited()

    @property
    def config_path(self) -> Path:
        raw = self._config_path if self._config_path is not None else config.PATH
        return Path(raw).expanduser()

    @property
    def is_dirty(self) -> bool:
        return self._dirty

    def _connect_dirty_inputs(self) -> None:
        self.lead_combo.currentTextChanged.connect(self._on_form_edited)
        self.audit_checkbox.toggled.connect(self._on_form_edited)
        self.theme_selector.currentTextChanged.connect(self._on_form_edited)
        self.server_host_input.textChanged.connect(self._on_form_edited)
        self.server_port_input.valueChanged.connect(self._on_form_edited)
        self.server_token_input.textChanged.connect(self._on_form_edited)
        self.phone_buzz_checkbox.toggled.connect(self._on_form_edited)
        self.threshold_input.valueChanged.connect(self._on_form_edited)

    def _capture_state(self) -> dict[str, object]:
        lead = self.lead_combo.currentData()
        return {
            "lead": lead if lead else "",
            "members": ", ".join(self._team),
            "audit": self.audit_checkbox.isChecked(),
            "theme": self.theme_selector.currentText(),
            "server_host": self.server_host_input.text(),
            "server_port": self.server_port_input.value(),
            "server_token": self.server_token_input.text(),
            "phone_buzz": self.phone_buzz_checkbox.isChecked(),
            "threshold": self.threshold_input.value(),
        }

    def _apply_state(self, state: dict[str, object]) -> None:
        self._tracking_dirty = False
        try:
            lead = str(state["lead"])
            idx = self.lead_combo.findData(lead)
            if idx >= 0:
                self.lead_combo.setCurrentIndex(idx)
            else:
                self.lead_combo.setCurrentIndex(0)
            self._lead = lead

            members = str(state["members"])
            self._team = [m.strip() for m in members.split(",") if m.strip()]

            self.audit_checkbox.setChecked(bool(state["audit"]))
            theme = str(state["theme"])
            if self.theme_selector.findText(theme) < 0:
                self.theme_selector.addItem(theme)
            self.theme_selector.setCurrentText(theme)
            self.server_host_input.setText(str(state["server_host"]))
            self.server_port_input.setValue(int(state["server_port"]))
            self.server_token_input.setText(str(state["server_token"]))
            self.phone_buzz_checkbox.setChecked(bool(state["phone_buzz"]))
            self.threshold_input.setValue(int(state["threshold"]))
            self._update_team_label()
        finally:
            self._tracking_dirty = True

    def _set_dirty(self, dirty: bool) -> None:
        if dirty == self._dirty:
            return
        self._dirty = dirty
        self.save_button.setEnabled(dirty)
        self.revert_button.setEnabled(dirty)
        self.dirty_changed.emit(dirty)

    def _on_form_edited(self, *_args) -> None:
        if not self._tracking_dirty:
            return
        self._set_dirty(self._capture_state() != self._loaded_state)

    def _confirm_discard(self, action: str) -> bool:
        if not self._dirty:
            return True
        answer = QMessageBox.question(
            self,
            "Discard unsaved settings?",
            f"You have unsaved changes in Settings.\n\nDiscard them and {action}?",
            QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        return answer == QMessageBox.StandardButton.Discard

    def reset_to_defaults(self) -> None:
        """Restore the form to schema defaults without writing to disk."""
        room = config.RoomDefaults()
        server = config.ServerDefaults()
        notifications = config.NotificationDefaults()
        self._enabled_models = {name: True for name in REGISTRY.names()}
        save_enabled_to_config(self._enabled_models)
        self._team = list(room.members)
        self._lead = room.lead
        self._populate_lead_combo()
        self.audit_checkbox.setChecked(room.audit)
        if self.theme_selector.findText(room.theme) < 0:
            self.theme_selector.addItem(room.theme)
        self.theme_selector.setCurrentText(room.theme)
        self.server_host_input.setText(server.host)
        self.server_port_input.setValue(server.port)
        self.server_token_input.setText(server.token)
        self.phone_buzz_checkbox.setChecked(notifications.phone_buzz)
        self.threshold_input.setValue(notifications.threshold_seconds)
        self._update_team_label()
        self.status.setText("Restored defaults in the form. Save to write them.")
        self._on_form_edited()

    def revert(self) -> None:
        """Restore the last loaded/saved values without re-reading disk."""
        if not self._dirty:
            return
        self._apply_state(self._loaded_state)
        self._populate_lead_combo()
        self._update_team_label()
        self.status.setText("Reverted unsaved changes.")
        self._set_dirty(False)

    def reload(self, force: bool = False) -> bool:
        """Load shared preferences into the form."""
        if not force and not self._confirm_discard("reload from disk"):
            self.status.setText("Keeping unsaved changes.")
            return False
        room = config.get_defaults(self._config_path)
        server = config.get_server_defaults(self._config_path)
        notifications = config.get_notification_defaults(self._config_path)

        self._enabled_models = load_enabled_from_config()
        self._team = list(room.members)
        self._lead = room.lead
        self._populate_lead_combo()

        self._apply_state(
            {
                "lead": room.lead,
                "members": ", ".join(room.members),
                "audit": room.audit,
                "theme": room.theme,
                "server_host": server.host,
                "server_port": server.port,
                "server_token": server.token,
                "phone_buzz": notifications.phone_buzz,
                "threshold": notifications.threshold_seconds,
            }
        )
        self._loaded_state = self._capture_state()
        self.status.setText("Loaded settings from disk.")
        self._set_dirty(False)
        return True

    def save(self) -> bool:
        """Persist validated settings and report a usable error when validation fails."""
        lead = self.lead_combo.currentData()
        lead_str = lead if lead else ""
        members = self._team

        if not members:
            self.status.setText("Enter at least one model ID for the default roster.")
            self.team_button.setFocus()
            return False
        if len(members) != len(set(members)):
            self.status.setText("Default roster model IDs must be unique.")
            self.team_button.setFocus()
            return False
        if lead_str and lead_str not in members:
            self.status.setText("Default lead must be included in the default roster.")
            self.lead_combo.setFocus()
            return False

        host = self.server_host_input.text().strip()
        if not host:
            self.status.setText("Server host cannot be empty.")
            self.server_host_input.setFocus()
            return False

        try:
            config.save_section(
                "room",
                {
                    "lead": lead_str,
                    "members": members,
                    "audit": self.audit_checkbox.isChecked(),
                    "theme": self.theme_selector.currentText(),
                },
                self._config_path,
            )
            config.save_section(
                "server",
                {
                    "host": host,
                    "port": self.server_port_input.value(),
                    "token": self.server_token_input.text(),
                },
                self._config_path,
            )
            config.save_section(
                "notifications",
                {
                    "phone_buzz": self.phone_buzz_checkbox.isChecked(),
                    "threshold_seconds": self.threshold_input.value(),
                },
                self._config_path,
            )
            save_enabled_to_config(self._enabled_models)
        except OSError as exc:
            self.status.setText(f"Could not save settings: {exc}")
            return False

        self.status.setText("Saved. Changes apply to new GUI sessions.")
        self._loaded_state = self._capture_state()
        self._set_dirty(False)
        self.saved.emit()
        return True

    def ensure_config_exists(self) -> Path:
        """Create a default config file so the host can open it on first run."""
        path = self.config_path
        if path.exists():
            return path
        room = config.RoomDefaults()
        server = config.ServerDefaults()
        notifications = config.NotificationDefaults()
        config.save_section(
            "room",
            {
                "lead": room.lead,
                "members": room.members,
                "audit": room.audit,
                "theme": room.theme,
            },
            path,
        )
        config.save_section(
            "server",
            {
                "host": server.host,
                "port": server.port,
                "token": server.token,
            },
            path,
        )
        config.save_section(
            "notifications",
            {
                "phone_buzz": notifications.phone_buzz,
                "threshold_seconds": notifications.threshold_seconds,
            },
            path,
        )
        # Also save enabled models defaults
        save_enabled_to_config({name: True for name in REGISTRY.names()})
        return path

    def request_open_config_file(self) -> None:
        """Ask the host to open config.toml, creating a default file if needed."""
        self.config_file_requested.emit(str(self.ensure_config_exists()))

    def request_open_config_directory(self) -> None:
        """Ask the host to reveal the config directory."""
        path = self.config_path.parent
        path.mkdir(parents=True, exist_ok=True)
        self.config_directory_requested.emit(str(path))

    def check_health(self) -> None:
        """Report local executable and credential readiness without invoking a model."""
        if getattr(self, "_health_scanner", None) is not None:
            return
        self.health_button.setEnabled(False)
        self._health_scanner = HealthScanner(self)
        self._health_scanner.finished.connect(self._show_health)
        self._health_scanner.finished.connect(self._health_scanner.deleteLater)
        self._health_scanner.finished.connect(lambda _: setattr(self, "_health_scanner", None))
        self._health_scanner.start()

    def _show_health(self, results: list) -> None:
        ready = sum(result.available and result.credential_ready for result in results)
        unchecked = sum(result.available and not result.credential_checked for result in results)
        status = f"{ready}/{len(results)} agents ready"
        if unchecked:
            status += f"; {unchecked} auth checks unavailable"
        self.health_status.setText(status)
        self.health_button.setEnabled(True)
        self.health_completed.emit()


__all__ = ["SettingsPage"]
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
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from .. import config
from .health import HealthScanner


class SettingsPage(QWidget):
    """Edit the shared TOML defaults without owning the active Room."""

    saved = Signal()
    health_completed = Signal()

    def __init__(self, config_path: str | Path | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._config_path = config_path
        self.setAccessibleName("Settings workspace")

        title = QLabel("Settings", self)
        title.setAccessibleName("Settings heading")

        self.members_input = QLineEdit(self)
        self.members_input.setAccessibleName("Default roster")
        self.members_input.setToolTip("Comma-separated model IDs used by new GUI sessions.")

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

        form = QFormLayout()
        form.addRow("Default roster", self.members_input)
        form.addRow("", self.audit_checkbox)
        form.addRow("Theme", self.theme_selector)
        form.addRow("", self.phone_buzz_checkbox)
        form.addRow("Notify after", self.threshold_input)

        self.status = QLabel("", self)
        self.status.setAccessibleName("Settings status")
        self.save_button = QPushButton("Save settings", self)
        self.save_button.clicked.connect(self.save)
        buttons = QHBoxLayout()
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
        self.reload()

    def reload(self) -> None:
        """Load shared preferences into the form."""
        data = config.load_config(self._config_path)
        room = data.get("room", {})
        notifications = data.get("notifications", {})
        room = room if isinstance(room, dict) else {}
        notifications = notifications if isinstance(notifications, dict) else {}

        members = room.get("members", config.RoomDefaults().members)
        if not isinstance(members, list) or not all(isinstance(member, str) for member in members):
            members = config.RoomDefaults().members
        self.members_input.setText(", ".join(members))
        self.audit_checkbox.setChecked(bool(room.get("audit", config.RoomDefaults().audit)))

        theme = room.get("theme", config.RoomDefaults().theme)
        if isinstance(theme, str) and theme:
            if self.theme_selector.findText(theme) < 0:
                self.theme_selector.addItem(theme)
            self.theme_selector.setCurrentText(theme)

        self.phone_buzz_checkbox.setChecked(bool(notifications.get("phone_buzz", False)))
        threshold = notifications.get("threshold_seconds", 30)
        self.threshold_input.setValue(threshold if isinstance(threshold, int) and threshold >= 0 else 30)
        self.status.clear()

    def save(self) -> bool:
        """Persist validated settings and report a usable error when validation fails."""
        members = [member.strip() for member in self.members_input.text().split(",") if member.strip()]
        if not members:
            self.status.setText("Enter at least one model ID for the default roster.")
            self.members_input.setFocus()
            return False
        if len(members) != len(set(members)):
            self.status.setText("Default roster model IDs must be unique.")
            self.members_input.setFocus()
            return False

        try:
            config.save_section(
                "room",
                {
                    "members": members,
                    "audit": self.audit_checkbox.isChecked(),
                    "theme": self.theme_selector.currentText(),
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
        except OSError as exc:
            self.status.setText(f"Could not save settings: {exc}")
            return False

        self.status.setText("Saved. Changes apply to new GUI sessions.")
        self.saved.emit()
        return True

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

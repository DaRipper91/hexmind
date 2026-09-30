"""Model selection dialog for enabling/disabling models and choosing the default roster."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..core import REGISTRY
from .. import config as config_module


class ModelSelectorDialog(QDialog):
    """Dialog for managing model enabled state and default roster selection.

    Two columns:
    - Enabled: controls global visibility of the model in all UI surfaces
    - In Team: controls whether the model is in the default roster for new sessions

    Keyboard: Tab to navigate, Space to toggle checkboxes, Enter to confirm
    Mouse: Left-click toggles checkboxes
    """

    saved = Signal(dict, list)  # enabled_dict, team_list

    def __init__(
        self,
        current_enabled: dict[str, bool] | None = None,
        current_team: list[str] | None = None,
        current_lead: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Select Team & Enabled Models")
        self.setModal(True)
        self.resize(900, 600)

        self._current_lead = current_lead or ""
        self._enabled = dict(current_enabled) if current_enabled else {}
        self._team = list(current_team) if current_team else []

        self._build_ui()
        self._populate_table()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        # Header
        header = QLabel(
            "Configure which models are enabled (visible in UI) and which are in the default team roster.\n"
            "The lead model is always placed at the top of the team table.",
            self,
        )
        header.setWordWrap(True)
        layout.addWidget(header)

        # Table
        self.table = QTableWidget(0, 4, self)
        self.table.setHorizontalHeaderLabels(["Enabled", "In Team", "Model", "Details"])
        self.table.setAccessibleName("Model selection")
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table.setAlternatingRowColors(True)
        layout.addWidget(self.table, 1)

        # Buttons row
        button_row = QHBoxLayout()
        self.select_all_enabled = QPushButton("Enable All", self)
        self.select_all_enabled.clicked.connect(self._enable_all)
        self.disable_all = QPushButton("Disable All", self)
        self.disable_all.clicked.connect(self._disable_all)
        self.select_team_all = QPushButton("Select All for Team", self)
        self.select_team_all.clicked.connect(self._select_all_team)
        self.clear_team = QPushButton("Clear Team", self)
        self.clear_team.clicked.connect(self._clear_team)

        button_row.addWidget(self.select_all_enabled)
        button_row.addWidget(self.disable_all)
        button_row.addStretch()
        button_row.addWidget(self.select_team_all)
        button_row.addWidget(self.clear_team)
        layout.addLayout(button_row)

        # Dialog buttons
        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            Qt.Orientation.Horizontal,
            self,
        )
        self.button_box.accepted.connect(self._on_accept)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)

    def _populate_table(self) -> None:
        """Fill the table with all registry models sorted by weight."""
        models = REGISTRY.by_weight()
        self.table.setRowCount(len(models))

        for row, name in enumerate(models):
            model = REGISTRY.get(name)

            # Enabled checkbox
            enabled = self._enabled.get(name, True)  # default True if not in config
            enabled_check = QCheckBox("", self)
            enabled_check.setChecked(enabled)
            enabled_check.setAccessibleName(f"Enable {model.label}")
            enabled_check.stateChanged.connect(lambda state, n=name: self._on_enabled_changed(n, state))
            self.table.setCellWidget(row, 0, self._center_widget(enabled_check))

            # In Team checkbox
            in_team = name in self._team
            team_check = QCheckBox("", self)
            team_check.setChecked(in_team)
            team_check.setAccessibleName(f"Add {model.label} to team")
            team_check.stateChanged.connect(lambda state, n=name: self._on_team_changed(n, state))
            self.table.setCellWidget(row, 1, self._center_widget(team_check))

            # Model name with lead indicator
            display_name = f"{model.label} ({name})"
            if name == self._current_lead:
                display_name = f"★ {display_name}"
            name_item = QTableWidgetItem(display_name)
            name_item.setData(Qt.ItemDataRole.UserRole, name)
            name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 2, name_item)

            # Details: tier, domains, best_at
            details = f"[{model.tier}] {', '.join(model.domains) or '—'} — {model.best_at}"
            details_item = QTableWidgetItem(details)
            details_item.setFlags(details_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 3, details_item)

        # Sort by weight (already sorted by REGISTRY.by_weight)
        # But we want lead at top visually - handled by the ★ prefix

    def _center_widget(self, widget: QWidget) -> QWidget:
        """Wrap a widget in a container that centers it in the cell."""
        container = QWidget(self)
        layout = QHBoxLayout(container)
        layout.addWidget(widget)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setContentsMargins(0, 0, 0, 0)
        return container

    def _on_enabled_changed(self, name: str, state: int) -> None:
        self._enabled[name] = state == Qt.CheckState.Checked.value
        # If disabling a model that's in team, also remove from team
        if not self._enabled[name] and name in self._team:
            self._team.remove(name)
            # Update the team checkbox
            row = self._find_row(name)
            if row >= 0:
                widget = self.table.cellWidget(row, 1)
                if widget:
                    check = widget.findChild(QCheckBox)
                    if check:
                        check.blockSignals(True)
                        check.setChecked(False)
                        check.blockSignals(False)

    def _on_team_changed(self, name: str, state: int) -> None:
        in_team = state == Qt.CheckState.Checked.value
        if in_team:
            if name not in self._team:
                self._team.append(name)
        else:
            if name in self._team:
                self._team.remove(name)

    def _find_row(self, name: str) -> int:
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 2)
            if item and item.data(Qt.ItemDataRole.UserRole) == name:
                return row
        return -1

    def _enable_all(self) -> None:
        for row in range(self.table.rowCount()):
            widget = self.table.cellWidget(row, 0)
            if widget:
                check = widget.findChild(QCheckBox)
                if check:
                    check.blockSignals(True)
                    check.setChecked(True)
                    check.blockSignals(False)
            name_item = self.table.item(row, 2)
            if name_item:
                name = name_item.data(Qt.ItemDataRole.UserRole)
                self._enabled[name] = True

    def _disable_all(self) -> None:
        for row in range(self.table.rowCount()):
            widget = self.table.cellWidget(row, 0)
            if widget:
                check = widget.findChild(QCheckBox)
                if check:
                    check.blockSignals(True)
                    check.setChecked(False)
                    check.blockSignals(False)
            name_item = self.table.item(row, 2)
            if name_item:
                name = name_item.data(Qt.ItemDataRole.UserRole)
                self._enabled[name] = False
                if name in self._team:
                    self._team.remove(name)
                    # Update team checkbox
                    team_widget = self.table.cellWidget(row, 1)
                    if team_widget:
                        team_check = team_widget.findChild(QCheckBox)
                        if team_check:
                            team_check.blockSignals(True)
                            team_check.setChecked(False)
                            team_check.blockSignals(False)

    def _select_all_team(self) -> None:
        for row in range(self.table.rowCount()):
            widget = self.table.cellWidget(row, 1)
            if widget:
                check = widget.findChild(QCheckBox)
                if check and check.isEnabled():
                    check.blockSignals(True)
                    check.setChecked(True)
                    check.blockSignals(False)
            name_item = self.table.item(row, 2)
            if name_item:
                name = name_item.data(Qt.ItemDataRole.UserRole)
                if name not in self._team and self._enabled.get(name, True):
                    self._team.append(name)

    def _clear_team(self) -> None:
        for row in range(self.table.rowCount()):
            widget = self.table.cellWidget(row, 1)
            if widget:
                check = widget.findChild(QCheckBox)
                if check:
                    check.blockSignals(True)
                    check.setChecked(False)
                    check.blockSignals(False)
        self._team.clear()

    def _on_accept(self) -> None:
        # Ensure lead is in team if set
        if self._current_lead and self._current_lead not in self._team:
            self._team.insert(0, self._current_lead)
        # Ensure team only contains enabled models
        self._team = [m for m in self._team if self._enabled.get(m, True)]
        self.saved.emit(self._enabled, self._team)
        self.accept()

    def get_results(self) -> tuple[dict[str, bool], list[str]]:
        """Return (enabled_dict, team_list)."""
        return self._enabled, self._team


def load_enabled_from_config() -> dict[str, bool]:
    """Load enabled models from config.toml, with fallback to all True."""
    enabled = config_module.get_enabled_models()
    if not enabled:
        # Default: all models enabled
        return {name: True for name in REGISTRY.names()}
    # Ensure all registry models have an entry
    result = {}
    for name in REGISTRY.names():
        result[name] = enabled.get(name, True)
    return result


def save_enabled_to_config(enabled: dict[str, bool]) -> None:
    """Save enabled models to config.toml."""
    config_module.save_enabled_models(enabled)


__all__ = ["ModelSelectorDialog", "load_enabled_from_config", "save_enabled_to_config"]
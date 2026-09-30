"""Agentdeck panel for hexmind — displays agentdeck items (skills, agents, commands) discovered
from the agentdeck data model.

This panel embeds agentdeck's data model and presents items in a searchable table, allowing
users to browse and search their agentdeck inventory from within hexmind. Follows the
hexmind visual grammar (dark substrate, signal hues, measured restraint).
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QModelIndex, QSortFilterProxyModel, QEvent, QAbstractTableModel
from PySide6.QtGui import QColor, QFont, QCursor, QAction
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem, QHeaderView,
    QLineEdit, QPushButton, QLabel, QAbstractItemView, QAbstractScrollArea,
    QFrame, QSpacerItem, QSizePolicy, QSizeGrip, QMenu
)


class AgentdeckPanel(QWidget):
    """Panel that displays agentdeck items in a searchable table, following hexmind visual grammar."""

    #: Signal emitted when an item is double-clicked
    itemActivated = pyqtSignal(object)  # Item

    #: Signal emitted when request copy of item ID
    copyIdRequested = pyqtSignal(str)

    def __init__(self, items: list, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumWidth(600)
        self.setMinimumHeight(400)
        self._items = items or []
        self._selected_item: object | None = None
        self._setup_ui()
        self._populate_table()
        # Install event filter for hover effects
        self.table.viewport().installEventFilter(self)

    # ── Colours (hexmind visual grammar) ────────────────────────────────

    from hexmind.qt.theme import (  # noqa: F811 — injected by host at runtime
        SUBSTRATE, PANEL, PANEL_EDGE, GRID,
        INK, INK_DIM, INK_FAINT,
        CYAN, VIOLET, GREEN, AMBER, RED, SLATE,
        STATE_HUE,
    )

    # ── UI Construction ──────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(4)

        # ── Search bar ────────────────────────────────────────────────────
        search_row = QHBoxLayout()
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("🔍 Search agentdeck items…")
        self.search_box.setClearButtonEnabled(True)
        self.search_box.textChanged.connect(self._on_search_changed)
        search_row.addWidget(self.search_box, 1)

        self.clear_search = QPushButton("Clear")
        self.clear_search.setToolTip("Clear search (Esc)")
        self.clear_search.setEnabled(False)
        self.clear_search.clicked.connect(self._clear_search)
        search_row.addWidget(self.clear_search)

        # Search shortcut hint
        self.shortcut_hint = QLabel("⌘K / Ctrl+K")
        self.shortcut_hint.setStyleSheet(f"color: {INK_DIM}; font-size: 10pt;")
        search_row.addWidget(self.shortcut_hint)

        lay.addLayout(search_row)

        # ── Table view ─────────────────────────────────────────────────────
        self.table = QTableWidget(0, 7)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)  # We draw our own grid per design rules
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)  # Description stretches
        self.table.verticalHeader().setVisible(False)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)
        self.table.horizontalHeader().setDefaultSectionSize(120)  # Minimum section size

        # Set column headers per hexmind conventions
        self.table.setHorizontalHeaderLabels(["Kind", "Name", "Provider", "Scope", "Description", "Status", "Warnings"])

        # Set column width proportions (roughly)
        # Kind: 40, Name: 200, Provider: 100, Scope: 80, Description: 300 (stretched), Status: 80, Warnings: 120
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Fixed)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Fixed)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.Fixed)
        self.table.horizontalHeader().setSectionResizeMode(6, QHeaderView.Fixed)

        lay.addWidget(self.table, 1)

        # ── Status bar ─────────────────────────────────────────────────────
        self.status = QLabel("")
        self.status.setStyleSheet(f"color: {INK_DIM}; font-size: 11pt;")
        self.status.setTextInteractionFlags(Qt.TextSelectableByMouse)
        lay.addWidget(self.status)

        # ── Resize grip (for standalone use) ───────────────────────────────
        # Only show if widget is top-level (not embedded)
        # self._grip = QSizeGrip(self)  # Uncomment if needed

    # ── Population ───────────────────────────────────────────────────────

    def _populate_table(self, items: list | None = None) -> None:
        """Populate the table with agentdeck items (or a filtered subset)."""
        items = items or self._items
        self.table.setRowCount(0)
        for row_idx, item in enumerate(items):
            row = self.table.rowCount()
            self.table.insertRow(row)

            # ── Kind ──────────────────────────────────────────────────────
            kind_str = str(item.kind).split(".")[-1] if "." in str(item.kind) else str(item.kind)
            kind_item = QTableWidgetItem(kind_str)
            kind_item.setData(Qt.ItemDataRole.UserRole, item.id)
            # Color-code by kind kind
            kind_lower = str(item.kind).lower()
            if "skill" in kind_lower:
                kind_item.setForeground(QColor(self.CYAN))
            elif "agent" in kind_lower:
                kind_item.setForeground(QColor(self.VIOLET))
            elif "command" in kind_lower:
                kind_item.setForeground(QColor(self.AMBER))
            else:
                kind_item.setForeground(QColor(self.INK))
            self.table.setItem(row, 0, kind_item)

            # ── Name ──────────────────────────────────────────────────────
            name_item = QTableWidgetItem(item.name)
            name_item.setData(Qt.ItemDataRole.UserRole, item.id)
            # Truncate with tooltip
            self._set_tooltip(name_item, item.name)
            self.table.setItem(row, 1, name_item)

            # ── Provider ──────────────────────────────────────────────────
            prov = item.provider or "-"
            prov_item = QTableWidgetItem(prov)
            self._set_tooltip(prov_item, prov)
            self.table.setItem(row, 2, prov_item)

            # ── Scope ─────────────────────────────────────────────────────
            scope = item.scope or "-"
            scope_item = QTableWidgetItem(scope)
            self._set_tooltip(scope_item, scope)
            self.table.setItem(row, 3, scope_item)

            # ── Description ───────────────────────────────────────────────
            desc = item.description or "-"
            desc_item = QTableWidgetItem(desc)
            self._set_tooltip(desc_item, desc)
            self.table.setItem(row, 4, desc_item)

            # ── Status ─────────────────────────────────────────────────────
            status_text = "✓" if item.enabled else "✗"
            status_item = QTableWidgetItem(status_text)
            # Color by status using hexmind STATE_HUE
            status_key = "enabled" if item.enabled else "disabled"
            status_color = STATE_HUE.get(status_key, self.INK)
            status_item.setForeground(QColor(status_color))
            # Tooltip with full state info
            self._set_tooltip(status_item, f"{'Enabled' if item.enabled else 'Disabled'}")
            self.table.setItem(row, 5, status_item)

            # ── Warnings ───────────────────────────────────────────────────
            warns = item.warnings or []
            warns_text = "; ".join(str(w) for w in warns) if warns else ""
            warns_item = QTableWidgetItem(warns_text)
            if warns:
                warns_item.setForeground(QColor(self.AMBER))
                warns_item.setToolTip("\n".join(str(w) for w in warns))
            else:
                warns_item.setForeground(QColor(self.INK_DIM))
            self._set_tooltip(warns_item, warns_text or "No warnings")
            self.table.setItem(row, 6, warns_item)

        # Row count update for status
        self._update_status(len(items))

    # ── Search & Filter ──────────────────────────────────────────────────

    def _on_search_changed(self, text: str) -> None:
        """Filter table rows based on search text."""
        if not text:
            self.clear_search.setEnabled(False)
            self._populate_table(self._items)
            self.status.setText("")
            return

        self.clear_search.setEnabled(True)
        search_lower = text.lower()
        filtered = []

        for item in self._items:
            name_lower = item.name.lower()
            desc_lower = (item.description or "").lower()
            prov_lower = (item.provider or "").lower()
            kind_lower = str(item.kind).lower()
            scope_lower = (item.scope or "").lower()

            matches = (
                search_lower in name_lower
                or search_lower in desc_lower
                or search_lower in prov_lower
                or search_lower in kind_lower
                or search_lower in scope_lower
            )

            if matches:
                filtered.append(item)

        self._populate_table(filtered)

        if not filtered:
            self.status.setText(f'No items match "{text}".')
        else:
            self.status.setText(f"{len(filtered)} item{'s' if len(filtered) != 1 else ''} found")

    def _clear_search(self) -> None:
        """Clear the search field and show all items."""
        self.search_box.clear()

    # ── Selection ────────────────────────────────────────────────────────

    def get_selected_item(self) -> object | None:
        """Return the selected item, or None if nothing is selected."""
        selected = self.table.currentItem()
        if selected is None:
            return None
        row = selected.row()
        if 0 <= row < len(self._items):
            return self._items[row]
        return None

    # ── Context Menu ─────────────────────────────────────────────────────

    def _show_context_menu(self, position: int) -> None:
        """Show context menu on right-click."""
        item = self.table.itemAt(position)
        if item is None:
            return

        row = item.row()
        if not (0 <= row < len(self._items)):
            return

        selected = self._items[row]
        menu = QMenu(self)

        # Copy ID action
        copy_id_action = QAction("Copy ID", self)
        copy_id_action.setToolTip("Copy item identifier")
        copy_id_action.triggered.connect(lambda: self.copyIdRequested.emit(selected.id))
        menu.addAction(copy_id_action)

        # Copy name action
        copy_name_action = QAction("Copy Name", self)
        copy_name_action.triggered.connect(lambda: QApplication.clipboard().setText(selected.name))
        menu.addAction(copy_name_action)

        # Favorite toggle (placeholder - would need state management)
        fav_action = QAction("Add to Favorites" if not getattr(selected, "_favorited", False) else "Remove from Favorites", self)
        menu.addAction(fav_action)

        # Separator
        menu.addSeparator()

        # Open details action
        details_action = QAction("View Details", self)
        details_action.triggered.connect(self._view_details)
        menu.addAction(details_action)

        # Execute at cursor position
        menu.exec(self.table.viewport().mapToGlobal(position))

    def _view_details(self) -> None:
        """Show details of selected item (placeholder for detail view)."""
        selected = self.get_selected_item()
        if selected:
            # Emit signal or open detail dialog
            pass  # TODO: implement detail view

    # ── Event Filter for Hover ───────────────────────────────────────────

    def eventFilter(self, obj, event):
        """Handle hover events for row highlighting."""
        if obj == self.table.viewport() and event.type() == QEvent.MouseMove:
            # Find the row under the cursor
            index = self.table.indexAt(event.pos())
            if index.isValid():
                row = index.row()
                # Could highlight row here
                pass
        return super().eventFilter(obj, event)

    # ── Helper Methods ───────────────────────────────────────────────────

    @staticmethod
    def _set_tooltip(item: QTableWidgetItem, text: str) -> None:
        """Set tooltip text, handling ellipsis and newlines."""
        if not text:
            item.setToolTip("")
            return
        # Replace newlines with spaces for tooltip
        tooltip = text.replace("\n", " | ")
        # Truncate if too long (QToolTip has limits)
        if len(tooltip) > 200:
            tooltip = tooltip[:197] + "..."
        item.setToolTip(tooltip)

    def _update_status(self, count: int) -> None:
        """Update the status bar text."""
        if count == 0:
            self.status.setText("No items")
        elif count == 1:
            self.status.setText("1 item")
        else:
            self.status.setText(f"{count} items")

    # ── Keyboard Support ─────────────────────────────────────────────────

    def keyPressEvent(self, event) -> None:
        """Handle keyboard shortcuts."""
        key = event.key()
        text = event.text()

        # Ctrl/Cmd + K to focus search
        if (event.modifiers() & Qt.ControlModifier) and text.lower() == "k":
            self.search_box.setFocus()
            self.search_box.selectAll()
            event.accept()
            return

        # Delete to clear search
        if key == Qt.Key_Delete or key == Qt.Key_Backspace:
            if self.search_box.hasFocus():
                self._clear_search()
                event.accept()
                return

        super().keyPressEvent(event)
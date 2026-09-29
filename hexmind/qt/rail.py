"""The presentation-only workspace shell for the standalone Hexmind window."""
from __future__ import annotations

from collections.abc import Mapping

from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)


class BenchRail(QWidget):
    """A fixed-width workspace rail around one injected Room widget."""

    page_names = ("Room", "Direct Line", "Calibration Rack", "Settings")

    def __init__(
        self,
        room: QWidget,
        parent: QWidget | None = None,
        workspace_pages: Mapping[str, QWidget] | None = None,
    ) -> None:
        super().__init__(parent)
        self.room = room
        self.navigation = QWidget(self)
        self.navigation.setAccessibleName("Workspace navigation")
        self.navigation.setFixedWidth(56)
        self.stack = QStackedWidget(self)
        self.stack.setAccessibleName("Workspaces")
        self.pages: dict[str, QWidget] = {
            "Room": room,
            "Direct Line": self._placeholder("Direct Line"),
            "Calibration Rack": self._placeholder("Calibration Rack"),
            "Settings": self._placeholder("Settings"),
        }
        if workspace_pages:
            invalid_names = set(workspace_pages).difference(self.page_names).union(
                {"Room"} if "Room" in workspace_pages else set()
            )
            if invalid_names:
                raise ValueError(f"Unsupported workspace pages: {', '.join(sorted(invalid_names))}")
            self.pages.update(workspace_pages)
        self.buttons: dict[str, QToolButton] = {}

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        navigation_layout = QVBoxLayout(self.navigation)
        navigation_layout.setContentsMargins(0, 0, 0, 0)
        navigation_layout.setSpacing(0)
        for index, name in enumerate(self.page_names):
            self.stack.addWidget(self.pages[name])
            button = QToolButton(self.navigation)
            button.setText(name)
            button.setToolTip(name)
            button.setAccessibleName(f"Open {name} workspace")
            button.setCheckable(True)
            button.setAutoExclusive(True)
            button.clicked.connect(lambda checked=False, workspace=name: self.set_workspace(workspace))
            navigation_layout.addWidget(button)
            self.buttons[name] = button
        navigation_layout.addStretch()

        layout.addWidget(self.navigation)
        layout.addWidget(self.stack)
        self.set_workspace("Room")

    @staticmethod
    def _placeholder(name: str) -> QWidget:
        page = QWidget()
        page.setAccessibleName(f"{name} workspace")
        layout = QVBoxLayout(page)
        label = QLabel(f"{name}\nComing soon", page)
        label.setAccessibleName(f"{name} placeholder")
        layout.addWidget(label)
        return page

    @property
    def current_workspace(self) -> str:
        """Return the selected workspace name."""
        return self.page_names[self.stack.currentIndex()]

    def set_workspace(self, name: str) -> None:
        """Select a workspace by its roadmap name."""
        if name not in self.pages:
            raise ValueError(f"Unknown workspace: {name}")
        index = self.page_names.index(name)
        self.stack.setCurrentIndex(index)
        self.buttons[name].setChecked(True)


__all__ = ["BenchRail"]

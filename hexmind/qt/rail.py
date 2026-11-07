"""The presentation-only workspace shell for the standalone Hexmind window."""
from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from PySide6.QtCore import QByteArray, QSize, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from . import theme

ICONS = Path(__file__).parent / "icons"
ICON_SIZE = 22

#: The short label under each icon, and its icon file. The full name stays in the tooltip and the
#: accessible name, which starts with the visible label (WCAG 2.5.3).
RAIL = {
    "Room": ("Room", "rail-room.svg"),
    "Direct Line": ("Direct", "rail-direct.svg"),
    "Calibration Rack": ("Models", "rail-models.svg"),
    "Settings": ("Settings", "rail-settings.svg"),
}


def rail_icon(filename: str, size: int = ICON_SIZE, ratio: float = 2.0) -> QIcon:
    """The rail SVGs are drawn in `currentColor`; QtSvg cannot tint, so each state is rendered with
    its own hue: dim at rest, ink under the pointer, violet when the workspace is selected."""
    source = (ICONS / filename).read_text(encoding="utf-8")
    icon = QIcon()
    for color, mode, state in ((theme.INK_DIM, QIcon.Mode.Normal, QIcon.State.Off),
                               (theme.INK, QIcon.Mode.Active, QIcon.State.Off),
                               (theme.VIOLET, QIcon.Mode.Normal, QIcon.State.On),
                               (theme.VIOLET, QIcon.Mode.Active, QIcon.State.On)):
        renderer = QSvgRenderer(QByteArray(source.replace("currentColor", color).encode()))
        pixmap = QPixmap(round(size * ratio), round(size * ratio))
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        renderer.render(painter)
        painter.end()
        pixmap.setDevicePixelRatio(ratio)
        icon.addPixmap(pixmap, mode, state)
    return icon


class BenchRail(QWidget):
    """An icon rail of workspaces around one injected Room widget."""

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
        self.navigation.setObjectName("benchRail")  # styled by theme.stylesheet(), never here
        self.navigation.setAccessibleName("Workspace navigation")
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
        navigation_layout.setContentsMargins(6, 10, 6, 10)
        navigation_layout.setSpacing(4)
        for index, name in enumerate(self.page_names):
            self.stack.addWidget(self.pages[name])
            short, icon = RAIL[name]
            button = QToolButton(self.navigation)
            button.setText(short)
            button.setIcon(rail_icon(icon))
            button.setIconSize(QSize(ICON_SIZE, ICON_SIZE))
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            button.setToolTip(name)
            button.setAccessibleName(short if short == name else f"{short}: {name} workspace")
            button.setCheckable(True)
            button.setAutoExclusive(True)
            button.clicked.connect(lambda checked=False, workspace=name: self.set_workspace(workspace))
            navigation_layout.addWidget(button)
            self.buttons[name] = button
        navigation_layout.addStretch()
        # Sized from the labels, not pinned: a fixed 56px elided "Direct Line" to "Dir…ine".
        self.navigation.setFixedWidth(
            max(max(b.sizeHint().width() for b in self.buttons.values()), ICON_SIZE + 40) + 12)

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

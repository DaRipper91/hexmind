"""`hexmind-gui` — the room on its own, as a desktop window.

    hexmind-gui
    hexmind-gui --lead codex --audit

The embeddable widget is `hexmind.qt.HexmindWidget`, and this is deliberately *not* a fork of it.
Aether puts that widget in a tab; here it is the whole window, plus the chrome a desktop app owes
its user: a menu bar, a status bar, and a way to open a task's file in the OS default application.

**The stylesheet is applied here, not in the widget.** `docs/AETHER-INTERFACE.md` forbids
`HexmindWidget` from restyling its host — a widget that paints over the app that embeds it is a
widget nobody can embed. So the QSS has to belong to whoever owns the `QApplication`, and in an
embedded deployment that is Aether, not us. This module is the case where we *are* the host, so
`theme.stylesheet()` is ours to apply. If a rule is missing here it is missing everywhere; the fix
belongs in `theme.py`, never in a local `setStyleSheet` call.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import threading
import time
from typing import Any

from PySide6.QtGui import QAction, QIcon, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QMainWindow,
    QMenu,
    QMessageBox,
    QSystemTrayIcon,
    QWidget,
)

from .. import config
from ..desktop import install_desktop_entry
from . import theme
from .chat import DirectLine
from .models import CalibrationRack
from .rail import BenchRail
from .settings import SettingsPage

APP_NAME = "Hexmind"
ORG_NAME = "hexmind"


class HexmindWindow(QMainWindow):
    """A window that owns the stylesheet and a menu bar, wrapped around one room."""

    def __init__(self, room: QWidget | None = None, **room_kwargs: Any) -> None:
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} — multi-model agent team")
        self.resize(1280, 820)

        # `room` is injectable so a test can stand a window up around a stub, and so the window is
        # never the reason a room fails to build.
        self.room = room if room is not None else self._build_room(**room_kwargs)
        self.settings_page = SettingsPage(parent=self)
        self.calibration_rack = CalibrationRack(parent=self)
        self.direct_line = DirectLine(parent=self)
        self.bench_rail = BenchRail(
            self.room,
            self,
            workspace_pages={
                "Direct Line": self.direct_line,
                "Calibration Rack": self.calibration_rack,
                "Settings": self.settings_page,
            },
        )
        self.setCentralWidget(self.bench_rail)
        self._turn_started_at: float | None = None
        self._notification_defaults = config.get_notification_defaults()
        self.tray_icon: QSystemTrayIcon | None = None
        self._setup_notifications()
        open_file_requested = getattr(self.room, "openFileRequested", None)
        connect = getattr(open_file_requested, "connect", None)
        if callable(connect):
            connect(self.open_path)
        self._build_menus()
        self.statusBar().showMessage(f"working in {getattr(self.room, 'cwd', os.getcwd())}")
        try:
            from PySide6.QtCore import QByteArray

            gui_cfg = config.load_config().get("gui", {})
            if "geometry" in gui_cfg:
                self.restoreGeometry(QByteArray.fromHex(gui_cfg["geometry"].encode("ascii")))
        except (OSError, TypeError, ValueError):
            self.statusBar().showMessage("Could not restore saved window geometry")

    def _build_room(self, **room_kwargs: Any) -> QWidget:
        """Stand up the room with an audit ledger wired in.

        This is the module that *is* the application, so it is where the ledger's location gets
        decided — the same way the CLI (`__main__.py:104`) and the TUI do it. The widget itself
        only forwards what it is handed, so an embedded host stays free to point the room at
        whatever ledger it already keeps."""
        from .. import auditor
        from .stats import stats_path
        from .widget import HexmindWidget

        return HexmindWidget(stats=auditor.Stats(stats_path()), **room_kwargs)

    def _build_menus(self) -> None:
        # The menus are kept as attributes, not just used as locals. `QMenuBar.actions()[i].menu()`
        # hands back a *temporary* wrapper, and PySide6 lets the underlying C++ `QMenu` be deleted
        # with it — so anything that round-trips through `action.menu()` is a use-after-free waiting
        # to happen. Holding the reference on the window is the only way to keep them inspectable.
        file_menu = self.file_menu = self.menuBar().addMenu("&File")

        # A double-clicked path in a task title arrives as `openFileRequested`; the widget is
        # deliberately not allowed to know what an "open" means, because in Aether it means
        # "open in the editor tab", not "launch xdg-open". Here it means the OS default.
        self.open_action = QAction("Open &File…", self)
        self.open_action.setShortcut(QKeySequence.StandardKey.Open)
        self.open_action.triggered.connect(self._open_file_dialog)
        file_menu.addAction(self.open_action)
        file_menu.addSeparator()
        self.quit_action = QAction("&Quit", self)
        self.quit_action.setShortcut(QKeySequence.StandardKey.Quit)
        self.quit_action.triggered.connect(self.close)
        file_menu.addAction(self.quit_action)

        room_menu = self.room_menu = self.menuBar().addMenu("&Room")
        self.refresh_action = QAction("&Refresh team", self)
        self.refresh_action.setShortcut(QKeySequence.StandardKey.Refresh)
        self.refresh_action.triggered.connect(self._refresh_team)
        room_menu.addAction(self.refresh_action)
        # Phase 0.4 (P11): the menu entry opens the room's palette. It carries no QKeySequence
        # of its own — the widget owns the single live Ctrl+K QShortcut — so a menu click opens
        # the palette once instead of double-firing it. Duck-typed like every action here, so a
        # partial room answers without raising.
        self.palette_action = QAction("Command palette (Ctrl+K)…", self)
        self.palette_action.setToolTip("Ctrl+K")
        self.palette_action.triggered.connect(self._open_palette)
        room_menu.addAction(self.palette_action)
        self.stats_action = QAction("Reload &stats", self)
        self.stats_action.triggered.connect(self._reload_stats)
        room_menu.addAction(self.stats_action)

        help_menu = self.help_menu = self.menuBar().addMenu("&Help")
        self.about_action = QAction("&About", self)
        self.about_action.triggered.connect(self._about)
        help_menu.addAction(self.about_action)

    def _setup_notifications(self) -> None:
        turn_state = getattr(self.room, "turnState", None)
        connect = getattr(turn_state, "connect", None)
        if callable(connect):
            connect(self._on_turn_state)

        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        tray = QSystemTrayIcon(QIcon.fromTheme("dialog-information"), self)
        tray.setToolTip(APP_NAME)
        menu = QMenu(self)
        show_action = menu.addAction("Show Hexmind")
        show_action.triggered.connect(self.showNormal)
        menu.addSeparator()
        quit_action = menu.addAction("Quit")
        quit_action.triggered.connect(self.close)
        tray.setContextMenu(menu)
        tray.show()
        self.tray_icon = tray

    def _on_turn_state(self, in_flight: bool) -> None:
        if in_flight:
            self._turn_started_at = time.monotonic()
            return
        started = self._turn_started_at
        self._turn_started_at = None
        if started is None:
            return
        elapsed = time.monotonic() - started
        if elapsed < self._notification_defaults.threshold_seconds:
            return

        title = f"{APP_NAME} turn complete"
        body = f"Finished after {round(elapsed)} seconds."
        if self.tray_icon is not None:
            self.tray_icon.showMessage(
                title,
                body,
                QSystemTrayIcon.MessageIcon.Information,
                5000,
            )
        if self._notification_defaults.phone_buzz:
            from ..notify import notify

            threading.Thread(
                target=notify,
                args=(title, body),
                name="hexmind-notification",
                daemon=True,
            ).start()

    # ---------- actions, all duck-typed so a stub room works too ----------

    def open_path(self, path: str) -> None:
        """Hand a path to the OS. Failures are reported, never raised: a missing file must not take
        the window down mid-conversation."""
        if not path:
            return
        try:
            if sys.platform == "darwin":
                subprocess.Popen(["open", path])
            elif os.name == "nt":
                os.startfile(path)  # type: ignore[attr-defined]
            else:
                subprocess.Popen(["xdg-open", path])
        except Exception as exc:  # noqa: BLE001 - presentation must not crash the room
            QMessageBox.warning(self, "Could not open file", f"{path}\n\n{exc}")

    def _open_file_dialog(self) -> None:
        start = getattr(self.room, "cwd", os.getcwd())
        path, _ = QFileDialog.getOpenFileName(self, "Open file", start)
        if path:
            self.open_path(path)

    def _refresh_team(self) -> None:
        refresh = getattr(self.room, "refresh_team", None)
        if callable(refresh):
            refresh()

    def _open_palette(self) -> None:
        opener = getattr(self.room, "open_palette", None)
        if callable(opener):
            opener()

    def _reload_stats(self) -> None:
        stats = getattr(self.room, "stats", None)
        reload_ = getattr(stats, "reload", None)
        if callable(reload_):
            reload_()

    def _about(self) -> None:
        QMessageBox.about(
            self,
            f"About {APP_NAME}",
            f"<b>{APP_NAME}</b> — a multi-model agent team in one room.<br><br>"
            "Same orchestrator, backends and model registry as the TUI and <code>--once</code>; "
            "this window is presentation only.<br><br>"
            "Ctrl+K for the command palette, Ctrl+L to clear the transcript.",
        )

    def closeEvent(self, event) -> None:  # Qt's spelling, not ours
        """The room is a QThread, and a QThread destroyed while running aborts the process. The
        widget's own `closeEvent` stops it, and Qt walks central widgets, so this only has to make
        sure the widget actually gets the event."""
        self.room.close()
        try:
            from .. import config
            geo = bytes(self.saveGeometry().toHex()).decode("ascii")
            config.save_section("gui", {"geometry": geo})
        except (OSError, TypeError, ValueError):
            self.statusBar().showMessage("Could not save window geometry")
        super().closeEvent(event)


def build_parser() -> argparse.ArgumentParser:
    """The room's knobs, mirroring `hexmind`'s own flags so the two entry points are learnable as
    one. Only the ones a window can honour are here — no `--once`, `--serve` or `--timeout`, since
    those describe a headless run."""
    p = argparse.ArgumentParser(prog="hexmind-gui", description=APP_NAME + " as a desktop window.")
    p.add_argument("--lead", default=None, metavar="AGENT",
                   help="agent that plans and summarizes (pick it here if you do not pass one)")
    p.add_argument("--without", action="append", default=[], metavar="AGENT",
                   help="leave an agent out, e.g. --without codex (repeatable)")
    p.add_argument("--with", dest="with_", action="append", default=[], metavar="AGENT",
                   help="add an opt-in member, e.g. --with qwen (local model; slow on small machines)")
    p.add_argument("--audit", action="store_true",
                   help="start with the runner-up audit loop on (toggle in room: /audit on|off)")
    p.add_argument("--cwd", default=None, help="folder the team works in (default: current)")
    p.add_argument("--install-desktop", action="store_true",
                   help="install a per-user desktop menu entry for hexmind-gui")
    return p


def main(argv: list[str] | None = None) -> int:
    """Build the application, the window and the room, then hand control to Qt."""
    args = build_parser().parse_args(argv)

    if args.install_desktop:
        try:
            desktop_path = install_desktop_entry()
        except (OSError, ValueError) as exc:
            print(f"hexmind-gui: {exc}", file=sys.stderr)
            return 1
        print(f"Installed desktop entry: {desktop_path}")
        return 0

    from .. import config
    from ..backends import available
    from ..core import OPT_IN, ROSTER

    room_cfg = config.load_config().get("room", {})
    lead = args.lead
    if lead is None and room_cfg.get("lead"):
        lead = str(room_cfg["lead"])

    audit = args.audit
    if not audit and "audit" in room_cfg and not any(arg.startswith("--audit") for arg in (argv or sys.argv[1:])):
        audit = bool(room_cfg["audit"])

    cwd = os.path.abspath(args.cwd or os.getcwd())
    # The widget discovers the roster itself when `members` is None, but the --without/--with
    # filters have already been applied here, so pass the filtered list through.
    configured_members = room_cfg.get("members")
    default_members = list(ROSTER)
    if (
        not args.without
        and not args.with_
        and isinstance(configured_members, list)
        and all(isinstance(member, str) for member in configured_members)
    ):
        default_members = configured_members
    members = [m for m in available(default_members) if m not in args.without
               and (m not in OPT_IN or m in args.with_)]

    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(ORG_NAME)
    # Applied once, by the process that owns the application. See the module docstring: the widget
    # must not do this, or it would repaint whatever host embedded it.
    app.setStyleSheet(theme.stylesheet())

    if not members:
        # A window that opens with an empty roster and no explanation is the worst first run: the
        # user cannot tell "no team" from "broken". Say it plainly and stop.
        QMessageBox.critical(
            None,
            "No team available",
            "No hexmind agent CLIs were found on your PATH.\n\n"
            "Install at least one of claude, agy, codex, opencode, copilot, kimi "
            "and start hexmind-gui again.",
        )
        return 1

    if lead is not None and lead not in members:
        QMessageBox.critical(
            None,
            "That lead is not installed",
            f"'{lead}' is not one of the installed members:\n\n  "
            + ", ".join(members),
        )
        return 1

    # One window, one room. Building the room via a throwaway HexmindWindow and then wrapping it in
    # a second one would hand the first window's closeEvent to the room when that window is garbage
    # collected -- which stops the room's QThread out from under the window we are about to show.
    try:
        window = HexmindWindow(members=members, lead=lead, audit=audit, cwd=cwd)
    except Exception as exc:  # noqa: BLE001 - a bad flag should not be a bare traceback
        QMessageBox.critical(None, f"{APP_NAME} could not start", str(exc))
        return 1

    window.show()
    return app.exec()


__all__ = ["HexmindWindow", "build_parser", "main"]

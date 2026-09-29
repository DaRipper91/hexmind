"""The standalone `hexmind-gui` window, offscreen.

The window is thin on purpose — chrome around a room that is tested in test_qt.py. What is worth
pinning here is the contract that makes it *safe to be a host*: it applies the stylesheet itself
(the widget must not), it never builds the room twice, and every menu action is duck-typed so a
partial room cannot take the window down. Those are the three ways this file could quietly rot.

Skipped as a whole without PySide6, like every other Qt test here. Run with
`QT_QPA_PLATFORM=offscreen`.
"""
from __future__ import annotations

import os
import sys
from types import SimpleNamespace

import pytest

pytest.importorskip("PySide6", reason="the qt extra is not installed")

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QApplication, QWidget

from hexmind.qt import app as A
from hexmind.qt import theme
from hexmind.qt.chat import DirectLine
from hexmind.qt.models import CalibrationRack
from hexmind.qt.rail import BenchRail
from hexmind.qt.settings import SettingsPage


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication(sys.argv[:1])
    yield app


class StubRoom(QWidget):
    """Just enough room for the window's actions. If a menu entry ever hard-references a real
    `HexmindWidget` attribute, this stops being a valid stand-in and the test below fails."""

    def __init__(self) -> None:
        super().__init__()
        self.cwd = "/tmp/hexmind-stub"
        self.refreshed = 0
        self.reloaded = 0
        self.stats = self  # the window reaches stats.reload(), not room.reload()

    def refresh_team(self) -> None:
        self.refreshed += 1

    def reload(self) -> None:
        self.reloaded += 1


class FileRoom(StubRoom):
    openFileRequested = Signal(str)


class NotificationRoom(StubRoom):
    turnState = Signal(bool)


@pytest.fixture
def room(qapp):
    r = StubRoom()
    yield r
    # No `deleteLater()`: the window adopted the room as its central widget, so the room's C++
    # object is already gone by the time the window is collected. Touching it here is a
    # use-after-free, not a tidy-up.


@pytest.fixture
def window(qapp, room):
    w = A.HexmindWindow(room=room)
    yield w
    w.close()
    w.deleteLater()


# ---------- construction ----------


def test_window_wraps_the_injected_room_in_a_bench_rail(window, room):
    assert isinstance(window.centralWidget(), BenchRail)
    assert window.room is room
    assert window.centralWidget().stack.currentWidget() is room
    assert window.centralWidget().stack.widget(0) is room
    assert isinstance(window.settings_page, SettingsPage)
    assert window.centralWidget().pages["Settings"] is window.settings_page
    assert isinstance(window.calibration_rack, CalibrationRack)
    assert window.centralWidget().pages["Calibration Rack"] is window.calibration_rack
    assert isinstance(window.direct_line, DirectLine)
    assert window.centralWidget().pages["Direct Line"] is window.direct_line


def test_window_titles_and_sizes_itself(window):
    assert A.APP_NAME in window.windowTitle()
    assert window.width() > 0 and window.height() > 0


def test_status_bar_reports_the_rooms_cwd(window, room):
    assert room.cwd in window.statusBar().currentMessage()


def test_long_turn_uses_saved_phone_notification_without_blocking(qapp, monkeypatch):
    room = NotificationRoom()
    monkeypatch.setattr(A.QSystemTrayIcon, "isSystemTrayAvailable", staticmethod(lambda: False))
    monkeypatch.setattr(
        A.config,
        "get_notification_defaults",
        lambda: SimpleNamespace(phone_buzz=True, threshold_seconds=30),
    )
    clock = iter((100.0, 135.0))
    monkeypatch.setattr(A.time, "monotonic", lambda: next(clock))
    sent = []

    def fake_thread(*, target, args, name, daemon):
        sent.append((target, args, name, daemon))
        target(*args)
        return SimpleNamespace(start=lambda: None)

    monkeypatch.setattr(A.threading, "Thread", fake_thread)
    from hexmind import notify as notify_module

    monkeypatch.setattr(notify_module, "notify", lambda *args: sent.append(args))
    window = A.HexmindWindow(room=room)
    room.turnState.emit(True)
    room.turnState.emit(False)
    assert sent and sent[-1][0] == "Hexmind turn complete"
    window.close()
    window.deleteLater()


def test_close_reaches_the_central_widget(qapp, room):
    """`closeEvent` must forward, or the room's QThread is destroyed while running and Qt aborts the
    whole process — which no assertion in this file would survive to report."""
    closed = []
    room.closeEvent = lambda event: closed.append(event)
    A.HexmindWindow(room=room).close()
    assert len(closed) == 1


# ---------- menus are wired, and wired to duck-typed calls ----------


def _action(window, menu_attr, needle):
    """Find an action by substring, through a menu the window holds a reference to.

    Deliberately *not* `menuBar().actions()[i].menu()`: that returns a temporary wrapper, and
    PySide6 will let the C++ QMenu be deleted along with it. The production code keeps the menus on
    the window for the same reason, so the test reads them the same way the app would."""
    menu = getattr(window, menu_attr)
    return next(a for a in menu.actions() if needle in a.text())


def test_the_three_menus_exist(window):
    titles = [getattr(window, attr).title()
              for attr in ("file_menu", "room_menu", "help_menu")]
    for expected in ("&File", "&Room", "&Help"):
        assert expected in titles
    # ...and that they are the ones actually on the bar, in order.
    assert [a.menu().title() for a in window.menuBar().actions()] == titles


def test_every_action_is_reachable_from_the_menu_that_owns_it(window):
    """An action built but never added to a menu is invisible; an action added to the wrong menu is
    worse. The attributes and the menus have to agree."""
    for menu_attr, action_attr in (
        ("file_menu", "open_action"),
        ("file_menu", "quit_action"),
        ("room_menu", "refresh_action"),
        ("room_menu", "palette_action"),
        ("room_menu", "stats_action"),
        ("help_menu", "about_action"),
    ):
        assert getattr(window, action_attr) in getattr(window, menu_attr).actions()


def test_refresh_action_calls_the_room(window, room):
    action = _action(window, "room_menu", "Refresh team")
    assert action.text() == "&Refresh team"
    action.trigger()
    assert room.refreshed == 1


def test_reload_stats_action_reaches_through_the_stats_attribute(window, room):
    _action(window, "room_menu", "stats").trigger()
    assert room.reloaded == 1


def test_palette_entry_opens_the_room_palette(window, room):
    """Phase 0.4 (P11): the menu entry is a live path to the room's Ctrl+K palette, not a dead
    control. Duck-typed, so the StubRoom — which has no `open_palette` — answers a click by
    doing nothing instead of raising."""
    opened = []
    room.open_palette = lambda: opened.append(True)
    entry = _action(window, "room_menu", "palette")
    assert entry.isEnabled()
    entry.trigger()
    assert opened == [True]


def test_palette_entry_without_a_room_palette_does_not_raise(window):
    """A partial room (no `open_palette`) must not take the window down mid-conversation."""
    _action(window, "room_menu", "palette").trigger()


def test_palette_action_carries_no_shortcut(window):
    """The widget owns the single live Ctrl+K QShortcut. If this action ever gains its own
    QKeySequence, one keypress fires the palette twice — this test catches that regression."""
    entry = _action(window, "room_menu", "palette")
    assert entry.shortcut().isEmpty(), "Ctrl+K must fire exactly once, from the widget"
    assert entry.toolTip() == "Ctrl+K"


def test_quit_action_closes_the_window(window):
    quit_action = _action(window, "file_menu", "Quit")
    assert quit_action.isEnabled()
    quit_action.trigger()
    assert not window.isVisible()


def test_open_action_has_a_standard_shortcut(window):
    open_action = _action(window, "file_menu", "Open")
    assert open_action.shortcut().toString()  # Ctrl+O on every platform Qt supports


# ---------- open_path: never raises, never shells out ----------


def test_open_path_ignores_an_empty_path(window):
    window.open_path("")  # must not raise, must not launch anything


def test_open_path_never_goes_through_a_shell(window, monkeypatch):
    """A filename comes from task titles, which come from models. `shell=True` here would be a
    command injection with a model in the loop, so the argv form is the contract."""
    seen = {}

    class FakePopen:
        def __init__(self, argv, *a, **kw):
            seen["argv"] = argv
            seen["kwargs"] = kw

    monkeypatch.setattr(A.subprocess, "Popen", FakePopen)
    monkeypatch.setattr(A.sys, "platform", "linux")
    monkeypatch.setattr(A.os, "name", "posix")

    window.open_path("/tmp/a file; rm -rf.txt")
    assert seen["argv"][0] == "xdg-open"
    assert seen["argv"][1] == "/tmp/a file; rm -rf.txt"  # one argv slot, not a command line
    assert "shell" not in seen["kwargs"]


def test_open_path_reports_a_failure_instead_of_raising(window, monkeypatch):
    def boom(*a, **kw):
        raise OSError("no display")

    monkeypatch.setattr(A.subprocess, "Popen", boom)
    shown = []
    monkeypatch.setattr(A.QMessageBox, "warning",
                        lambda *a, **kw: shown.append(a[1:]))

    window.open_path("/tmp/whatever")  # the point: no exception escapes
    assert shown and shown[0][0] == "Could not open file"


def test_task_path_signal_uses_the_window_open_path(qapp, monkeypatch):
    opened = []
    monkeypatch.setattr(A.HexmindWindow, "open_path", lambda self, path: opened.append(path))
    window = A.HexmindWindow(room=FileRoom())

    window.room.openFileRequested.emit("/tmp/example.py")

    assert opened == ["/tmp/example.py"]
    window.close()
    window.deleteLater()


# ---------- the stylesheet belongs to the host ----------


class StubWindow:
    """A `HexmindWindow` with no room, no thread and no menu bar. `main()` is only interesting for
    what it does *around* the window, so this keeps the room out of it."""

    def __init__(self, room=None) -> None:
        self.room = room
        self.shown = False

    def show(self) -> None:
        self.shown = True

    def close(self) -> None:  # pragma: no cover - the real window's closeEvent is tested above
        pass


@pytest.fixture
def host(monkeypatch, qapp):
    """Turn `main()` into something runnable: a fake roster, a window that is not a room, a
    non-blocking `exec`, and a dialog-free way to see what it wanted to say."""
    from hexmind import backends

    built = []

    def _make_window(*a, **kw):
        built.append(kw)
        return StubWindow()

    monkeypatch.setattr(A, "HexmindWindow", _make_window)
    # `main()` does `from .backends import available` *inside* the function, so it resolves the
    # attribute at call time — patching the module it lives on is what actually takes effect.
    monkeypatch.setattr(backends, "available", lambda roster: ["claude", "codex"])
    monkeypatch.setattr(qapp, "exec", lambda: 0)
    said = []
    monkeypatch.setattr(A.QMessageBox, "critical", lambda *a, **kw: said.append((a[1], a[2])))
    monkeypatch.setattr(A.QMessageBox, "about", lambda *a, **kw: said.append((a[1], a[2])))

    before = qapp.styleSheet()
    try:
        yield SimpleNamespace(built=built, said=said, qapp=qapp)
    finally:
        qapp.setStyleSheet(before)


def test_main_applies_the_theme_stylesheet(host):
    """`docs/AETHER-INTERFACE.md` forbids `HexmindWidget` from restyling its host. The window is the
    case where we *are* the host, so the QSS has to land here — if it does not, the standalone app
    ships unstyled while the embedded one looks right, and nobody notices locally.

    Applied by `main()`, not by `HexmindWindow.__init__`: a `QMainWindow` does not get to assume it
    owns the `QApplication`. That is the same rule the widget is held to, one level down."""
    host.qapp.setStyleSheet("")
    assert A.main([]) == 0
    assert theme.stylesheet() and theme.stylesheet() in host.qapp.styleSheet()
    assert host.built, "main() must build the window it is about to show"


def test_main_sets_the_application_name(host):
    """QSettings scopes the widget's remembered tab index to these, so they are not cosmetic."""
    A.main([])
    assert host.qapp.applicationName() == A.APP_NAME
    assert host.qapp.organizationName() == A.ORG_NAME


def test_main_refuses_to_start_with_an_empty_roster(monkeypatch, host):
    """A window that opens with an empty team and no explanation is the worst first run: the user
    cannot tell 'nothing installed' from 'broken'. It has to say so and exit non-zero."""
    from hexmind import backends

    monkeypatch.setattr(backends, "available", lambda roster: [])
    assert A.main([]) == 1
    assert not host.built
    assert host.said and host.said[0][0] == "No team available"


def test_main_rejects_a_lead_that_is_not_installed(host):
    assert A.main(["--lead", "kimi"]) == 1
    assert not host.built
    assert host.said and "kimi" in host.said[0][1]
    assert "claude" in host.said[0][1]  # it lists what *is* there, so the fix is obvious


def test_main_builds_exactly_one_window(host):
    """The room is a QThread. Building it inside a throwaway window and showing a second one hands
    the first window's `closeEvent` to the room when that window is collected, which stops the
    thread out from under the window about to be shown."""
    A.main([])
    assert len(host.built) == 1


def test_main_passes_its_flags_to_the_room(host, tmp_path):
    """The parsed --lead/--without/--audit/--cwd used to be dropped: main() built `HexmindWindow()`
    bare, so the room ignored every flag and ran the unfiltered roster in the current folder."""
    assert A.main(["--lead", "codex", "--without", "claude", "--audit", "--cwd", str(tmp_path)]) == 0
    assert host.built == [{"members": ["codex"], "lead": "codex", "audit": True, "cwd": str(tmp_path)}]


def test_the_window_does_not_write_a_local_stylesheet(window, room):
    """One owner of the QSS. A per-widget setStyleSheet would be a second, divergent one."""
    assert room.styleSheet() == ""


# ---------- the audit ledger has to be reachable from the GUI ----------


def test_the_window_hands_the_room_an_audit_ledger(monkeypatch, qapp):
    """T16, closed. `--audit` reaches the orchestrator, and the orchestrator writes every verdict
    into `stats` — but the Qt layer never built one, so the GUI recorded no audit history at all
    while looking like it did. `HexmindWindow` is the application, so it is where the ledger's
    location is decided, exactly as it is in `__main__.py` and `tui.py`.

    The widget is stubbed rather than constructed: this asserts what the *window* passes, and
    building a real room here would start a thread for a fact about a keyword argument."""
    from hexmind import auditor
    from hexmind.qt import widget as W
    from hexmind.qt.stats import stats_path

    seen = {}

    def _fake_widget(**kwargs):
        seen.update(kwargs)
        return StubRoom()

    monkeypatch.setattr(W, "HexmindWidget", _fake_widget)
    A.HexmindWindow()

    stats = seen.get("stats")
    assert isinstance(stats, auditor.Stats), "the room must be built with an audit ledger"
    # The same ledger the CLI, the TUI and the stats panel all resolve, so the GUI is not its own
    # island of history.
    assert stats.path == stats_path() == os.path.expanduser("~/.local/share/hexmind/stats.json")


# ---------- build_parser mirrors the room's flags ----------


def test_parser_defaults():
    args = A.build_parser().parse_args([])
    assert args.lead is None
    assert args.without == [] and args.with_ == []
    assert args.audit is False
    assert args.cwd is None


def test_parser_accumulates_repeated_filters():
    args = A.build_parser().parse_args(["--without", "agy", "--without", "codex", "--with", "qwen"])
    assert args.without == ["agy", "codex"]
    assert args.with_ == ["qwen"]


def test_parser_has_none_of_the_headless_flags():
    """`--once`, `--serve` and `--timeout` describe a run with no window; honouring them here would
    be a lie. They are asserted absent so adding one is a deliberate act."""
    try:
        A.build_parser().parse_args(["--once"])
    except SystemExit:
        pass
    else:
        raise AssertionError("--once should not be a hexmind-gui flag")


# ---------- module surface ----------


def test_public_names():
    assert A.__all__ == ["HexmindWindow", "build_parser", "main"]


def test_console_script_target_resolves():
    """pyproject points `hexmind-gui` here. A rename that leaves the entry point dangling ships a
    command that dies with an ImportError, which packaging tests never catch."""
    from importlib import import_module

    assert callable(import_module("hexmind.qt.app", __package__).main)


def test_main_uses_config_room_defaults_and_cli_overrides(host, tmp_path, monkeypatch):
    from hexmind import config
    cfg_file = tmp_path / "config.toml"
    monkeypatch.setattr(config, "PATH", cfg_file)
    config.save_section("room", {"lead": "codex", "audit": True}, cfg_file)

    # 1. No CLI flags: picks up lead="codex" and audit=True from config
    assert A.main([]) == 0
    assert host.built[-1]["lead"] == "codex"
    assert host.built[-1]["audit"] is True

    # 2. CLI flag override: explicit --lead claude overrides config's "codex"
    assert A.main(["--lead", "claude"]) == 0
    assert host.built[-1]["lead"] == "claude"
    assert host.built[-1]["audit"] is True


def test_main_uses_saved_roster_without_cli_roster_filters(host, tmp_path, monkeypatch):
    from hexmind import backends, config

    cfg_file = tmp_path / "config.toml"
    monkeypatch.setattr(config, "PATH", cfg_file)
    monkeypatch.setattr(backends, "available", lambda roster: roster)
    config.save_section("room", {"members": ["codex"], "audit": False}, cfg_file)

    assert A.main([]) == 0
    assert host.built[-1]["members"] == ["codex"]

"""The Bench Rail navigation shell, offscreen."""
from __future__ import annotations

import sys

import pytest

pytest.importorskip("PySide6", reason="the qt extra is not installed")

from PySide6.QtWidgets import QApplication, QLabel, QWidget

from hexmind.qt.rail import BenchRail


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication(sys.argv[:1])
    yield app


@pytest.fixture
def room(qapp):
    return QWidget()


@pytest.fixture
def rail(qapp, room):
    shell = BenchRail(room)
    shell.show()
    yield shell
    shell.close()
    shell.deleteLater()


def test_rail_is_fixed_width_and_starts_in_the_room(rail, room):
    assert rail.navigation.minimumWidth() == 56
    assert rail.navigation.maximumWidth() == 56
    assert rail.stack.currentWidget() is room
    assert rail.current_workspace == "Room"
    assert rail.buttons["Room"].isChecked()


def test_rail_pages_are_in_roadmap_order(rail, room):
    assert rail.page_names == ("Room", "Direct Line", "Calibration Rack", "Settings")
    assert [rail.stack.widget(index) for index in range(rail.stack.count())] == [
        room,
        rail.pages["Direct Line"],
        rail.pages["Calibration Rack"],
        rail.pages["Settings"],
    ]
    navigation_layout = rail.navigation.layout()
    assert [
        navigation_layout.itemAt(index).widget().text()
        for index in range(len(rail.page_names))
    ] == list(rail.page_names)


@pytest.mark.parametrize("name", ("Direct Line", "Calibration Rack", "Settings"))
def test_future_workspace_buttons_select_accessible_placeholders(rail, name):
    rail.buttons[name].click()

    placeholder = rail.pages[name]
    assert rail.stack.currentWidget() is placeholder
    assert placeholder.accessibleName() == f"{name} workspace"
    assert placeholder.findChild(QLabel).text() == f"{name}\nComing soon"


def test_returning_to_room_preserves_the_injected_widget(rail, room):
    rail.buttons["Settings"].click()
    rail.buttons["Room"].click()

    assert rail.stack.currentWidget() is room
    assert rail.stack.widget(0) is room


def test_workspace_api_selects_a_page_and_rejects_unknown_names(rail):
    rail.set_workspace("Calibration Rack")

    assert rail.current_workspace == "Calibration Rack"
    assert rail.stack.currentWidget() is rail.pages["Calibration Rack"]

    with pytest.raises(ValueError, match="Unknown workspace"):
        rail.set_workspace("Missing")


def test_navigation_buttons_are_accessible(rail):
    for name, button in rail.buttons.items():
        assert button.accessibleName() == f"Open {name} workspace"
        assert button.toolTip() == name


def test_rail_accepts_a_real_future_workspace(room):
    settings = QWidget()
    rail = BenchRail(room, workspace_pages={"Settings": settings})

    rail.set_workspace("Settings")

    assert rail.stack.currentWidget() is settings
    rail.close()


@pytest.mark.parametrize("name", ("Room", "Missing"))
def test_rail_rejects_invalid_workspace_replacements(room, name):
    with pytest.raises(ValueError, match="Unsupported workspace pages"):
        BenchRail(room, workspace_pages={name: QWidget()})

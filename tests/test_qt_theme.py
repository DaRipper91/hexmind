"""The palette meets WCAG contrast, and the stylesheet keeps focus distinct from hover."""
from __future__ import annotations

import pytest

from hexmind.qt import theme as T

SURFACES = {"SUBSTRATE": T.SUBSTRATE, "PANEL": T.PANEL, "GRID": T.GRID, "PANEL_HOVER": T.PANEL_HOVER}


def _luminance(hex_color: str) -> float:
    channels = [int(hex_color.lstrip("#")[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    r, g, b = (c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: str, b: str) -> float:
    hi, lo = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def test_contrast_helper_matches_wcag():
    assert round(contrast("#ffffff", "#000000"), 1) == 21.0


@pytest.mark.parametrize("name", ["INK", "INK_DIM", "INK_FAINT", "SLATE"])
@pytest.mark.parametrize("surface", SURFACES)
def test_text_tokens_meet_4_5_to_1(name, surface):
    """WCAG 1.4.3. INK_FAINT (3.3:1) and SLATE (4.24 on PANEL) used to fail."""
    assert contrast(getattr(T, name), SURFACES[surface]) >= 4.5


@pytest.mark.parametrize("surface", SURFACES)
def test_control_edges_meet_3_to_1(surface):
    """WCAG 1.4.11: every input, button and checkbox outline was PANEL_EDGE at 1.25:1."""
    assert contrast(T.CONTROL_EDGE, SURFACES[surface]) >= 3.0


def test_selected_text_meets_4_5_to_1():
    """Selected text in input fields is SUBSTRATE on VIOLET (6.1:1); selection on PANEL_HOVER is INK (>=4.5:1)."""
    assert contrast(T.SUBSTRATE, T.VIOLET) >= 4.5
    assert contrast(T.INK, T.PANEL_HOVER) >= 4.5


def test_list_padding_and_row_selection_rules():
    """Task 4.7: list padding and row selection rules in stylesheet."""
    sheet = T.stylesheet()
    assert "QListWidget::item" in sheet
    assert "padding: 6px 10px;" in sheet
    assert f"selection-background-color: {T.PANEL_HOVER};" in sheet
    assert f"selection-color: {T.INK};" in sheet
    assert f"border-left: 2px solid {T.VIOLET};" in sheet


def _blocks(qss: str) -> dict[str, str]:
    blocks = {}
    for chunk in qss.split("}"):
        if "{" in chunk:
            selector, body = chunk.split("{", 1)
            blocks[" ".join(selector.split()).split("*/")[-1].strip()] = body
    return blocks


def test_every_focusable_kind_has_a_visible_focus_rule():
    """WCAG 2.4.7: checkboxes, tabs, rail buttons and tables showed no focus at all."""
    selectors = " ".join(_blocks(T.stylesheet()))
    for needed in ("QCheckBox::indicator:focus", "QTabBar::tab:focus", "QToolButton:focus",
                   "QTableView:focus", "QTableView::item:focus"):
        assert needed in selectors, needed


def test_hover_never_uses_the_focus_hue():
    hovers = {sel: body for sel, body in _blocks(T.stylesheet()).items()
              if ":hover" in sel and "border" in body}
    assert hovers
    assert [sel for sel, body in hovers.items() if T.VIOLET in body] == []


def test_every_text_size_derives_from_the_base():
    """The Text size setting scales the whole app: no font-size may stay pinned to 14px."""
    import re

    sizes = {int(px) for px in re.findall(r"font-size:\s*(\d+)px", T.stylesheet(20))}
    assert sizes == {18, 20, 22}
    assert T.base_text_px("16") == 16
    assert T.base_text_px("nonsense") == T.FONT_SIZE


def test_every_url_in_stylesheet_points_to_existing_file():
    """Task 3.6: Verify that every image: url(...) references an existing asset on disk."""
    import re
    from pathlib import Path

    urls = re.findall(r"url\(([^)]+)\)", T.stylesheet())
    assert urls, "stylesheet should reference icon URLs"
    for raw in urls:
        path = Path(raw.strip("\"'"))
        assert path.exists(), f"Asset {path} referenced in stylesheet must exist"
        assert path.is_file(), f"Asset {path} must be a file"


def test_typography_tokens_and_roles():
    """Task 4.4: role-based label rules are present, line-height is absent, no off-scale sizes."""
    sheet = T.stylesheet()
    assert "line-height" not in sheet, "line-height is not a valid QSS property"

    selectors = " ".join(_blocks(sheet))
    for needed in ('QLabel[role="title"]', 'QLabel[role="heading"]', 'QLabel[role="caption"]'):
        assert needed in selectors, f"{needed} selector must be present in stylesheet"


def test_primary_button_variant_and_styling():
    """Task 4.5: Primary button variant rule in stylesheet and set on primary actions."""
    from hexmind.qt.chat import DirectLine
    from hexmind.qt.models import CalibrationRack
    from hexmind.qt.settings import SettingsPage
    from hexmind.qt.widget import HexmindWidget

    sheet = T.stylesheet()
    assert 'QPushButton[variant="primary"]' in sheet

    w = HexmindWidget()
    assert w.sendButton.property("variant") == "primary"
    w.close()

    s = SettingsPage()
    assert s.save_button.property("variant") == "primary"
    s.close()

    c = DirectLine()
    assert c.ask_button.property("variant") == "primary"
    c.close()

    m = CalibrationRack()
    assert m.probe_button.property("variant") == "primary"
    m.close()



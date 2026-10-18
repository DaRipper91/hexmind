"""The palette meets WCAG contrast, and the stylesheet keeps focus distinct from hover."""
from __future__ import annotations

import pytest

from hexmind.qt import theme as T

SURFACES = {"SUBSTRATE": T.SUBSTRATE, "PANEL": T.PANEL, "GRID": T.GRID}


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
    """Selected text was INK on VIOLET, 2.71:1."""
    assert "selection-color: {INK}".format(INK=T.INK) not in T.stylesheet()
    assert contrast(T.SUBSTRATE, T.VIOLET) >= 4.5


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

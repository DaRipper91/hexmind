"""The visual grammar for the hexmind GUI, in one place.

This is `docs/design-philosophy.md` ("Measured Sublime") reduced to values. The philosophy fixes
the language — the dark substrate, the posted signals, the phased rhythm, the restraint — and
this module is that language expressed as constants, so no panel has to invent a colour and a
later panel cannot quietly disagree with an earlier one.

The rules this file encodes, and why each one is a rule rather than a preference:

* **A small permanent hue set, never improvised.** cyan is motion and flow, violet is structure and
  identity, green is verification, amber is warning. A hue means one thing everywhere. The TUI has
  the same idea in `AGENT_COLOR`; here the *states* get hues too, because a graph has more states
  than a roster list does.
* **Near-black, blue-black substrate.** Not `#000`: the palette is a powered-down lab at night,
  and pure black kills the glow that carries "this node is live".
* **Glow is depth, not decoration.** A halo means live. A border means structure. If everything
  glows, nothing is live.
* **One deliberate rupture per canvas.** Strict grid, so the rare break carries meaning.

`stylesheet()` returns the app-wide QSS. Panels add their own local styling where a rule is about
that panel's shape rather than the app's, but no panel may introduce a new colour literal.
"""
from __future__ import annotations

from pathlib import Path

ICONS = (Path(__file__).parent / "icons").as_posix()

# ---------- the signal palette ----------
# Chosen once, obeyed absolutely. If a future state needs a hue, it is added *here* with a
# meaning attached, not chosen at the call site.

SUBSTRATE = "#0a0d14"          # the bench itself
PANEL = "#0f1420"               # a raised surface
PANEL_EDGE = "#1c2436"          # a seam between surfaces (panes, tables, splitters) -- not controls
CONTROL_EDGE = "#636e88"        # the outline of anything you can operate: >= 3:1 on every surface
GRID = "#141a28"                # the strict grid, barely above the substrate
PANEL_HOVER = "#161c2c"         # a surface under the pointer

INK = "#e6edf7"                 # primary text: clinical, high contrast
INK_DIM = "#8b98ae"             # secondary labels
INK_FAINT = "#7d8899"           # whisper-quiet labels that serve from below (still >= 4.5:1)

CYAN = "#39d0d8"                # motion and flow — running, streaming, in transit
VIOLET = "#9d7cf0"              # structure and identity — lead, identity, selection
GREEN = "#5fd68a"               # verification — done, passed, audited clean
AMBER = "#e8b04b"               # warning — failed, gated, needs a human
RED = "#f2686b"                 # failure — hard error, cancelled, contradicted
SLATE = "#7686a0"               # idle, asleep, known-but-not-awake

# ---------- typography ----------
# A single system font stack, sized so the bench reads at a comfortable distance.
# Scaling honors the platform's device pixel ratio; Qt applies it automatically
# when AA_EnableHighDpiScaling is set (QApplication does this by default in Qt 6).
FONT_FAMILY = '"Inter", "SF Pro Text", "Segoe UI", "Roboto", "Helvetica Neue", Arial, sans-serif'
FONT_MONO = '"JetBrains Mono", "Fira Code", "SF Mono", "Consolas", "Liberation Mono", monospace'
FONT_SIZE = 14                  # base body text, px
FONT_SIZE_SMALL = 12            # captions, secondary labels
FONT_SIZE_LARGE = 16            # section headings, status lines
FONT_WEIGHT = 400
FONT_WEIGHT_MEDIUM = 500
FONT_WEIGHT_SEMIBOLD = 600
LINE_HEIGHT = 1.5

# ---------- geometry ----------
# Border radius softens the laboratory edge without breaking the grid.
BORDER_RADIUS = 8               # panels, inputs, buttons
BORDER_RADIUS_SMALL = 4         # badges, pills, indicators
BORDER_WIDTH = 1.5              # seam thickness, px

#: Every state a task can be in, and the hue that posts it. This is the single mapping the whole
#: app reads: the table, the graph node, the status pill and the legend all resolve through it, so
#: a colour can never mean two things.
STATE_HUE = {
    "pending":  SLATE,
    "running":  CYAN,
    "auditing": VIOLET,
    "revising": AMBER,
    "done":     GREEN,
    "failed":   RED,
    "skipped":  SLATE,
    "cancelled": RED,
}

#: `BUSY_STATUSES` in core.py is the one list of "a model is working"; a task in one of these is
#: what makes a node glow. Imported rather than restated so the two can never drift.
BUSY_HUES = ("running", "auditing", "revising")

#: Verdict vocabulary from `auditor.parse_verdict`. A verdict is the product's most consequential
#: single word, so it gets its own reserved hue rather than borrowing the task status scale.
VERDICT_HUE = {"PASS": GREEN, "FAIL": RED, "UNKNOWN": SLATE}


def state_hue(status: str) -> str:
    """The posted hue for a task status. Unknown statuses read as idle rather than crashing —
    a status the app has not been taught about must not take the window down."""
    return STATE_HUE.get(status, SLATE)


def is_live(status: str) -> bool:
    """True when a node should glow: it is in flight, not settled."""
    return status in BUSY_HUES


def base_text_px(choice: str) -> int:
    """The base text size for a `[room] text_size` setting. "system" reads the desktop's font (KDE's
    setting, via the QApplication font), so the GUI scales with the rest of the desktop."""
    if choice == "system":
        from PySide6.QtGui import QFontInfo
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance()
        return QFontInfo(app.font()).pixelSize() if app is not None else FONT_SIZE
    try:
        return int(choice)
    except (TypeError, ValueError):
        return FONT_SIZE


def stylesheet(base: int = FONT_SIZE) -> str:
    """App-wide QSS. Panels compose this rather than restating it, so a hue change is one edit.

    Every text size derives from `base`, so the Text size setting scales the whole app at once."""
    small, large = base - 2, base + 2
    return f"""
    QWidget {{
        background: {SUBSTRATE};
        color: {INK};
        font-family: {FONT_FAMILY};
        font-size: {base}px;
        font-weight: {FONT_WEIGHT};
    }}
    QLabel[role="title"] {{
        font-size: {large}px;
        font-weight: {FONT_WEIGHT_SEMIBOLD};
        color: {INK};
    }}
    QLabel[role="heading"] {{
        font-size: {base}px;
        font-weight: {FONT_WEIGHT_SEMIBOLD};
        color: {INK};
    }}
    QLabel[role="caption"] {{
        font-size: {small}px;
        color: {INK_DIM};
    }}
    QMainWindow::separator {{
        background: {PANEL_EDGE};
        width: {BORDER_WIDTH}px;
        height: {BORDER_WIDTH}px;
    }}
    QToolTip {{
        background: {PANEL};
        color: {INK};
        border: {BORDER_WIDTH}px solid {PANEL_EDGE};
        border-radius: {BORDER_RADIUS_SMALL}px;
        padding: 6px 8px;
        font-size: {small}px;
    }}

    /* --- structure: violet, because this is identity and selection --- */
    QTabWidget::pane {{
        border: {BORDER_WIDTH}px solid {PANEL_EDGE};
        border-radius: {BORDER_RADIUS}px;
        background: {SUBSTRATE};
    }}
    QTabWidget::tab-bar {{
        left: 8px;
    }}
    QTabBar::tab {{
        background: {PANEL};
        color: {INK_DIM};
        padding: 6px 12px;
        margin-right: 2px;
        border: {BORDER_WIDTH}px solid {PANEL_EDGE};
        border-bottom: none;
        border-top-left-radius: {BORDER_RADIUS}px;
        border-top-right-radius: {BORDER_RADIUS}px;
    }}
    QTabBar::tab:!selected {{
        margin-top: 2px;
    }}
    QTabBar::tab:selected {{
        background: {SUBSTRATE};
        color: {VIOLET};
        border-top: 2px solid {VIOLET};
    }}
    QTabBar::tab:hover:!selected {{ color: {INK}; background: {PANEL_HOVER}; }}
    QTabBar::tab:focus {{ border-bottom: 2px solid {VIOLET}; }}
    QTabBar QToolButton {{ min-width: 24px; }}
    QToolButton:focus {{ border: 2px solid {VIOLET}; border-radius: {BORDER_RADIUS_SMALL}px; }}

    /* --- the workspace rail: icons over short labels; violet marks where you are --- */
    #benchRail {{ background: {PANEL}; border-right: {BORDER_WIDTH}px solid {PANEL_EDGE}; }}
    #benchRail QToolButton {{
        background: transparent;
        color: {INK_DIM};
        border: none;
        border-left: 2px solid transparent;
        border-radius: {BORDER_RADIUS_SMALL}px;
        padding: 8px 4px 6px 4px;
        font-size: {small}px;
    }}
    #benchRail QToolButton:hover {{ color: {INK}; background: {PANEL_HOVER}; }}
    #benchRail QToolButton:checked {{
        color: {VIOLET};
        background: {SUBSTRATE};
        border-left: 2px solid {VIOLET};
    }}
    #benchRail QToolButton:focus {{ border: 2px solid {VIOLET}; }}

    /* --- inputs --- */
    QLineEdit, QPlainTextEdit, QTextBrowser, QTextEdit, QSpinBox, QDoubleSpinBox {{
        background: {PANEL};
        color: {INK};
        border: {BORDER_WIDTH}px solid {CONTROL_EDGE};
        border-radius: {BORDER_RADIUS}px;
        padding: 8px 10px;
        selection-background-color: {VIOLET};
        selection-color: {SUBSTRATE};
    }}
    QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
        border: {BORDER_WIDTH}px solid {VIOLET};
        background: {PANEL_HOVER};
    }}
    QSpinBox::up-button, QSpinBox::down-button,
    QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
        subcontrol-origin: border;
        width: 22px;
        border-left: {BORDER_WIDTH}px solid {PANEL_EDGE};
        background: {PANEL};
    }}
    QSpinBox::up-button, QDoubleSpinBox::up-button {{
        subcontrol-position: top right;
        border-top-right-radius: {BORDER_RADIUS}px;
    }}
    QSpinBox::down-button, QDoubleSpinBox::down-button {{
        subcontrol-position: bottom right;
        border-bottom-right-radius: {BORDER_RADIUS}px;
    }}
    QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{
        image: url({ICONS}/chevron-up.svg);
        width: 8px;
        height: 8px;
    }}
    QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{
        image: url({ICONS}/chevron-down.svg);
        width: 8px;
        height: 8px;
    }}
    QSpinBox::up-button:hover, QSpinBox::down-button:hover,
    QDoubleSpinBox::up-button:hover, QDoubleSpinBox::down-button:hover {{
        background: {PANEL_HOVER};
    }}
    QLineEdit:disabled, QPushButton:disabled, QComboBox:disabled {{
        color: {INK_FAINT};
        background: {GRID};
    }}

    /* --- buttons: quiet until wanted --- */
    QPushButton {{
        background: {PANEL};
        color: {INK};
        border: {BORDER_WIDTH}px solid {CONTROL_EDGE};
        border-radius: {BORDER_RADIUS}px;
        padding: 8px 16px;
        min-height: 32px;
    }}
    QPushButton[variant="primary"] {{
        background: {VIOLET};
        color: {SUBSTRATE};
        border: {BORDER_WIDTH}px solid {VIOLET};
        font-weight: 600;
    }}
    QPushButton[variant="primary"]:hover {{
        background: #af92f5;
        border-color: #af92f5;
        color: {SUBSTRATE};
    }}
    QPushButton[variant="primary"]:disabled {{
        background: {GRID};
        color: {INK_FAINT};
        border: {BORDER_WIDTH}px solid {CONTROL_EDGE};
        font-weight: 400;
    }}
    /* Hover brightens the outline; violet is reserved for keyboard focus, so the two never look alike. */
    QPushButton:hover {{ border: {BORDER_WIDTH}px solid {INK_DIM}; color: {INK}; background: {PANEL_HOVER}; }}
    QPushButton:pressed {{ background: {GRID}; }}
    QPushButton:checked {{
        border: {BORDER_WIDTH}px solid {CYAN};
        color: {CYAN};
        background: {PANEL_HOVER};
    }}
    QPushButton#stopButton {{
        color: {RED};
        border: {BORDER_WIDTH}px solid {RED};
    }}
    QPushButton#stopButton:hover {{
        background: #2a1518;
        border: {BORDER_WIDTH}px solid {RED};
    }}
    QPushButton#stopButton:disabled {{
        color: {INK_FAINT};
        border: {BORDER_WIDTH}px solid {PANEL_EDGE};
        background: {GRID};
    }}
    QPushButton:focus {{
        outline: none;
        border: {BORDER_WIDTH}px solid {VIOLET};
    }}

    QLabel#turnMeter {{
        color: {CYAN};
        font-family: {FONT_MONO};
        font-weight: {FONT_WEIGHT_SEMIBOLD};
        padding: 0 6px;
        font-size: {small}px;
    }}

    QComboBox {{
        background: {PANEL};
        color: {INK};
        border: {BORDER_WIDTH}px solid {CONTROL_EDGE};
        border-radius: {BORDER_RADIUS}px;
        padding: 8px 10px;
        min-height: 32px;
    }}
    QComboBox::drop-down {{
        subcontrol-origin: padding;
        subcontrol-position: center right;
        border-left: {BORDER_WIDTH}px solid {PANEL_EDGE};
        width: 24px;
    }}
    QComboBox QAbstractItemView {{
        background: {PANEL};
        color: {INK};
        selection-background-color: {VIOLET};
        selection-color: {SUBSTRATE};
        border: {BORDER_WIDTH}px solid {PANEL_EDGE};
        border-radius: 0 0 {BORDER_RADIUS}px {BORDER_RADIUS}px;
    }}
    QComboBox::down-arrow {{
        image: url({ICONS}/chevron-down.svg);
        width: 10px;
        height: 10px;
    }}
    QComboBox:focus {{
        border: {BORDER_WIDTH}px solid {VIOLET};
        background: {PANEL_HOVER};
    }}

    /* --- checkboxes: the indicator must read on the dark substrate --- */
    QCheckBox {{ spacing: 8px; }}
    QCheckBox::indicator {{
        width: 18px;
        height: 18px;
        border: {BORDER_WIDTH}px solid {CONTROL_EDGE};
        border-radius: {BORDER_RADIUS_SMALL}px;
        background: {PANEL};
    }}
    QCheckBox::indicator:hover {{ border: {BORDER_WIDTH}px solid {INK_DIM}; }}
    QCheckBox::indicator:checked {{
        background: {GREEN};
        border: {BORDER_WIDTH}px solid {GREEN};
    }}
    QCheckBox::indicator:checked:hover {{ border: {BORDER_WIDTH}px solid {INK}; }}
    QCheckBox::indicator:disabled {{
        background: {GRID};
        border: {BORDER_WIDTH}px solid {PANEL_EDGE};
    }}
    QCheckBox:focus {{
        outline: none;
    }}
    QCheckBox::indicator:focus {{ border: 2px solid {VIOLET}; }}

    /* --- trees and tables --- */
    QTreeWidget, QTreeView, QTableWidget, QTableView, QListWidget, QListView {{
        background: {SUBSTRATE};
        color: {INK};
        border: {BORDER_WIDTH}px solid {PANEL_EDGE};
        border-radius: {BORDER_RADIUS}px;
        alternate-background-color: {GRID};
        gridline-color: {PANEL_EDGE};
        selection-background-color: {PANEL_HOVER};
        selection-color: {INK};
    }}
    QListWidget::item {{ padding: 6px 10px; }}
    QTreeWidget::item:selected, QTableWidget::item:selected,
    QListWidget::item:selected, QListView::item:selected {{
        background: {PANEL_HOVER};
        color: {INK};
        border-left: 2px solid {VIOLET};
        border-radius: {BORDER_RADIUS_SMALL}px;
    }}
    QTreeView:focus, QTableView:focus, QListView:focus {{ border: 2px solid {VIOLET}; }}
    QTableView::item:focus {{ border: 1px solid {CYAN}; }}
    QTreeWidget::item:hover, QTableWidget::item:hover,
    QListWidget::item:hover, QListView::item:hover {{ background: {PANEL_HOVER}; }}

    QHeaderView::section {{
        background: {PANEL};
        color: {INK_DIM};
        border: none;
        border-right: {BORDER_WIDTH}px solid {PANEL_EDGE};
        border-bottom: {BORDER_WIDTH}px solid {PANEL_EDGE};
        padding: 6px 8px;
        font-weight: {FONT_WEIGHT_MEDIUM};
        font-size: {small}px;
    }}

    /* --- scrollbars: present, never loud --- */
    QScrollBar:vertical {{
        background: {SUBSTRATE};
        width: 12px;
        margin: 0;
        border-radius: {BORDER_RADIUS_SMALL}px;
    }}
    QScrollBar::handle:vertical {{
        background: {CONTROL_EDGE};
        min-height: 40px;
        border-radius: {BORDER_RADIUS_SMALL}px;
    }}
    QScrollBar::handle:vertical:hover {{ background: {VIOLET}; }}
    QScrollBar:horizontal {{ background: {SUBSTRATE}; height: 12px; margin: 0; border-radius: {BORDER_RADIUS_SMALL}px; }}
    QScrollBar::handle:horizontal {{ background: {CONTROL_EDGE}; min-width: 40px; border-radius: {BORDER_RADIUS_SMALL}px; }}
    QScrollBar::handle:horizontal:hover {{ background: {VIOLET}; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
    QScrollBar::add-page, QScrollBar::sub-page {{ background: none; }}

    /* --- the command palette overlay --- */
    #palette {{
        background: {PANEL};
        border: {BORDER_WIDTH}px solid {VIOLET};
        border-radius: {BORDER_RADIUS}px;
    }}
    #paletteInput {{
        background: {PANEL};
        border: none;
        border-bottom: {BORDER_WIDTH}px solid {PANEL_EDGE};
        border-radius: 0;
        font-size: {large}px;
        padding: 12px 14px;
    }}
    #paletteList::item {{ padding: 7px 10px; border: none; }}
    #paletteList::item:selected {{ background: {GRID}; color: {VIOLET}; }}
    #paletteHint {{
        color: {INK_DIM};
        font-size: {small}px;
        padding: 8px 14px;
        border-top: {BORDER_WIDTH}px solid {PANEL_EDGE};
    }}

    QSplitter::handle {{ background: {PANEL_EDGE}; }}
    QStatusBar {{ background: {PANEL}; color: {INK_DIM}; border-top: {BORDER_WIDTH}px solid {PANEL_EDGE}; }}
    QStatusBar::item {{ border: none; }}
    """

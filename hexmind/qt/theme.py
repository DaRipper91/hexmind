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


def stylesheet() -> str:
    """App-wide QSS. Panels compose this rather than restating it, so a hue change is one edit."""
    return f"""
    QWidget {{
        background: {SUBSTRATE};
        color: {INK};
        font-family: {FONT_FAMILY};
        font-size: {FONT_SIZE}px;
        font-weight: {FONT_WEIGHT};
        line-height: {LINE_HEIGHT};
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
        font-size: {FONT_SIZE_SMALL}px;
    }}

    /* --- structure: violet, because this is identity and selection --- */
    QTabWidget::pane {{
        border: {BORDER_WIDTH}px solid {PANEL_EDGE};
        border-radius: {BORDER_RADIUS}px;
        background: {SUBSTRATE};
    }}
    QTabBar::tab {{
        background: {PANEL};
        color: {INK_DIM};
        padding: 8px 14px;
        border: {BORDER_WIDTH}px solid {PANEL_EDGE};
        border-bottom: none;
        border-top-left-radius: {BORDER_RADIUS}px;
        border-top-right-radius: {BORDER_RADIUS}px;
        min-width: 70px;
    }}
    QTabBar::tab:selected {{
        background: {SUBSTRATE};
        color: {VIOLET};
        border-top: 2px solid {VIOLET};
    }}
    QTabBar::tab:hover:!selected {{ color: {INK}; background: {PANEL_HOVER}; }}

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
    QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QSpinBox:focus {{
        border: {BORDER_WIDTH}px solid {VIOLET};
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
    QPushButton:hover {{ border: {BORDER_WIDTH}px solid {VIOLET}; color: {INK}; background: {PANEL_HOVER}; }}
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
        font-size: {FONT_SIZE_SMALL}px;
    }}

    QComboBox {{
        background: {PANEL};
        color: {INK};
        border: {BORDER_WIDTH}px solid {CONTROL_EDGE};
        border-radius: {BORDER_RADIUS}px;
        padding: 8px 10px;
        min-height: 32px;
    }}
    QComboBox::drop-down {{ border: none; width: 24px; }}
    QComboBox QAbstractItemView {{
        background: {PANEL};
        color: {INK};
        selection-background-color: {VIOLET};
        selection-color: {SUBSTRATE};
        border: {BORDER_WIDTH}px solid {PANEL_EDGE};
        border-radius: 0 0 {BORDER_RADIUS}px {BORDER_RADIUS}px;
    }}
    QComboBox::down-arrow {{
        image: none;
        border-left: 5px solid transparent;
        border-right: 5px solid transparent;
        border-top: 5px solid {INK_DIM};
        margin-right: 8px;
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
    QCheckBox::indicator:hover {{ border: {BORDER_WIDTH}px solid {VIOLET}; }}
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

    /* --- trees and tables --- */
    QTreeWidget, QTreeView, QTableWidget, QTableView, QListWidget, QListView {{
        background: {SUBSTRATE};
        color: {INK};
        border: {BORDER_WIDTH}px solid {PANEL_EDGE};
        border-radius: {BORDER_RADIUS}px;
        alternate-background-color: {GRID};
        gridline-color: {PANEL_EDGE};
        selection-background-color: {PANEL};
        selection-color: {VIOLET};
    }}
    QTreeWidget::item:selected, QTableWidget::item:selected,
    QListWidget::item:selected, QListView::item:selected {{
        background: {GRID};
        color: {VIOLET};
        border-radius: {BORDER_RADIUS_SMALL}px;
    }}
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
        font-size: {FONT_SIZE_SMALL}px;
        border-top-left-radius: {BORDER_RADIUS_SMALL}px;
        border-top-right-radius: {BORDER_RADIUS_SMALL}px;
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
        font-size: 16px;
        padding: 12px 14px;
    }}
    #paletteList::item {{ padding: 7px 10px; border: none; }}
    #paletteList::item:selected {{ background: {GRID}; color: {VIOLET}; }}

    QSplitter::handle {{ background: {PANEL_EDGE}; }}
    QStatusBar {{ background: {PANEL}; color: {INK_DIM}; border-top: {BORDER_WIDTH}px solid {PANEL_EDGE}; }}
    QStatusBar::item {{ border: none; }}
    """

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
PANEL_EDGE = "#1c2436"          # a seam between surfaces
GRID = "#141a28"                # the strict grid, barely above the substrate

INK = "#e6edf7"                 # primary text: clinical, high contrast
INK_DIM = "#8b98ae"             # secondary labels
INK_FAINT = "#5a6577"           # whisper-quiet labels that serve from below

CYAN = "#39d0d8"                # motion and flow — running, streaming, in transit
VIOLET = "#9d7cf0"              # structure and identity — lead, identity, selection
GREEN = "#5fd68a"               # verification — done, passed, audited clean
AMBER = "#e8b04b"               # warning — failed, gated, needs a human
RED = "#f2686b"                 # failure — hard error, cancelled, contradicted
SLATE = "#6b7a94"               # idle, asleep, known-but-not-awake

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
        font-size: 13px;
    }}
    QMainWindow::separator {{
        background: {PANEL_EDGE};
        width: 1px;
        height: 1px;
    }}
    QToolTip {{
        background: {PANEL};
        color: {INK};
        border: 1px solid {PANEL_EDGE};
        padding: 4px 6px;
    }}

    /* --- structure: violet, because this is identity and selection --- */
    QTabWidget::pane {{
        border: 1px solid {PANEL_EDGE};
        background: {SUBSTRATE};
    }}
    QTabBar::tab {{
        background: {PANEL};
        color: {INK_DIM};
        padding: 6px 12px;
        border: 1px solid {PANEL_EDGE};
        border-bottom: none;
    }}
    QTabBar::tab:selected {{
        background: {SUBSTRATE};
        color: {VIOLET};
        border-top: 2px solid {VIOLET};
    }}
    QTabBar::tab:hover:!selected {{ color: {INK}; }}

    /* --- inputs --- */
    QLineEdit, QPlainTextEdit, QTextBrowser, QTextEdit, QSpinBox, QDoubleSpinBox {{
        background: {PANEL};
        color: {INK};
        border: 1px solid {PANEL_EDGE};
        padding: 4px 6px;
        selection-background-color: {VIOLET};
        selection-color: {INK};
    }}
    QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QSpinBox:focus {{
        border: 1px solid {VIOLET};
    }}
    QLineEdit:disabled, QPushButton:disabled, QComboBox:disabled {{
        color: {INK_FAINT};
        background: {GRID};
    }}

    /* --- buttons: quiet until wanted --- */
    QPushButton {{
        background: {PANEL};
        color: {INK};
        border: 1px solid {PANEL_EDGE};
        padding: 5px 12px;
    }}
    QPushButton:hover {{ border: 1px solid {VIOLET}; color: {INK}; }}
    QPushButton:pressed {{ background: {GRID}; }}
    QPushButton:checked {{
        border: 1px solid {CYAN};
        color: {CYAN};
    }}
    QPushButton#stopButton {{
        color: {RED};
        border: 1px solid {RED};
    }}
    QPushButton#stopButton:hover {{
        background: #2a1518;
    }}
    QPushButton#stopButton:disabled {{
        color: {INK_FAINT};
        border: 1px solid {PANEL_EDGE};
        background: {GRID};
    }}

    QLabel#turnMeter {{
        color: {CYAN};
        font-family: monospace;
        font-weight: bold;
        padding: 0 4px;
    }}

    QComboBox {{
        background: {PANEL};
        border: 1px solid {PANEL_EDGE};
        padding: 4px 8px;
    }}
    QComboBox::drop-down {{ border: none; width: 18px; }}
    QComboBox QAbstractItemView {{
        background: {PANEL};
        color: {INK};
        selection-background-color: {VIOLET};
        selection-color: {INK};
        border: 1px solid {PANEL_EDGE};
    }}

    /* --- checkboxes: the indicator must read on the dark substrate --- */
    QCheckBox {{ spacing: 6px; }}
    QCheckBox::indicator {{
        width: 15px;
        height: 15px;
        border: 1px solid {PANEL_EDGE};
        background: {PANEL};
    }}
    QCheckBox::indicator:hover {{ border: 1px solid {VIOLET}; }}
    QCheckBox::indicator:checked {{
        background: {GREEN};
        border: 1px solid {GREEN};
    }}
    QCheckBox::indicator:checked:hover {{ border: 1px solid {INK}; }}
    QCheckBox::indicator:disabled {{
        background: {GRID};
        border: 1px solid {PANEL_EDGE};
    }}

    /* --- trees and tables --- */
    QTreeWidget, QTreeView, QTableWidget, QTableView, QListWidget, QListView {{
        background: {SUBSTRATE};
        color: {INK};
        border: 1px solid {PANEL_EDGE};
        alternate-background-color: {GRID};
    }}
    QTreeWidget::item:selected, QTableWidget::item:selected,
    QListWidget::item:selected, QListView::item:selected {{
        background: {GRID};
        color: {VIOLET};
    }}
    QTreeWidget::item:hover, QTableWidget::item:hover,
    QListWidget::item:hover, QListView::item:hover {{ background: {PANEL}; }}

    QHeaderView::section {{
        background: {PANEL};
        color: {INK_DIM};
        border: none;
        border-right: 1px solid {PANEL_EDGE};
        border-bottom: 1px solid {PANEL_EDGE};
        padding: 4px 6px;
        font-weight: 600;
    }}

    /* --- scrollbars: present, never loud --- */
    QScrollBar:vertical {{
        background: {SUBSTRATE};
        width: 10px;
        margin: 0;
    }}
    QScrollBar::handle:vertical {{
        background: {PANEL_EDGE};
        min-height: 24px;
    }}
    QScrollBar::handle:vertical:hover {{ background: {VIOLET}; }}
    QScrollBar:horizontal {{ background: {SUBSTRATE}; height: 10px; margin: 0; }}
    QScrollBar::handle:horizontal {{ background: {PANEL_EDGE}; min-width: 24px; }}
    QScrollBar::handle:horizontal:hover {{ background: {VIOLET}; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
    QScrollBar::add-page, QScrollBar::sub-page {{ background: none; }}

    /* --- the command palette overlay --- */
    #palette {{
        background: {PANEL};
        border: 1px solid {VIOLET};
    }}
    #paletteInput {{
        background: {PANEL};
        border: none;
        border-bottom: 1px solid {PANEL_EDGE};
        font-size: 15px;
        padding: 10px 12px;
    }}
    #paletteList::item {{ padding: 5px 8px; border: none; }}
    #paletteList::item:selected {{ background: {GRID}; color: {VIOLET}; }}

    QSplitter::handle {{ background: {PANEL_EDGE}; }}
    QStatusBar {{ background: {PANEL}; color: {INK_DIM}; border-top: 1px solid {PANEL_EDGE}; }}
    QStatusBar::item {{ border: none; }}
    """

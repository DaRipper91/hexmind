"""Audit statistics panel: who is reliable, and where the team hurts.

The numbers come from `auditor.Stats` — the same per-agent, per-domain pass/fail ledger that
drives `pick_auditor` and `/ranks`. This module only *reads* it: nothing here calls `record`, so
refreshing a panel can never distort the statistics it is displaying.

One thing the panel must not obscure: `audited_run` records only the *first* verdict
(`round_idx == 0`, auditor.py:244-246). So everything here is **first-attempt** reliability, which
is not the same as "did the task eventually pass". A task that failed, was revised, and passed
still counts as one failure. That is deliberate — it measures the agent, not the retry loop — but
it is a reading instruction, so it is printed in the panel rather than left to be inferred.

Layout is two horizontal bar charts (named categories read down the left edge, so long model and
domain names never collide into an unreadable x axis) over the exact numbers:

    reliability by agent   one stacked bar per agent, pass over fail
    where the team hurts   one stacked bar per domain, worst first
    the ledger             the per-agent/per-domain counts, cell text tinted by ratio

Every hue is a `theme` constant. There is no colour literal in this file.

`compute_*` and `cell_tone` are pure logic, testable without widgets and without pyqtgraph.
`StatsPanel` is the embeddable widget; pyqtgraph is imported optionally so a missing `qt` extra
degrades to the ledger instead of taking the room down.
"""
from __future__ import annotations

import logging
import os
from typing import Iterable, Sequence

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QLabel,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .. import auditor
from . import theme

logger = logging.getLogger(__name__)

try:
    import pyqtgraph as pg

    HAVE_PG = True
except Exception:  # pragma: no cover - depends on the qt extra
    pg = None  # type: ignore
    HAVE_PG = False

#: The same default the CLI (`__main__.py:104`) and the server (`server.py:106`) resolve to, so
#: all three front-ends read the same ledger without having to be told about each other.
DEFAULT_STATS_PATH = "~/.local/share/hexmind/stats.json"

#: The string the CLI's `/ranks` prints for the same condition. One sentence, one wording.
NO_STATS = "No audit stats recorded yet."

#: Bar thickness as a fraction of the row pitch. The remainder is the gap between rows, so the
#: bars never touch and a run of bars still reads as a list of separate rows.
BAR_HEIGHT = 0.62


# ---------------------------------------------------------------- pure logic


def stats_path() -> str:
    """The canonical ledger location, expanded."""
    return os.path.expanduser(DEFAULT_STATS_PATH)


def cell(data: dict, agent: str, domain: str) -> tuple[int, int]:
    """`(passed, failed)` for one agent/domain cell; `(0, 0)` when nothing is recorded.

    Tolerant of a partial or hand-edited file: a missing agent, a missing domain, or a missing
    counter all read as zero attempts rather than raising, because a corrupt stats.json is a
    display problem, not a reason to lose the window.
    """
    entry = (data.get(agent) or {}).get(domain) or {}
    passed = int(entry.get("pass", 0) or 0)
    failed = int(entry.get("fail", 0) or 0)
    return passed, failed


def active_domains(data: dict, agents: Sequence[str]) -> list[str]:
    """Domains with at least one recorded attempt, in taxonomy order.

    Deliberately *not* a mirror of `Stats.table` (auditor.py:120-141). That method lists only
    taxonomy domains and falls back to arbitrary ones only when it finds none at all, so a
    ledger holding both `tests` and `sorcery` loses the `sorcery` column. That is a defensible
    choice for a text table and an indefensible one for a chart: the whole point of the trouble
    view is to surface the domains work keeps failing in, and the off-taxonomy names are exactly
    the interesting ones. `core.py` stores plan domains verbatim, so a domain outside
    `auditor.DOMAINS` is real recorded data, not corruption.

    Ordering: the canonical `DOMAINS` order first, then any domain the data contains that the
    taxonomy does not know about, in first-seen order.
    """
    seen: list[str] = []
    for agent in agents:
        for domain in (data.get(agent) or {}):
            if sum(cell(data, agent, domain)) and domain not in seen:
                seen.append(domain)
    return [d for d in auditor.DOMAINS if d in seen] + [d for d in seen if d not in auditor.DOMAINS]


def discovered_agents(data: dict) -> list[str]:
    """Every agent in the ledger, sorted, for when the host has no roster to offer.

    The standalone app opens this panel with no room behind it, so the ledger has to be able to
    describe itself. Sorting keeps the standalone view stable between refreshes.
    """
    return sorted(data)


def compute_cells(
    data: dict, agents: Sequence[str], domains: Sequence[str]
) -> list[tuple[str, list[tuple[int, int]]]]:
    """`[(agent, [(passed, failed) per domain])]` in the given agent and domain order.

    Kept in the caller's order rather than sorted: for a live room the roster order is meaningful,
    and re-sorting here would fight whatever the room decided.
    """
    return [(agent, [cell(data, agent, d) for d in domains]) for agent in agents]


def compute_agent_totals(
    data: dict, agents: Sequence[str], domains: Sequence[str] | None = None
) -> list[tuple[str, int, int]]:
    """`[(agent, passed, failed)]` summed over every domain.

    `domains` narrows the sum to the columns actually on screen, which is what a filtered ledger
    should mean; by default the sum is over the whole ledger for that agent.
    """
    out: list[tuple[str, int, int]] = []
    for agent in agents:
        keys = list(domains) if domains is not None else list((data.get(agent) or {}).keys())
        passed = sum(cell(data, agent, d)[0] for d in keys)
        failed = sum(cell(data, agent, d)[1] for d in keys)
        out.append((agent, passed, failed))
    return out


def compute_trouble(
    data: dict, agents: Sequence[str], domains: Sequence[str] | None = None
) -> list[tuple[str, int, int]]:
    """`[(domain, passed, failed)]` summed across agents, worst first.

    Ordered by failures descending because that is the question the panel answers: not "how much
    have we done" but "where does the work keep coming back". Domains with no attempts are
    dropped — a bar of zeroes is noise, not information. Ties keep taxonomy order, so the chart
    does not reshuffle between two identical refreshes.
    """
    keys = list(domains) if domains is not None else active_domains(data, agents)
    rows = []
    for domain in keys:
        passed = sum(cell(data, a, domain)[0] for a in agents)
        failed = sum(cell(data, a, domain)[1] for a in agents)
        if passed + failed:
            rows.append((domain, passed, failed))
    rank = {d: i for i, d in enumerate(auditor.DOMAINS)}
    rows.sort(key=lambda r: (-r[2], rank.get(r[0], len(rank))))
    return rows


def cell_tone(passed: int, failed: int) -> str:
    """The hue for one ledger cell's text.

    Thresholds live here, once, rather than at the call site. An unrecorded cell reads as dim
    rather than as a score of zero: absence of evidence is not evidence of failure, and painting
    an unrecorded cell red would say something the ledger does not know.
    """
    total = passed + failed
    if total == 0:
        return theme.INK_DIM
    ratio = passed / total
    if ratio < 0.5:
        return theme.RED
    if ratio < 0.8:
        return theme.AMBER
    return theme.INK


def summary_line(agent_totals: Iterable[tuple[str, int, int]]) -> str:
    """A one-line readout under the charts: attempts, and the share that passed clean."""
    rows = list(agent_totals)
    passed = sum(p for _, p, _ in rows)
    failed = sum(f for _, _, f in rows)
    total = passed + failed
    if not total:
        return NO_STATS
    return f"{total} first-attempt audits recorded — {passed} passed, {failed} failed ({passed / total:.0%} clean)"


# ---------------------------------------------------------------- the widget


def _config_pg() -> None:
    """Pull pyqtgraph's own defaults into the theme, once, at first use.

    pyqtgraph ships a light background and its own antialiasing default; without this the charts
    arrive as bright rectangles pasted into a dark panel, which breaks the substrate the rest of
    the app treats as the bench itself.
    """
    if not HAVE_PG:
        return
    pg.setConfigOption("background", theme.SUBSTRATE)
    pg.setConfigOption("foreground", theme.INK_DIM)
    pg.setConfigOptions(antialias=True)


def _stack_bars(plot, labels: Sequence[str], passed: Sequence[int], failed: Sequence[int]) -> None:
    """Draw one horizontal stacked bar per label into `plot`: failures first, then passes.

    Explicit `x0`/`x1`/`y0`/`y1` rather than `x`/`width`, because `BarGraphItem` treats `width`
    as a *span centred on* `x` — the obvious-looking call would centre every bar on its own
    midpoint and float the stack off the zero line.

    Two `BarGraphItem`s rather than one multi-coloured bar: the segments need independent brushes
    and the substrate-coloured pen between them is what keeps adjacent rows from bleeding.
    """
    n = len(labels)
    plot.clear()
    if not n:
        return
    y0 = [i - BAR_HEIGHT / 2 for i in range(n)]
    y1 = [i + BAR_HEIGHT / 2 for i in range(n)]
    lows = [0.0] * n
    fail_top = [float(f) for f in failed]
    pass_top = [float(f + p) for f, p in zip(failed, passed)]

    # Draw passes first, failures over them: the taller pass bar is the backdrop, and the short
    # fail bar lands on the left of the same row, leaving the two to read as one stacked bar.
    plot.addItem(
        pg.BarGraphItem(
            x0=fail_top, x1=pass_top, y0=y0, y1=y1,
            brush=pg.mkBrush(theme.GREEN), pen=pg.mkPen(theme.SUBSTRATE),
        )
    )
    plot.addItem(
        pg.BarGraphItem(
            x0=lows, x1=fail_top, y0=y0, y1=y1,
            brush=pg.mkBrush(theme.RED), pen=pg.mkPen(theme.SUBSTRATE),
        )
    )

    axis = plot.getAxis("left")
    axis.setTicks([[(i, labels[i]) for i in range(n)]])
    axis.setTextPen(pg.mkPen(theme.INK))
    plot.getAxis("bottom").setTextPen(pg.mkPen(theme.INK_DIM))
    plot.setMouseEnabled(x=False, y=False)
    plot.setMenuEnabled(False)
    plot.showGrid(x=True, y=False, alpha=0.14)
    # Inverted so the first agent sits at the top, the way a list reads. The y range has to be set
    # by hand: flipping the axis does not re-range it, so without this the first and last rows sit
    # half-clipped off the top and bottom edges.
    view = plot.getViewBox()
    view.invertY(True)
    view.setYRange(-0.75, n - 0.25, padding=0)
    if max(pass_top) > 0:
        view.setXRange(0, max(pass_top) * 1.02, padding=0)


def _chart(title: str, subtitle: str) -> tuple[QWidget, object]:
    """A titled chart well. Returns the container and the `PlotWidget` (or `None` without pg)."""
    box = QWidget()
    lay = QVBoxLayout(box)
    lay.setContentsMargins(8, 8, 8, 4)
    lay.setSpacing(2)
    heading = QLabel(title)
    heading.setStyleSheet(f"color: {theme.INK}; font-weight: 600;")
    note = QLabel(subtitle)
    note.setWordWrap(True)
    note.setStyleSheet(f"color: {theme.INK_FAINT}; font-size: 11px;")
    lay.addWidget(heading)
    lay.addWidget(note)
    if not HAVE_PG:
        hint = QLabel(
            "pyqtgraph is not installed — run `pip install hexmind[qt]` for the charts. "
            "The ledger below is unaffected."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: {theme.INK_FAINT}; font-style: italic;")
        lay.addWidget(hint, 1)
        return box, None
    _config_pg()
    plot = pg.PlotWidget(background=theme.SUBSTRATE)
    lay.addWidget(plot, 1)
    return box, plot


class StatsPanel(QWidget):
    """Embeddable panel: agent reliability, team trouble spots, and the exact ledger.

    `agents` is the roster, in the order the room wants it shown; when omitted the panel reads
    the roster out of the ledger itself so the standalone app has something to show. `path`
    exists for tests and for a host that keeps its stats somewhere other than the default.
    """

    def __init__(
        self,
        parent=None,
        *,
        path: str | None = None,
        agents: Sequence[str] | None = None,
    ) -> None:
        super().__init__(parent)
        self.path = os.path.expanduser(path) if path else stats_path()
        self._agents = list(agents or [])
        self._explicit_agents = bool(agents)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(6)

        self.summary = QLabel(NO_STATS)
        self.summary.setStyleSheet(f"color: {theme.INK_DIM};")
        outer.addWidget(self.summary)

        split = QSplitter(Qt.Orientation.Vertical)
        outer.addWidget(split, 1)

        top = QSplitter(Qt.Orientation.Horizontal)
        agent_box, self.agent_plot = _chart(
            "Reliability by agent",
            "First-attempt audits only. A task that needed a revision still counts as a failure here.",
        )
        trouble_box, self.trouble_plot = _chart(
            "Where the team hurts",
            "Worst domains first. This is the one to route work away from.",
        )
        top.addWidget(agent_box)
        top.addWidget(trouble_box)
        top.setSizes([400, 400])
        split.addWidget(top)

        ledger = QWidget()
        led_lay = QVBoxLayout(ledger)
        led_lay.setContentsMargins(8, 4, 8, 8)
        led_lay.setSpacing(2)
        led_title = QLabel("The ledger")
        led_title.setStyleSheet(f"color: {theme.INK}; font-weight: 600;")
        self.table = QTableWidget(0, 0)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        led_lay.addWidget(led_title)
        led_lay.addWidget(self.table, 1)
        split.addWidget(ledger)
        split.setSizes([280, 320])

        self.reload()

    # -- data

    def reload(self) -> None:
        """Re-read the ledger from disk and redraw. Safe to call at any time."""
        try:
            data = auditor.Stats(self.path).data
        except Exception:  # pragma: no cover - Stats already absorbs a corrupt file
            logger.warning("Could not read stats from %s", self.path, exc_info=True)
            data = {}
        self._data = data if isinstance(data, dict) else {}
        if not self._explicit_agents or not self._agents:
            self._agents = discovered_agents(self._data)
        self._rebuild()

    def set_agents(self, agents: Sequence[str]) -> None:
        """Point the panel at a roster — the room's order, not the ledger's."""
        self._agents = list(agents or [])
        self._explicit_agents = True
        self._rebuild()

    def set_path(self, path: str) -> None:
        """Read a different ledger from now on, and redraw from it."""
        self.path = os.path.expanduser(path)
        self.reload()

    # -- rendering

    def _rebuild(self) -> None:
        domains = active_domains(self._data, self._agents)
        if not domains or not self._agents:
            self._clear_all()
            self.summary.setText(NO_STATS)
            return

        totals = compute_agent_totals(self._data, self._agents, domains)
        self.summary.setText(summary_line(totals))
        self._draw_agents(totals)
        self._draw_trouble(compute_trouble(self._data, self._agents, domains))
        self._fill_ledger(domains, totals)

    def _clear_all(self) -> None:
        for plot in (self.agent_plot, self.trouble_plot):
            if plot is not None:
                try:
                    plot.clear()
                except Exception:  # pragma: no cover
                    pass
        self.table.setRowCount(0)
        self.table.setColumnCount(0)

    def _draw_agents(self, totals: Sequence[tuple[str, int, int]]) -> None:
        if self.agent_plot is None:
            return
        try:
            _stack_bars(
                self.agent_plot,
                [name for name, _, _ in totals],
                [p for _, p, _ in totals],
                [f for _, _, f in totals],
            )
        except Exception:  # pragma: no cover - presentation only
            logger.warning("Agent chart failed to draw", exc_info=True)

    def _draw_trouble(self, rows: Sequence[tuple[str, int, int]]) -> None:
        if self.trouble_plot is None:
            return
        try:
            _stack_bars(
                self.trouble_plot,
                [name for name, _, _ in rows],
                [p for _, p, _ in rows],
                [f for _, _, f in rows],
            )
        except Exception:  # pragma: no cover - presentation only
            logger.warning("Trouble chart failed to draw", exc_info=True)

    def _fill_ledger(
        self, domains: Sequence[str], totals: Sequence[tuple[str, int, int]]
    ) -> None:
        cells = compute_cells(self._data, self._agents, domains)
        by_agent = {name: (p, f) for name, p, f in totals}

        self.table.clear()
        self.table.setColumnCount(len(domains) + 2)
        self.table.setRowCount(len(cells))
        self.table.setHorizontalHeaderLabels(["Agent", *domains, "overall"])

        for row, (agent, row_cells) in enumerate(cells):
            name_item = QTableWidgetItem(agent)
            name_item.setForeground(QColor(theme.INK))
            self.table.setItem(row, 0, name_item)

            for col, (passed, failed) in enumerate(row_cells, start=1):
                total = passed + failed
                text = f"{passed}/{total}" if total else "—"
                item = QTableWidgetItem(text)
                item.setForeground(QColor(cell_tone(passed, failed)))
                if total:
                    item.setToolTip(f"{passed} passed, {failed} failed on first attempt")
                else:
                    item.setToolTip("no audits recorded in this domain")
                self.table.setItem(row, col, item)

            passed, failed = by_agent.get(agent, (0, 0))
            total = passed + failed
            overall = QTableWidgetItem(f"{passed}/{total}" if total else "—")
            overall.setForeground(QColor(cell_tone(passed, failed)))
            overall.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.table.setItem(row, len(domains) + 1, overall)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for col in range(1, len(domains) + 2):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        self.table.resizeColumnsToContents()


__all__ = [
    "BAR_HEIGHT",
    "DEFAULT_STATS_PATH",
    "HAVE_PG",
    "NO_STATS",
    "StatsPanel",
    "active_domains",
    "cell",
    "cell_tone",
    "compute_agent_totals",
    "compute_cells",
    "compute_trouble",
    "discovered_agents",
    "stats_path",
    "summary_line",
]

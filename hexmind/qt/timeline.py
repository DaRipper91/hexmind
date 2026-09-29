"""Audit and verdict timeline: what the auditor actually said, task by task, in plan order.

The task board already shows *status*. This panel answers a different question: **did the work
survive the audit, and what did the auditor say about it?** Those are not the same axis, and
conflating them is the mistake this module exists to avoid.

The load-bearing decision is that **the verdict is read only from `Task.audit`** — which is
`"" | pass | fixed | disputed`, with the only assignments in the codebase at auditor.py:249 and
auditor.py:267. It is deliberately *not* inferred from `status`, because a task can be `failed` or
`skipped` for reasons that never went near an auditor (a backend died, a gate blocked it, a
dependency was skipped). Such a task reads red in its status cell and honestly reads UNKNOWN in its
verdict cell. A green verdict there would be a lie, and the panel's whole value is that its
verdicts can be trusted.

`fixed` is a PASS — the auditor rejected the work and a revision got it accepted — but it is
carried as *text detail*, never as a fourth hue. `theme.VERDICT_HUE` reserves three colours for
three meanings, and a revision that reads identically to a first-time pass is how a team concludes
it never needed revising.

There are no timestamps on `Task`, so plan order is the only time proxy there is, and it is the
honest one: the plan is what the team agreed to do, in the order it agreed to do it. Task ids are
`f"t{i+1}"` (core.py:320, 331), so a plain string sort puts t10 before t2 — hence `event_key`.

Every hue is a `theme` constant. There is no colour literal in this file.

`verdict_of`, `verdict_detail`, `event_key`, `timeline_rows`, `tally`, `summary_line` and
`visible_rows` are pure logic, testable without widgets and without a running room.
`TimelinePanel` is the embeddable widget, and it rebuilds from a host's `snapshot()` when given one.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Iterable, Sequence

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from . import theme

logger = logging.getLogger(__name__)

#: The three verdicts, matching `theme.VERDICT_HUE` exactly. Any new value has to be added in both
#: places or this panel draws a cell with no colour.
PASS = "PASS"
FAIL = "FAIL"
UNKNOWN = "UNKNOWN"

COLUMNS = ("Task", "Agent", "Domain", "Status", "Verdict", "Detail")

NO_TASKS = "No plan yet. Ask the lead to plan and the verdicts land here."
NO_VERDICTS = "No audited tasks yet. The runner-up reviews work as it finishes."

#: The reading instruction, printed where the verdict is read rather than left to be inferred —
#: the same discipline the stats panel applies to "first-attempt".
CAPTION = (
    "Verdicts are the auditor's own, never the task status. "
    "Work accepted only after a revision still reads as cleared — the detail says so."
)

#: Task ids are short and meaningless to a human ("t7"), so they are pushed right against the
#: column edge and the eye reads them down the margin rather than through the data.
AlignRight = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter


# ---------- pure logic ----------


def tasks_of(source: Any) -> list[Any]:
    """The task list out of whatever the caller had to hand.

    A room's `snapshot()` gives `{"tasks": {id: Task}}`; a host that already flattened it gives a
    list; a generator works too. Anything unrecognised yields an empty list rather than raising,
    because a panel must not be able to take the room down by being pointed at the wrong thing.
    """
    if source is None:
        return []
    if isinstance(source, dict):
        if "tasks" in source:
            return tasks_of(source["tasks"])
        source = list(source.values())
    if isinstance(source, (list, tuple, set, frozenset)):
        return [item for item in source if item is not None]
    if isinstance(source, Iterable) and not isinstance(source, (str, bytes)):
        return [item for item in source if item is not None]
    return []


def verdict_of(task: Any) -> str:
    """The audit verdict of one task, and nothing else.

    Reads `Task.audit` only. `pass` and `fixed` are both PASS — a task that needed a revision still
    ended up accepted. `disputed` is FAIL. Everything else, including the empty string on a task
    that never reached an auditor, is UNKNOWN. An unrecognised value also reads UNKNOWN, so a
    future `Task.audit` state shows as "not judged" instead of being silently read as a pass.
    """
    value = str(getattr(task, "audit", "") or "").strip().lower()
    if value in ("pass", "fixed"):
        return PASS
    if value == "disputed":
        return FAIL
    return UNKNOWN


def verdict_detail(task: Any) -> str:
    """The words that make a verdict readable, and the only place `fixed` is allowed to show up.

    Naming the auditor matters because a disputed verdict is a disagreement between two named
    models, not a mysterious red cell.
    """
    audit = str(getattr(task, "audit", "") or "").strip().lower()
    auditor = str(getattr(task, "auditor", "") or "").strip()
    if audit == "fixed":
        return f"passed after revision vs {auditor}" if auditor else "passed after revision"
    if audit == "disputed":
        return f"disputed vs {auditor}" if auditor else "disputed"
    if audit == "pass":
        return f"cleared by {auditor}" if auditor else "cleared"
    return ""


def history_detail(task: Any) -> str:
    """Format every recorded audit round for the courtroom tooltip."""
    history = getattr(task, "audit_history", None)
    if not isinstance(history, list) or not history:
        return ""
    lines = []
    for entry in history:
        if not isinstance(entry, dict):
            continue
        round_number = entry.get("round", "?")
        verdict = str(entry.get("verdict", "UNKNOWN"))
        auditor = str(entry.get("auditor", "") or "")
        issues = str(entry.get("issues", "") or "").strip()
        line = f"Round {round_number}: {verdict}"
        if auditor:
            line += f" by {auditor}"
        if issues and verdict != PASS:
            line += f" — {issues}"
        lines.append(line)
    return "\n".join(lines)


def event_key(item: Any) -> tuple[int, int, str]:
    """Plan order, numerically. Accepts a task or a bare id.

    Task ids are `t1`, `t2`, … `t10`, so a lexicographic sort files t10 between t1 and t2 and the
    timeline reads as if the plan had been reordered. Splitting the digits and sorting them as a
    number fixes that; ids with no digits sort after the numeric ones, alphabetically, so an
    unexpected id is visible at the end rather than smeared through the middle.
    """
    tid = item if isinstance(item, str) else str(getattr(item, "id", "") or "")
    digits = "".join(ch for ch in tid if ch.isdigit())
    if digits:
        return (0, int(digits), tid)
    return (1, 0, tid)


@dataclass(frozen=True)
class Row:
    """One task, flattened to exactly what the table draws.

    Frozen because a row is a reading of a task, not a view onto it: nothing here may be edited,
    and nothing here may be confused for the `Task` it came from.
    """

    task_id: str
    agent: str
    domain: str
    status: str
    verdict: str
    detail: str
    history: str = ""


def timeline_rows(tasks: Any) -> list[Row]:
    """Every task as a `Row`, in plan order. Tolerant of a list, an id-keyed dict or a snapshot."""
    rows: list[Row] = []
    for task in tasks_of(tasks):
        rows.append(
            Row(
                task_id=str(getattr(task, "id", "") or ""),
                agent=str(getattr(task, "agent", "") or ""),
                domain=str(getattr(task, "domain", "") or ""),
                status=str(getattr(task, "status", "") or ""),
                verdict=verdict_of(task),
                detail=verdict_detail(task),
                history=history_detail(task),
            )
        )
    rows.sort(key=lambda row: event_key(row.task_id))
    return rows


def tally(rows: Sequence[Row]) -> dict[str, int]:
    """How many of each verdict, plus the total. Always returns all three keys, so a caller can
    read `counts[FAIL]` without a `.get()` guard on a verdict that simply has not happened yet."""
    counts = {PASS: 0, FAIL: 0, UNKNOWN: 0, "total": len(rows)}
    for row in rows:
        counts[row.verdict] = counts.get(row.verdict, 0) + 1
    return counts


def summary_line(counts: dict[str, int]) -> str:
    """The one-line reading of the tally.

    A room where nothing has been audited yet says so in its own words instead of printing
    "0 cleared, 0 disputed", which would read as a run in which everything failed to be judged.
    """
    total = int(counts.get("total", 0) or 0)
    if not total:
        return NO_TASKS
    passed = int(counts.get(PASS, 0) or 0)
    failed = int(counts.get(FAIL, 0) or 0)
    unknown = int(counts.get(UNKNOWN, 0) or 0)
    if not passed and not failed:
        return f"{total} planned · none audited yet"
    bits = [f"{total} planned", f"{passed} cleared", f"{failed} disputed"]
    if unknown:
        bits.append(f"{unknown} never audited")
    return " · ".join(bits)


def visible_rows(rows: Sequence[Row], audited_only: bool = False) -> list[Row]:
    """The rows to draw. `audited_only` drops the UNKNOWN ones.

    Off by default: a fresh room is nearly all UNKNOWN, and hiding those by default would make the
    panel look broken before the audit loop has had anything to do. The filter is offered because
    once a plan is long, "the three tasks the auditor rejected" is the question worth one click.
    """
    if not audited_only:
        return list(rows)
    return [row for row in rows if row.verdict != UNKNOWN]


# ---------- the widget ----------


class TimelinePanel(QWidget):
    """The audit/verdict timeline, embeddable as a tab.

    Constructed with nothing it shows its empty states; hand it `tasks=` or a `host=` with a
    `snapshot()` and it builds from that. Every hue resolves through `theme`, so a state added to
    the app's palette shows up here without a second edit.
    """

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        host: Any | None = None,
        tasks: Any | None = None,
        audited_only: bool = False,
    ) -> None:
        super().__init__(parent)
        self._host = host
        self._rows: list[Row] = timeline_rows(tasks) if tasks is not None else []
        self._audited_only = bool(audited_only)
        self._build()
        self._rebuild()

    # -- construction

    def _build(self) -> None:
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 6, 8, 8)
        lay.setSpacing(4)

        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        self.summary = QLabel()
        self.summary.setStyleSheet(f"color: {theme.INK}; font-weight: 600;")
        head.addWidget(self.summary, 1)
        self.auditedOnly = QCheckBox("audited only")
        self.auditedOnly.setChecked(self._audited_only)
        self.auditedOnly.setToolTip("Hide tasks the auditor has not judged")
        self.auditedOnly.toggled.connect(self._on_audited_only)
        head.addWidget(self.auditedOnly, 0)
        lay.addLayout(head)

        self.caption = QLabel(CAPTION)
        self.caption.setWordWrap(True)
        self.caption.setStyleSheet(f"color: {theme.INK_FAINT}; font-size: 11px;")
        lay.addWidget(self.caption)

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(list(COLUMNS))
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        lay.addWidget(self.table, 1)

    # -- data

    def set_host(self, host: Any | None) -> None:
        """Point the panel at a room and rebuild from it. A host without `snapshot()` clears it."""
        self._host = host
        self.refresh()

    def set_tasks(self, tasks: Any) -> None:
        """Replace the rows outright, without going back to the host."""
        self._rows = timeline_rows(tasks)
        self._rebuild()

    def set_audited_only(self, on: bool) -> None:
        """Same as ticking the checkbox, and keeps the checkbox in step when set in code."""
        self.auditedOnly.setChecked(bool(on))

    def refresh(self) -> None:
        """Re-read the host's snapshot. Safe to call at any time; a missing host clears the panel."""
        snapshot = getattr(self._host, "snapshot", None)
        self._rows = timeline_rows(snapshot()) if callable(snapshot) else []
        self._rebuild()

    # -- rendering

    def _on_audited_only(self, on: bool) -> None:
        self._audited_only = bool(on)
        self._rebuild()

    def _rebuild(self) -> None:
        rows = visible_rows(self._rows, self._audited_only)
        self.summary.setText(summary_line(tally(self._rows)))

        if not rows:
            self._clear()
            self.caption.setText(NO_VERDICTS if self._audited_only and self._rows else CAPTION)
            return

        self.caption.setText(CAPTION)
        self.table.setRowCount(len(rows))
        for index, row in enumerate(rows):
            self._fill_row(index, row)
        self._size_columns()

    def _clear(self) -> None:
        self.table.clear()
        self.table.setRowCount(0)
        self.table.setHorizontalHeaderLabels(list(COLUMNS))

    def _fill_row(self, index: int, row: Row) -> None:
        self._cell(index, 0, row.task_id, theme.INK, AlignRight)
        self._cell(index, 1, row.agent or "—", theme.INK)
        self._cell(index, 2, row.domain or "—", theme.INK_DIM)

        status_item = self._cell(index, 3, row.status or "—", theme.state_hue(row.status))
        # The two columns disagree on purpose, often. Say so on the status cell rather than
        # letting a red status next to an UNKNOWN verdict look like a rendering fault.
        status_item.setToolTip(f"task status · verdict {row.verdict.lower()} by the auditor")

        verdict_item = self._cell(index, 4, row.verdict, theme.VERDICT_HUE.get(row.verdict, theme.SLATE))
        verdict_item.setToolTip(row.history or row.detail or "no audit verdict recorded")
        self._cell(index, 5, row.detail or "—", theme.INK_DIM)

    def _cell(self, index: int, column: int, text: str, hue: str, align=None) -> QTableWidgetItem:
        item = QTableWidgetItem(text)
        item.setForeground(QColor(hue))
        if align is not None:
            item.setTextAlignment(align)
        self.table.setItem(index, column, item)
        return item

    def _size_columns(self) -> None:
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        for column in (1, 2, 3, 4):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        self.table.resizeColumnsToContents()


__all__ = [
    "CAPTION",
    "COLUMNS",
    "FAIL",
    "NO_TASKS",
    "NO_VERDICTS",
    "PASS",
    "Row",
    "TimelinePanel",
    "UNKNOWN",
    "event_key",
    "history_detail",
    "summary_line",
    "tally",
    "tasks_of",
    "timeline_rows",
    "verdict_detail",
    "verdict_of",
    "visible_rows",
]

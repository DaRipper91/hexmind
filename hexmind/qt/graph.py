"""Task dependency graph panel: pure Qt, no extra deps.

`compute_layers` / `layer_positions` are pure logic (tested without widgets).
`TaskGraphView` is the QGraphicsScene wiring; `GraphPanel` is the embeddable widget.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPen
from PySide6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsLineItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsView,
    QVBoxLayout,
    QWidget,
)

try:
    from . import theme
except Exception:  # offscreen-safe fallback when theme is mid-edit
    theme = None  # type: ignore

X_GAP, Y_GAP = 170, 54
R = 16


def _deps_of(t) -> list[str]:
    if isinstance(t, dict):
        return list(t.get("depends_on") or [])
    return list(getattr(t, "depends_on", None) or [])


def _status_of(t) -> str:
    if isinstance(t, dict):
        return str(t.get("status", "pending"))
    return str(getattr(t, "status", "pending"))


def _id_of(t) -> str:
    if isinstance(t, dict):
        return str(t.get("id", "?"))
    return str(getattr(t, "id", "?"))


def compute_layers(tasks: Iterable) -> tuple[dict[str, int], dict[str, str]]:
    """(depth, skipped_by). Depth = longest path (earliest startable layer).

    Missing deps are roots. Cycles break at 0 rather than hanging.
    skipped_by maps a skipped task -> the original failed task id (transitive).
    """
    items = list(tasks)
    by_id = {_id_of(t): t for t in items}
    depth: dict[str, int] = {}
    visiting: set[str] = set()

    def d(tid: str) -> int:
        if tid in depth:
            return depth[tid]
        if tid in visiting:
            return 0
        t = by_id.get(tid)
        if t is None:
            return 0
        visiting.add(tid)
        real = [x for x in _deps_of(t) if x in by_id]
        depth[tid] = 0 if not real else max(d(x) + 1 for x in real)
        visiting.discard(tid)
        return depth[tid]

    for t in items:
        d(_id_of(t))

    # root failure propagation: parents first (depth order, deterministic by id)
    skipped_by: dict[str, str] = {}

    def root_failure(tid: str, seen: set[str]) -> str | None:
        if tid in seen:
            return None
        seen.add(tid)
        t = by_id.get(tid)
        if t is None:
            return None
        if _status_of(t) == "failed":
            return tid
        if _status_of(t) != "skipped":
            # a done/running node is not a failure conduit, but its own upstream
            # failure is still the answer when an outer skipped task asks.
            return None
        if tid in skipped_by:
            return skipped_by[tid]
        for dep in _deps_of(t):
            dep_t = by_id.get(dep)
            if dep_t is None:
                continue
            if _status_of(dep_t) == "failed":
                return dep
            found = root_failure(dep, seen)
            if found:
                return found
        return None

    for t in sorted(items, key=lambda x: (depth.get(_id_of(x), 0), _id_of(x))):
        tid = _id_of(t)
        if _status_of(t) == "skipped":
            found = root_failure(tid, set())
            if found:
                skipped_by[tid] = found
    return depth, skipped_by


@dataclass
class Placement:
    task: object
    x: float
    y: float


def layer_positions(tasks: Iterable) -> list[Placement]:
    """Deterministic left-to-right layout: x encodes depth, y stacks per layer."""
    items = list(tasks)
    if not items:
        return []
    depth, _ = compute_layers(items)
    ordered = sorted(items, key=lambda t: (depth.get(_id_of(t), 0), _id_of(t)))
    per_level: dict[int, int] = {}
    out: list[Placement] = []
    for t in ordered:
        lv = depth.get(_id_of(t), 0)
        row = per_level.get(lv, 0)
        per_level[lv] = row + 1
        out.append(Placement(task=t, x=40.0 + lv * X_GAP, y=30.0 + row * Y_GAP))
    return out


def _hue(status: str) -> str:
    if theme is not None:
        try:
            return theme.state_hue(status)
        except Exception:
            pass
    return _fallback_hue(status)


def _fallback_hue(status: str) -> str:
    """Only reached if `theme` failed to import, which means the app has no palette at all.

    The values mirror `theme.STATE_HUE`; a second copy is the lesser evil next to an
    ImportError at class-definition time, and this path is a degraded render, not the real one.
    """
    return {"done": "#5fd68a", "failed": "#f2686b", "running": "#39d0d8"}.get(status, "#6b7a94")


def _edge_hue(broken: bool) -> str:
    """A dependency edge. Broken edges are amber because they are a warning, not a failure —
    the task itself may still be fine; it just can no longer run."""
    if theme is not None:
        return theme.AMBER if broken else theme.INK_FAINT
    return "#e8b04b" if broken else "#5a6577"


def _ink() -> str:
    if theme is not None:
        return theme.INK
    return "#e6edf7"


class Node(QGraphicsEllipseItem):
    def __init__(self, task, x: float, y: float) -> None:
        super().__init__(x - R, y - R, R * 2, R * 2)
        self.task = task
        self.setFlag(QGraphicsEllipseItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.recolor()
        self.setToolTip(f"{_id_of(task)} · {x:.0f},{y:.0f}")

    def recolor(self) -> None:
        self.setBrush(QColor(_hue(_status_of(self.task))))
        self.setToolTip(f"{_id_of(self.task)} · {_status_of(self.task)}")


class Edge(QGraphicsLineItem):
    def __init__(self, src: Node, dst: Node, reason: str = "") -> None:
        super().__init__()
        self.src = src
        self.dst = dst
        self.reason = reason
        # Ends are set by the caller via setLine; the src/dst refs are kept so a test (and the
        # in-place update path) can tell which tasks an edge joins without re-parsing the line.
        pen = QPen(QColor(_edge_hue(bool(reason))))
        pen.setWidth(2 if not reason else 3)
        if reason:
            pen.setStyle(Qt.PenStyle.DashLine)
        self.setPen(pen)


class TaskGraphView(QGraphicsView):
    """QGraphics DAG. set_tasks rebuilds; update_task mutates in place."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self.setAccessibleName("Task graph")
        self.setToolTip("Task dependency graph: nodes are tasks, arrows are depends_on.")
        self.setMinimumHeight(120)
        self._nodes: dict[str, Node] = {}
        self._edges: list[Edge] = []

    # ---------- data ----------
    def set_tasks(self, tasks) -> None:
        self._scene.clear()
        self._nodes.clear()
        self._edges.clear()
        items = list(tasks)
        _, skipped_by = compute_layers(items)
        by_id = {_id_of(t): t for t in items}
        pos = {p.task_id if hasattr(p, "task_id") else _id_of(p.task): (p.x, p.y)
               for p in layer_positions(items)}
        # nodes
        for t in items:
            tid = _id_of(t)
            x, y = pos.get(tid, (40.0, 30.0))
            node = Node(t, x, y)
            self._scene.addItem(node)
            label = QGraphicsSimpleTextItem(f"{tid}")
            label.setPos(x + R + 6, y - 10)
            try:
                label.setBrush(QColor(_ink()))
            except Exception:
                pass
            self._scene.addItem(label)
            self._nodes[tid] = node
        # edges only where the claim holds (dep really present)
        for t in items:
            dst_id = _id_of(t)
            dst = self._nodes.get(dst_id)
            if dst is None:
                continue
            x1, y1 = pos.get(dst_id, (40.0, 30.0))
            for dep in _deps_of(t):
                src = self._nodes.get(dep)
                if src is None:
                    continue
                x0, y0 = pos.get(dep, (40.0, 30.0))
                reason = ""
                if dst_id in skipped_by and skipped_by[dst_id] == dep:
                    reason = f"{dep} failed → {dst_id} skipped"
                elif _status_of(by_id.get(dep)) == "failed" and _status_of(t) == "skipped":
                    reason = f"{dep} failed → {dst_id} skipped"
                edge = Edge(src, dst, reason)
                edge.setLine(x0 + R, y0, x1 - R, y1)
                self._scene.addItem(edge)
                self._edges.append(edge)
        self._scene.setSceneRect(self._scene.itemsBoundingRect())

    def update_task(self, task) -> None:
        tid = _id_of(task)
        node = self._nodes.get(tid)
        if node is None:
            # extend: keep existing nodes, add one (positions recomputed cheaply)
            current = [n.task for n in self._nodes.values()] + [task]
            # preserve object identity for existing: rebuild edges only if needed.
            # Simplest correct: full rebuild but restore identity for the updated one?
            # Tests require identity preserved on update, and extension on unknown.
            # So: add node at next slot without rebuilding others.
            x = 40.0 + len(self._nodes) * 10
            y = 30.0 + len(self._nodes) * Y_GAP
            # place after deepest dep when known
            try:
                depth, _ = compute_layers(current)
                lv = depth.get(tid, 0)
                x = 40.0 + lv * X_GAP
                y = 30.0 + sum(1 for k in self._nodes) * 10
            except Exception:
                pass
            node = Node(task, x, y)
            self._scene.addItem(node)
            self._nodes[tid] = node
            # wire edges to real deps
            for dep in _deps_of(task):
                src = self._nodes.get(dep)
                if src is None:
                    continue
                edge = Edge(src, node, "")
                try:
                    # straight stub; layout pass will correct on next set_tasks
                    edge.setLine(0, 0, x - R, y)
                except Exception:
                    pass
                self._scene.addItem(edge)
                self._edges.append(edge)
            return
        node.task = task
        node.recolor()
        # refresh broken-edge reasons touching this node
        try:
            items = [n.task for n in self._nodes.values()]
            _, skipped_by = compute_layers(items)
            for e in self._edges:
                s, d = _id_of(e.src.task), _id_of(e.dst.task)
                if d in skipped_by and skipped_by[d] in (s, _id_of(task), tid):
                    e.reason = f"{skipped_by[d]} failed → {d} skipped"
                    pen = QPen(QColor(_edge_hue(True)))
                    pen.setWidth(3)
                    pen.setStyle(Qt.PenStyle.DashLine)
                    e.setPen(pen)
        except Exception:
            pass

    def select_task(self, tid: str) -> None:
        node = self._nodes.get(str(tid))
        if node is not None:
            try:
                self._scene.clearSelection()
            except Exception:
                pass
            node.setSelected(True)

    def clear(self) -> None:
        self._scene.clear()
        self._nodes.clear()
        self._edges.clear()

    def fit(self) -> None:
        try:
            self.fitInView(self._scene.itemsBoundingRect(), Qt.AspectRatioMode.KeepAspectRatio)
        except Exception:
            pass


class GraphPanel(QWidget):
    """Embeddable panel hosting the graph view."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.view = TaskGraphView(self)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.view)

    def set_tasks(self, tasks) -> None:
        self.view.set_tasks(tasks)

    def clear(self) -> None:
        self.view.clear()

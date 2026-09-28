"""The task graph panel, offscreen.

Skipped when PySide6 is absent, like `tests/test_qt.py`. `QT_QPA_PLATFORM=offscreen`.

Most of what matters in this panel is *geometry and logic*, not pixels, so the majority of these
tests never construct a widget: `compute_layers` and `layer_positions` are pure and are tested
directly, which is both faster and a stronger test than asserting on a scene. The widget tests
that remain cover the wiring a pure test cannot reach — that a status change re-colours the right
node, and that a cascade explanation reaches the user.
"""
from __future__ import annotations

import pytest

pytest.importorskip("PySide6", reason="the qt extra is not installed")

from PySide6.QtWidgets import QApplication

from hexmind.core import Task
from hexmind.qt import theme
from hexmind.qt.graph import (
    GraphPanel,
    TaskGraphView,
    compute_layers,
    layer_positions,
)


def t(task_id: str, depends_on: list[str] | None = None, status: str = "pending",
      **kw) -> Task:
    return Task(id=task_id, title=f"task {task_id}", agent="claude", instructions="x",
                depends_on=depends_on or [], status=status, **kw)


# ---------- layering: the pure logic ----------

def test_an_empty_plan_layers_to_nothing():
    assert compute_layers([]) == ({}, {})
    assert layer_positions([]) == []


def test_roots_are_layer_zero():
    depth, _ = compute_layers([t("a"), t("b")])
    assert depth == {"a": 0, "b": 0}


def test_depth_is_the_earliest_a_task_could_start():
    """Longest path, not shortest. `c` has a direct edge to `a` *and* a chain under it, so its
    real depth is 2 — a shortest-path or BFS layering would put it at 1 and draw the graph
    implying `c` could run before `b`, which is false."""
    tasks = [t("a"), t("b", ["a"]), t("c", ["a", "b"])]
    depth, _ = compute_layers(tasks)
    assert depth["a"] == 0
    assert depth["b"] == 1
    assert depth["c"] == 2


def test_layout_is_left_to_right_by_depth():
    """Cause to effect: x encodes depth, so a plan always reads the same way."""
    placements = {p.task.id: p for p in layer_positions([t("a"), t("b", ["a"]), t("c", ["b"])])}
    assert placements["a"].x < placements["b"].x < placements["c"].x


def test_layout_is_deterministic():
    """The same plan must lay out identically every time, or two runs cannot be compared by eye."""
    tasks = [t("a"), t("b"), t("c", ["a"]), t("d", ["a"]), t("e", ["b", "c"])]
    first = [(p.task.id, p.x, p.y) for p in layer_positions(tasks)]
    second = [(p.task.id, p.x, p.y) for p in layer_positions(tasks)]
    assert first == second


def test_nodes_in_a_layer_never_overlap():
    tasks = [t(f"n{i}") for i in range(12)]  # 12 independent roots, one layer
    placements = layer_positions(tasks)
    ys = sorted(p.y for p in placements)
    assert len(set(ys)) == len(ys), "two nodes share a row"


def test_a_dependency_on_a_task_that_is_not_present_is_treated_as_a_root():
    """A hand-built Task list (a test, or a partially-restored session) can name a dependency that
    is not in the set. That must not raise — the panel still draws everything else."""
    depth, _ = compute_layers([t("a", ["ghost"])])
    assert depth["a"] == 0


def test_a_cycle_does_not_hang_or_raise():
    """`parse_plan` rejects cycles, so this cannot arrive from a lead. But a self-referential or
    mutually-referential list must still render rather than spin forever in the layout."""
    depth, _ = compute_layers([t("a", ["b"]), t("b", ["a"])])
    assert set(depth) == {"a", "b"}


# ---------- cascades: the forensic value ----------

def test_a_task_whose_dependency_failed_is_recorded_as_skipped_by_it():
    tasks = [t("a", status="failed"), t("b", ["a"], status="skipped")]
    _, skipped_by = compute_layers(tasks)
    assert skipped_by["b"] == "a", "the graph must say WHICH upstream task caused the skip"


def test_the_skip_reason_survives_a_deep_chain():
    tasks = [t("a", status="failed"), t("b", ["a"], status="skipped"),
             t("c", ["b"], status="skipped"), t("d", ["c"], status="skipped")]
    _, skipped_by = compute_layers(tasks)
    # every downstream task points at the original failure, not at its immediate parent, so
    # "why was this skipped" is always one answer rather than a chain to walk
    assert skipped_by == {"b": "a", "c": "a", "d": "a"}


def test_a_healthy_chain_records_no_skips():
    _, skipped_by = compute_layers([t("a", status="done"), t("b", ["a"], status="done")])
    assert skipped_by == {}


# ---------- theme: the single mapping ----------

def test_every_core_task_status_has_a_posted_hue():
    from hexmind.core import BUSY_STATUSES
    for status in BUSY_STATUSES | {"pending", "done", "failed", "skipped"}:
        assert theme.state_hue(status) in theme.STATE_HUE.values()


def test_an_unknown_status_reads_as_idle_rather_than_raising():
    assert theme.state_hue("teleporting") == theme.SLATE


def test_live_is_exactly_the_busy_set():
    """A node glows iff it is in flight. If these two ever disagree, the glow starts lying."""
    from hexmind.core import BUSY_STATUSES
    live = {s for s in theme.STATE_HUE if theme.is_live(s)}
    assert live == set(BUSY_STATUSES)


def test_busy_hues_agree_with_the_core_list():
    from hexmind.core import BUSY_STATUSES
    assert set(theme.BUSY_HUES) == set(BUSY_STATUSES)


# ---------- the widget ----------

@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def panel(qapp):
    """Every panel built is kept referenced and closed, in the same shape as `tests/test_qt.py`'s
    `room` fixture. A QGraphicsView whose scene is destroyed while Qt still holds pointers to its
    items is a segfault, not a Python exception, so cleanup here is not optional."""
    made: list[GraphPanel] = []

    def build(**kwargs) -> GraphPanel:
        widget = GraphPanel(**kwargs)
        made.append(widget)
        return widget

    yield build
    for widget in made:
        widget.clear()
        widget.close()
        del widget
    made.clear()
    qapp.processEvents()


def test_set_tasks_builds_one_node_per_task(panel):
    view = panel().view
    view.set_tasks([t("a"), t("b", ["a"]), t("c", ["a"])])
    assert set(view._nodes) == {"a", "b", "c"}


def test_an_edge_exists_only_where_a_dependency_is_real(panel):
    """A wire is a claim about causality, so it is drawn only where the claim holds."""
    view = panel().view
    view.set_tasks([t("a"), t("b", ["a"]), t("c", ["ghost"])])
    assert len(view._edges) == 1, "only b-after-a is a real edge"
    edge = view._edges[0]
    assert edge.src.task.id == "a" and edge.dst.task.id == "b"


def test_a_failed_dependency_marks_its_edge_as_a_broken_claim(panel):
    view = panel().view
    view.set_tasks([t("a", status="failed"), t("b", ["a"], status="skipped")])
    assert len(view._edges) == 1
    assert view._edges[0].reason, "a broken edge must say so, not draw as a normal wire"
    assert "a" in view._edges[0].reason


def test_updating_a_task_mutates_its_node_in_place(panel):
    """Rebuilding on every status change would make nodes jump while the user watches."""
    view = panel().view
    task = t("a")
    view.set_tasks([task])
    node = view._nodes["a"]
    view.update_task(t("a", status="done"))
    assert view._nodes["a"] is node, "the node object was replaced; it should have been updated"
    assert node.task.status == "done"


def test_a_task_event_for_an_unknown_task_extends_rather_than_drops_it(panel):
    view = panel().view
    view.set_tasks([t("a")])
    view.update_task(t("b", ["a"]))
    assert set(view._nodes) == {"a", "b"}


def test_selecting_a_task_selects_its_node(panel):
    view = panel().view
    view.set_tasks([t("a"), t("b")])
    view.select_task("b")
    assert [n.task.id for n in view._scene.selectedItems()] == ["b"]


def test_clearing_empties_the_graph(panel):
    view = panel().view
    view.set_tasks([t("a"), t("b", ["a"])])
    view.clear()
    assert not view._nodes and not view._edges and not view._scene.items()


def test_the_panel_is_offscreen_safe_and_paints(panel):
    """A QGraphicsView that raises on paint is a window that shows nothing and explains nothing."""
    p = panel()
    p.set_tasks([t("a"), t("b", ["a"])])
    p.resize(900, 600)
    p.view.fit()
    p.view.grab()  # forces a real render of every item

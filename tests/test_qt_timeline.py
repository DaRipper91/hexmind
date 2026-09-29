"""The audit/verdict timeline, offscreen.

Skipped when PySide6 is absent, like `tests/test_qt.py`. `QT_QPA_PLATFORM=offscreen`.

Most of these tests never build a widget. The verdict rules, the plan ordering and the tally are
pure, and that is where the claims this panel makes about *itself* get pinned down: that a verdict
is never inferred from a status, that a revision is not silently a first-time pass, and that a
task the auditor never saw is reported as unknown rather than folded into a pass rate.

The widget tests at the end cover the wiring a pure test cannot reach: that a red status next to an
UNKNOWN verdict is drawn as two different things, and that the filter reduces rows without
rewriting the summary.
"""
from __future__ import annotations

import pytest

pytest.importorskip("PySide6", reason="the qt extra is not installed")

from PySide6.QtWidgets import QApplication

from hexmind.core import Task
from hexmind.qt import theme, timeline


def make_task(tid, *, agent="w1", domain="tests", status="done", audit="", auditor=""):
    """A real `Task`, because the panel reads attributes the dataclass actually has."""
    return Task(
        id=tid,
        title=f"do {tid}",
        agent=agent,
        instructions="",
        status=status,
        domain=domain,
        audit=audit,
        auditor=auditor,
    )


#: Four tasks covering the whole `Task.audit` vocabulary plus the two cases the panel exists to
#: keep apart: t2 never reached an auditor, and t3's work was contradicted after a revision.
PLAN = [
    make_task("t1", agent="lead", audit="pass", auditor="claude"),
    make_task("t2", agent="w1", domain="security", status="failed", audit="", auditor=""),
    make_task("t3", agent="w2", domain="sorcery", audit="disputed", auditor="gpt-5"),
    make_task("t4", agent="w3", domain="docs", audit="fixed", auditor="gpt-5"),
]


# ---------- the verdict axis, kept off the status axis ----------


def test_the_three_audited_states_read_as_two_verdicts():
    """`pass` and `fixed` are both PASS, `disputed` is FAIL. Nothing else is a verdict."""
    assert timeline.verdict_of(make_task("t1", audit="pass")) == timeline.PASS
    assert timeline.verdict_of(make_task("t1", audit="fixed")) == timeline.PASS
    assert timeline.verdict_of(make_task("t1", audit="disputed")) == timeline.FAIL


def test_a_task_the_auditor_never_saw_is_unknown():
    assert timeline.verdict_of(make_task("t1", audit="")) == timeline.UNKNOWN


def test_a_failed_task_is_not_a_disputed_task():
    """The load-bearing distinction. `failed`/`skipped` happen for reasons that never went near an
    auditor — a backend died, a gate blocked it — so the verdict stays UNKNOWN rather than being
    inferred from the status. A red FAIL here would be a verdict nobody gave."""
    assert timeline.verdict_of(make_task("t1", status="failed", audit="")) == timeline.UNKNOWN
    assert timeline.verdict_of(make_task("t1", status="skipped", audit="")) == timeline.UNKNOWN
    # and the status is still available to whoever wants it
    assert theme.state_hue("failed") == theme.RED


def test_an_unrecognised_audit_value_reads_as_not_judged():
    """A future `Task.audit` state must show as unknown rather than fall through to a pass."""
    assert timeline.verdict_of(make_task("t1", audit="contested")) == timeline.UNKNOWN
    assert timeline.verdict_of(make_task("t1", audit="PASS")) == timeline.PASS  # case-insensitive


def test_the_verdicts_match_the_theme_it_draws_them_with():
    """Three meanings, three hues, and the vocabulary is spelled the same way in both places."""
    hues = set(theme.VERDICT_HUE)
    assert hues == {timeline.PASS, timeline.FAIL, timeline.UNKNOWN}


# ---------- `fixed` is carried as words, not as a fourth colour ----------


def test_a_revision_says_so_in_the_detail_column():
    """Same hue as a clean pass, different words. This is the only place `fixed` is visible."""
    task = make_task("t1", audit="fixed", auditor="gpt-5")
    assert timeline.verdict_detail(task) == "passed after revision vs gpt-5"


def test_a_clean_pass_and_a_dispute_both_name_the_auditor():
    """A red cell is a disagreement between two named models, not a mystery."""
    assert timeline.verdict_detail(make_task("t1", audit="pass", auditor="claude")) == "cleared by claude"
    assert timeline.verdict_detail(make_task("t1", audit="disputed", auditor="gpt-5")) == "disputed vs gpt-5"


def test_audit_history_preserves_each_round_for_the_courtroom():
    task = make_task("t1", audit="fixed", auditor="gpt-5")
    task.audit_history = [
        {"round": 1, "auditor": "gpt-5", "verdict": "FAIL", "issues": "missing test"},
        {"round": 2, "auditor": "gpt-5", "verdict": "PASS", "issues": ""},
    ]

    assert timeline.history_detail(task) == (
        "Round 1: FAIL by gpt-5 — missing test\n"
        "Round 2: PASS by gpt-5"
    )


def test_an_unjudged_task_has_nothing_to_say():
    assert timeline.verdict_detail(make_task("t1", audit="")) == ""
    assert timeline.verdict_detail(make_task("t1", audit="pass")) == "cleared"


# ---------- plan order ----------


def test_task_ten_sorts_after_task_two():
    """Ids are `t{i+1}` (core.py:320), so a lexicographic sort files t10 between t1 and t2 and the
    timeline reads as if the plan had been reordered."""
    order = sorted(["t10", "t2", "t1"], key=timeline.event_key)
    assert order == ["t1", "t2", "t10"]


def test_ids_without_digits_sort_last():
    """An id the app has not seen is visible at the end rather than smeared through the middle."""
    keys = sorted(["zeta", "t3", "alpha"], key=timeline.event_key)
    assert keys == ["t3", "alpha", "zeta"]


def test_event_key_takes_either_a_task_or_a_bare_id():
    assert timeline.event_key("t7") == timeline.event_key(make_task("t7"))
    assert timeline.event_key(make_task("t7")) == (0, 7, "t7")


# ---------- assembling rows ----------


def test_rows_come_out_in_plan_order():
    rows = timeline.timeline_rows([make_task("t2"), make_task("t10"), make_task("t1")])
    assert [row.task_id for row in rows] == ["t1", "t2", "t10"]


def test_a_snapshot_dict_and_a_plain_list_agree():
    """`_Room.snapshot()` gives `{"tasks": {id: Task}}`; a host that already flattened it gives a
    list. Both have to build the same table."""
    as_list = timeline.timeline_rows(PLAN)
    as_dict = timeline.timeline_rows({task.id: task for task in PLAN})
    as_snapshot = timeline.timeline_rows({"tasks": {task.id: task for task in PLAN}})
    assert as_list == as_dict == as_snapshot


def test_an_unrecognised_source_yields_nothing_rather_than_raising():
    """A panel must not be able to take the room down by being pointed at the wrong thing."""
    for junk in (None, 7, "t1", object()):
        assert timeline.tasks_of(junk) == []


def test_a_row_is_a_flattened_reading_of_a_task():
    row = timeline.timeline_rows(PLAN)[0]
    assert (row.task_id, row.agent, row.domain) == ("t1", "lead", "tests")
    assert (row.status, row.verdict) == ("done", timeline.PASS)


def test_a_row_is_frozen():
    """A row is a reading of a task, not a view onto it — nothing may be edited in place."""
    row = timeline.timeline_rows(PLAN)[0]
    with pytest.raises(Exception):
        row.verdict = timeline.FAIL  # type: ignore[misc]


# ---------- counting, and the empty states ----------


def test_the_tally_always_carries_all_three_keys():
    """A caller reads `counts[FAIL]` with no `.get()` guard, even before anything has failed."""
    assert timeline.tally([]) == {timeline.PASS: 0, timeline.FAIL: 0, timeline.UNKNOWN: 0, "total": 0}
    assert timeline.tally(timeline.timeline_rows(PLAN)) == {
        timeline.PASS: 2,
        timeline.FAIL: 1,
        timeline.UNKNOWN: 1,
        "total": 4,
    }


def test_a_room_with_nothing_planned_says_so_in_its_own_words():
    assert timeline.summary_line(timeline.tally([])) == timeline.NO_TASKS


def test_a_plan_nobody_has_audited_is_not_reported_as_a_run_of_failures():
    """The branch that matters: "0 cleared, 0 disputed" would read as a run where nothing was
    judged rather than as a plan that has not started being judged."""
    rows = timeline.timeline_rows([make_task("t1"), make_task("t2")])
    line = timeline.summary_line(timeline.tally(rows))
    assert line == "2 planned · none audited yet"
    assert "cleared" not in line


def test_the_summary_counts_the_never_audited_alongside_the_rest():
    """They are in the denominator, so the line has to admit they are there."""
    line = timeline.summary_line(timeline.tally(timeline.timeline_rows(PLAN)))
    assert line == "4 planned · 2 cleared · 1 disputed · 1 never audited"


# ---------- the filter ----------


def test_the_filter_is_off_by_default():
    """A fresh room is nearly all UNKNOWN; hiding those by default would make the panel look
    broken before the audit loop has had anything to do."""
    rows = timeline.timeline_rows(PLAN)
    assert timeline.visible_rows(rows) == rows
    assert len(timeline.visible_rows(rows)) == 4


def test_audited_only_drops_the_unjudged_rows():
    rows = timeline.timeline_rows(PLAN)
    kept = timeline.visible_rows(rows, audited_only=True)
    assert [row.task_id for row in kept] == ["t1", "t3", "t4"]


# ---------- the widget ----------


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def panel(qapp):
    """Every panel built is kept referenced and closed, in the same shape as `test_qt_graph.py`."""
    from hexmind.qt.timeline import TimelinePanel

    made: list = []

    def build(**kwargs) -> TimelinePanel:
        widget = TimelinePanel(**kwargs)
        made.append(widget)
        return widget

    yield build

    for widget in made:
        widget.close()
        del widget
    made.clear()
    qapp.processEvents()


def test_the_panel_builds_one_row_per_task(panel):
    p = panel(tasks=PLAN)
    assert p.table.rowCount() == len(PLAN)
    assert [p.table.item(r, 0).text() for r in range(p.table.rowCount())] == ["t1", "t2", "t3", "t4"]


def test_the_columns_are_the_ones_the_module_documents(panel):
    p = panel(tasks=PLAN)
    labels = [p.table.horizontalHeaderItem(i).text() for i in range(p.table.columnCount())]
    assert labels == list(timeline.COLUMNS)


def test_the_verdict_cell_is_tinted_from_the_verdict_hue(panel):
    p = panel(tasks=PLAN)
    hues = [p.table.item(r, 4).foreground().color().name() for r in range(4)]
    assert hues == [theme.VERDICT_HUE[v] for v in (timeline.PASS, timeline.UNKNOWN, timeline.FAIL, timeline.PASS)]


def test_a_failed_task_draws_a_red_status_beside_an_unknown_verdict(panel):
    """The two axes are separate columns with separate hues, which is the point of the panel. A
    red status next to a grey verdict is information, not a rendering fault."""
    p = panel(tasks=PLAN)
    status_item = p.table.item(1, 3)  # t2
    verdict_item = p.table.item(1, 4)
    assert status_item.text() == "failed"
    assert status_item.foreground().color().name() == theme.RED
    assert verdict_item.text() == timeline.UNKNOWN
    assert verdict_item.foreground().color().name() == theme.VERDICT_HUE[timeline.UNKNOWN]


def test_the_detail_column_reveals_the_revision(panel):
    p = panel(tasks=PLAN)
    assert p.table.item(3, 5).text() == "passed after revision vs gpt-5"
    assert p.table.item(3, 4).text() == timeline.PASS


def test_the_status_cell_says_the_two_columns_disagree(panel):
    p = panel(tasks=PLAN)
    assert "verdict unknown" in p.table.item(1, 3).toolTip()


def test_the_panel_summarises_even_when_everything_is_filtered_out(panel):
    """The tally is over the plan, not the visible slice — the numbers must not shrink when the
    filter does, or the summary would report a different run than the one that happened."""
    p = panel(tasks=PLAN)
    before = p.summary.text()
    p.set_audited_only(True)
    assert p.table.rowCount() == 3
    assert p.summary.text() == before


def test_setting_the_filter_in_code_moves_the_checkbox(panel):
    p = panel(tasks=PLAN)
    p.set_audited_only(True)
    assert p.auditedOnly.isChecked() is True


def test_ticking_the_checkbox_filters(panel, qapp):
    p = panel(tasks=PLAN)
    p.auditedOnly.setChecked(True)
    qapp.processEvents()
    assert p.table.rowCount() == 3


def test_a_host_supplies_the_tasks(panel):
    class Host:
        def snapshot(self):
            return {"tasks": {t.id: t for t in PLAN}}

    p = panel()
    assert p.table.rowCount() == 0
    p.set_host(Host())
    assert p.table.rowCount() == len(PLAN)


def test_a_host_without_a_snapshot_clears_the_panel(panel):
    p = panel(tasks=PLAN)
    p.set_host(object())
    assert p.table.rowCount() == 0
    assert p.summary.text() == timeline.NO_TASKS


def test_the_table_cannot_be_edited(panel):
    """Verdicts are read out of the ledger, never written back into it."""
    p = panel(tasks=PLAN)
    from PySide6.QtWidgets import QAbstractItemView

    assert p.table.editTriggers() == QAbstractItemView.EditTrigger.NoEditTriggers

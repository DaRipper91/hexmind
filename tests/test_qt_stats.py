"""The audit statistics panel, offscreen.

Skipped when PySide6 is absent, like `tests/test_qt.py`. `QT_QPA_PLATFORM=offscreen`.

The panel's job is to report the ledger without lying about it, so most of these tests never build
a widget: the counting, ordering, and tinting functions are pure and are tested directly. That is
also where the claims this panel makes about *itself* get pinned down — that it never writes to the
ledger, that unrecorded is not the same as failed, and that it shows a domain `/ranks` would hide.
The widget tests at the end cover the wiring a pure test cannot reach.
"""
from __future__ import annotations

import json

import pytest

pytest.importorskip("PySide6", reason="the qt extra is not installed")

from PySide6.QtWidgets import QApplication

from hexmind import auditor
from hexmind.qt import stats, theme

# A small, deliberately uneven ledger. Three agents, three known domains, one domain the taxonomy
# has never heard of, one agent with nothing recorded, and one cell that is present but zeroed.
LEDGER = {
    "claude": {
        "tests": {"pass": 9, "fail": 1},
        "security": {"pass": 4, "fail": 4},
        "docs": {"pass": 0, "fail": 0},
    },
    "kimi": {
        "security": {"pass": 0, "fail": 6},
    },
    "gemini": {
        "tests": {"pass": 1, "fail": 0},
        "sorcery": {"pass": 1, "fail": 0},  # not in auditor.DOMAINS
    },
    "ghost": {},  # in the roster, nothing recorded
}
ROSTER = ["claude", "kimi", "gemini", "ghost"]
# What `active_domains` must produce for LEDGER: taxonomy order (`tests` precedes `security` in
# `auditor.DOMAINS`), then the one off-taxonomy domain, in first-seen order. Not named DOMAINS so it
# cannot shadow the real taxonomy by accident.
ACTIVE_DOMAINS = ["tests", "security", "sorcery"]


@pytest.fixture
def ledger(tmp_path):
    """A real stats.json on disk, so the panel exercises the same read path the CLI does."""
    path = tmp_path / "stats.json"
    path.write_text(json.dumps(LEDGER), encoding="utf-8")
    return str(path)


# ---------- reading the ledger: tolerant on purpose ----------


def test_a_cell_reports_its_two_counters():
    assert stats.cell(LEDGER, "claude", "tests") == (9, 1)


def test_a_missing_agent_or_domain_is_zero_attempts_not_an_error():
    """A hand-edited or partial file must not take the window down."""
    assert stats.cell(LEDGER, "nobody", "tests") == (0, 0)
    assert stats.cell(LEDGER, "claude", "nothing-here") == (0, 0)


def test_a_present_but_zeroed_cell_is_still_zero_attempts():
    assert stats.cell(LEDGER, "claude", "docs") == (0, 0)


def test_a_null_entry_does_not_raise():
    """`{"claude": {"tests": null}}` is a plausible hand-edit and must degrade, not explode."""
    assert stats.cell({"claude": {"tests": None}}, "claude", "tests") == (0, 0)
    assert stats.cell({"claude": None}, "claude", "tests") == (0, 0)


def test_a_missing_file_reads_as_an_empty_ledger(tmp_path):
    empty = auditor.Stats(str(tmp_path / "never-written.json")).data
    assert empty == {}


def test_the_default_path_is_the_one_the_cli_and_server_resolve():
    """Three front-ends, one ledger. If these drift, the panel reports a different history than
    `/ranks` does, and both would be right."""
    from hexmind import __main__, server

    expanded = stats.stats_path()
    assert expanded.startswith("/") or expanded[:1].isalpha()  # expanded, not literally "~"
    for module in (__main__, server):
        src = __import__("inspect").getsource(module)
        assert stats.DEFAULT_STATS_PATH.split("/")[-1] in src


# ---------- columns: taxonomy first, then whatever the data actually contains ----------


def test_active_domains_are_in_taxonomy_order():
    assert stats.active_domains(LEDGER, ROSTER) == ACTIVE_DOMAINS


def test_active_domains_keeps_an_off_taxonomy_domain_alongside_a_known_one():
    """`Stats.table` (auditor.py:120-141) lists only taxonomy domains, falling back to arbitrary
    ones only when it finds none at all — so a ledger holding both `tests` and `sorcery` loses
    `sorcery` there. The panel deliberately diverges: `core.py:334` stores plan domains verbatim,
    so an off-taxonomy name is real recorded data, and a chart that hid it would hide exactly the
    domains work keeps coming back in."""
    assert "sorcery" in stats.active_domains(LEDGER, ROSTER)
    assert "tests" in stats.active_domains(LEDGER, ROSTER)


def test_a_domain_with_nothing_recorded_anywhere_gets_no_column():
    assert "docs" not in stats.active_domains(LEDGER, ROSTER)


def test_active_domains_is_empty_for_an_empty_ledger():
    assert stats.active_domains({}, ROSTER) == []


def test_discovered_agents_is_sorted_so_the_standalone_view_is_stable():
    assert stats.discovered_agents(LEDGER) == ["claude", "gemini", "ghost", "kimi"]


# ---------- totals ----------


def test_agent_totals_sum_across_every_domain_by_default():
    """`claude` is 13 pass and 5 fail across tests + security."""
    totals = dict((a, (p, f)) for a, p, f in stats.compute_agent_totals(LEDGER, ["claude"]))
    assert totals["claude"] == (13, 5)


def test_agent_totals_narrow_to_the_columns_on_screen():
    """With a filtered ledger, the total must be the total of what is shown — otherwise the bar
    chart and the `overall` column would disagree with each other."""
    totals = stats.compute_agent_totals(LEDGER, ["claude"], ["tests"])
    assert totals == [("claude", 9, 1)]


def test_an_agent_with_nothing_recorded_totals_to_zero():
    assert stats.compute_agent_totals(LEDGER, ["ghost"]) == [("ghost", 0, 0)]


def test_compute_cells_keeps_the_callers_order():
    """Roster order is the room's decision to make; re-sorting here would fight it."""
    cells = stats.compute_cells(LEDGER, ["kimi", "claude"], ["security"])
    assert [name for name, _ in cells] == ["kimi", "claude"]


# ---------- where the team hurts ----------


def test_trouble_is_ordered_by_failures_descending():
    """The question this chart answers is where work keeps coming back, so worst first."""
    rows = stats.compute_trouble(LEDGER, ROSTER, ACTIVE_DOMAINS)
    # security 10 fails, tests 1, sorcery 0.
    assert [name for name, _, _ in rows] == ["security", "tests", "sorcery"]


def test_a_never_failing_domain_still_appears_in_the_trouble_chart():
    """Zero failures is not zero information — sorcery is the domain nothing comes back on, which
    is worth seeing, and dropping it would make the chart answer a narrower question than asked."""
    assert "sorcery" in [d for d, _, _ in stats.compute_trouble(LEDGER, ROSTER, ACTIVE_DOMAINS)]


def test_trouble_sums_across_agents():
    rows = dict((d, (p, f)) for d, p, f in stats.compute_trouble(LEDGER, ROSTER, ACTIVE_DOMAINS))
    assert rows["security"] == (4, 10)  # claude 4/4 plus kimi 0/6


def test_a_domain_with_no_attempts_is_dropped_not_drawn_as_a_zero_bar():
    """A bar of zeroes is noise. The panel would be answering a question nobody asked."""
    assert "docs" not in [d for d, _, _ in stats.compute_trouble(LEDGER, ROSTER, ACTIVE_DOMAINS)]


def test_trouble_is_deterministic_across_identical_refreshes():
    """Two identical reads must not reshuffle the chart under the user's eyes."""
    first = stats.compute_trouble(LEDGER, ROSTER, ACTIVE_DOMAINS)
    second = stats.compute_trouble(LEDGER, ROSTER, ACTIVE_DOMAINS)
    assert first == second


# ---------- tinting: the reading instruction, enforced ----------


def test_a_clean_cell_reads_as_neutral_ink():
    assert stats.cell_tone(9, 1) == theme.INK


def test_a_cell_below_half_reads_as_red():
    assert stats.cell_tone(1, 3) == theme.RED


def test_a_cell_between_half_and_eighty_reads_as_amber():
    assert stats.cell_tone(5, 3) == theme.AMBER


def test_an_unrecorded_cell_reads_as_dim_not_red():
    """The one that matters. Absence of evidence is not evidence of failure, and a red empty cell
    would report a failure the ledger does not contain."""
    assert stats.cell_tone(0, 0) == theme.INK_DIM
    assert stats.cell_tone(0, 0) != theme.RED


def test_tone_thresholds_agree_with_the_documented_cuts():
    assert stats.cell_tone(4, 5) == theme.RED    # 0.44
    assert stats.cell_tone(5, 5) == theme.AMBER  # exactly 0.5 is not "below half"
    assert stats.cell_tone(79, 21) == theme.AMBER
    assert stats.cell_tone(4, 1) == theme.INK    # exactly 0.8


def test_every_tone_is_a_theme_constant():
    """No colour literal is allowed in the Qt layer; this fails loudly if one creeps in."""
    allowed = {theme.RED, theme.AMBER, theme.INK, theme.INK_DIM, theme.INK_FAINT}
    for p, f in [(0, 0), (0, 5), (5, 5), (9, 1), (5, 0)]:
        assert stats.cell_tone(p, f) in allowed


# ---------- the summary line ----------


def test_an_empty_ledger_says_the_same_words_as_ranks():
    from hexmind.qt import stats as s

    assert s.summary_line([]) == s.NO_STATS
    assert s.summary_line([("claude", 0, 0)]) == s.NO_STATS


def test_the_summary_reports_first_attempt_counts_and_a_percentage():
    line = stats.summary_line([("claude", 9, 1)])
    assert "10" in line and "9 passed" in line and "1 failed" in line and "90% clean" in line


def test_the_summary_says_first_attempt_so_the_number_is_not_overread():
    """`audited_run` records only round 0 (auditor.py:244-246), so this is reliability-before-any-
    revision, not eventual pass rate. The panel has to say so where the number is read."""
    assert "first-attempt" in stats.summary_line([("claude", 1, 0)])


# ---------- the widget ----------


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def panel(qapp, monkeypatch):
    """Every panel built is kept referenced and closed, in the same shape as `test_qt_graph.py` —
    a live pyqtgraph scene whose items outlive the widget is a segfault, not an exception."""
    from hexmind.qt.stats import StatsPanel

    made: list = []

    def build(path=None, **kwargs) -> StatsPanel:
        widget = StatsPanel(path=path, **kwargs)
        made.append(widget)
        return widget

    yield build

    for widget in made:
        widget.close()
        del widget
    made.clear()
    qapp.processEvents()


def test_the_panel_builds_a_row_per_agent_and_a_column_per_active_domain(panel, ledger):
    p = panel(ledger, agents=ROSTER)
    assert p.table.rowCount() == len(ROSTER)
    assert p.table.columnCount() == len(ACTIVE_DOMAINS) + 2  # + Agent + overall
    labels = [p.table.horizontalHeaderItem(i).text() for i in range(p.table.columnCount())]
    assert labels == ["Agent", *ACTIVE_DOMAINS, "overall"]


def test_the_zeroed_docs_domain_gets_no_column(panel, ledger):
    """`docs` is present in the ledger as `{"pass": 0, "fail": 0}`. A column of zeroes would claim
    something is known about that domain, and nothing is."""
    p = panel(ledger, agents=ROSTER)
    labels = [p.table.horizontalHeaderItem(i).text() for i in range(p.table.columnCount())]
    assert "docs" not in labels


def test_an_agent_with_no_recordings_gets_a_row_of_dashes_not_a_blank(panel, ledger):
    p = panel(ledger, agents=ROSTER)
    row = [r for r in range(p.table.rowCount())
           if p.table.item(r, 0).text() == "ghost"][0]
    for col in range(1, p.table.columnCount()):
        assert p.table.item(row, col).text() == "—"


def test_the_roster_is_shown_in_the_order_the_room_gave_it(panel, ledger):
    p = panel(ledger, agents=["kimi", "claude"])
    assert [p.table.item(r, 0).text() for r in range(p.table.rowCount())] == ["kimi", "claude"]


def test_set_agents_reorders_without_touching_the_file(panel, ledger):
    p = panel(ledger, agents=["kimi", "claude"])
    p.set_agents(["claude", "kimi"])
    assert [p.table.item(r, 0).text() for r in range(p.table.rowCount())] == ["claude", "kimi"]


def test_without_a_roster_the_panel_reads_one_out_of_the_ledger(panel, ledger):
    """The standalone app has no room behind it, so the ledger has to describe itself."""
    p = panel(ledger)
    assert p._agents == ["claude", "gemini", "ghost", "kimi"]


def test_a_missing_ledger_shows_the_empty_message_and_no_rows(panel, tmp_path):
    p = panel(str(tmp_path / "never-written.json"), agents=ROSTER)
    assert p.table.rowCount() == 0
    assert p.summary.text() == stats.NO_STATS


def test_a_corrupt_ledger_is_survivable(panel, tmp_path):
    """`Stats` already backs a corrupt file up and starts empty; the panel must simply show that
    rather than raise on top of it."""
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    p = panel(str(bad), agents=ROSTER)
    assert p.summary.text() == stats.NO_STATS
    assert p.table.rowCount() == 0


def test_reloading_the_same_file_is_idempotent(panel, ledger):
    p = panel(ledger, agents=ROSTER)
    before = [p.table.item(r, c).text()
              for r in range(p.table.rowCount()) for c in range(p.table.columnCount())]
    p.reload()
    after = [p.table.item(r, c).text()
             for r in range(p.table.rowCount()) for c in range(p.table.columnCount())]
    assert before == after


def test_set_path_redraws_from_the_new_ledger(panel, ledger, tmp_path):
    other = tmp_path / "other.json"
    other.write_text(json.dumps({"only": {"tests": {"pass": 2, "fail": 0}}}), encoding="utf-8")
    p = panel(ledger, agents=ROSTER)
    p.set_path(str(other))
    p.set_agents(["only"])
    assert p.table.item(0, 0).text() == "only"
    assert "2 first-attempt" in p.summary.text()
    assert "2 passed" in p.summary.text()
    assert "0 failed" in p.summary.text()


def test_reloading_never_writes_to_the_ledger(panel, ledger, tmp_path):
    """The panel is a reader. If it called `record`, refreshing a window would change the very
    numbers it displays — and would poison `pick_auditor` for the next real audit."""
    before = (tmp_path / "stats.json").read_text(encoding="utf-8")
    p = panel(ledger, agents=ROSTER)
    p.reload()
    p.set_agents(["kimi"])
    p.reload()
    assert (tmp_path / "stats.json").read_text(encoding="utf-8") == before
    assert sorted(p.name for p in tmp_path.iterdir()) == ["stats.json"]


def test_the_panel_paints(panel, ledger):
    """A panel that raises on paint is a window that shows nothing and explains nothing."""
    p = panel(ledger, agents=ROSTER)
    p.resize(1000, 700)
    p.grab()


@pytest.mark.skipif(not stats.HAVE_PG, reason="pyqtgraph is not installed")
def test_both_charts_draw_one_stacked_bar_per_row(panel, ledger):
    p = panel(ledger, agents=ROSTER)
    p.resize(1000, 700)
    p.grab()
    # two BarGraphItems per chart (passes then failures) plus the grid/axis furniture
    assert len(p.agent_plot.items()) >= 2
    assert len(p.trouble_plot.items()) >= 2


@pytest.mark.skipif(not stats.HAVE_PG, reason="pyqtgraph is not installed")
def test_the_first_row_sits_at_the_top_of_the_axis(panel, ledger):
    """Rows are indexed from 0 and the y axis is inverted, so a positive y range means the first
    agent is at the top. Without the inversion the chart would read bottom-up like a histogram."""
    p = panel(ledger, agents=ROSTER)
    lo, hi = p.agent_plot.getViewBox().viewRange()[1]
    assert lo < hi, "inverted y should give an ascending range; a descending one reads backwards"


@pytest.mark.skipif(not stats.HAVE_PG, reason="pyqtgraph is not installed")
def test_the_charts_are_told_to_render(panel, ledger):
    """A chart that is still autoscale-on is a chart that keeps moving under the cursor."""
    p = panel(ledger, agents=ROSTER)
    assert p.agent_plot.getViewBox().state["autoRange"][1] is False


def test_a_missing_pyqtgraph_degrades_to_the_ledger(panel, ledger, monkeypatch):
    """The `qt` extra is opt-in, so a user who installed only PySide6 must still get the numbers —
    the charts are the garnish, the ledger is the meal."""
    monkeypatch.setattr(stats, "HAVE_PG", False)
    monkeypatch.setattr(stats, "pg", None)
    p = panel(ledger, agents=ROSTER)
    p.resize(1000, 700)
    p.grab()
    assert p.agent_plot is None and p.trouble_plot is None
    assert p.table.rowCount() == len(ROSTER)
    assert stats.NO_STATS not in p.summary.text()


def test_bar_height_leaves_a_gap_between_rows(ledger):
    """Rows are one unit apart, so a bar thicker than 1.0 would make adjacent rows touch and the
    stack would read as a single block."""
    assert 0 < stats.BAR_HEIGHT < 1

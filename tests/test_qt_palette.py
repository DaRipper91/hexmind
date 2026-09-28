"""The command palette, offscreen.

Skipped when PySide6 is absent, like `tests/test_qt.py`. `QT_QPA_PLATFORM=offscreen`.

The palette's search is a pure function, and the tests are shaped around that: the ranking rules
and the `MIN_QUERY` cut are asserted directly with no widget at all, because a relevance order you
can only judge by eye in a window is a relevance order nobody will notice when it regresses. The
widget tests then cover only the wiring a pure test cannot reach — that typing filters the list,
that `Enter` emits the *action key* rather than the display name, and that `Esc` closes.
"""
from __future__ import annotations

import pytest

pytest.importorskip("PySide6", reason="the qt extra is not installed")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from hexmind.qt.palette import (
    MIN_QUERY,
    PALETTE_LIMIT,
    Command,
    CommandPalette,
    as_commands,
    filter_commands,
    palette_commands,
)


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _click_row(palette: CommandPalette, row: int) -> None:
    """Click a row the way a user does: a real mouse event at the row's position in the viewport.

    `itemClicked` is a view signal, so it only fires for a real click on the view — poking the
    signal directly would test the connection but not the hit-testing that a user depends on.
    """
    from PySide6.QtCore import QPoint
    from PySide6.QtTest import QTest

    rect = palette.list.visualItemRect(palette.list.item(row))
    QTest.mouseClick(palette.list.viewport(), Qt.MouseButton.LeftButton, pos=QPoint(0, 0) + rect.center())


@pytest.fixture
def palette(qapp):
    """A palette that is closed on teardown — a live frameless dialog outlives the test and
    segfaults at interpreter shutdown if it is not explicitly closed."""
    p = CommandPalette(
        [
            Command("clear transcript", "Wipe the conversation view", "clear"),
            Command("toggle peer audit", "Turn the audit loop on or off", "audit"),
            Command("refresh team", "Re-read the roster", "refresh"),
            Command("lead: claude", "Make claude the lead", "lead:claude", keywords="claude"),
        ]
    )
    yield p
    p.close()
    p.deleteLater()


# ---------- ranking: the pure logic ----------

def test_an_empty_query_offers_the_commands_in_their_natural_order():
    """The palette is useful the instant it opens; a relevance order on an empty query is
    just a shuffle the user has to re-learn every time."""
    commands = as_commands([("beta", "", "b"), ("alpha", "", "a"), ("gamma", "", "g")])
    assert [c.name for c in filter_commands(commands, "")] == ["beta", "alpha", "gamma"]


def test_a_one_character_query_is_still_too_short_to_rank():
    """Ranking `"a"` against a dozen commands is noise, and a user typing `a` is usually typing
    the start of `audit` or `ask`. Showing natural order is the calmer answer."""
    commands = as_commands([("apply patch", "", "x"), ("archive room", "", "y"), ("ask", "", "z")])
    assert [c.name for c in filter_commands(commands, "a")] == ["apply patch", "archive room", "ask"]


def test_two_characters_is_enough_to_start_ranking():
    commands = as_commands([("apply patch", "", "x"), ("plumb the line", "", "y")])
    assert [c.name for c in filter_commands(commands, "pl")] == ["plumb the line", "apply patch"]


def test_an_exact_name_beats_a_name_that_merely_starts_with_the_query():
    commands = as_commands([("run", "do the thing", "run"), ("rerun the room", "do the other", "rerun")])
    assert [c.name for c in filter_commands(commands, "run")] == ["run", "rerun the room"]


def test_a_prefix_beats_a_substring():
    commands = as_commands([("plan mode", "", "a"), ("explain the plan", "", "b")])
    assert [c.name for c in filter_commands(commands, "plan")] == ["plan mode", "explain the plan"]


def test_a_hint_match_ranks_below_any_name_match():
    commands = [
        Command("reset room", "", "reset"),
        Command("wipe", "Reset the room and its transcript", "wipe"),
    ]
    assert [c.name for c in filter_commands(commands, "reset")] == ["reset room", "wipe"]


def test_a_keyword_match_ranks_last_because_it_is_the_weakest_promise():
    commands = [
        Command("wipe", "", "wipe", keywords="reset"),
        Command("reset room", "Wipe everything", "reset"),
    ]
    assert [c.name for c in filter_commands(commands, "reset")] == ["reset room", "wipe"]


def test_ties_break_on_the_shorter_name_then_alphabetically():
    """Two commands that both merely contain the query are equally relevant, so the tie is
    broken on something stable. Without this, ordering would depend on dict/list order and the
    palette would reshuffle between runs."""
    # All three merely *contain* `ab`; none starts with it, so the tie-break is what orders them.
    # The two four-character names tie on length and so fall back to alphabetical order.
    commands = as_commands([("x ab", "", "1"), ("a a ab", "", "2"), ("a ab", "", "3")])
    assert [c.name for c in filter_commands(commands, "ab")] == ["a ab", "x ab", "a a ab"]


def test_non_matching_commands_are_dropped_not_merely_ranked_last():
    commands = as_commands([("clear transcript", "", "clear"), ("refresh team", "", "refresh")])
    assert [c.name for c in filter_commands(commands, "zzz")] == []


def test_matching_is_case_and_whitespace_insensitive():
    commands = as_commands([("Clear Transcript", "", "clear")])
    assert [c.name for c in filter_commands(commands, "  CLEAR  ")] == ["Clear Transcript"]


def test_a_name_matching_case_insensitively_still_ranks_as_a_prefix():
    commands = as_commands([("Clear Transcript", "", "clear"), ("clear the cache", "", "c2")])
    assert [c.name for c in filter_commands(commands, "clear")][0] == "clear the cache"


def test_the_list_is_capped_so_it_stays_scannable():
    many = as_commands([(f"command {i:02d}", "", str(i)) for i in range(50)])
    assert len(filter_commands(many, "command")) == PALETTE_LIMIT


def test_as_commands_carries_the_action_key_through():
    [command] = as_commands([("name", "hint", "act:1")])
    assert (command.name, command.hint, command.action) == ("name", "hint", "act:1")


def test_keywords_do_not_affect_command_equality():
    """Two commands that differ only in search terms are the same command; otherwise a
    keyword-added command would read as a distinct entry to anything comparing palettes."""
    assert Command("a", "h", "act", keywords="x") == Command("a", "h", "act")


def test_min_query_is_the_documented_threshold():
    assert MIN_QUERY == 2


# ---------- the overlay: wiring a pure test cannot reach ----------

def test_opening_lists_every_command_below_the_limit(palette):
    palette.open_palette()
    assert palette.list.count() == 4
    assert palette.isVisible()


def test_typing_filters_the_list(palette):
    palette.open_palette()
    palette.input.setText("refresh")
    assert palette.list.count() == 1
    assert palette.list.item(0).text() == "refresh team"


def test_a_query_with_no_match_leaves_an_empty_list(palette):
    palette.open_palette()
    palette.input.setText("qqqq")
    assert palette.list.count() == 0


def test_the_first_row_is_selected_so_enter_always_has_a_target(palette):
    palette.open_palette()
    palette.input.setText("lead")
    assert palette.list.currentRow() == 0


def test_the_selected_row_expands_into_its_description(palette):
    """A palette is scanned, not read, so the highlighted row has to say what it does —
    otherwise the user has to hover and wait to find out what `/go` actually did."""
    palette.open_palette()
    palette.input.setText("refresh")
    assert palette.hint.text() == "Re-read the roster"


def test_enter_on_a_filtered_row_emits_that_rows_action_key(palette):
    """The action key, not the label: the host dispatches on the key, so a display rename
    must not silently break a dispatched action."""
    seen: list[str] = []
    palette.chosen.connect(seen.append)
    palette.open_palette()
    palette.input.setText("peer")
    palette.input.returnPressed.emit()
    assert seen == ["audit"]


def test_clicking_a_row_emits_the_same_key_as_enter(palette):
    seen: list[str] = []
    palette.chosen.connect(seen.append)
    palette.open_palette()
    palette.input.setText("lead")
    _click_row(palette, 0)
    assert seen == ["lead:claude"]


def test_choosing_closes_the_palette(palette):
    palette.open_palette()
    palette.input.setText("refresh")
    palette.input.returnPressed.emit()
    assert not palette.isVisible()


def test_escape_closes_without_choosing_anything(palette):
    seen: list[str] = []
    palette.chosen.connect(seen.append)
    palette.open_palette()
    from PySide6.QtGui import QKeyEvent
    from PySide6.QtCore import QEvent

    palette.eventFilter(palette, QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier))
    assert seen == []
    assert not palette.isVisible()


def test_reopening_starts_from_a_clean_slate(palette):
    palette.open_palette()
    palette.input.setText("refresh")
    palette.close()
    palette.open_palette()
    assert palette.input.text() == ""
    assert palette.list.count() == 4


def test_toggle_opens_then_closes(palette):
    palette.toggle()
    assert palette.isVisible()
    palette.toggle()
    assert not palette.isVisible()


def test_set_commands_swaps_the_vocabulary(palette):
    """The roster changes, so the per-agent commands change with it."""
    palette.open_palette()
    palette.set_commands(as_commands([("only this", "", "only")]))
    assert palette.list.count() == 1
    assert palette.list.item(0).text() == "only this"


def test_the_palette_width_is_capped_so_a_long_hint_cannot_span_the_screen(palette):
    palette.open_palette()
    assert 420 <= palette.width() <= 720


def test_the_palette_stays_on_screen(qapp):
    """A palette that opens past the bottom edge is a palette the user cannot see."""
    from hexmind.qt.palette import _clamp_origin

    area = qapp.primaryScreen().availableGeometry()
    p = CommandPalette(as_commands([("a command", "", "a")]))
    try:
        p.resize(500, 300)
        x, y = _clamp_origin(p, area.right() + 5000, area.bottom() + 5000)
        assert area.contains(p.rect().translated(x, y).center())
    finally:
        p.close()
        p.deleteLater()


# ---------- the host's vocabulary ----------

class _Room:
    def __init__(self, members):
        self.members = members


def test_the_vocabulary_carries_the_room_actions():
    names = [c.name for c in palette_commands(_Room([]))]
    assert names == ["clear transcript", "toggle peer audit", "refresh team"]


def test_each_teammate_gets_a_lead_command():
    names = [c.name for c in palette_commands(_Room(["claude", "codex"]))]
    assert "lead: claude" in names and "lead: codex" in names


def test_a_teammate_is_findable_by_their_own_name():
    """Otherwise you have to remember to type the `lead: ` prefix to switch to a person."""
    [match] = filter_commands(palette_commands(_Room(["claude"])), "claude")
    assert match.action == "lead:claude"


def test_a_room_with_no_members_still_has_its_actions():
    """`getattr(..., None) or []` — a room mid-startup has no roster yet and must not raise."""
    assert len(palette_commands(_Room(None))) == 3

import asyncio
import json

from textual.widgets import Button, Static

from hexmind import tui
from hexmind.core import REGISTRY, Task
from hexmind.tui import HELP, HexmindApp
from tests.test_core import FakeBackend


def test_room_runs_a_plan_and_fills_task_board():
    plan = json.dumps({"reply": "on it", "tasks": [
        {"id": "a", "agent": "claude", "title": "a"},
        {"id": "b", "agent": "agy", "title": "b", "depends_on": ["a"]}]})

    async def go():
        app = HexmindApp(FakeBackend(plan), ["claude", "agy"], "claude", "test")
        async with app.run_test() as pilot:
            await pilot.click("#input")
            await pilot.press(*"build it", "enter")
            await app.workers.wait_for_complete()
            await pilot.pause()
            assert [t.status for t in app.tasks.values()] == ["done", "done"]
            table = app.query_one("#tasks")
            assert table.row_count == 2
            assert str(table.get_cell("1.a", "audit")) == ""  # not audited
            t = app.tasks["1.a"]
            t.status, t.audit, t.auditor = "done", "fixed", "agy"
            app.on_team_event("task", {"task": t})
            assert str(table.get_cell("1.a", "audit")) == "fixed·agy"

    asyncio.run(go())


def _app():
    return HexmindApp(FakeBackend(json.dumps({"reply": "hi", "tasks": []})), ["claude", "agy"], "claude", "test")


def test_wide_layout_is_side_by_side():
    async def go():
        app = _app()
        async with app.run_test(size=(120, 40)) as pilot:
            assert not app.has_class("narrow")
            assert app.query_one("#left").display and app.query_one("#right").display
            assert not app.query_one("#tabs").display

    asyncio.run(go())


def test_narrow_layout_tabs_between_chat_and_tasks():
    async def go():
        app = _app()
        async with app.run_test(size=(40, 20)) as pilot:
            left, right = app.query_one("#left"), app.query_one("#right")
            assert app.has_class("narrow") and app.query_one("#tabs").display
            assert left.display and not right.display
            await pilot.click("#tab-tasks")
            assert not left.display and right.display
            await pilot.click("#tab-chat")
            assert left.display and not right.display
            await pilot.resize_terminal(120, 40)
            await pilot.pause()
            assert left.display and right.display and not app.has_class("narrow")

    asyncio.run(go())


def test_single_keys_only_fire_when_input_blurred():
    async def go():
        app = _app()
        async with app.run_test(size=(40, 20)) as pilot:
            await pilot.press("q", "v", "c")  # typed into the input, not shortcuts
            assert app.is_running and app.query_one("#input").value == "qvc" and app.view == "chat"
            await pilot.press("escape", "v")
            assert app.view == "tasks" and app.focused is app.query_one("#tasks")
            await pilot.press("i")
            assert app.view == "chat" and app.focused is app.query_one("#input")
            await pilot.press("escape", "question_mark")
            assert app.screen.__class__.__name__ == "HelpScreen"
            await pilot.press("escape", "q")
        assert not app.is_running

    asyncio.run(go())


def test_short_terminal_collapses_team_to_one_line():
    async def go():
        app = _app()
        async with app.run_test(size=(40, 15)) as pilot:
            assert app.has_class("short")
            assert "busy" in str(app.query_one("#team").render()) and "\n" not in str(app.query_one("#team").render())
            await pilot.resize_terminal(90, 7)
            await pilot.pause()
            assert app.has_class("tiny") and not app.query_one("Header").display

    asyncio.run(go())


def test_narrow_table_is_compact_and_rebuilds_on_resize():
    plan = json.dumps({"reply": "on it", "tasks": [{"id": "a", "agent": "claude", "title": "alpha"}]})

    async def go():
        app = HexmindApp(FakeBackend(plan), ["claude", "agy"], "claude", "test")
        async with app.run_test(size=(50, 20)) as pilot:
            await pilot.press(*"go", "enter")
            await app.workers.wait_for_complete()
            await pilot.pause()
            table = app.query_one("#tasks")
            assert [c.value for c in table.columns] == ["task", "status", "title"]
            assert str(table.get_cell("1.a", "title")) == "claude alpha"
            assert app.sub_title == "claude · audit:off"
            t = app.tasks["1.a"]
            t.audit, t.auditor = "pass", "agy"
            app.on_team_event("task", {"task": t})
            assert str(table.get_cell("1.a", "status")) == "done pass·agy"
            await pilot.press("escape", "v", "enter")  # open the task sheet
            assert app.screen.__class__.__name__ == "TaskScreen"
            await pilot.press("escape")
            await pilot.resize_terminal(120, 40)
            await pilot.pause()
            assert [c.value for c in table.columns] == ["task", "agent", "status", "audit", "title"]
            assert str(table.get_cell("1.a", "audit")) == "pass·agy" and table.row_count == 1
            assert app.sub_title == "test backend · lead: claude · audit: off"

    asyncio.run(go())


def test_task_sheet_copies_output(monkeypatch):
    import hexmind.tui as tui
    monkeypatch.setattr(tui.shutil, "which", lambda _: None)
    plan = json.dumps({"reply": "on it", "tasks": [{"id": "a", "agent": "claude", "title": "alpha"}]})

    async def go():
        app = HexmindApp(FakeBackend(plan), ["claude"], "claude", "test")
        copied = []
        app.copy_to_clipboard = copied.append
        async with app.run_test(size=(50, 20)) as pilot:
            await pilot.press(*"go", "enter")
            await app.workers.wait_for_complete()
            await pilot.pause()
            await pilot.press("escape", "v", "enter")
            await pilot.click("#copy")
            assert copied == [app.tasks["1.a"].output]

    asyncio.run(go())


# ---------- /team roster (WS-10) ----------
# One control surface for sleep / wake / lead, over the same state the /sleep, /wake and /lead
# commands change. INVARIANT S-1: a model holding a live task cannot be slept, so the control is
# disabled and names the task that blocks it, rather than offering a button guaranteed to fail.

ROSTER = ("claude", "agy", "opencode-pickle", "opencode-ling")


def _team_app(known=ROSTER, members=("claude", "agy"), lead="claude", plan=None):
    """A room whose roster is a known, fixed handful of models, so a row is addressable by id."""
    app = HexmindApp(FakeBackend(plan or json.dumps({"reply": "hi", "tasks": []})),
                     list(members), lead, "test")
    app.orch.known = list(known)
    return app


def _hold(app, agent, tid="t1", title="do the thing", status="running"):
    """Put a live task on a model, the way the orchestrator does, so can_sleep has a reason to give."""
    app.orch.all_tasks.append(Task(id=tid, title=title, agent=agent, instructions="x", status=status))
    app.orch.busy = {t.agent for t in app.orch.all_tasks if t.status in ("running", "auditing", "revising")}


def _order(screen) -> list[str]:
    return [w.id[len("row-"):] for w in screen.query("#roster > Vertical") if w.id]


def _state(screen, model) -> str:
    return str(screen.query_one(f"#row-{model} .state").render())


def test_roster_lists_every_known_model_with_its_state():
    async def go():
        app = _team_app()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.press("escape", "t")
            roster = app.screen
            assert type(roster).__name__ == "TeamScreen"
            # preferred-first, so the models the plan favours are the ones you reach first
            assert _order(roster) == ["opencode-pickle", "opencode-ling", "agy", "claude"]
            assert _state(roster, "claude") == "lead"
            assert _state(roster, "agy") == "awake"
            assert _state(roster, "opencode-pickle") == "asleep"
            assert roster.query_one("#sleep-agy", Button) and not roster.query("#wake-agy")

    asyncio.run(go())


def test_a_busy_model_is_listed_with_the_task_that_holds_it():
    async def go():
        app = _team_app()
        _hold(app, "agy")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.press("escape", "t")
            assert _state(app.screen, "agy") == "busy · t1"

    asyncio.run(go())


def test_roster_with_no_models_is_an_empty_state_not_a_crash():
    async def go():
        app = _team_app(known=())
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.press("escape", "t")
            assert _order(app.screen) == []
            assert "no models" in str(app.screen.query_one("#roster Static").render()).lower()
            await pilot.press("escape")
            assert type(app.screen).__name__ == "Screen"

    asyncio.run(go())


def test_roster_is_keyboard_navigable_and_closes_on_escape():
    async def go():
        app = _team_app()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.press("escape", "t")
            roster = app.screen
            rows = list(roster.query("#roster > Vertical"))
            assert roster.focused is rows[0].query_one("#wake-opencode-pickle"), \
                "focus must land on the first row's control"
            await pilot.press("j")
            assert roster.focused is rows[1].query_one("#wake-opencode-ling")
            await pilot.press("down")
            assert roster.focused is rows[2].query_one("#sleep-agy")
            rows[2].query_one("#lead-agy").focus()
            await pilot.press("k")
            assert roster.focused is rows[1].query_one("#lead-opencode-ling"), "j/k keep the same control"
            await pilot.press("k", "k")  # the cursor stops at the ends rather than wrapping
            assert roster.focused is rows[0].query_one("#lead-opencode-pickle")
            await pilot.press("escape")
            assert type(app.screen).__name__ == "Screen"
            await pilot.press("escape", "t")
            await pilot.press("q")
            assert type(app.screen).__name__ == "Screen"

    asyncio.run(go())


def test_a_model_holding_a_live_task_cannot_be_slept_from_the_roster():
    async def go():
        app = _team_app()
        _hold(app, "agy")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.press("escape", "t")
            sleep = app.screen.query_one("#sleep-agy", Button)
            assert sleep.disabled, "INVARIANT S-1: a busy model's Sleep control must be disabled"
            assert "t1" in str(sleep.tooltip) and "do the thing" in str(sleep.tooltip)
            await pilot.click("#sleep-agy")
            assert "agy" in app.orch.members, "a disabled control must not sleep a busy model"
            lead_sleep = app.screen.query_one("#sleep-claude", Button)
            assert lead_sleep.disabled and "is the lead" in str(lead_sleep.tooltip)
            assert app.orch.lead == "claude"

    asyncio.run(go())


def test_sleeping_from_the_roster_takes_the_model_out_of_the_room():
    async def go():
        app = _team_app()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.press("escape", "t")
            await pilot.click("#sleep-agy")
            await pilot.pause()
            assert "agy" not in app.orch.members and "agy" in app.orch.known
            assert _state(app.screen, "agy") == "asleep"
            assert not app.screen.query("#sleep-agy"), "an asleep row offers Wake, not Sleep"
            assert not app.screen.query_one("#wake-agy", Button).disabled
            # the room's own panes keep tracking the room while the roster is open
            assert "agy" not in str(app.room.query_one("#team", Static).render())

    asyncio.run(go())


def test_waking_from_the_roster_puts_the_model_back():
    async def go():
        app = _team_app()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.press("escape", "t")
            await pilot.click("#wake-opencode-pickle")
            await pilot.pause()
            assert "opencode-pickle" in app.orch.members
            assert _state(app.screen, "opencode-pickle") == "awake"
            assert not app.screen.query("#wake-opencode-pickle")

    asyncio.run(go())


def test_promoting_a_model_to_lead_from_the_roster():
    async def go():
        app = _team_app()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.press("escape", "t")
            await pilot.click("#lead-agy")
            await pilot.pause()
            assert app.orch.lead == "agy"
            assert _state(app.screen, "agy") == "lead" and _state(app.screen, "claude") == "awake"
            # the new lead can no longer sleep, and the old one now can
            assert app.screen.query_one("#sleep-agy", Button).disabled
            assert not app.screen.query_one("#sleep-claude", Button).disabled
            assert app.screen.query_one("#lead-agy", Button).disabled

    asyncio.run(go())


def test_a_text_only_model_cannot_be_promoted_from_the_roster():
    async def go():
        app = _team_app(known=("claude", "qwen"), members=("claude",))
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.press("escape", "t", "j")  # onto the qwen row
            lead = app.screen.query_one("#lead-qwen", Button)
            assert lead.disabled and "text-only" in str(lead.tooltip)
            assert app.orch.lead == "claude"

    asyncio.run(go())


def test_the_model_card_opens_from_the_roster_and_returns_to_it():
    async def go():
        app = _team_app()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.press("escape", "t")
            await pilot.press("question_mark")  # the card for the row under the cursor
            card = app.screen
            assert type(card).__name__ == "ModelCardScreen"
            assert "opencode-pickle" in str(card.query_one(Static).render())
            assert "Best at:" in str(card.query_one(Static).render())
            await pilot.press("escape")
            assert type(app.screen).__name__ == "TeamScreen"
            await pilot.press("j", "j")  # onto the agy row
            await pilot.click("#card-agy")
            assert type(app.screen).__name__ == "ModelCardScreen"
            assert "Gemini" in str(app.screen.query_one(Static).render())
            await pilot.press("escape", "escape")
            assert type(app.screen).__name__ == "Screen"

    asyncio.run(go())


def test_the_roster_live_refreshes_when_a_task_starts_and_finishes():
    async def go():
        plan = json.dumps({"reply": "on it", "tasks": [{"id": "t1", "agent": "agy", "title": "alpha"}]})
        app = _team_app(plan=plan)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.click("#input")
            await pilot.press(*"go", "enter")
            await app.workers.wait_for_complete()
            await pilot.press("escape", "t")
            assert not app.screen.query_one("#sleep-agy", Button).disabled
            t = app.orch.all_tasks[0]
            t.status = "running"
            app.orch.busy = {"agy"}
            app.on_team_event("task", {"task": t})  # the same channel the runner uses
            await pilot.pause()
            assert _state(app.screen, "agy") == "busy · t1"
            assert app.screen.query_one("#sleep-agy", Button).disabled
            t.status = "done"
            app.orch.busy = set()
            app.on_team_event("task", {"task": t})
            await pilot.pause()
            assert not app.screen.query_one("#sleep-agy", Button).disabled

    asyncio.run(go())


def test_every_roster_control_carries_an_accessible_label():
    async def go():
        app = _team_app()
        _hold(app, "agy")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.press("escape", "t")
            buttons = app.screen.query(Button)
            assert len(buttons) == 3 * len(ROSTER) + 1  # three row controls a row, plus Close
            for button in buttons:
                assert str(button.label).strip() and str(button.tooltip).strip(), \
                    f"{button.id} needs a label and a tooltip"
            assert "working on t1" in str(app.screen.query_one("#sleep-agy", Button).tooltip)
            assert "wake" in str(app.screen.query_one("#wake-opencode-pickle", Button).tooltip).lower()

    asyncio.run(go())


def test_only_one_roster_is_open_at_a_time():
    async def go():
        app = _team_app()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.press("escape", "t", "t")
            assert len([s for s in app.screen_stack if type(s).__name__ == "TeamScreen"]) == 1
            assert app.is_running

    asyncio.run(go())


def test_the_roster_fits_a_tiny_terminal_by_scrolling():
    async def go():
        app = _team_app(known=REGISTRY.names())  # every model hexmind knows: the longest roster there is
        async with app.run_test(size=(40, 9)) as pilot:
            await pilot.press("escape", "t")
            roster = app.screen.query_one("#roster")
            assert roster.region.height <= 9 and roster.region.width <= 40
            rows = roster.query("#roster > Vertical")
            assert len(rows) == len(REGISTRY.names())  # then the S-1 note and Close
            assert all(r.region.right <= 40 for r in rows)
            assert roster.max_scroll_y > 0, "a roster taller than the screen must scroll, not clip"
            for widget in app.screen.query("*"):
                if widget.display and widget.region.width:
                    assert widget.region.right <= 40, f"{widget} sticks out past the screen"
            await pilot.press("escape")
            assert type(app.screen).__name__ == "Screen"

    asyncio.run(go())


def test_the_team_key_is_reachable_and_listed():
    assert any(getattr(b, "key", "") == "t" and b.action == "team" for b in HexmindApp.BINDINGS)
    assert "team" in HELP and "[b]t[/b]" in HELP


def test_changing_the_lead_updates_everything_that_names_the_leader():
    """app.lead used to be a separate copy of orch.lead and went stale on the first /lead, so the
    subtitle, the (lead) marker and the busy line kept showing the old leader while the room
    obeyed the new one."""
    async def go():
        app = HexmindApp(FakeBackend(json.dumps({"reply": "ok", "tasks": []})),
                         ["claude", "agy"], "claude", "test")
        async with app.run_test(size=(100, 28)) as pilot:
            assert app.lead == "claude"
            await pilot.click("#input")
            await pilot.press(*"/lead agy", "enter")
            await app.workers.wait_for_complete()
            await pilot.pause(0.5)
            assert app.orch.lead == "agy"
            assert app.lead == "agy", "app.lead must follow orch.lead, not a stale copy"
            assert "lead: agy" in app.sub_title
            app.refresh_team()
            team = str(app.query_one("#team", Static).render())
            assert "agy" in team and "(lead)" in team
    asyncio.run(go())


def _said(app) -> str:
    """What the room has actually shown, as text. `app.history` holds Markdown objects, so asking
    them for a str gives a repr; the chat log holds the rendered lines."""
    from textual.widgets import RichLog
    return "\n".join(line.plain if hasattr(line, "plain") else str(line)
                     for line in app.room.query_one("#chat", RichLog).lines)


# ---------- the startup lead picker (Option A: block until the room has a lead) ----------
def test_a_room_started_without_a_lead_blocks_on_the_picker_and_the_choice_takes_effect(monkeypatch):
    """Without a lead the first request went into the backend as DIRECT_CMDS[None] and raised
    KeyError out of the message loop. The room must not be usable until the user has picked."""
    monkeypatch.setattr(tui, "lead_candidates", lambda orch: ["claude", "agy"])
    backend = FakeBackend(json.dumps({"reply": "ok", "tasks": []}))

    async def go():
        app = HexmindApp(backend, ["claude", "agy"], None, "test")
        async with app.run_test(size=(100, 28)) as pilot:
            await pilot.pause()
            assert type(app.screen).__name__ == "LeadPicker"
            assert app.orch.lead is None, "the request path must be blocked, not merely discouraged"
            assert app.round == 0, "nothing may be sent to the backend before there is a lead"

            await pilot.press("j")  # walk to the second model
            await pilot.click("#pick-agy")
            await pilot.pause()
            assert app.orch.lead == "agy"
            assert type(app.screen).__name__ == "Screen", "the picker closes once there is a lead"
            assert "lead: agy" in app.sub_title

    asyncio.run(go())


def test_declining_the_picker_re_asks_on_the_next_request_instead_of_running_it(monkeypatch):
    """Escape is allowed — the user may want to look around first. But a request typed afterwards
    goes back to them as a question, not to a backend that has no model to answer with."""
    monkeypatch.setattr(tui, "lead_candidates", lambda orch: ["claude", "agy"])
    backend = FakeBackend(json.dumps({"reply": "ok", "tasks": []}))

    async def go():
        app = HexmindApp(backend, ["claude", "agy"], None, "test")
        async with app.run_test(size=(100, 28)) as pilot:
            await pilot.pause()
            await pilot.press("escape")
            await pilot.pause()
            assert app.orch.lead is None
            assert type(app.screen).__name__ == "Screen", "declining leaves the room, without a lead"
            assert app.focused.id == "input", "the room is usable again, so the cursor goes back to it"

            await pilot.click("#input")
            await pilot.press(*"build me a thing", "enter")
            await app.workers.wait_for_complete()
            await pilot.pause()
            assert type(app.screen).__name__ == "LeadPicker", "the request re-asks instead of running"
            assert app.orch.lead is None

    asyncio.run(go())


def test_commands_still_work_in_a_room_with_no_lead(monkeypatch):
    """A room with no lead is stuck, not broken: /help and /lead must still answer, because the
    user needs a way to find out what to do next."""
    monkeypatch.setattr(tui, "lead_candidates", lambda orch: ["claude", "agy"])
    backend = FakeBackend(json.dumps({"reply": "ok", "tasks": []}))

    async def go():
        app = HexmindApp(backend, ["claude", "agy"], None, "test")
        async with app.run_test(size=(100, 28)) as pilot:
            await pilot.pause()
            await pilot.press("escape")
            await pilot.pause()
            await pilot.click("#input")
            await pilot.press(*"/lead", "enter")
            await app.workers.wait_for_complete()
            await pilot.pause()
            assert type(app.screen).__name__ == "Screen", "a command must not re-open the picker"
            said = _said(app)
            assert "No lead yet" in said
            assert "Lead is None" not in said

    asyncio.run(go())


def test_one_candidate_is_chosen_without_asking(monkeypatch):
    """A question with one answer is a delay, not a decision. The model is still set through
    set_lead, so the same validation and the same chat record apply."""
    monkeypatch.setattr(tui, "lead_candidates", lambda orch: ["claude"])
    backend = FakeBackend(json.dumps({"reply": "ok", "tasks": []}))

    async def go():
        app = HexmindApp(backend, ["claude"], None, "test")
        async with app.run_test(size=(100, 28)) as pilot:
            await pilot.pause()
            assert app.orch.lead == "claude"
            assert type(app.screen).__name__ == "Screen"

    asyncio.run(go())


def test_a_room_where_nothing_can_lead_says_so_instead_of_showing_an_empty_picker(monkeypatch):
    monkeypatch.setattr(tui, "lead_candidates", lambda orch: [])
    backend = FakeBackend(json.dumps({"reply": "ok", "tasks": []}))

    async def go():
        app = HexmindApp(backend, ["claude"], None, "test")
        async with app.run_test(size=(100, 28)) as pilot:
            await pilot.pause()
            assert type(app.screen).__name__ == "Screen", "an empty picker would be a dead end"
            assert app.orch.lead is None
            said = _said(app)
            assert "No model can lead" in said

    asyncio.run(go())


def test_only_one_picker_at_a_time(monkeypatch):
    """Two stacked views of the same question, and the second one's dismissal would land after the
    first has already set a lead."""
    monkeypatch.setattr(tui, "lead_candidates", lambda orch: ["claude", "agy"])

    async def go():
        app = HexmindApp(FakeBackend(json.dumps({"reply": "ok", "tasks": []})),
                         ["claude", "agy"], None, "test")
        async with app.run_test(size=(100, 28)) as pilot:
            await pilot.pause()
            app.ask_lead()
            await pilot.pause()
            assert sum(isinstance(s, tui.LeadPicker) for s in app.screen_stack) == 1

    asyncio.run(go())


def test_candidates_are_the_models_that_can_actually_lead(monkeypatch):
    """set_lead refuses text-only models and unwoken-but-uninstalled ones, so offering them is a
    choice that cannot be taken. In-room models come first; the rest follow registry weight."""
    from hexmind.core import TEXT_ONLY, Orchestrator
    text_only = next(m for m in TEXT_ONLY if m in REGISTRY.models)
    monkeypatch.setattr(REGISTRY, "available", lambda: ["claude", text_only, "agy"])
    orch = Orchestrator(FakeBackend("{}"), ["claude", text_only], "claude")

    candidates = tui.lead_candidates(orch)

    assert candidates[0] == "claude", "whoever is in the room leads the list"
    assert text_only not in candidates
    assert set(candidates) == {"claude", "agy"}, "installed, leadable, in weight order"


def test_a_typed_lead_command_still_goes_through_set_lead(monkeypatch):
    """The picker must not become a second way to change the lead that skips the orchestrator."""
    monkeypatch.setattr(tui, "lead_candidates", lambda orch: ["claude", "agy"])
    backend = FakeBackend(json.dumps({"reply": "ok", "tasks": []}))

    async def go():
        app = HexmindApp(backend, ["claude", "agy"], None, "test")
        async with app.run_test(size=(100, 28)) as pilot:
            await pilot.pause()
            await pilot.click("#pick-claude")
            await pilot.pause()
            said = _said(app)
            assert "is the lead now" in said, "the same record /lead NAME writes"

    asyncio.run(go())

"""Textual chat room: one input for the user, a live task board for the team."""
from __future__ import annotations

import asyncio
import os
import shutil

from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.visual import VisualType
from textual.widget import Widget
from textual.widgets import Button, DataTable, Footer, Header, Input, RichLog, Static

from .core import BUSY_STATUSES, REGISTRY, TEXT_ONLY, Orchestrator, Task, TeamBusy, TeamError

STATUS_STYLE = {"pending": "dim", "running": "yellow", "done": "green", "failed": "red", "skipped": "dim strike",
                "auditing": "magenta", "revising": "orange1"}
# Generated from the registry, so a newly registered model always has a colour instead of
# silently falling through to white. "you" is the user, not a model.
AGENT_COLOR: dict[str, str] = {**REGISTRY.colors(), "you": "bold white"}

BUSY, IDLE = ("*", ".") if os.environ.get("FORCE_ASCII") else ("●", "○")
NARROW, SHORT, TINY = 80, 18, 10  # breakpoints: below NARROW cols -> tabbed single view; below SHORT/TINY rows -> compact
HELP = """[b]Keys[/b] (press [b]Esc[/b] to leave the input)

  [b]v[/b]        switch Chat / Tasks
  [b]i[/b] / Enter  type a message
  [b]j[/b] / [b]k[/b]    scroll chat / move task cursor
  [b]t[/b]        the team roster: sleep, wake, lead
  [b]c[/b]        clear chat
  [b]q[/b]        quit
  [b]?[/b]        this help

Ctrl+Q / Ctrl+L work anywhere."""


def audit_cell(t: Task, name=lambda m: m) -> str:
    """'pass·agy' / 'fixed·codex' / 'disputed·claude'; blank until audited. `name` maps model -> nickname."""
    audit, auditor = getattr(t, "audit", ""), getattr(t, "auditor", "")
    return f"{audit}·{name(auditor)}" if audit and auditor else audit or ""


class HelpScreen(ModalScreen):
    CSS = """
    HelpScreen { align: center middle; }
    #help { width: 44; max-width: 100%; height: auto; max-height: 100%; padding: 1 2; border: solid $primary; background: $surface; }
    #help Button { margin-top: 1; }
    """
    BINDINGS = [("escape,q,question_mark", "dismiss", "Close")]

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="help"):  # scrolls rather than pushing Close off a short screen
            yield Static(HELP)
            yield Button("Close", id="close", compact=True)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss()


class TaskScreen(ModalScreen):
    """Full-screen task detail for narrow terminals, where a split-off detail pane would be a sliver."""
    CSS = """
    TaskScreen { align: center middle; }
    #sheet { width: 100%; height: 90%; border: solid $primary; background: $surface; }
    #sheet RichLog { height: 1fr; }
    #sheet Horizontal { height: 1; }
    /* Same rule the tab bar got in cc529e9: a 1-cell margin on every auto-width button bought
       nothing (they carry their own padding) and only ever cost columns. With two short labels the
       row still has room to spare at the 40-column floor, but the margin is what put the tab bar's
       `?` off the screen, and this sheet is a phone-width screen too. */
    #sheet Button { width: auto; min-width: 0; margin-right: 0; }
    """
    BINDINGS = [("escape,q", "dismiss", "Close")]

    def __init__(self, write, output: str) -> None:
        super().__init__()
        self.write, self.output = write, output  # write fills a RichLog with the task detail

    def compose(self) -> ComposeResult:
        with Vertical(id="sheet"):
            yield RichLog(wrap=True, min_width=0)  # always visible, so wrap to the sheet instead of 78 cols
            with Horizontal():
                yield Button("Close", id="close", compact=True)
                yield Button("Copy", id="copy", compact=True, disabled=not self.output)

    def on_mount(self) -> None:
        self.write(self.query_one(RichLog))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "copy":
            self.app.copy_to_clipboard(self.output)  # OSC 52; Termux may not honour it, so also try termux-api
            if shutil.which("termux-clipboard-set"):
                self.termux_copy()
            self.notify("Copied task output")
        else:
            self.dismiss()

    @work(exclusive=True)
    async def termux_copy(self) -> None:
        # termux-api hangs if the Termux:API app is missing, so never block the UI on it
        proc = await asyncio.create_subprocess_exec("termux-clipboard-set", stdin=asyncio.subprocess.PIPE,
                                                    stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
        try:
            await asyncio.wait_for(proc.communicate(self.output.encode()), 5)
        except asyncio.TimeoutError:
            pass
        finally:  # also runs if the sheet is closed and the worker cancelled
            if proc.returncode is None:
                proc.kill()


def labelled(content: VisualType, tooltip: str, classes: str = "") -> Static:
    """A Static that answers a mouse hover: Widget.tooltip is a property, not a constructor argument."""
    widget = Static(content, classes=classes)
    widget.tooltip = tooltip
    return widget


TEAM_NOTE = ("A model that is working cannot be put to sleep until its task finishes. "
             "Sleeping parks its session: its history and journal stay readable.")


class ModelCardScreen(ModalScreen):
    """Registry.describe() for one model: the reference card the roster's Card control opens."""

    CSS = """
    ModelCardScreen { align: center middle; }
    #card { width: 68; max-width: 100%; height: auto; max-height: 100%; padding: 1 2; border: solid $primary; background: $surface; }
    #card Button { margin-top: 1; }
    """
    BINDINGS = [("escape,q,question_mark", "dismiss", "Close")]

    def __init__(self, model: str) -> None:
        super().__init__()
        self.model = model

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="card"):
            yield Static(REGISTRY.describe(self.model))
            yield Button("Close", id="close", compact=True, tooltip="Back to the team roster")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss()


class TeamScreen(ModalScreen):
    """The /team roster: every model hexmind knows, what it is doing, and the three things you can
    change about it. Same state as /sleep, /wake and /lead — one place to see and change the room,
    rather than three (WS-10). A control is disabled with the reason in its tooltip instead of
    being offered as a button guaranteed to fail: INVARIANT S-1."""

    CSS = """
    TeamScreen { align: center middle; }
    /* one scroll box, like HelpScreen, so a long roster scrolls rather than pushing Close off a
       short screen. `.who` and `.state` are declared here, and the narrow overrides in
       HexmindApp.CSS: a screen's own stylesheet never matches an ancestor's classes. */
    #roster { width: 96; max-width: 100%; height: auto; max-height: 100%; border: solid $primary; background: $surface; }
    #roster > Vertical { height: 1; layout: horizontal; }
    #roster .who { width: auto; }
    #roster .state { width: 1fr; min-width: 0; overflow: hidden; text-overflow: ellipsis; }
    #roster .domains { width: 1fr; min-width: 0; overflow: hidden; text-overflow: ellipsis; text-style: dim; }
    #roster Button { width: auto; min-width: 0; height: 1; margin-left: 1; }
    #team-note { padding: 0 1; text-style: dim; }
    """
    BINDINGS = [("escape,q", "dismiss", "Close"),
                # j/k and the arrows walk the rows; ? is the Card control on the row under the cursor
                Binding("j,down", "cursor(1)", "Next model", show=False),
                Binding("k,up", "cursor(-1)", "Previous model", show=False),
                Binding("question_mark", "card", "Model card", show=False)]

    def __init__(self) -> None:
        super().__init__()
        self.rows: list[str] = []  # the models on show, in display order

    @property
    def orch(self) -> Orchestrator:
        return self.app.orch

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="roster"):
            yield from self.roster_widgets()

    def on_mount(self) -> None:
        if self.rows:
            self.focus_control(self.rows[0])

    # ---------- rows ----------
    def names(self) -> list[str]:
        """Every model hexmind knows, awake or not, preferred first — the same order /team lists."""
        return REGISTRY.by_weight([m for m in self.orch.known if m in REGISTRY])

    def state(self, name: str) -> str:
        """lead / awake / asleep / busy with the task ids holding it, as the /team command lists them."""
        orch = self.orch
        if name not in orch.members:
            return "asleep"
        held = [t.id for t in orch.all_tasks if t.agent == name and t.status in BUSY_STATUSES]
        state = "lead" if name == orch.lead else "busy" if held else "awake"
        return f"{state} · {', '.join(held)}" if held else state

    def roster_widgets(self) -> list[Widget]:
        self.rows = self.names()
        if not self.rows:  # nothing registered at all: say so rather than open an empty box
            return [Static("No models registered — check hexmind/models.toml.", id="team-empty")]
        return [*(self.row(name) for name in self.rows),
                Static(TEAM_NOTE, id="team-note"),
                Button("Close", id="close", compact=True, tooltip="Close the team roster")]

    def row(self, name: str) -> Vertical:
        model = REGISTRY.get(name)
        label = Text(self.orch.name(name), style=AGENT_COLOR.get(name, "white"))
        if name in self.orch.nicknames:  # the nickname is what the user calls it, so keep the model name too
            label.append(f" ({name})", style="dim")
        state = self.state(name)
        return Vertical(
            labelled(label, f"{name}: {model.description}", classes="who"),
            labelled(Text(state, style="dim" if state in ("awake", "asleep") else ""),
                     f"{name} is {state}", classes="state"),
            Static(", ".join(model.domains), classes="domains"),
            *self.controls(name),
            id=f"row-{name}",
        )

    def controls(self, name: str) -> list[Button]:
        """Sleep or Wake, Lead, and the reference card. Sleep is disabled with can_sleep's reason
        in the tooltip, so a busy model (INVARIANT S-1) and the lead are never offered a refusal."""
        if name in self.orch.members:
            allowed, reason = self.orch.can_sleep(name)
            toggle = Button("Sleep", id=f"sleep-{name}", compact=True, disabled=not allowed,
                            tooltip=f"Sleep {name} — parks its session, its history stays readable" if allowed
                            else f"Cannot sleep {name} — {reason}")
        else:
            toggle = Button("Wake", id=f"wake-{name}", compact=True,
                            tooltip=f"Wake {name} — brings it back into the room; its CLI is re-checked")
        return [toggle, self.lead_control(name), self.card_control(name)]

    def lead_control(self, name: str) -> Button:
        if name == self.orch.lead:
            return Button("Lead", id=f"lead-{name}", compact=True, disabled=True,
                          tooltip=f"{name} is already the lead")
        if name in TEXT_ONLY:  # set_lead refuses: no file or tool access, so nothing to lead with
            return Button("Lead", id=f"lead-{name}", compact=True, disabled=True,
                          tooltip=f"{name} is text-only: it cannot see files, so it can't lead")
        return Button("Lead", id=f"lead-{name}", compact=True, tooltip=f"Make {name} the lead")

    def card_control(self, name: str) -> Button:
        return Button("Card", id=f"card-{name}", compact=True,
                      tooltip=f"Reference card for {name} — best at, not for, domains, footprint")

    async def rebuild(self) -> None:
        """The room moves under the roster (a task starts or ends), so the rows have to follow it:
        a Sleep that just became legal must be offered and one that just became illegal hidden."""
        model, control = self.focused_model(), self.focused_control()
        rows = self.query_one("#roster", VerticalScroll)
        await rows.remove_children()
        await rows.mount(*self.roster_widgets())
        if model and control:
            self.focus_control(model, control)

    # ---------- keyboard ----------
    def focused_model(self) -> str | None:
        widget = self.focused
        while widget is not None and widget is not self:
            if widget.id and widget.id.startswith("row-"):
                return widget.id[len("row-"):]
            widget = widget.parent
        return None

    def focused_control(self) -> str | None:
        """Which control the cursor is on, as a verb: the same Sleep-or-Wake column stays put as the
        cursor walks, even though a woken model has swapped the button for its opposite."""
        verb, _, _ = (getattr(self.focused, "id", "") or "").partition("-")
        return verb if verb in ("sleep", "wake", "lead", "card") else None

    def row_controls(self, model: str) -> list[Button]:
        return list(self.query(f"#row-{model} Button"))

    def focus_control(self, model: str, control: str | None = None) -> None:
        """Land on the same control of `model` where it survives, else its first enabled one."""
        enabled = [b for b in self.row_controls(model) if not b.disabled]
        target = next((b for b in enabled if b.id == f"{control}-{model}"), None) or (enabled[0] if enabled else None)
        if target:
            target.focus()

    def action_cursor(self, step: int) -> None:
        if not self.rows:
            return
        here, control = self.focused_model() or self.rows[0], self.focused_control()
        index = max(0, min(len(self.rows) - 1, self.rows.index(here) + step))  # stop at the ends, don't wrap
        self.focus_control(self.rows[index], control)

    def action_card(self) -> None:
        if model := self.focused_model():
            self.open_card(model)

    def open_card(self, model: str) -> None:
        self.app.push_screen(ModelCardScreen(model))

    # ---------- actions ----------
    def on_button_pressed(self, event: Button.Pressed) -> None:
        verb, _, model = (event.button.id or "").partition("-")  # ids are verb-model, and models have hyphens
        if verb == "close":
            self.dismiss()
        elif verb == "card":
            self.open_card(model)
        else:
            self.change(verb, model)

    def change(self, verb: str, model: str) -> None:
        """Every change goes through the orchestrator, which re-checks can_sleep and can still
        refuse: the row may have been sleepable a moment before a task was handed to that model."""
        orch = self.orch
        try:
            if verb == "sleep":
                self.report(orch.sleep(model))
            elif verb == "wake":
                self.report(orch.wake(model), refused=not orch.is_awake(model))
            else:
                self.report(orch.set_lead(model))
        except TeamBusy as e:
            self.report(f"**Not now.** {e}", refused=True)
        except TeamError as e:
            self.report(f"**{e}**", refused=True)
        self.call_later(self.rebuild)  # a refused change leaves the row as it was

    def report(self, text: str, refused: bool = False) -> None:
        """Recorded in the chat like the /sleep, /wake and /lead commands record it; a refusal is
        also raised as a toast, because the chat is behind the roster while it is open."""
        self.app.say("Hexmind", text)
        if refused:
            self.notify(text, severity="warning", timeout=8)


class TaskTable(DataTable):
    def _on_click(self, event) -> None:
        # DataTable only selects a row that is already highlighted, so on a phone every task would take two taps.
        # Textual runs DataTable's own _on_click after this one (handlers run down the MRO), so highlight first.
        row = event.style.meta.get("row", -1)
        if self.app.has_class("narrow") and row >= 0:
            self.move_cursor(row=row)


class HexmindApp(App):
    TITLE = "Hexmind"
    CSS = """
    #left { width: 2fr; }
    #right { width: 1fr; border-left: solid $primary; }
    #chat { height: 1fr; }
    #team { height: auto; padding: 0 1; border-bottom: solid $primary; }
    #tasks { height: 1fr; }
    #detail { height: 1fr; border-top: solid $primary; }
    #tabs { display: none; height: 1; }
    /* The bar is shown only in narrow mode, where 40 columns is the floor: six buttons at
       (label + 2 padding) + a 1-cell margin each = 41, and `?` fell off the end. The buttons pad
       themselves, so the margin buys nothing but the overflow — the spacer separates the two
       groups on a wider phone. */
    #tabs Button { width: auto; min-width: 0; margin-right: 0; }
    #tabs .spacer { width: 1fr; }
    #tabs .active { text-style: bold reverse; }
    .narrow #tabs { display: block; }
    .narrow #left, .narrow #right { width: 1fr; }
    .narrow #right { border-left: none; }
    .narrow.view-chat #right, .narrow.view-tasks #left { display: none; }
    .short #team { border-bottom: none; }
    .tiny Header, .tiny Footer { display: none; }
    .tiny #input { height: 1; border: none; padding: 0 1; }
    .narrow #detail { display: none; }
    /* a /team row cannot hold a name, a state and three controls on one line at 40 cols, so on a
       phone it becomes two: the name, then the controls. The domains are the first thing to go. */
    .narrow #roster > Vertical { height: 2; layout: vertical; }
    .narrow #roster .domains { display: none; }
    .narrow #roster .who { width: 1fr; min-width: 0; overflow: hidden; text-overflow: ellipsis; }
    .narrow #roster Button { margin-left: 0; }
    """
    BINDINGS = [("ctrl+q", "quit", "Quit"), ("ctrl+l", "clear", "Clear chat"),
                # single-key alternatives for soft keyboards; Input consumes printable keys, so these only fire when it is blurred
                Binding("escape", "blur", "Leave input", show=False),
                Binding("q", "quit", "Quit", show=False), Binding("c", "clear", "Clear chat", show=False),
                Binding("v", "toggle_view", "Chat/Tasks", show=False), Binding("i,enter", "focus_input", "Type", show=False),
                Binding("j", "move(1)", "Down", show=False), Binding("k", "move(-1)", "Up", show=False),
                Binding("t", "team", "Team", show=False),
                Binding("question_mark", "help", "Help", show=False)]

    def __init__(self, backend, members: list[str], lead: str, backend_name: str, audit: bool = False, stats=None):
        super().__init__()
        self.members = members
        self.backend_name, self.audit = backend_name, audit
        self.sub_title = f"{backend_name} backend · lead: {lead} · audit: {'on' if audit else 'off'}"
        self.orch = Orchestrator(backend, members, lead, emit=self.on_team_event, audit=audit, stats=stats)
        self.tasks: dict[str, Task] = {}  # row key -> task, across all requests
        self.lead_state = "idle"
        self.turn = asyncio.Lock()  # one request at a time; later ones queue
        self.round = 0
        self.view = "chat"  # which pane shows in narrow (tabbed) mode
        self.table_width = 0  # terminal width the narrow task table's fixed columns were sized for
        self.history: list = []  # chat renderables, replayed to re-wrap when a narrow terminal changes width

    @property
    def lead(self) -> str:
        """The leader, always. A separate self.lead went stale the first time /lead ran: the
        subtitle, the (lead) marker and the busy line all read it while set_lead() changed
        orch.lead, so the room kept showing the old leader. A property cannot diverge."""
        return self.orch.lead

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="tabs"):  # touch targets; only shown in narrow mode
            yield Button("Chat", id="tab-chat", compact=True, classes="active")
            yield Button("Tasks", id="tab-tasks", compact=True)
            yield Static(classes="spacer")
            yield Button("Team", id="do-team", compact=True, tooltip="Show the team roster")
            yield Button("Clear", id="do-clear", compact=True)
            yield Button("Quit", id="do-quit", compact=True)
            yield Button("?", id="do-help", compact=True)
        with Horizontal(id="body"):
            with Vertical(id="left"):
                yield RichLog(id="chat", wrap=True, markup=True)
                yield Input(placeholder="Ask the team anything…", id="input")
            with Vertical(id="right"):
                yield Static(id="team")
                yield TaskTable(id="tasks", cursor_type="row")
                yield RichLog(id="detail", wrap=True)
        yield Footer()

    def on_mount(self) -> None:
        self.set_class(True, "view-chat")
        self.apply_size(self.size.width, self.size.height)
        self.refresh_team()
        self.say("Hexmind", f"Team ready: {', '.join(self.members)}. Type a request; the lead splits it up.")
        self.query_one("#input").focus()

    # ---------- responsive layout ----------
    @property
    def room(self) -> Widget:
        """Where the panes live. `App.query_one` only sees the top of the screen stack, so a team
        event arriving while /team is open would otherwise miss every pane it has to refresh."""
        return self.screen_stack[0]

    def on_resize(self, event) -> None:
        self.apply_size(event.size.width, event.size.height)

    def apply_size(self, width: int, height: int) -> None:
        short, narrow = height < SHORT, width < NARROW
        changed = short != self.has_class("short")
        if narrow != self.has_class("narrow") or not self.room.query_one("#tasks", DataTable).columns or narrow and width != self.table_width:
            self.set_class(narrow, "narrow")
            self.table_width = width
            self.build_table()
        self.sub_title = (f"{self.backend_name} backend · lead: {self.lead} · audit: {'on' if self.audit else 'off'}" if not narrow
                          else f"{self.orch.name(self.lead)} · audit:{'on' if self.audit else 'off'}" if width >= 45 else "")
        self.set_class(short, "short")
        self.set_class(height < TINY, "tiny")
        # RichLog renders new lines at >= min_width (default 78), which scrolls sideways on a phone; the chat can be
        # hidden (width 0) while it's written to, so size it from the terminal rather than letting it shrink to fit
        chat = self.room.query_one("#chat", RichLog)
        min_width = (width if narrow else 2 * width // 3) - 2  # chat pane minus scrollbar; 78 (RichLog's default) at 120 cols
        if min_width != chat.min_width:
            chat.min_width = min_width
            chat.clear()  # RichLog never re-wraps written lines, so write them again at the new width
            for renderable in self.history:  # layout hasn't caught up with the resize yet, so give the width explicitly
                chat.write(renderable, width=min_width)
        if changed:
            self.refresh_team()

    # ---------- task board ----------
    def columns(self) -> dict[str, int | None]:
        """Column -> fixed width (None: fit content). Narrow widths add up to the screen so the table never scrolls sideways."""
        if not self.has_class("narrow"):
            return dict.fromkeys(("task", "agent", "status", "audit", "title"))
        return {"task": 5, "status": 12, "title": max(8, self.table_width - 25)}  # 25: those two, 1-cell padding each side, scrollbar

    def cells(self, key: str, t: Task) -> dict:
        audit = audit_cell(t, self.orch.name)
        status = Text(t.status, style=STATUS_STYLE.get(t.status, ""))
        if not self.has_class("narrow"):
            return {"task": key, "agent": self.orch.name(t.agent), "status": status,
                    "audit": Text(audit, style="red" if getattr(t, "audit", "") == "disputed" else ""), "title": t.title}
        if audit:  # compact: fold audit into status and agent into title
            status.append(f" {audit}", style="red" if getattr(t, "audit", "") == "disputed" else "dim")
        return {"task": key, "status": status,
                "title": Text.assemble((f"{self.orch.name(t.agent)} ", AGENT_COLOR.get(t.agent, "")), t.title)}

    def build_table(self) -> None:
        """(Re)create the columns for the current width and refill rows, keeping the cursor."""
        table = self.room.query_one("#tasks", DataTable)
        row = table.cursor_row
        table.clear(columns=True)
        for col, width in self.columns().items():
            table.add_column(col, key=col, width=width)
        for key, t in self.tasks.items():
            table.add_row(*self.cells(key, t).values(), key=key)
        if self.tasks:
            table.move_cursor(row=row)

    def set_view(self, view: str) -> None:
        self.view = view
        self.set_class(view == "chat", "view-chat")
        self.set_class(view == "tasks", "view-tasks")
        self.query_one("#tab-chat").set_class(view == "chat", "active")
        self.query_one("#tab-tasks").set_class(view == "tasks", "active")
        self.query_one("#input" if view == "chat" else "#tasks").focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        action = {"tab-chat": lambda: self.set_view("chat"), "tab-tasks": lambda: self.set_view("tasks"),
                  "do-team": self.action_team, "do-clear": self.action_clear, "do-quit": self.exit,
                  "do-help": self.action_help}.get(event.button.id)
        if action:
            action()

    def action_toggle_view(self) -> None:
        self.set_view("tasks" if self.view == "chat" else "chat")

    def action_focus_input(self) -> None:
        self.set_view("chat")

    def action_blur(self) -> None:
        if isinstance(self.focused, Input):
            self.query_one("#chat" if self.view == "chat" or not self.has_class("narrow") else "#tasks").focus()

    def action_move(self, step: int) -> None:
        if isinstance(self.focused, DataTable):
            self.focused.move_cursor(row=self.focused.cursor_row + step)
        else:
            self.query_one("#chat", RichLog).scroll_relative(y=step)

    def action_help(self) -> None:
        self.push_screen(HelpScreen())

    def action_team(self) -> None:
        """One roster at a time: a second `t` on an open roster would stack a copy of the same state."""
        if not any(isinstance(s, TeamScreen) for s in self.screen_stack):
            self.push_screen(TeamScreen())

    # ---------- chat ----------
    def say(self, who: str, text: str) -> None:
        if not self.is_mounted:
            return  # an emit can fire before the widgets exist (a startup leader choice)
        if text.startswith("ESCALATION"):
            lines = [Panel(Markdown(text), title=f"{self.orch.name(who)} · needs you", border_style="bold red"), ""]
        else:
            label = self.orch.name(who)
            lines = [Text(label if label == who else f"{label} ({who})", style=AGENT_COLOR.get(who, "bold magenta")),
                     Markdown(text) if who != "you" else Text(text), ""]
        chat = self.room.query_one("#chat", RichLog)
        for renderable in lines:
            self.history.append(renderable)
            chat.write(renderable)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        event.input.value = ""
        if not text:
            return
        self.say("you", text)
        if self.turn.locked():
            self.say("Hexmind", "_Team is busy — queued, will start when the current request finishes._")
        self.handle(text)

    @work(group="turns")
    async def handle(self, text: str) -> None:
        async with self.turn:
            self.round += 1
            try:
                await self.orch.handle(text)
            except Exception as e:
                self.say("Hexmind", f"**Error:** {e}")
                self.lead_state = "idle"
                self.refresh_team()

    # ---------- team events from the orchestrator ----------
    def on_team_event(self, kind: str, data: dict) -> None:
        if kind == "message":
            self.say(data["from"], data["text"] or "_(no reply)_")
        elif kind == "status":
            self.lead_state = data["state"]
        elif kind == "team":
            if not self.is_mounted:
                return  # a startup leader choice emits before the widgets exist; nothing to redraw
            # a model was slept, woken, or promoted: drop stale board rows for anyone no longer
            # in the room, then refresh the panes that name the roster (sub_title, team, board)
            gone = {m for m in self.orch.known if m not in self.orch.members}
            for key, t in list(self.tasks.items()):
                if t.agent in gone:
                    del self.tasks[key]
            self.apply_size(self.size.width, self.size.height)  # recomputes sub_title for the new lead
            self.build_table()
        elif kind == "plan":
            table = self.room.query_one("#tasks", DataTable)
            for t in data["tasks"]:
                key = f"{self.round}.{t.id}"
                self.tasks[key] = t
                table.add_row(*self.cells(key, t).values(), key=key)
            lines = [f"- **{t.id}** → {self.orch.name(t.agent)}: {t.title}" + (f" _(after {', '.join(t.depends_on)})_" if t.depends_on else "")
                     for t in data["tasks"]]
            self.say("Hexmind", "**Plan**\n" + "\n".join(lines))
        elif kind == "task":
            t = data["task"]
            key = f"{self.round}.{t.id}"
            table = self.room.query_one("#tasks", DataTable)
            for col, value in self.cells(key, t).items():
                if col in ("status", "audit"):
                    table.update_cell(key, col, value)
            if t.status in ("done", "failed"):
                first = t.output.strip().splitlines()[0][:200] if t.output.strip() else ""
                self.say(t.agent, f"**{t.id} {t.status}** — {t.title}\n\n{first}")
            if table.cursor_row is not None and table.is_valid_row_index(table.cursor_row):
                self.show_task(table.coordinate_to_cell_key((table.cursor_row, 0)).row_key.value)
        self.refresh_team()

    def refresh_team(self) -> None:
        if not self.is_mounted:
            return
        active = sum(t.status in ("pending", "running", "auditing", "revising") for t in self.tasks.values())
        self.room.query_one("#tab-tasks", Button).label = f"Tasks ({active})" if active else "Tasks"
        lines, busy_count = [], 0
        for m in self.members:
            busy = [k for k, t in self.tasks.items() if t.agent == m and t.status in ("running", "revising")]
            auditing = [k for k, t in self.tasks.items() if getattr(t, "auditor", "") == m and t.status == "auditing"]
            parts = ([f"working: {', '.join(busy)}"] if busy else []) + ([f"auditing {', '.join(auditing)}"] if auditing else [])
            state = " · ".join(parts) or "idle"
            if m == self.lead and self.lead_state != "idle":
                state = self.lead_state + (f" · {state}" if busy else "")
            dot = BUSY if state != "idle" else IDLE
            busy_count += state != "idle"
            lines.append(f"[{AGENT_COLOR.get(m, 'white')}]{dot} {self.orch.name(m)}[/]{f' [dim]({m})[/]' if m in self.orch.nicknames else ''}{' (lead)' if m == self.lead else ''}  [dim]{state}[/]")
        if self.has_class("short"):  # soft keyboard open: one-line summary leaves rows for the task list
            idle = len(self.members) - busy_count
            lines = [f"[yellow]{BUSY}[/] {busy_count} busy · [dim]{IDLE} {idle} idle · lead: {self.orch.name(self.lead)}[/]"]
        self.room.query_one("#team", Static).update("\n".join(lines))
        for screen in self.screen_stack:  # a roster left open tracks the room it is changing
            if isinstance(screen, TeamScreen):
                screen.call_later(screen.rebuild)

    # ---------- task detail ----------
    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if event.row_key is not None:
            self.show_task(event.row_key.value)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        if self.has_class("narrow") and event.row_key.value in self.tasks:
            key = event.row_key.value
            self.push_screen(TaskScreen(lambda log: self.write_task(log, key), self.tasks[key].output))

    def show_task(self, key: str) -> None:
        self.write_task(self.query_one("#detail", RichLog), key)

    def write_task(self, detail: RichLog, key: str) -> None:
        t = self.tasks.get(key)
        detail.clear()
        if t:
            audit = audit_cell(t, self.orch.name)
            detail.write(Text(f"{key} · {self.orch.name(t.agent)} · {t.status}" + (f" · audit {audit}" if audit else ""), style="bold"))
            detail.write(Text(t.instructions, style="dim"))
            detail.write("")
            detail.write(Markdown(t.output) if t.output else Text("(no output yet)", style="dim"))

    def action_clear(self) -> None:
        self.history.clear()
        self.query_one("#chat", RichLog).clear()

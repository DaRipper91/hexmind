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
from textual.widgets import Button, DataTable, Footer, Header, Input, RichLog, Static

from .core import Orchestrator, Task

STATUS_STYLE = {"pending": "dim", "running": "yellow", "done": "green", "failed": "red", "skipped": "dim strike",
                "auditing": "magenta", "revising": "orange1"}
AGENT_COLOR = {
    "claude": "orange1", "agy": "cyan", "codex": "green", "jules": "magenta", "qwen": "yellow",
    "qwen-large": "gold1",
    "opencode": "bright_blue", "opencode-ultra": "blue", "opencode-muse": "sky_blue1",
    "opencode-mimo": "turquoise2", "opencode-pickle": "yellow3", "opencode-ling": "green3",
    "copilot": "white", "kimi": "red", "you": "bold white"
}
BUSY, IDLE = ("*", ".") if os.environ.get("FORCE_ASCII") else ("●", "○")
NARROW, SHORT, TINY = 80, 18, 10  # breakpoints: below NARROW cols -> tabbed single view; below SHORT/TINY rows -> compact
HELP = """[b]Keys[/b] (press [b]Esc[/b] to leave the input)

  [b]v[/b]        switch Chat / Tasks
  [b]i[/b] / Enter  type a message
  [b]j[/b] / [b]k[/b]    scroll chat / move task cursor
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
    #sheet Button { width: auto; min-width: 0; margin-right: 1; }
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
    #tabs Button { width: auto; min-width: 0; margin-right: 1; }
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
    """
    BINDINGS = [("ctrl+q", "quit", "Quit"), ("ctrl+l", "clear", "Clear chat"),
                # single-key alternatives for soft keyboards; Input consumes printable keys, so these only fire when it is blurred
                Binding("escape", "blur", "Leave input", show=False),
                Binding("q", "quit", "Quit", show=False), Binding("c", "clear", "Clear chat", show=False),
                Binding("v", "toggle_view", "Chat/Tasks", show=False), Binding("i,enter", "focus_input", "Type", show=False),
                Binding("j", "move(1)", "Down", show=False), Binding("k", "move(-1)", "Up", show=False),
                Binding("question_mark", "help", "Help", show=False)]

    def __init__(self, backend, members: list[str], lead: str, backend_name: str, audit: bool = False, stats=None):
        super().__init__()
        self.members, self.lead = members, lead
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

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="tabs"):  # touch targets; only shown in narrow mode
            yield Button("Chat", id="tab-chat", compact=True, classes="active")
            yield Button("Tasks", id="tab-tasks", compact=True)
            yield Static(classes="spacer")
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
    def on_resize(self, event) -> None:
        self.apply_size(event.size.width, event.size.height)

    def apply_size(self, width: int, height: int) -> None:
        short, narrow = height < SHORT, width < NARROW
        changed = short != self.has_class("short")
        if narrow != self.has_class("narrow") or not self.query_one("#tasks", DataTable).columns or narrow and width != self.table_width:
            self.set_class(narrow, "narrow")
            self.table_width = width
            self.build_table()
        self.sub_title = (f"{self.backend_name} backend · lead: {self.lead} · audit: {'on' if self.audit else 'off'}" if not narrow
                          else f"{self.orch.name(self.lead)} · audit:{'on' if self.audit else 'off'}" if width >= 45 else "")
        self.set_class(short, "short")
        self.set_class(height < TINY, "tiny")
        # RichLog renders new lines at >= min_width (default 78), which scrolls sideways on a phone; the chat can be
        # hidden (width 0) while it's written to, so size it from the terminal rather than letting it shrink to fit
        chat = self.query_one("#chat", RichLog)
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
        table = self.query_one("#tasks", DataTable)
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
                  "do-clear": self.action_clear, "do-quit": self.exit, "do-help": self.action_help}.get(event.button.id)
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

    # ---------- chat ----------
    def say(self, who: str, text: str) -> None:
        if text.startswith("ESCALATION"):
            lines = [Panel(Markdown(text), title=f"{self.orch.name(who)} · needs you", border_style="bold red"), ""]
        else:
            label = self.orch.name(who)
            lines = [Text(label if label == who else f"{label} ({who})", style=AGENT_COLOR.get(who, "bold magenta")),
                     Markdown(text) if who != "you" else Text(text), ""]
        chat = self.query_one("#chat", RichLog)
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
        elif kind == "plan":
            table = self.query_one("#tasks", DataTable)
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
            table = self.query_one("#tasks", DataTable)
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
        active = sum(t.status in ("pending", "running", "auditing", "revising") for t in self.tasks.values())
        self.query_one("#tab-tasks", Button).label = f"Tasks ({active})" if active else "Tasks"
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
        self.query_one("#team", Static).update("\n".join(lines))

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

"""Textual chat room: one input for the user, a live task board for the team."""
from __future__ import annotations

import asyncio

from rich.markdown import Markdown
from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import DataTable, Footer, Header, Input, RichLog, Static

from .core import Orchestrator, Task

STATUS_STYLE = {"pending": "dim", "running": "yellow", "done": "green", "failed": "red", "skipped": "dim strike"}
AGENT_COLOR = {"claude": "orange1", "agy": "cyan", "codex": "green", "jules": "magenta", "you": "bold white"}


class HexmindApp(App):
    TITLE = "Hexmind"
    CSS = """
    #left { width: 2fr; }
    #right { width: 1fr; border-left: solid $primary; }
    #chat { height: 1fr; }
    #team { height: auto; padding: 0 1; border-bottom: solid $primary; }
    #tasks { height: 1fr; }
    #detail { height: 1fr; border-top: solid $primary; }
    """
    BINDINGS = [("ctrl+q", "quit", "Quit"), ("ctrl+l", "clear", "Clear chat")]

    def __init__(self, backend, members: list[str], lead: str, backend_name: str):
        super().__init__()
        self.members, self.lead = members, lead
        self.sub_title = f"{backend_name} backend · lead: {lead}"
        self.orch = Orchestrator(backend, members, lead, emit=self.on_team_event)
        self.tasks: dict[str, Task] = {}  # row key -> task, across all requests
        self.lead_state = "idle"
        self.turn = asyncio.Lock()  # one request at a time; later ones queue
        self.round = 0

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal():
            with Vertical(id="left"):
                yield RichLog(id="chat", wrap=True, markup=True)
                yield Input(placeholder="Ask the team anything…", id="input")
            with Vertical(id="right"):
                yield Static(id="team")
                yield DataTable(id="tasks", cursor_type="row")
                yield RichLog(id="detail", wrap=True)
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#tasks", DataTable)
        for col in ("task", "agent", "status", "title"):
            table.add_column(col, key=col)
        self.refresh_team()
        self.say("Hexmind", f"Team ready: {', '.join(self.members)}. Type a request; the lead splits it up.")
        self.query_one("#input").focus()

    # ---------- chat ----------
    def say(self, who: str, text: str) -> None:
        chat = self.query_one("#chat", RichLog)
        chat.write(Text(f"{who}", style=AGENT_COLOR.get(who, "bold magenta")))
        chat.write(Markdown(text) if who != "you" else Text(text))
        chat.write("")

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
                table.add_row(key, t.agent, t.status, t.title, key=key)
            lines = [f"- **{t.id}** → {t.agent}: {t.title}" + (f" _(after {', '.join(t.depends_on)})_" if t.depends_on else "")
                     for t in data["tasks"]]
            self.say("Hexmind", "**Plan**\n" + "\n".join(lines))
        elif kind == "task":
            t = data["task"]
            key = f"{self.round}.{t.id}"
            table = self.query_one("#tasks", DataTable)
            table.update_cell(key, "status", Text(t.status, style=STATUS_STYLE[t.status]))
            if t.status in ("done", "failed"):
                first = t.output.strip().splitlines()[0][:200] if t.output.strip() else ""
                self.say(t.agent, f"**{t.id} {t.status}** — {t.title}\n\n{first}")
            if table.cursor_row is not None and table.is_valid_row_index(table.cursor_row):
                self.show_task(table.coordinate_to_cell_key((table.cursor_row, 0)).row_key.value)
        self.refresh_team()

    def refresh_team(self) -> None:
        lines = []
        for m in self.members:
            busy = [k for k, t in self.tasks.items() if t.agent == m and t.status == "running"]
            state = f"working: {', '.join(busy)}" if busy else "idle"
            if m == self.lead and self.lead_state != "idle":
                state = self.lead_state + (f" · {state}" if busy else "")
            dot = "●" if state != "idle" else "○"
            lines.append(f"[{AGENT_COLOR.get(m, 'white')}]{dot} {m}[/]{' (lead)' if m == self.lead else ''}  [dim]{state}[/]")
        self.query_one("#team", Static).update("\n".join(lines))

    # ---------- task detail ----------
    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if event.row_key is not None:
            self.show_task(event.row_key.value)

    def show_task(self, key: str) -> None:
        t = self.tasks.get(key)
        detail = self.query_one("#detail", RichLog)
        detail.clear()
        if t:
            detail.write(Text(f"{key} · {t.agent} · {t.status}", style="bold"))
            detail.write(Text(t.instructions, style="dim"))
            detail.write("")
            detail.write(Markdown(t.output) if t.output else Text("(no output yet)", style="dim"))

    def action_clear(self) -> None:
        self.query_one("#chat", RichLog).clear()

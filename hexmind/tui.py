"""Textual chat room: one input for the user, a live task board for the team."""
from __future__ import annotations

import asyncio
import base64
import os
import shutil
import subprocess
import sys

from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text
from textual import events, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.coordinate import Coordinate
from textual.screen import ModalScreen
from textual.widgets import Button, DataTable, Footer, Header, Input, RichLog, Static

from .core import Orchestrator, Task

STATUS_STYLE = {
    "pending": "dim",
    "running": "yellow",
    "done": "green",
    "failed": "red",
    "skipped": "dim strike",
    "auditing": "magenta",
    "revising": "orange1",
}
AGENT_COLOR = {
    "claude": "orange1",
    "agy": "cyan",
    "codex": "green",
    "jules": "magenta",
    "qwen": "yellow",
    "opencode": "bright_blue",
    "copilot": "white",
    "you": "bold white",
}


def is_ascii() -> bool:
    """Detect if ASCII-only rendering is requested via FORCE_ASCII or NO_COLOR."""
    return (
        os.environ.get("FORCE_ASCII", "").strip().lower() in ("1", "true", "yes")
        or os.environ.get("NO_COLOR", "").strip().lower() in ("1", "true", "yes")
    )


def copy_to_clipboard(text: str) -> bool:
    """Copy text using OSC 52 escape sequences with termux-clipboard-set fallback."""
    if not text:
        return False
    try:
        b64 = base64.b64encode(text.encode("utf-8")).decode("ascii")
        sys.stdout.write(f"\033]52;c;{b64}\007")
        sys.stdout.flush()
    except Exception:
        pass
    if shutil.which("termux-clipboard-set"):
        try:
            subprocess.run(["termux-clipboard-set"], input=text.encode("utf-8"), check=False, timeout=1)
        except Exception:
            pass
    return True


def audit_cell(t: Task, name=lambda m: m) -> str:
    """'pass·agy' / 'fixed·codex' / 'disputed·claude'; blank until audited. `name` maps model -> nickname."""
    audit, auditor = getattr(t, "audit", ""), getattr(t, "auditor", "")
    return f"{audit}·{name(auditor)}" if audit and auditor else audit or ""


def chat_tab_label(ascii_mode: bool) -> str:
    return "Chat" if ascii_mode else "💬 Chat"


def tasks_tab_label(ascii_mode: bool, count: int = 0) -> str:
    prefix = "Tasks" if ascii_mode else "📋 Tasks"
    return f"{prefix} ({count})" if count > 0 else prefix


class TaskTable(DataTable):
    """DataTable enhanced for mobile touch/tap selection and responsive columns."""

    async def _on_click(self, event: events.Click) -> None:
        """Ensure single tap selects the row immediately on mobile/touch."""
        meta = event.style.meta if hasattr(event, "style") else {}
        if "row" in meta and meta["row"] >= 0 and self.cursor_type != "none":
            row_index = meta["row"]
            if self.is_valid_row_index(row_index):
                self.cursor_coordinate = Coordinate(row_index, max(0, meta.get("column", 0)))
                self._post_selected_message()
                self._scroll_cursor_into_view(animate=True)
                event.stop()
                return
        await super()._on_click(event)

    def get_cell(self, row_key, column_key):
        """Safe get_cell supporting fallback to app.tasks when columns are compressed in narrow mode."""
        if column_key not in self.columns:
            if hasattr(self.app, "tasks"):
                k = row_key.value if hasattr(row_key, "value") else str(row_key)
                t = self.app.tasks.get(k)
                if t:
                    if column_key == "audit":
                        return audit_cell(t, self.app.orch.name)
                    elif column_key == "agent":
                        return self.app.orch.name(t.agent)
                    elif column_key == "status":
                        return t.status
                    elif column_key == "title":
                        return t.title
            return ""
        return super().get_cell(row_key, column_key)

    def update_cell(self, row_key, column_key, value, update_width=False):
        """Safely update cell if column is currently registered."""
        if column_key in self.columns:
            super().update_cell(row_key, column_key, value, update_width=update_width)


class TaskSheet(ModalScreen):
    """Mobile modal sheet displaying full task details and output."""

    BINDINGS = [
        ("escape", "dismiss", "Close"),
        ("q", "dismiss", "Close"),
        ("c", "copy_output", "Copy Output"),
    ]

    def __init__(self, key: str, task: Task, name_fn, ascii_mode: bool = False):
        super().__init__()
        self.task_key = key
        self.task_item = task
        self.name_fn = name_fn
        self.ascii_mode = ascii_mode

    def compose(self) -> ComposeResult:
        t = self.task_item
        audit = audit_cell(t, self.name_fn)
        status_label = f"[{STATUS_STYLE.get(t.status, 'white')}]{t.status}[/]"
        header_text = f"**Task {self.task_key}** · {self.name_fn(t.agent)} · {status_label}"
        if audit:
            header_text += f" · audit: {audit}"

        with Vertical(id="dialog"):
            yield Static(Markdown(header_text), id="dialog-title")
            with VerticalScroll(id="dialog-content"):
                if t.title:
                    yield Static(Text(f"Title: {t.title}", style="bold"))
                    yield Static("")
                if t.instructions:
                    yield Static(Text("Instructions:", style="dim bold"))
                    yield Static(Text(t.instructions, style="dim"))
                    yield Static("")
                yield Static(Text("Output:", style="bold"))
                if t.output:
                    yield Static(Markdown(t.output))
                else:
                    yield Static(Text("(no output yet)", style="dim italic"))
            with Horizontal(id="dialog-actions"):
                yield Button("Copy Output", id="sheet-copy", classes="action-btn")
                yield Button("Close", id="sheet-close", classes="action-btn -active-tab")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "sheet-close":
            self.dismiss()
        elif event.button.id == "sheet-copy":
            self.action_copy_output()

    def action_copy_output(self) -> None:
        if self.task_item and self.task_item.output:
            copy_to_clipboard(self.task_item.output)
            self.notify("Copied output to clipboard", timeout=2)
        else:
            self.notify("No output to copy", timeout=2)


class HelpModal(ModalScreen):
    """Mobile modal displaying touch navigation and keyboard shortcuts."""

    BINDINGS = [
        ("escape", "dismiss", "Close"),
        ("q", "dismiss", "Close"),
        ("enter", "dismiss", "Close"),
        ("question_mark", "dismiss", "Close"),
        ("?", "dismiss", "Close"),
    ]

    HELP_TEXT = """
# Hexmind Shortcuts & Touch Guide

### Touch Controls
- **[Chat] / [Tasks]**: Switch between Chat and Tasks views
- **Task Row**: Tap any row to open the Task Detail Sheet
- **[Clear]**: Clear chat history
- **[Quit]**: Exit Hexmind
- **[?]**: Toggle this help

### Keyboard Shortcuts (when input blurred)
- `i` / `Enter`: Focus input (switches to Chat tab)
- `Esc`: Blur input / back / close modal
- `v` / `Tab`: Toggle between Chat and Tasks views
- `c`: Clear chat
- `q`: Quit Hexmind
- `?`: Toggle this help

### Desktop Chords
- `Ctrl+Q`: Quit
- `Ctrl+L`: Clear chat
"""

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Static(Markdown(self.HELP_TEXT.strip()), id="dialog-content")
            with Horizontal(id="dialog-actions"):
                yield Button("Close", id="help-close", classes="action-btn -active-tab")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "help-close":
            self.dismiss()


class HexmindApp(App):
    TITLE = "Hexmind"
    CSS = """
    Screen {
        layout: vertical;
        overflow: hidden;
    }
    #action-bar {
        height: auto;
        dock: top;
        background: $surface;
        border-bottom: solid $primary;
        padding: 0 1;
    }
    #action-tabs, #action-tools {
        height: auto;
        width: auto;
    }
    .action-btn {
        min-width: 6;
        height: 1;
        margin: 0 1 0 0;
        padding: 0 1;
        border: none;
        background: $surface-darken-1;
        color: $text-muted;
    }
    .action-btn:hover {
        background: $surface-lighten-1;
        color: $text;
    }
    .tab-btn.-active-tab {
        background: $primary;
        color: $text;
        text-style: bold;
    }

    /* Wide Mode (>= 80 cols) */
    .wide #action-bar {
        layout: horizontal;
    }
    .wide #action-tools {
        align-horizontal: right;
        width: 1fr;
    }
    .wide #left {
        width: 2fr;
        display: block;
    }
    .wide #right {
        width: 1fr;
        display: block;
        border-left: solid $primary;
    }
    .wide #detail {
        display: block;
        height: 1fr;
        border-top: solid $primary;
    }

    /* Narrow Mode (< 80 cols) */
    .narrow #action-bar {
        layout: vertical;
    }
    .narrow #action-tabs {
        layout: horizontal;
    }
    .narrow #action-tools {
        layout: horizontal;
    }
    .narrow.view-chat #left {
        width: 1fr;
        display: block;
    }
    .narrow.view-chat #right {
        display: none;
    }
    .narrow.view-tasks #left {
        display: none;
    }
    .narrow.view-tasks #right {
        width: 1fr;
        display: block;
        border-left: none;
    }
    .narrow #detail {
        display: none;
    }

    #main-container {
        height: 1fr;
    }
    #left {
        height: 100%;
    }
    #right {
        height: 100%;
    }
    #chat {
        height: 1fr;
    }
    #input {
        dock: bottom;
    }
    #team {
        height: auto;
        padding: 0 1;
        border-bottom: solid $primary;
    }
    #tasks {
        height: 1fr;
    }

    /* Short Mode (< 20 rows) */
    .short #team {
        height: 1;
        padding: 0 1;
    }

    /* Ultra-short Mode (< 12 rows) */
    .ultra-short Header {
        display: none;
    }
    .ultra-short Footer {
        display: none;
    }
    .ultra-short #action-bar {
        padding: 0;
    }
    .ultra-short #input {
        border: none;
        padding: 0;
        margin: 0;
        height: 1;
    }

    /* Dialogs */
    TaskSheet, HelpModal {
        align: center middle;
    }
    #dialog {
        width: 96%;
        max-width: 80;
        height: 85%;
        background: $surface;
        border: thick $primary;
        padding: 1;
    }
    #dialog-title {
        text-style: bold;
        color: $text;
        border-bottom: solid $primary;
        padding-bottom: 1;
        margin-bottom: 1;
    }
    #dialog-content {
        height: 1fr;
    }
    #dialog-actions {
        height: auto;
        dock: bottom;
        align-horizontal: right;
        margin-top: 1;
    }
    #dialog-actions Button {
        min-width: 10;
        margin-left: 1;
    }
    """

    BINDINGS = [
        ("ctrl+q", "quit", "Quit"),
        ("ctrl+l", "clear", "Clear chat"),
        ("escape", "escape", "Blur / Back"),
        Binding("q", "quit", "Quit", show=False),
        Binding("c", "clear", "Clear", show=False),
        Binding("v", "toggle_view", "Toggle View", key_display="v/Tab"),
        Binding("tab", "toggle_view", "Toggle View", show=False, priority=True),
        Binding("i", "focus_input", "Focus Input", show=False),
        Binding("question_mark", "help", "Help", key_display="?"),
        Binding("?", "help", "Help", show=False),
    ]

    def __init__(self, backend, members: list[str], lead: str, backend_name: str, audit: bool = False, stats=None):
        super().__init__()
        self.members, self.lead = members, lead
        self.backend_name = backend_name
        self.audit = audit
        self.ascii_mode = is_ascii()
        self.sub_title = f"{backend_name} backend · lead: {lead} · audit: {'on' if audit else 'off'}"
        self.orch = Orchestrator(backend, members, lead, emit=self.on_team_event, audit=audit, stats=stats)
        self.tasks: dict[str, Task] = {}  # row key -> task, across all requests
        self.chat_history: list[tuple[str, str]] = []  # (who, text) for clean replay on resize
        self.lead_state = "idle"
        self.turn = asyncio.Lock()  # one request at a time; later ones queue
        self.round = 0
        self.is_narrow = False
        self.layout_width = 80
        self.active_tab = "chat"

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="action-bar"):
            with Horizontal(id="action-tabs"):
                yield Button(chat_tab_label(self.ascii_mode), id="btn-chat", classes="action-btn tab-btn -active-tab")
                yield Button(tasks_tab_label(self.ascii_mode), id="btn-tasks", classes="action-btn tab-btn")
            with Horizontal(id="action-tools"):
                yield Button("Clear", id="btn-clear", classes="action-btn tool-btn")
                yield Button("?", id="btn-help", classes="action-btn tool-btn")
                yield Button("Quit", id="btn-quit", classes="action-btn tool-btn")
        with Horizontal(id="main-container"):
            with Vertical(id="left"):
                placeholder = "Ask the team anything..." if self.ascii_mode else "Ask the team anything…"
                yield RichLog(id="chat", wrap=True, markup=True)
                yield Input(placeholder=placeholder, id="input")
            with Vertical(id="right"):
                yield Static(id="team")
                yield TaskTable(id="tasks", cursor_type="row")
                yield RichLog(id="detail", wrap=True)
        yield Footer()

    def on_mount(self) -> None:
        width = self.size.width if self.size.width > 0 else 80
        height = self.size.height if self.size.height > 0 else 24
        self.update_responsive_layout(width, height, force=True)
        self.switch_tab("chat")
        self.refresh_team()
        self.say("Hexmind", f"Team ready: {', '.join(self.members)}. Type a request; the lead splits it up.")
        self.query_one("#input").focus()

    def on_resize(self, event: events.Resize) -> None:
        self.update_responsive_layout(event.size.width, event.size.height)

    def update_responsive_layout(self, width: int, height: int, force: bool = False) -> None:
        was_narrow, was_width = self.is_narrow, self.layout_width
        self.is_narrow = width < 80
        self.layout_width = width
        is_short = height < 20
        is_ultra_short = height < 12

        if self.is_narrow:
            self.add_class("narrow")
            self.remove_class("wide")
        else:
            self.add_class("wide")
            self.remove_class("narrow")

        if is_short:
            self.add_class("short")
        else:
            self.remove_class("short")

        if is_ultra_short:
            self.add_class("ultra-short")
        else:
            self.remove_class("ultra-short")

        # Subtitle shortening on narrow screens (< 60 cols)
        if width < 60:
            lead_name = self.orch.name(self.lead)
            audit_str = "audit:on" if self.audit else "audit:off"
            self.sub_title = f"{self.backend_name} · {lead_name} · {audit_str}"
        else:
            audit_str = "on" if self.audit else "off"
            self.sub_title = f"{self.backend_name} backend · lead: {self.lead} · audit: {audit_str}"

        # Reconfigure table columns if breakpoint changed or on initial mount;
        # narrow title width tracks the screen so the table never scrolls sideways
        if force or was_narrow != self.is_narrow or (self.is_narrow and was_width != width):
            self.reconfigure_tasks_table()
        if not force and was_narrow != self.is_narrow:
            self.replay_chat()

        self.refresh_team()

    def switch_tab(self, tab: str) -> None:
        self.active_tab = tab
        btn_chat = self.query_one("#btn-chat", Button)
        btn_tasks = self.query_one("#btn-tasks", Button)
        if tab == "chat":
            self.remove_class("view-tasks")
            self.add_class("view-chat")
            btn_chat.add_class("-active-tab")
            btn_tasks.remove_class("-active-tab")
            self.query_one("#input", Input).focus()
        else:
            self.remove_class("view-chat")
            self.add_class("view-tasks")
            btn_tasks.add_class("-active-tab")
            btn_chat.remove_class("-active-tab")
            self.query_one("#tasks", TaskTable).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        btn_id = event.button.id
        if btn_id == "btn-chat":
            self.switch_tab("chat")
        elif btn_id == "btn-tasks":
            self.switch_tab("tasks")
        elif btn_id == "btn-clear":
            self.action_clear()
        elif btn_id == "btn-help":
            self.action_help()
        elif btn_id == "btn-quit":
            self.exit()

    def action_escape(self) -> None:
        if isinstance(self.screen, (TaskSheet, HelpModal)):
            self.screen.dismiss()
            return
        inp = self.query_one("#input", Input)
        if inp.has_focus:
            self.set_focus(None)

    def action_focus_input(self) -> None:
        if self.is_narrow and self.active_tab != "chat":
            self.switch_tab("chat")
        self.query_one("#input", Input).focus()

    def action_toggle_view(self) -> None:
        if isinstance(self.screen, ModalScreen):  # Tab is a priority binding; keep focus cycling in dialogs
            self.screen.focus_next()
            return
        if self.is_narrow:
            new_tab = "tasks" if self.active_tab == "chat" else "chat"
            self.switch_tab(new_tab)
        else:
            inp = self.query_one("#input", Input)
            tasks = self.query_one("#tasks", TaskTable)
            if inp.has_focus:
                tasks.focus()
            else:
                inp.focus()

    def action_help(self) -> None:
        if isinstance(self.screen, HelpModal):
            self.screen.dismiss()
        else:
            self.push_screen(HelpModal())

    # ---------- chat ----------
    def say(self, who: str, text: str) -> None:
        self.chat_history.append((who, text))
        self._write_chat_message(who, text)

    def _write_chat_message(self, who: str, text: str) -> None:
        chat = self.query_one("#chat", RichLog)
        if text.startswith("ESCALATION"):
            chat.write(Panel(Markdown(text), title=f"{self.orch.name(who)} · needs you", border_style="bold red"))
            chat.write("")
            return
        label = self.orch.name(who)
        chat.write(Text(label if label == who else f"{label} ({who})", style=AGENT_COLOR.get(who, "bold magenta")))
        chat.write(Markdown(text) if who != "you" else Text(text))
        chat.write("")

    def replay_chat(self) -> None:
        chat = self.query_one("#chat", RichLog)
        chat.clear()
        for who, text in self.chat_history:
            self._write_chat_message(who, text)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        event.input.value = ""
        if not text:
            return
        self.say("you", text)
        if self.turn.locked():
            sep = " -- " if self.ascii_mode else " — "
            self.say("Hexmind", f"_Team is busy{sep}queued, will start when the current request finishes._")
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
    def update_task_badge(self) -> None:
        pending_active = sum(1 for t in self.tasks.values() if t.status in ("pending", "running", "auditing", "revising"))
        btn = self.query_one("#btn-tasks", Button)
        btn.label = tasks_tab_label(self.ascii_mode, pending_active)

    def on_team_event(self, kind: str, data: dict) -> None:
        if kind == "message":
            self.say(data["from"], data["text"] or "_(no reply)_")
        elif kind == "status":
            self.lead_state = data["state"]
        elif kind == "plan":
            table = self.query_one("#tasks", TaskTable)
            for t in data["tasks"]:
                key = f"{self.round}.{t.id}"
                self.tasks[key] = t
                if self.is_narrow:
                    status_str = audit_cell(t, self.orch.name) or t.status
                    table.add_row(key, Text(status_str, style=STATUS_STYLE.get(t.status, "")), f"[{self.orch.name(t.agent)}] {t.title}", key=key)
                else:
                    table.add_row(key, self.orch.name(t.agent), t.status, audit_cell(t, self.orch.name), t.title, key=key)
            lines = [f"- **{t.id}** → {self.orch.name(t.agent)}: {t.title}" + (f" _(after {', '.join(t.depends_on)})_" if t.depends_on else "")
                     for t in data["tasks"]]
            self.say("Hexmind", "**Plan**\n" + "\n".join(lines))
            self.update_task_badge()
        elif kind == "task":
            t = data["task"]
            key = f"{self.round}.{t.id}"
            table = self.query_one("#tasks", TaskTable)
            if self.is_narrow:
                status_str = audit_cell(t, self.orch.name) or t.status
                table.update_cell(key, "status", Text(status_str, style=STATUS_STYLE.get(t.status, "")))
                table.update_cell(key, "title", f"[{self.orch.name(t.agent)}] {t.title}")
            else:
                table.update_cell(key, "status", Text(t.status, style=STATUS_STYLE.get(t.status, "")))
                table.update_cell(key, "audit", Text(audit_cell(t, self.orch.name), style="red" if getattr(t, "audit", "") == "disputed" else ""))
            if t.status in ("done", "failed"):
                first = t.output.strip().splitlines()[0][:200] if t.output.strip() else ""
                sep = " -- " if self.ascii_mode else " — "
                self.say(t.agent, f"**{t.id} {t.status}**{sep}{t.title}\n\n{first}")
            if not self.is_narrow and table.cursor_row is not None and table.is_valid_row_index(table.cursor_row):
                self.show_task(table.coordinate_to_cell_key((table.cursor_row, 0)).row_key.value)
            self.update_task_badge()
        self.refresh_team()

    def refresh_team(self) -> None:
        dot_busy = "*" if self.ascii_mode else "●"
        dot_idle = "." if self.ascii_mode else "○"

        if self.has_class("short"):
            busy_count = 0
            idle_count = 0
            for m in self.members:
                is_busy = (
                    any(t.agent == m and t.status in ("running", "revising") for t in self.tasks.values())
                    or any(getattr(t, "auditor", "") == m and t.status == "auditing" for t in self.tasks.values())
                )
                if is_busy or (m == self.lead and self.lead_state != "idle"):
                    busy_count += 1
                else:
                    idle_count += 1
            lead_name = self.orch.name(self.lead)
            summary = (
                f"[{AGENT_COLOR.get(self.lead, 'white')}]{dot_busy}[/] {busy_count} busy · "
                f"{dot_idle} {idle_count} idle · lead: {lead_name}"
            )
            self.query_one("#team", Static).update(summary)
            return

        lines = []
        for m in self.members:
            busy = [k for k, t in self.tasks.items() if t.agent == m and t.status in ("running", "revising")]
            auditing = [k for k, t in self.tasks.items() if getattr(t, "auditor", "") == m and t.status == "auditing"]
            parts = ([f"working: {', '.join(busy)}"] if busy else []) + ([f"auditing {', '.join(auditing)}"] if auditing else [])
            state = " · ".join(parts) or "idle"
            if m == self.lead and self.lead_state != "idle":
                state = self.lead_state + (f" · {state}" if busy else "")
            dot = dot_busy if state != "idle" else dot_idle
            lines.append(f"[{AGENT_COLOR.get(m, 'white')}]{dot} {self.orch.name(m)}[/]{f' [dim]({m})[/]' if m in self.orch.nicknames else ''}{' (lead)' if m == self.lead else ''}  [dim]{state}[/]")
        self.query_one("#team", Static).update("\n".join(lines))

    def reconfigure_tasks_table(self) -> None:
        table = self.query_one("#tasks", TaskTable)
        cursor = table.cursor_row
        table.clear(columns=True)
        if self.is_narrow:
            table.add_column("task", key="task", width=5)
            table.add_column("status", key="status", width=9)
            # full-width pane: task + status + 1-col cell padding each side + 2-col scrollbar
            table.add_column("title", key="title", width=max(8, self.layout_width - 5 - 9 - 6 - 2))
        else:
            table.add_column("task", key="task", width=5)
            table.add_column("agent", key="agent", width=8)
            table.add_column("status", key="status", width=9)
            table.add_column("audit", key="audit", width=12)
            table.add_column("title", key="title")

        for key, t in self.tasks.items():
            if self.is_narrow:
                status_str = audit_cell(t, self.orch.name) or t.status
                title_str = f"[{self.orch.name(t.agent)}] {t.title}"
                table.add_row(key, Text(status_str, style=STATUS_STYLE.get(t.status, "")), title_str, key=key)
            else:
                audit_str = audit_cell(t, self.orch.name)
                table.add_row(
                    key,
                    self.orch.name(t.agent),
                    Text(t.status, style=STATUS_STYLE.get(t.status, "")),
                    Text(audit_str, style="red" if getattr(t, "audit", "") == "disputed" else ""),
                    t.title,
                    key=key,
                )
        if cursor is not None and table.is_valid_row_index(cursor):
            table.move_cursor(row=cursor)

    # ---------- task detail ----------
    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if event.row_key is not None and not self.is_narrow:
            self.show_task(event.row_key.value)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        if event.row_key is not None:
            key = event.row_key.value
            if self.is_narrow:
                if isinstance(self.screen, TaskSheet):
                    return
                t = self.tasks.get(key)
                if t:
                    self.push_screen(TaskSheet(key, t, self.orch.name, self.ascii_mode))
            else:
                self.show_task(key)

    def show_task(self, key: str) -> None:
        t = self.tasks.get(key)
        detail = self.query_one("#detail", RichLog)
        detail.clear()
        if t:
            audit = audit_cell(t, self.orch.name)
            detail.write(Text(f"{key} · {self.orch.name(t.agent)} · {t.status}" + (f" · audit {audit}" if audit else ""), style="bold"))
            detail.write(Text(t.instructions, style="dim"))
            detail.write("")
            detail.write(Markdown(t.output) if t.output else Text("(no output yet)", style="dim"))

    def action_clear(self) -> None:
        self.chat_history.clear()
        self.query_one("#chat", RichLog).clear()

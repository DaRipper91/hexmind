"""The command palette: every room action behind one keystroke.

A room has two ways to act — ask it something, or change it. The first already has an input line.
The second (clear the transcript, toggle peer audit, switch the lead, open a file) was scattered
across buttons and menus, so anything that needed three clicks to reach had to be worth three
clicks. The palette is where the expensive-to-reach things live.

Design, in the order the decisions actually fell out:

* **The input line wins the prefix.** Typing `/` in the main input autocompletes a slash command;
  the palette exists for the verbs that have no slash form, so it must not fight the input line
  for the same keystrokes. It opens on `Ctrl+K` and closes on `Esc` or a click outside.
* **The label is the name, the description says what it does.** A palette is scanned, not read, so
  the list carries both and the selected row expands into the description rather than the user
  having to hover to find out what `/go` actually did.
* **Ranking is pure and tested without a widget.** `filter_commands` is the whole search, which
  means the ranking can be asserted directly instead of being "verified" by eye in a window.

The object names (`#palette`, `#paletteInput`, `#paletteList`) are the ones already styled in
`theme.stylesheet()`; this module is the widget those rules were written for. No colour literal
appears here — the QSS resolves every one of them.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Iterable, Sequence

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

#: How many rows the palette shows at once. Beyond this the list stops being scannable and starts
#: being a document, which is what the input line is for.
PALETTE_LIMIT = 20

#: Below this, a query is treated as "still typing" and the first commands are offered in their
#: natural order rather than a relevance order — ranking `"a"` against a dozen commands is noise.
MIN_QUERY = 2


@dataclass(frozen=True)
class Command:
    """One thing you can do from the palette.

    `action` is an opaque key the *host* dispatches; the palette never imports the room's methods
    or calls a backend. That is the same one-way rule the rest of `hexmind.qt` obeys, and it is
    what lets the palette be tested with three lines of pure data.
    """

    name: str
    hint: str = ""
    action: str = ""
    keywords: str = field(default="", compare=False)

    def haystack(self) -> str:
        return f"{self.name} {self.hint} {self.keywords}".lower()


def _rank(command: Command, needle: str) -> int | None:
    """Match quality, lower is better, `None` means no match at all.

    Ordered by how much the match promises: a command *named* what you typed is what you meant, and
    a command that merely mentions the word in its description is a guess. Ties break on name
    length, so a short exact-ish name sorts above a long one that happens to contain it.
    """
    name = command.name.lower()
    if name == needle:
        return 0
    if name.startswith(needle):
        return 1
    if needle in name:
        return 2
    if needle in command.hint.lower():
        return 3
    if needle in command.keywords.lower():
        return 4
    return None


def filter_commands(commands: Sequence[Command], query: str, limit: int = PALETTE_LIMIT) -> list[Command]:
    """The search. Pure — no widget, no Qt, no room.

    An empty or too-short query returns `commands` unchanged (truncated) so the palette is useful
    the instant it opens: the common actions are already listed, and the user can arrow down.
    """
    needle = (query or "").strip().lower()
    if len(needle) < MIN_QUERY:
        return list(commands)[:limit]

    scored: list[tuple[int, int, str, Command]] = []
    for command in commands:
        rank = _rank(command, needle)
        if rank is None:
            continue
        scored.append((rank, len(command.name), command.name.lower(), command))
    scored.sort(key=lambda entry: entry[:3])
    return [entry[3] for entry in scored[:limit]]


def as_commands(rows: Iterable[tuple[str, str, str]]) -> list[Command]:
    """`(name, hint, action)` triples into `Command`s. Convenience for the host's call site."""
    return [Command(name, hint, action) for name, hint, action in rows]


class CommandPalette(QDialog):
    """The overlay. Opens on `Ctrl+K`, filters as you type, runs the highlighted action on `Enter`.

    It emits `chosen(str)` with the action key rather than calling anything itself. The host
    decides what an action means, which is what keeps this file free of room logic — and what lets
    a test assert that `Enter` on a filtered row emits the right key without a live room.
    """

    chosen = Signal(str)

    def __init__(self, commands: Sequence[Command], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._commands = list(commands)
        self.setObjectName("palette")
        self.setWindowTitle("Command palette")
        self.setModal(True)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        self.input = QLineEdit()
        self.input.setObjectName("paletteInput")
        self.input.setAccessibleName("Command")
        self.input.setPlaceholderText("Type a command…")
        self.input.textChanged.connect(self._refresh)
        self.input.returnPressed.connect(self._accept_current)

        self.list = QListWidget()
        self.list.setObjectName("paletteList")
        self.list.setAccessibleName("Matching commands")
        self.list.itemActivated.connect(self._accept_item)
        self.list.itemClicked.connect(self._accept_item)

        self.hint = QLabel("")
        self.hint.setAccessibleName("Command description")
        self.hint.setWordWrap(True)

        body = QVBoxLayout(self)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        body.addWidget(self.input)
        body.addWidget(self.list)
        body.addWidget(self.hint)

        self._shortcut = QShortcut(QKeySequence("Ctrl+K"), self)
        self._shortcut.activated.connect(self.toggle)
        # Escape is the dialog default, but only once it has focus; binding it on the window means
        # it works whether the focus is in the input or the list.
        self.installEventFilter(self)

        self._refresh("")

    # ---------- the event filter ----------
    def eventFilter(self, obj: QWidget, event) -> bool:
        if obj is self and event.type() == event.Type.KeyPress and event.key() == Qt.Key.Key_Escape:
            self.close()
            return True
        return super().eventFilter(obj, event)

    # ---------- behaviour ----------
    def toggle(self) -> None:
        if self.isVisible():
            self.close()
        else:
            self.open_palette()

    def open_palette(self) -> None:
        """Show over the host window, centred, focused on the input, with a clean slate."""
        self.input.clear()
        self._refresh("")
        self.show()
        self._size_and_centre()
        self.input.setFocus()
        self.raise_()
        self.activateWindow()

    def _size_and_centre(self) -> None:
        """Size to the contents, then centre on the host if there is one.

        Sizing is unconditional because a parentless palette — the standalone app — would
        otherwise keep Qt's default 256px and show a wrapped, unreadable list. Only the centring
        needs a parent, so only the centring is conditional.
        """
        # A palette sized to its contents, centred on its host, reads as an overlay of that window
        # rather than a dialog that happens to be nearby. Width is capped so a long description
        # cannot make it span a 4K display.
        self.adjustSize()
        width = min(max(self.sizeHint().width(), 420), 720)
        self.resize(width, self.sizeHint().height())
        parent = self.parentWidget()
        if parent is None:
            centre = self.screen().availableGeometry().center() if self.screen() else None
        else:
            centre = parent.mapToGlobal(parent.rect().center())
        if centre is None:
            return
        self.move(*_clamp_origin(self, centre.x() - self.width() // 2, centre.y() - self.height() // 2))

    def set_commands(self, commands: Sequence[Command]) -> None:
        """Swap the vocabulary — the roster changes, so the per-agent commands change with it."""
        self._commands = list(commands)
        self._refresh(self.input.text())

    def _refresh(self, query: str) -> None:
        self._matches = filter_commands(self._commands, query)
        self.list.clear()
        for command in self._matches:
            item = QListWidgetItem(command.name)
            item.setData(Qt.ItemDataRole.UserRole, command.action or command.name)
            if command.hint:
                item.setToolTip(command.hint)
            self.list.addItem(item)
        if self.list.count():
            self.list.setCurrentRow(0)
        self._update_hint()

    def _update_hint(self) -> None:
        item = self.list.currentItem()
        if item is None:
            self.hint.setText("")
            return
        for command in self._matches:
            if (command.action or command.name) == item.data(Qt.ItemDataRole.UserRole):
                self.hint.setText(command.hint)
                return
        self.hint.setText(item.toolTip() or "")

    def _accept_current(self) -> None:
        item = self.list.currentItem()
        if item is not None:
            self._accept_item(item)

    def _accept_item(self, item: QListWidgetItem) -> None:
        if item is None:
            return
        action = str(item.data(Qt.ItemDataRole.UserRole) or "")
        self.close()
        if action:
            self.chosen.emit(action)


def _clamp_origin(palette: QWidget, x: int, y: int) -> tuple[int, int]:
    """Keep the palette's top-left on the screen it opens on.

    A palette that opens off the bottom edge is a palette the user cannot see, and a window whose
    bottom-right corner is past the screen edge is exactly where that tends to happen. Clamped
    against the *current* screen rather than the virtual desktop, so a palette never lands in the
    gap between two monitors.
    """
    area = palette.screen().availableGeometry() if palette.screen() else None
    if area is None:
        return x, y
    x = min(max(x, area.left()), max(area.left(), area.right() - palette.width() + 1))
    y = min(max(y, area.top()), max(area.top(), area.bottom() - palette.height() + 1))
    return x, y


def palette_commands(room: "PaletteHost") -> list[Command]:  # noqa: F821 - duck-typed on purpose
    """The vocabulary for a live room: the room's own actions plus one entry per teammate.

    Written against a duck-typed host rather than a `HexmindWidget` import so this function can be
    tested without building a room, and so the palette does not depend on the room module (which
    depends on the palette).
    """
    commands: list[Command] = [
        Command("clear transcript", "Wipe the conversation view (Ctrl+L)", "clear"),
        Command("toggle peer audit", "Turn the runner-up audit loop on or off", "audit"),
        Command("refresh team", "Re-read the roster from the room", "refresh"),
    ]
    for name in list(getattr(room, "members", None) or []):
        commands.append(
            Command(f"lead: {name}", f"Make {name} the lead — it plans and writes the answer",
                    f"lead:{name}", keywords=name)
        )
    return commands


def install_palette(room: QWidget) -> CommandPalette | None:
    """Attach a palette to a room widget, if the module can be imported.

    Mirrors the lazy-try/except wiring the rest of `hexmind.qt` uses: presentation that cannot
    load must not take the room down with it.
    """
    try:
        palette = CommandPalette(palette_commands(room), room)
    except Exception:  # pragma: no cover - presentation only
        return None

    def _dispatch(action: str) -> None:
        if action == "clear":
            clear = getattr(room, "_clear_transcript", None)
            if callable(clear):
                clear()
        elif action == "audit":
            box = getattr(room, "auditBox", None)
            if box is not None:
                box.toggle()
        elif action == "refresh":
            refresh = getattr(room, "refresh_team", None)
            if callable(refresh):
                refresh()
        elif action.startswith("lead:"):
            target = action.split(":", 1)[1]
            box = getattr(room, "leadBox", None)
            if box is not None:
                box.setCurrentText(target)

    palette.chosen.connect(_dispatch)
    palette.show()
    palette.close()  # constructed open so the shortcut is live; the user opens it with Ctrl+K
    return palette


__all__ = [
    "Command",
    "CommandPalette",
    "PALETTE_LIMIT",
    "MIN_QUERY",
    "as_commands",
    "filter_commands",
    "install_palette",
    "palette_commands",
]

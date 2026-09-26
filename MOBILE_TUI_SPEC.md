# Mobile & Touch Terminal Design Specification: Hexmind

> **Target Platform:** Google Pixel 10 Pro running either Termux (native Android userspace) or Android Linux Terminal (Debian VM via AVF / crosvm / xterm.js).  
> **Target Viewports:**  
> - Mobile Portrait: 40–60 columns × 20–35 rows (keyboard closed), 40–60 columns × 12–18 rows (keyboard open).  
> - Mobile Landscape: 90–120 columns × 18–24 rows (keyboard closed), 90–120 columns × 4–8 rows (keyboard open).  
> - Absolute Minimum Supported Viewport: **40 columns × 15 rows**.  
> **Framework:** Python 3.11+ with [Textual](https://textual.textualize.io/) (`textual>=0.80`) and Rich.

---

## 1. Audit of Current Layout, Widgets, Keybindings & Touch Support

Hexmind's TUI is implemented in [`hexmind/tui.py`](file:///data/data/com.termux/files/home/Projects/hexmind/hexmind/tui.py). While cleanly constructed for wide desktop monitors (>= 80 columns × 24 rows), the interface suffers critical layout breakdowns, unreadable content squashing, chord-binding barriers, and touch inaccessibility on mobile phone screens.

### 1.1 Current Problems

#### Fixed Horizontal Split Ratio (`#left` 2fr vs `#right` 1fr)
- **Location:** [`hexmind/tui.py:30-31`](file:///data/data/com.termux/files/home/Projects/hexmind/hexmind/tui.py#L30-L31), [`hexmind/tui.py:51-59`](file:///data/data/com.termux/files/home/Projects/hexmind/hexmind/tui.py#L51-L59)
- **Problem:** `Horizontal()` partitions the screen into `#left` (2fr) and `#right` (1fr, `border-left: solid $primary`). In a standard Pixel portrait terminal (e.g., 48 columns):
  - `#left` receives ~31 columns.
  - `#right` receives only ~16 columns (15 usable columns minus border).
  - `#team` (`Static`, [`line 56`](file:///data/data/com.termux/files/home/Projects/hexmind/hexmind/tui.py#L56)) wraps each agent line into 3–4 fragmented, illegible rows.
  - `#tasks` (`DataTable`, [`line 57`](file:///data/data/com.termux/files/home/Projects/hexmind/hexmind/tui.py#L57)) attempts to render 5 columns: `task`, `agent`, `status`, `audit`, and `title`. In 15 columns, only the first column and half of the second are visible; the rest is completely clipped offscreen.
  - `#detail` (`RichLog`, [`line 58`](file:///data/data/com.termux/files/home/Projects/hexmind/hexmind/tui.py#L58)) receives 15 columns, rendering task markdown output as a tall, 1-to-2-words-per-line vertical sliver.
  - `#chat` (`RichLog`, [`line 53`](file:///data/data/com.termux/files/home/Projects/hexmind/hexmind/tui.py#L53)) receives ~31 columns, severely truncating code blocks, bullet lists, and escalation panels.

#### Vertical Stack Collapse under Soft Keyboard
- **Location:** [`hexmind/tui.py:32-35`](file:///data/data/com.termux/files/home/Projects/hexmind/hexmind/tui.py#L32-L35)
- **Problem:** When the on-screen keyboard (Gboard) opens, available rows drop to 12–18 in portrait (and 4–8 in landscape).
  - `#team` has `height: auto` ([`line 33`](file:///data/data/com.termux/files/home/Projects/hexmind/hexmind/tui.py#L33)), consuming 4–6 rows depending on team size and wrapping.
  - Together with `Header` (1 row), `Footer` (1 row), and `#input` (3 rows with borders and padding), remaining height for `#tasks` (1fr) and `#detail` (1fr) collapses to 0–2 rows each. Neither can display content or be scrolled.
  - In landscape with keyboard (4–8 rows), vertical overflow pushes the `#input` widget completely offscreen, preventing user input.

#### DataTable Column Overload
- **Location:** [`hexmind/tui.py:63-64`](file:///data/data/com.termux/files/home/Projects/hexmind/hexmind/tui.py#L63-L64), [`hexmind/tui.py:113`](file:///data/data/com.termux/files/home/Projects/hexmind/hexmind/tui.py#L113)
- **Problem:** Five columns (`task`, `agent`, `status`, `audit`, `title`) are unconditionally registered. Even if `#right` spanned 100% of a 48-column screen, displaying 5 columns with cell borders and padding requires at least 65 columns (`task`: 5, `agent`: 8, `status`: 9, `audit`: 12, `title`: 25). On mobile portrait, the table forces horizontal scrolling or truncates essential task descriptions.

#### Header Subtitle & Placeholder Truncation
- **Location:** [`hexmind/tui.py:42`](file:///data/data/com.termux/files/home/Projects/hexmind/hexmind/tui.py#L42), [`hexmind/tui.py:54`](file:///data/data/com.termux/files/home/Projects/hexmind/hexmind/tui.py#L54)
- **Problem:**
  - `self.sub_title = f"{backend_name} backend · lead: {lead} · audit: {'on' if audit else 'off'}"` is 45–55 characters long, which collides with or truncates the title `"Hexmind"` on 40–50 column displays.
  - `placeholder="Ask the team anything…"` (24 characters) clips inside the cramped `#left` container when keyboard opens.

#### Keybinding & Focus Trapping Friction
- **Location:** [`hexmind/tui.py:37`](file:///data/data/com.termux/files/home/Projects/hexmind/hexmind/tui.py#L37), [`hexmind/tui.py:67`](file:///data/data/com.termux/files/home/Projects/hexmind/hexmind/tui.py#L67)
- **Problem:**
  - `BINDINGS = [("ctrl+q", "quit", "Quit"), ("ctrl+l", "clear", "Clear chat")]` exclusively uses `Ctrl` chords. Standard Android virtual keyboards (Gboard, Samsung Keyboard) have no `Ctrl` key. In Termux, users must tap the virtual extra-keys bar (`CTRL`), then tap the letter. In the Debian VM (Android Linux Terminal via AVF / crosvm / xterm.js), virtual modifier keys are in a separate toolbar and often trigger browser/webview shortcuts.
  - Focus trap: `self.query_one("#input").focus()` focuses the text input immediately on mount. While focused, every alphanumeric keypress is consumed as typed text. There is no binding for `Escape` to blur `#input`. Touch-only or keyboard-only users cannot navigate away from `#input` to scroll chat or inspect tasks.
  - Zero single-key navigation or help screen (`?` or `F1`).

#### Small / Missing Mouse and Tap Targets
- **Problem:**
  - There are zero on-screen buttons, tabs, or clickable badges for primary actions (`Quit`, `Clear`, `Help`).
  - Textual enables xterm mouse reporting (mode 1000/1002/1006) by default. However, tapping a row in `#tasks` inside a 15-column pane frequently triggers adjacent row selection due to high DPI (~440 dpi, ~18px cell height).
  - `#detail` updates only when a row is highlighted (`on_data_table_row_highlighted`, [`line 144`](file:///data/data/com.termux/files/home/Projects/hexmind/hexmind/tui.py#L144)), but finger drags inside a 15-column pane easily trigger parent container scrolling.

---

## 2. Responsive Breakpoints & Layout Collapse

### 2.1 Viewport Breakpoints

| Breakpoint Name | Width / Height | Mode / Behavior |
|---|---|---|
| **Wide** | Width >= 80 cols | Desktop dual-column layout (`#left` 2fr, `#right` 1fr). |
| **Narrow** | Width < 80 cols | Single-column tabbed layout: `[💬 Chat]` vs `[📋 Tasks]`. |
| **Short** | Height < 20 rows | Compact `#team` to 1 row; maximize `#tasks` or `#chat`. |
| **Ultra-short** | Height < 12 rows | Hide Header/Footer; 1-row input; maximum visible content. |

### 2.2 Narrow Mode Collapse: Tabbed Architecture

In Narrow Mode (< 80 columns), replace the side-by-side split with a two-tab view switched via an on-screen Touch Tab Bar:

```
+-------------------------------------------------------+
| Hexmind · claude                                    |  <- Header (compact)
+-------------------------------------------------------+
| [ 💬 Chat ]  [ 📋 Tasks (3) ]  |  [Clear]  [Quit]  [?]  |  <- Touch Action Bar (2 rows)
+-------------------------------------------------------+
| (Active Tab: Chat View)                               |
| claude: I have broken down the task into 3 steps.    |
| agy: Working on step 1...                            |
|                                                       |
|                                                       |
+-------------------------------------------------------+
| > Ask the team anything...                            |  <- Input (full width)
+-------------------------------------------------------+
```

1. **Tab 1: `[ 💬 Chat ]` (Active by default):**
   - Full-width `#chat` (`RichLog`, `wrap=True`) and bottom full-width `#input`.
   - Markdown messages, agent color tags, and escalation panels take advantage of all 40–60 columns.
   - On terminal resize, replay chat history with explicit current width to prevent mis-wrapped lines.
2. **Tab 2: `[ 📋 Tasks ]`:**
   - Full-width `#team` status summary.
   - Full-width `#tasks` (`DataTable`).
   - `#detail` is removed from the inline split and presented as a full-screen or 85%-height **Task Detail Modal Sheet** (`TaskSheet`) upon tapping/selecting a task row.

### 2.3 Soft Keyboard & Short Viewport Adaptation (< 20 rows)

When the keyboard opens (12–18 rows in portrait, 4–8 rows in landscape):
- In **Tasks View:**
  - Collapse `#team` from multi-line static text to a single summary line:
    `● 2 busy · ○ 1 idle · lead: claude`
  - Allocates maximum vertical space to `#tasks` so at least 5–7 rows remain visible.
- In **Chat View:**
  - `#chat` claims all space above the 1-row `#input`.
  - When rows < 12 (Landscape with keyboard):
    - Hide `Header` and `Footer` (`display: none;`).
    - Compress `#input` to 1 row without margin.

### 2.4 Responsive DataTable Columns (< 80 columns)

Dynamically adjust columns based on available width:
- **Wide Mode (>= 80 cols):** Full 5 columns: `task` (5), `agent` (8), `status` (9), `audit` (12), `title` (flex).
- **Narrow Mode (< 80 cols):** Compress to 3 columns:
  - `task` (width: 5): e.g., `1.a`
  - `status` (width: 8): e.g., `done`, `run`, `fail`, `rev`, `pass·agy`
  - `title` (flex: remaining width): includes agent nickname badge, e.g., `[agy] Implement backend`
- Column widths are explicitly recomputed and assigned without horizontal overflow so horizontal scrollbars never appear.

---

## 3. Mouse, Tap Events & Touch Action Bar

### 3.1 Touch Action Bar & Minimum Hit Targets

Termux supports standard xterm mouse reporting (SGR 1006 / mode 1000/1002). Mobile touch taps are delivered as mouse press/release events.

To guarantee touch precision on high-DPI smartphone screens (~440 dpi):
- Minimum tap target height: **2 terminal rows** (or 1 row with generous horizontal padding, minimum 6–8 characters wide).
- Introduce a dedicated, persistent Touch Action Bar immediately below the Header:
  - `[ 💬 Chat ]`: Switches to Chat tab, focuses `#input`.
  - `[ 📋 Tasks ]`: Switches to Tasks tab, displays badge count of active/pending tasks.
  - `[Clear]`: Clears `#chat` log (`action_clear`).
  - `[Quit]`: Exits application (`action_quit`).
  - `[?]`: Opens mobile Help modal.
- Each button uses Textual's `Button` or custom `Static` responding to `on_click` with visible hover/active styling.

### 3.2 Single-Tap Task Selection & Task Detail Sheet

- **Single-Tap Selection:** Implement `TaskTable(DataTable)` subclass. On mouse tap / row click, immediately highlight the row and emit `RowSelected` to open the detail sheet. (Prevent double-event dispatch by suppressing redundant event cascading).
- **Task Detail Sheet (`TaskSheet` ModalScreen):**
  - Displays: Task ID, Agent, Status, Audit results, Instructions, and full Task Output.
  - Content rendered inside a `VerticalScroll` with Rich Markdown.
  - Includes prominent, tappable buttons at the bottom:
    - `[Close]`: Dismisses modal and returns to `#tasks`.
    - `[Copy Output]`: Copies task output to system clipboard using OSC 52.

### 3.3 Touch Drag & Wheel Scrolling

- `#chat`, `#tasks`, and `TaskSheet` scrollable areas must support touch drag and wheel events.
- In `#chat`, auto-scroll follows new incoming messages while user is at the bottom; if user scrolls up via touch drag, pause auto-scroll until scrolled back to the bottom.

---

## 4. Single-Key & Tappable Alternatives for Chords

### 4.1 Keybinding Mapping Matrix

| Action | Current Desktop Chord | Single-Key Mobile Alternative | Tappable Touch Target |
|---|---|---|---|
| **Quit App** | `ctrl+q` | `q` (when input blurred) | Tap `[Quit]` button on Action Bar |
| **Clear Chat** | `ctrl+l` | `c` (when input blurred) | Tap `[Clear]` button on Action Bar |
| **Blur Input** | *(None)* | `escape` | Tap outside input or on Action Bar |
| **Focus Input** | Mouse click | `i` or `Enter` (from Chat tab) | Tap `#input` widget |
| **Toggle View** | *(None)* | `v` or `Tab` | Tap `[ 💬 Chat ]` or `[ 📋 Tasks ]` |
| **Open Task Detail**| Row highlight | `Enter` or `Space` on row | Tap task row in `TaskTable` |
| **Close Detail / Help**| *(None)* | `escape` or `q` | Tap `[Close]` button |
| **Mobile Help** | *(None)* | `?` (when input blurred) | Tap `[?]` button on Action Bar |
| **Scroll Chat / List** | PageUp / PageDown | `j` / `k` or `Down` / `Up` | Touch drag or mouse wheel |

### 4.2 Note on Termux Extra-Keys Row

Termux provides a configurable virtual extra-keys bar (`~/.termux/termux.properties`), typically populated with `ESC`, `TAB`, `CTRL`, `ALT`, `UP`, `DOWN`, `LEFT`, `RIGHT`. 
- **However, Hexmind must NOT rely on the extra-keys row being present or configured:**
  1. Users often use third-party keyboards (e.g. Gboard) or run inside the Android Linux Terminal (Debian VM via AVF / crosvm / xterm.js) where extra-keys rows are absent, cramped, or intercepted by the OS.
  2. Typing chords like `Ctrl+Q` requires two separate taps on high-latency virtual modifier keys.
  3. Every chord must have a single-key shortcut (accessible when `#input` is blurred via `Esc`) AND a visible, tappable button on screen.

---

## 5. Readable Contrast & Glyph Integrity

### 5.1 Contrast & Theme Compatibility
- Ensure all text and status colors satisfy WCAG AA contrast (minimum 4.5:1 ratio against terminal background):
  - Agent nicknames: `claude` (orange1 / #d97706), `agy` (cyan / #06b6d4), `codex` (green / #10b981), `jules` (magenta / #d946ef), `qwen` (yellow / #eab308).
  - Status indicators: `running` (yellow), `done` (green), `failed` (bright red), `auditing` (magenta).
  - Textual panels and dialog borders must use `$primary` and `$surface` tokens to adapt to dark/light terminal themes.

### 5.2 Glyph Integrity & ASCII Fallback Mode
- Avoid exotic, multi-byte Unicode or emoji characters that trigger double-width cell calculation discrepancies in `xterm.js` or `Termux`:
  - Replace ambiguous characters with standard single-cell symbols.
- Support `FORCE_ASCII=1` or `NO_COLOR=1` environment variables:
  - Status indicators: replace `●` (busy) and `○` (idle) with `*` and `.`.
  - Replace typographical em-dashes `—` with standard `--`.
  - Replace typographical ellipsis `…` with `...`.

---

## 6. Concrete, Prioritized Implementation Plan

### Priority 1: High (Essential for Mobile Usability)

#### P1.1: Responsive Layout Breakpoints & View Modes
- **File:** [`hexmind/tui.py`](file:///data/data/com.termux/files/home/Projects/hexmind/hexmind/tui.py)
- **Functions/Methods:** `HexmindApp.compose()`, `HexmindApp.on_resize()`, CSS definitions.
- **Changes:**
  - Add CSS classes `.narrow` (< 80 cols), `.wide` (>= 80 cols), `.short` (< 20 rows), `.view-chat`, and `.view-tasks`.
  - Implement `on_resize(event: Resize)` to toggle classes dynamically.
  - In `.narrow`, switch `#left` and `#right` between `display: none` and `display: block` depending on the active tab.

#### P1.2: Touch Tab Bar & Action Bar
- **File:** [`hexmind/tui.py`](file:///data/data/com.termux/files/home/Projects/hexmind/hexmind/tui.py)
- **Functions/Methods:** `HexmindApp.compose()`, new `TabBar(Widget)` or action buttons.
- **Changes:**
  - Add a 2-row touch action bar below Header with buttons for Chat, Tasks, Clear, Quit, Help.
  - Connect click handlers to tab switching and app actions.

#### P1.3: Escape-to-Blur & Single-Key Navigation
- **File:** [`hexmind/tui.py`](file:///data/data/com.termux/files/home/Projects/hexmind/hexmind/tui.py)
- **Functions/Methods:** `HexmindApp.BINDINGS`, `HexmindApp.action_blur()`, `HexmindApp.action_toggle_view()`.
- **Changes:**
  - Bind `escape` to blur `#input` (`self.query_one("#input").blur()`).
  - Add single-key bindings (`q`, `c`, `v`, `i`, `?`) active when `#input` is blurred.

#### P1.4: Mobile Task Detail Sheet (`TaskSheet`)
- **File:** [`hexmind/tui.py`](file:///data/data/com.termux/files/home/Projects/hexmind/hexmind/tui.py)
- **Classes/Methods:** New `TaskSheet(ModalScreen)`, `TaskTable(DataTable)`.
- **Changes:**
  - In narrow mode, row tap/selection pushes `TaskSheet` modal with full task details, markdown output, and tappable `[Close]` button.

---

### Priority 2: Medium (Layout Polish & Content Fitting)

#### P2.1: Dynamic DataTable Column Formatting
- **File:** [`hexmind/tui.py`](file:///data/data/com.termux/files/home/Projects/hexmind/hexmind/tui.py)
- **Functions/Methods:** `HexmindApp.on_mount()`, `HexmindApp.refresh_tasks_table()`.
- **Changes:**
  - In narrow mode, configure table with 3 columns (`task`, `status`, `title`), embedding agent into title badge and audit into status.
  - Dynamically recalculate column widths on resize so no horizontal scroll appears.

#### P2.2: Compact Header & Status Formatting
- **File:** [`hexmind/tui.py`](file:///data/data/com.termux/files/home/Projects/hexmind/hexmind/tui.py)
- **Functions/Methods:** `HexmindApp.refresh_team()`, `HexmindApp.__init__()`.
- **Changes:**
  - Shorten subtitle on narrow widths (< 60 cols).
  - In `.short` mode, collapse `#team` into a 1-row summary line.

#### P2.3: Chat History Replay on Width Resize
- **File:** [`hexmind/tui.py`](file:///data/data/com.termux/files/home/Projects/hexmind/hexmind/tui.py)
- **Functions/Methods:** `HexmindApp.on_resize()`, `HexmindApp.say()`.
- **Changes:**
  - Store chat message records and re-render `#chat` upon width change so markdown paragraphs and code fences re-wrap cleanly.

---

### Priority 3: Low (Terminal Polish & Clipboard Integration)

#### P3.1: OSC 52 & Termux Clipboard Helper
- **File:** `hexmind/platform.py` *(new)*
- **Functions:** `copy_to_clipboard(text: str)`.
- **Changes:**
  - Emit OSC 52 escape sequences (`\033]52;c;<base64>\007`) with fallback to `termux-clipboard-set`.

#### P3.2: ASCII and High-Contrast Fallback Mode
- **File:** [`hexmind/tui.py`](file:///data/data/com.termux/files/home/Projects/hexmind/hexmind/tui.py), `hexmind/platform.py`
- **Functions:** `is_ascii()`.
- **Changes:**
  - Detect `FORCE_ASCII` and `NO_COLOR` to substitute bullets with `*` / `.`.

#### P3.3: Mobile Acceptance Test Suite
- **File:** `tests/test_mobile_tui.py` *(new)*
- **Changes:**
  - Implement pilot test suite verifying 40×20, 60×30, and 120×40 viewports: zero horizontal overflow, tab switching, tap selection, and key navigation.

# Mobile & Touch Terminal Design Specification: Hexmind

> **Target Platform:** Google Pixel 10 Pro running Termux (native Android userspace) or Android Linux Terminal (Debian VM via AVF / crosvm / xterm.js).  
> **Target Viewports:**  
> - Mobile Portrait: 40–60 columns × 36–48 rows (keyboard closed), 40–60 columns × 12–18 rows (keyboard open).  
> - Mobile Landscape: 90–120 columns × 18–24 rows (keyboard closed), 90–120 columns × 4–8 rows (keyboard open).  
> - Absolute Minimum Supported Viewport: **40 columns × 15 rows**.  
> **Framework:** Python 3.12+ with [Textual](https://textual.textualize.io/) (`textual>=0.80`).

---

## 1. Audit of Current Layout, Widgets, Keybindings & Touch Support

Hexmind's current TUI implementation lives entirely in `hexmind/tui.py`. While functional on standard desktop terminals (>= 80 columns × 24 rows), the interface fails or severely degrades on narrow, touch-driven mobile screens.

### 1.1 Layout & Widget Sizing Issues

1. **Fixed Horizontal Split Ratio (`#left` 2fr vs `#right` 1fr)**
   - **Location:** [`hexmind/tui.py:30-31`](file:///data/data/com.termux/files/home/Projects/hexmind/hexmind/tui.py#L30-L31), [`hexmind/tui.py:51-59`](file:///data/data/com.termux/files/home/Projects/hexmind/hexmind/tui.py#L51-L59)
   - **Problem:** At 48 columns (typical Pixel portrait terminal), `#left` receives ~31 columns and `#right` receives only ~16 columns (minus 1 for the vertical border). Inside a 15-column width:
     - `#team` ([`hexmind/tui.py:56`](file:///data/data/com.termux/files/home/Projects/hexmind/hexmind/tui.py#L56)) wraps each member entry into 3–4 fragmented lines.
     - `#tasks` DataTable ([`hexmind/tui.py:57`](file:///data/data/com.termux/files/home/Projects/hexmind/hexmind/tui.py#L57)) attempts to render 5 columns (`task`, `agent`, `status`, `audit`, `title`). Only the first column and half of the second column are visible; the rest is clipped or forces horizontal scrolling.
     - `#detail` RichLog ([`hexmind/tui.py:58`](file:///data/data/com.termux/files/home/Projects/hexmind/hexmind/tui.py#L58)) receives 15 columns, rendering Markdown output as a tall, 1-word-per-line vertical sliver.
     - `#left` (chat) receives only ~31 columns, severely truncating code snippets, bullet lists, and escalation panels.

2. **Vertical Stack Collapse under Soft Keyboard**
   - **Location:** [`hexmind/tui.py:32-35`](file:///data/data/com.termux/files/home/Projects/hexmind/hexmind/tui.py#L32-L35)
   - **Problem:** When the on-screen keyboard (Gboard) opens, available rows drop to 12–18 in portrait (and 4–8 in landscape).
     - `#team` has `height: auto` ([`line 33`](file:///data/data/com.termux/files/home/Projects/hexmind/hexmind/tui.py#L33)), which occupies 4–6 rows depending on team size and wrapping.
     - Together with Header (1 row), Footer (1 row), and input borders, the remaining height for `#tasks` (1fr) and `#detail` (1fr) drops to 1–2 rows each. Neither widget can display content or scroll meaningfully.
     - In landscape with keyboard (4–8 rows), the app attempts to render Header, Footer, Input, Team, Tasks, and Detail simultaneously, overflowing the screen and clipping the input field entirely.

3. **DataTable Column Definition Overload**
   - **Location:** [`hexmind/tui.py:63-64`](file:///data/data/com.termux/files/home/Projects/hexmind/hexmind/tui.py#L63-L64), [`hexmind/tui.py:113`](file:///data/data/com.termux/files/home/Projects/hexmind/hexmind/tui.py#L113)
   - **Problem:** Columns are added unconditionally:
     ```python
     for col in ("task", "agent", "status", "audit", "title"):
         table.add_column(col, key=col)
     ```
     At 40–60 columns, 5 columns cannot fit even if `#right` occupied 100% width. Minimum readable widths (`task`: 5, `agent`: 8, `status`: 9, `audit`: 12, `title`: 25) require at least 65 columns including cell borders and padding.

4. **Header Subtitle Truncation**
   - **Location:** [`hexmind/tui.py:42`](file:///data/data/com.termux/files/home/Projects/hexmind/hexmind/tui.py#L42)
   - **Problem:** `self.sub_title = f"{backend_name} backend · lead: {lead} · audit: {'on' if audit else 'off'}"` is 45–55 characters long. On 40–50 column displays, Textual's Header truncates this string or overlaps with the title `"Hexmind"`.

5. **Input Field Placeholder Overflow**
   - **Location:** [`hexmind/tui.py:54`](file:///data/data/com.termux/files/home/Projects/hexmind/hexmind/tui.py#L54)
   - **Problem:** `placeholder="Ask the team anything…"` (24 characters) fits in 40 columns when full-width, but in the current 2fr split (~27 usable columns inside borders and margins), it leaves barely any room before user input scrolls horizontally.

---

### 1.2 Keybindings & Soft Keyboard Friction

1. **Reliance on Multi-Key Modifier Chords**
   - **Location:** [`hexmind/tui.py:37`](file:///data/data/com.termux/files/home/Projects/hexmind/hexmind/tui.py#L37)
     ```python
     BINDINGS = [("ctrl+q", "quit", "Quit"), ("ctrl+l", "clear", "Clear chat")]
     ```
   - **Problem:** Both bindings require `Ctrl` (`ctrl+q`, `ctrl+l`). On mobile touchscreens:
     - Gboard and standard virtual keyboards have no `Ctrl` key.
     - In Termux, the user must reach for the virtual extra-keys bar (`CTRL` key), then tap `q` or `l`.
     - In the Pixel Debian VM (Android Linux Terminal), virtual modifier keys are located on a separate toolbar and often trigger browser/webview shortcuts.
   - There are zero single-key alternatives for quitting or clearing.

2. **Input Focus Trapping**
   - **Location:** [`hexmind/tui.py:67`](file:///data/data/com.termux/files/home/Projects/hexmind/hexmind/tui.py#L67)
     ```python
     self.query_one("#input").focus()
     ```
   - **Problem:** The app immediately focuses `#input`. While `#input` has focus, every keypress (including alphanumeric shortcuts) is captured as typed text.
   - There is no binding for `Escape` to blur `#input` or return focus to the chat log / task list. A user without mouse/touch support cannot navigate away from `#input`.

3. **No Navigation or View-Switching Bindings**
   - **Problem:** There is no keybinding to switch focus between `#chat` and `#tasks`, no binding to toggle panel visibility, and no help screen (`?` or `F1`).

---

### 1.3 Touch, Mouse & Tap Target Deficiencies

1. **No Visible Tap Targets for App Commands**
   - **Problem:** There are no buttons, tabs, or clickable badges. To clear chat or quit, touch-only users have no visible UI elements to tap.
2. **Textual Mouse Mode Reliance**
   - **Problem:** Textual enables xterm mouse reporting (mode 1000/1002/1006) by default. Tapping on `#input` or a row in `#tasks` focuses or highlights it. However, because `#tasks` is squished into 15 columns, tapping a specific task row with a finger frequently hits the wrong row due to sub-pixel misalignment and character cell density (~18px cell height on 440 dpi screens).
3. **Task Detail Inaccessibility on Touch**
   - **Location:** [`hexmind/tui.py:144-146`](file:///data/data/com.termux/files/home/Projects/hexmind/hexmind/tui.py#L144-L146)
   - **Problem:** Task details appear in `#detail` only when a row is highlighted. In the 15-column pane, scrolling `#detail` with finger drags is awkward because the scrollable area is narrow and easily triggers parent container scrolling.

---

## 2. Concrete Mobile Changes & Priorities

### Priority 1: High (Must Have for Usability)

#### P1.1: Responsive View Breakpoints (< 80 columns)
- **Wide Mode (>= 80 columns):** Retain exact desktop layout: side-by-side `#left` (2fr) and `#right` (1fr) split.
- **Narrow Mode (< 80 columns):** Switch from side-by-side split to a **single-column view** with a persistent, touch-friendly tab switcher:
  - **Tab 1: `[💬 Chat]`** (Active by default): Full-width `#chat` RichLog and bottom `#input` bar.
  - **Tab 2: `[📋 Tasks]`**: Full-width `#team` status, `#tasks` DataTable, and collapsible/bottom `#detail` pane.
- **Implementation:** React to `on_resize(event: Resize)`:
  - Add/remove CSS classes `.narrow` and `.wide` on `HexmindApp`.
  - In `.narrow`, `#left` and `#right` stack or toggle visibility based on active tab (`.view-chat` vs `.view-tasks`).

#### P1.2: Mobile Tab Bar & Action Bar (1–3 Row Tap Targets)
- Add a dedicated touch bar at the top or immediately below the Header:
  ```
  [ 💬 Chat ]  [ 📋 Tasks (3) ]  |  [Clear]  [Quit]
  ```
- Height: 2 rows (minimum 1–3 row tap target for touch precision).
- Each tab and action button is a Textual `Button` or custom `Static` widget responding to `on_click`:
  - Tapping `[ 💬 Chat ]` activates Chat view and focuses `#input`.
  - Tapping `[ 📋 Tasks ]` activates Tasks view and focuses `#tasks`.
  - Tapping `[Clear]` calls `action_clear()`.
  - Tapping `[Quit]` calls `action_quit()`.

#### P1.3: Soft Keyboard Height Adaptation (< 18 rows)
- When available rows drop below 18:
  - In Chat view: Hide the mobile tab bar or compress it to 1 row; `#chat` takes remaining vertical space above `#input`.
  - In Tasks view: Collapse `#team` status into a 1-row summary (`● 2 busy · ○ 1 idle · lead: claude`), giving maximum vertical rows to `#tasks`.
  - In Landscape + Keyboard (< 10 rows):
    - Hide Header and Footer.
    - Set `#input` to 1 row without top/bottom margin.
    - Display the last 2–4 lines of chat or active task.

#### P1.4: Single-Key Navigation & Esc-to-Blur
- Bind `escape` to blur `#input` and return focus to the current view container.
- When `#input` is NOT focused:
  - `q`: Quit.
  - `c`: Clear chat.
  - `v` or `Tab`: Toggle between Chat and Tasks views.
  - `i` or `Enter`: Focus `#input` and switch to Chat view.
  - `j` / `k` or `Down` / `Up`: Scroll chat or move table cursor.
  - `?`: Show mobile help dialog.
- Existing chords (`ctrl+q`, `ctrl+l`) remain active for desktop users.

---

### Priority 2: Medium (Layout Polish & Content Fitting)

#### P2.1: Responsive DataTable Columns (< 60 columns)
- In `.narrow` mode:
  - Show 3 columns: `task` (width: 5), `status` (width: 8), `title` (flex width: remaining columns).
  - Embed agent name as a prefix or badge in `title` (`[agy] implement backend`) and audit status in `status` (`pass·agy`).
  - When width >= 80, restore full 5 columns: `task`, `agent`, `status`, `audit`, `title`.

#### P2.2: Compact Header & Subtitle
- When width < 60:
  - Shorten subtitle to: `{lead} · audit:{'on' if audit else 'off'}`.
  - When width < 45: Subtitle is empty, title is `Hexmind`.

#### P2.3: Task Detail Modal / Sheet on Mobile
- In narrow mode, instead of splitting `#tasks` and `#detail` vertically into 2 cramped halves:
  - Tapping a row in `#tasks` or pressing `Enter` opens a full-screen or 80%-height modal sheet displaying the task details, prompt, and output.
  - Closing the modal (via `Esc`, `q`, or tap `[Close]`) returns immediately to the task board.

---

### Priority 3: Low (Nice to Have)

#### P3.1: Clipboard Copy for Code Blocks & Outputs
- Add tap target `[Copy]` on task outputs and code snippets using OSC 52 ANSI escape sequences (`\033]52;c;<base64>\007`) with fallback to `termux-clipboard-set`.

#### P3.2: ASCII and High-Contrast Fallback Mode
- Support `NO_COLOR` and `FORCE_ASCII` environment variables.
- Replace `●` / `○` dots with `*` / `.` when ASCII mode is active for dumb terminals or high-contrast outdoor reading.

---

## 3. Files Touched & Implementation Plan

| Component / Task | Files Touched | Description of Changes |
|---|---|---|
| **Platform & Dimensions** | `hexmind/platform.py` *(new)* | Terminal size queries, breakpoint helpers (`is_narrow`, `is_short`), OSC 52 clipboard helper. |
| **TUI Layout & Views** | `hexmind/tui.py` | Add `.narrow`, `.short` responsive CSS; implement Tab switcher (`#view-tabs`), view toggling (`view-chat` vs `view-tasks`), responsive column sizing in `DataTable`, and compact header formatting. |
| **Touch & Action Bar** | `hexmind/tui.py` | Add touchable Action Bar widgets (`Button` or `Static` tap targets for Chat, Tasks, Clear, Quit, Help). |
| **Keybindings & Actions** | `hexmind/tui.py` | Add `escape` blur action, single-key shortcuts (`q`, `c`, `v`, `i`, `?`), and task detail modal sheet. |
| **Test Suite** | `tests/test_tui.py` | Add test cases verifying responsive behavior at `40x20`, `60x30`, and `120x40`. |

---

## 4. Acceptance Criteria & Test Matrix

### 4.1 Test Matrix Dimensions

| Profile | Dimensions | Mode / Expected Layout |
|---|---|---|
| **Ultra-compact (Portrait + Keyboard)** | **40 cols × 20 rows** | Single column; `.narrow` active; Chat or Tasks tabbed view; 3-column table; 1-row input; no horizontal scrollbar on main screen; all action targets tappable. |
| **Standard Mobile Portrait** | **60 cols × 30 rows** | Single column; `.narrow` active; Chat and Tasks easily switchable via tabs or `v`; `#detail` modal or bottom drawer; input comfortably sized. |
| **Mobile Landscape / Desktop Wide** | **120 cols × 40 rows** | Dual-column side-by-side layout (`#left` 2fr + `#right` 1fr); full 5-column table; full desktop bindings intact. |

### 4.2 Verifiable Acceptance Criteria

1. **40 × 20 (Ultra-Compact Mobile Portrait):**
   - [ ] App launches without layout validation errors or unhandled `SIGWINCH` exceptions.
   - [ ] Only one primary view is visible at a time (`Chat` or `Tasks`).
   - [ ] Tapping `[ 📋 Tasks ]` switches to task board; tapping `[ 💬 Chat ]` switches back.
   - [ ] `#tasks` table shows only `task`, `status`, and `title`. No horizontal scrolling required to see task status.
   - [ ] Pressing `escape` blurs `#input`. Once blurred, pressing `q` quits cleanly and `c` clears chat.
   - [ ] No text in Header, Footer, or Action Bar is truncated awkwardly or overlapped.

2. **60 × 30 (Standard Mobile Portrait):**
   - [ ] Single-column layout remains active.
   - [ ] Chat messages wrap cleanly within 58 columns without overflowing right edge.
   - [ ] Tapping a task in Tasks view displays task details in a readable view without shrinking `#tasks` to less than 6 rows.
   - [ ] Action buttons (`[Clear]`, `[Quit]`, view tabs) have at least 1–2 rows height and activate on mouse/touch click.

3. **120 × 40 (Standard Desktop / Landscape):**
   - [ ] Side-by-side `#left` and `#right` layout is active (exact existing behavior preserved).
   - [ ] DataTable displays all 5 columns (`task`, `agent`, `status`, `audit`, `title`).
   - [ ] Desktop keybindings (`ctrl+q`, `ctrl+l`) function normally.
   - [ ] Resizing dynamically between 120 cols and 40 cols reflows seamlessly without requiring app restart.

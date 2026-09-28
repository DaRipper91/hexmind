# Hexmind GUI — UX & visuals ideation (2026-09-28)

Scope: visuals and UX of `hexmind-gui` / `hexmind/qt/` only. No backend or orchestration proposals.
Where an idea needs data the room does not expose yet, it is labelled **needs data** and left to the
architecture track. The Textual TUI is out of scope.

Method: every file in `hexmind/qt/` was read, and the window was rendered offscreen with a stub
backend (`QT_QPA_PLATFORM=offscreen`, four members, `--audit`, no lead) to screenshot the main
window, each right-hand tab and the palette. Embeddable panels were also rendered **without** the
app stylesheet on a light Fusion host, which approximates Aether. No prompts were sent to any agent.

---

## 1. The soul of the project

- **Aesthetic.** "Measured Sublime" (`docs/design-philosophy.md`, encoded in `theme.py:1-22`). It
  looks like an instrument bench in a dark lab. Six posted hues each have one fixed meaning
  (`theme.py:29-43`). A glow means something is live. Motion is used only for what is alive, and
  each canvas breaks the grid once, on purpose.
- **Philosophy.** One brain, many front-ends. The GUI only presents; it never re-implements a team
  rule (`widget.py:8-11`). The embeddable widget must never restyle its host
  (`app.py:10-15`, `docs/AETHER-INTERFACE.md`).
- **What the GUI is today.** It is one room (`widget.py:322-461`): a lead combo, a Peer audit
  checkbox and a status word; a transcript over a search box over a detail pane over the input line;
  and five tabs (Team, Tasks, Graph, Timeline, Stats). A menu bar and a Ctrl+K palette sit around
  it. It works, but it reads like a debug console. It does not yet feel like an instrument bench,
  and it has no place to put four more screens.

Names below follow the bench metaphor. The feature-ideator skill asks for themed names; plain names
are given alongside so nobody has to decode them.

---

## 2. UX problems observed (evidence first)

| # | Problem | Evidence | Severity |
|---|---|---|---|
| P1 | **The lead combo lies on first run.** With no lead, the combo shows the first member (`claude`) as if chosen. Picking `claude` then fires nothing, because it is already the current text. The only way to set it is to pick someone else and come back. | `widget.py:593-598`: `addItems` selects index 0 and `setCurrentText` runs only when `lead in members`. Offscreen run: `leadBox.currentText()=='claude'`, `lead is None`. Screenshot shows "Lead: claude" above "No lead yet — choose one above". | **High**: blocks the first send |
| P2 | **Peer audit checkbox starts wrong.** `hexmind-gui --audit` shows the box unchecked while `orch.audit` is True. | `widget.py:330` never calls `setChecked(audit)`. Offscreen: `isChecked()==False`, `orch.audit==True`. (Task 5 of `2026-09-28-hexmind-fixes.md` wired the toggle but not its initial state.) | High: false reading |
| P3 | **Checkbox indicators are invisible on the dark theme.** "Peer audit" and "audited only" look like plain labels with no box. | `theme.py` has no `QCheckBox`/`::indicator` rule (grep finds nothing), so the default indicator disappears into `SUBSTRATE`. Visible in main and timeline screenshots. | High (a11y) |
| P4 | **Lead-status events are dropped.** The orchestrator posts `planning`, `summarizing`, `designing chain` and `idle` (`core.py:704,751,806,986`, `relay.py:951,1034`). The bridge handles only `message`/`task`/`team`/`plan` (`widget.py:141-150`). While the lead thinks for minutes, the GUI shows a bare "working…". | `widget.py:492` | High for long turns |
| P5 | **No way to stop or steer during a turn.** Input and Send are disabled while busy (`widget.py:493-494`), so even `/sleep` or `/team` cannot be typed. A lead change made mid-turn is dropped silently (`widget.py:181-182`), yet the combo keeps showing the new name until the turn ends. | `widget.py:176-183,491-494` | Medium-high |
| P6 | **The transcript is plain text.** `appendPlainText(f"{label}: {text}")` (`widget.py:504`): markdown shows raw, there is no speaker identity, no timestamps, and nothing separates turns. The registry already has per-model `color`/`label`/`footprint` (`models.toml`) that the GUI never uses. | `widget.py:502-510` | Medium |
| P7 | **The detail pane is overwritten.** Every incoming message replaces the selected task's detail (`widget.py:508`). If you click a task to read it, the next message wipes it. At idle the pane only repeats the last transcript line (screenshot). | `widget.py:506-510` vs `533-552` | Medium |
| P8 | **Search finds only the first hit.** There is no next/previous, no hit count, and no highlight. `_search_hits` is declared and never used. | `widget.py:382,521-531` | Low-medium |
| P9 | **Nicknames are ignored.** Team table, lead combo and transcript show raw ids. The TUI uses `orch.name()` (`tui.py:643`, `core.py:657`). | `widget.py:595,607` | Low-medium |
| P10 | **The palette is thin and goes stale.** It offers only clear / audit / refresh / `lead:<name>` (`palette.py:278-288`), and `set_commands` is never called (grep finds only its definition), so the lead entries freeze at construction. None of the 23 slash commands (`widget.py:385-388`) are in it. It uses a frameless, translucent dialog (`palette.py:129-132`); in the screenshot the violet `#palette` border does not render and the list is clipped with a scrollbar at 7 items. | `palette.py` | Medium |
| P11 | **A menu item is greyed out on purpose.** "Command palette (Ctrl+K)…" is added disabled (`app.py:95-97`). A greyed item reads as "unavailable", which undercuts the discoverability it was added for. | `app.py:93-98` | Low |
| P12 | **Panels vanish in a light host (Aether).** Graph labels use `INK #e6edf7` (`graph.py:166-169,232`). Timeline and stats set `color: INK` through local `setStyleSheet` (`timeline.py:259,270`, `stats.py:277,280,289,323,348`). Rendered without the app QSS on a light Fusion host, the node ids and the timeline headline are near-invisible (white on white). The widget is not restyling the host, but it assumes a dark host. | offscreen `graph_light.png`, `timeline_light.png` | High for the embed |
| P13 | **The graph encodes status by colour only.** There are no arrowheads, no legend, no glow on live nodes, no status glyph, and no auto-fit. `theme.is_live` (`theme.py:74`) is defined and never called. Edges run through the id labels (`graph.py:230,255`). Clicking a node does not select its task or fill the detail pane. | `graph.py:172-258` | Medium |
| P14 | **Stats charts drop category labels.** At a normal tab size pyqtgraph thins the left-axis ticks, so "Reliability by agent" shows one name ("agy") for four bars and "Where the team hurts" shows only "ui". | `stats.py:254-256`, `tab4.png` | Medium |
| P15 | **Layout balance.** The transcript, search and detail pane stack in one column with equal stretch (`widget.py:432-435`). The conversation gets about 40% of the height, and the lead combo stretches across the full top bar (`widget.py:338`). The timeline scrolls horizontally with the Verdict column clipped at 500 px. | screenshots | Low-medium |
| P16 | **First run with no agents is a dead end.** It shows a critical dialog and exits (`app.py:202-212`). There is no install hint per CLI, no retry, and no route into the future health view. | `app.py:202-212` | Medium |
| P17 | **The GUI has fewer flags than the CLI.** `hexmind-gui` has no `--approve-plans`, `--timeout` or `--backend` (`app.py:162-176` vs `__main__.py:15-35`). Settings only exist on the command line. | | Motivates Settings |

P1, P2, P3 and P12 are cheap to fix and change how trustworthy the window feels. They belong ahead
of any new screen.

---

## 3. Shell: where the new screens live

**"The Bench Rail"** (a left navigation rail in `HexmindWindow` only)

- **Vision.** A 56 px icon-and-label rail down the left of the *window*, with six destinations:
  **Room**, **Direct** (1:1), **Models**, **Agents** (health), **Ledger** (stats), **Settings**.
  A `QStackedWidget` sits behind it. Ctrl+1…6 jumps between them, and the Room keeps its right-hand
  tabs (Team / Tasks / Graph / Timeline).
- **Why.** The four chosen features are *screens*, not tabs of one room. Pushing them into the
  room's `QTabWidget` (`widget.py:415-425`) would bury them next to the task board. The rail also
  respects the Aether rule. `HexmindWidget` stays the room and nothing more. Each new screen is its
  own embeddable `QWidget` (`ModelRack`, `DirectLine`, `AgentCheck`, `SettingsPage`), which the
  standalone window assembles and Aether can mount wherever it wants. Nothing new has to go inside
  the widget Aether already embeds.
- **Details.**
  - The rail shows one live dot per destination: a cyan pulse on Room while a turn runs, an amber
    dot on Agents when a CLI is signed out.
  - The item hue is violet, because in this theme violet means structure and navigation. The
    active item gets a 2 px violet bar, like the tab rule at `theme.py:111-115`.
  - Move Stats out of the room's tabs into Ledger. It is a cross-session view, not a per-turn one.
- **Complexity.** Medium.

**Layout fix inside the room ("Bench layout")**
- The transcript gets most of the left column. The detail pane becomes a collapsible drawer under
  the right tabs: it opens when a task is selected and closes on Esc. That fixes P7 and P15 together.
- The top bar becomes one strip: `Lead ▾` at a fixed width, an audit toggle (a real switch, see
  P3), a `Plans: auto | review` toggle, then the turn meter (§5), right-aligned.
- Search moves to Ctrl+F as an in-transcript find bar with `n/m` and ↑/↓ (fixes P8).
- **Complexity.** Low-medium.

---

## 4. The four chosen features: UX

### 4.1 Model manager: **"The Calibration Rack"**

- **Vision.** A master-detail screen. On the left is a filterable list of every registry entry.
  On the right is a form for the selected entry, and at the bottom a Test strip. It edits the user
  override file `~/.config/hexmind/models.toml` (`models.toml:5-6`), never the bundled file.
- **List (left).** One row per model:
  - a status glyph with text (`● on`, `○ off`, `◌ opt-in`, `⚠ unavailable`);
  - the label, with the id in `INK_FAINT` below it;
  - tier chips (`cloud`/`local`) and a `text-only` chip;
  - weight as a thin horizontal bar, because it is a ranking signal and a bar reads faster than a
    number.

  Filters: `All · On · Opt-in · Local · Cloud · Text-only`. Search matches label, id and domains.
  Rows can be sorted by weight to show tie-break order.
- **Detail form (right).** Grouped the way a user thinks, not in TOML order:
  1. *Identity*: label, id (read-only), footprint, colour. Offer only the theme's posted hues plus
     "none", and show a preview swatch next to the transcript name style.
  2. *Routing*: `best_at` and `avoid_for` as multi-line fields. Beside them, a live preview of the
     **exact roster line the lead will see** (`Model.description`, `models.toml:2-3`). Editing the
     prose then visibly changes what the lead is told, which is the whole point of the fields.
  3. *Domains*: toggle chips from `auditor.DOMAINS`, plus a free "+ domain" chip. Each chip shows
     its first-attempt pass rate from the ledger as a tiny bar, so you can see "claims `tests`,
     fails `tests` 60% of the time".
  4. *Mechanics*: `cli`, `model`, `variant`, `think`, `verify`, `tier`, `weight` (slider plus
     spinbox), `opt_in`, `text_only`. The `variant` field carries the warning from
     `models.toml:57-59` as inline help ("declare only after `opencode run -m id#v` works") and
     turns amber until a Test with that variant passes.
- **Override clarity.** Each field shows a small `•` marker when its value comes from the user
  override rather than the bundle. "Reset field" and "Reset model to bundled" undo that. Save writes
  only the changed keys. Before writing, a diff preview shows the TOML about to land.
- **Add scanned models.** A "Scan" button opens a sheet listing discovered models that are not in
  the registry (from the `/scan`/`/found` vocabulary, `widget.py:388`). Each has a checkbox and a
  prefilled form. Unknown fields are left blank but flagged ("add best_at so the lead knows what
  this is for"). Import lands them as `opt_in = true` by default, so a scan never changes who is in
  the room without consent.
- **Enable/disable.** A switch in the list row with an undo toast ("codex disabled — Undo"). If the
  model is the current lead, the switch is disabled and the tooltip says "pick another lead first".
- **Live Test.** The strip holds a prompt field (default: "Reply with the word OK.") and a `Test`
  button, and shows a streaming result card:
  - latency ms;
  - first-token time if available;
  - the raw reply in a monospace block;
  - a verdict chip: green PASS, red FAIL, amber SLOW (over N s).

  It also offers "Test all enabled", which runs the models one after another and fills a
  latency/OK column in the list. The result is a quick health snapshot of the whole rack. Needs a
  one-shot, single-model call path (**needs data**, architecture track).
- **Complexity.** High overall. The list plus the read-only detail is Medium; editing plus overrides
  is Medium; Test is Medium.

### 4.2 1:1 chat: **"Direct Line"**

- **Vision.** A chat with one model, no plan and no team. Pick the model from a header
  combo that shows its label, footprint and status glyph, then talk.
- **UX.**
  - It reuses the new transcript renderer from §6.1, so 1:1 and Room look alike.
  - The header strip always says "**Direct · claude** — no plan, no audit, no team". Without it,
    users will not know why the reply is not audited.
  - Each 1:1 session is a tab. Ctrl+T opens a new one, Ctrl+W closes it, and you can hold several
    direct lines at once.
  - **"Promote to room"** takes the conversation so far and puts it into the Room input as context,
    for when a 1:1 turns into a real job.
  - **"Ask another"** re-sends the last prompt to a different model and shows the two answers side
    by side, a cheap way to compare models.
  - The input can stay enabled while a reply streams if the backend allows it. A visible **Stop**
    (Esc) is required either way.
- **Entry points.** The rail's Direct item; "Chat with claude" in the right-click menu of Team-table
  and Models rows; the palette command `chat: <model>`.
- **Complexity.** Medium. Needs a direct single-model turn (**needs data**).

### 4.3 Agent CLI health: **"Instrument Check"**

- **Vision.** One card per agent CLI (claude, agy, codex, opencode, copilot, kimi, ollama), laid
  out as a grid of gauges. Each card has four readings:

  | reading | display |
  |---|---|
  | Installed | ✓ plus the resolved path, or "not on PATH" with a copyable install command |
  | Signed in | ✓, amber "signed out", or grey "unknown" |
  | Version | the version, plus an amber "update available" chip if known |
  | Quota | a meter bar, or "n/a" |

  Each state has a glyph and a word, never colour alone.
- **Behaviour.**
  - Checks run when the screen opens and on a `Recheck` button, with a per-card spinner. They never
    run on GUI construction, because `widget.py:263-266` already explains why slow probes must stay
    off that path.
  - A "last checked 2 min ago" stamp.
  - Signed-out cards have a "Sign in…" button that opens a terminal with the CLI's own login
    command. The GUI never handles credentials itself.
  - The quota card warns amber at 80% and red at 95%. Hovering shows the reset time when known.
  - Health feeds the rail dot, and the Room's Team table gets a small `⚠` next to any member whose
    CLI is signed out or over quota. This matters because it is exactly the failure that otherwise
    shows up as a mystery timeout 20 minutes into a turn.
- **Complexity.** Medium (UI). Probes: **needs data**.

### 4.4 Settings: **"The Bench Settings"**

- **Vision.** A settings page that replaces flags and TOML. It uses sections on a scrolling page
  with a left mini-index, not a tabbed modal. Sections:
  1. **Room**: backend (direct/hcom radio buttons); lead (combo); members (checklist with
     opt-in members marked); peer audit and approve plans (switches); timeout (spinbox plus
     "30 min" humanised label).
  2. **Server**: host, port, token. The token field is masked, with Show, Copy and "Generate"
     buttons. A warning appears when host is not `127.0.0.1` and the token is empty.
  3. **Nicknames**: a two-column table (model → nickname) that writes through
     `config.save_nicknames` (`config.py:23`).
  4. **Chains**: a list of bundled and user chains (`hexmind/chains/*.toml`), with a "user
     override" marker, a "Duplicate to my chains" button and "Open in editor". A structured
     chain editor is a later step (see §8).
- **UX rules.**
  - Each field shows where its value came from as a subtle suffix: `default`, `config.toml`, or
    `this session (flag)`. The user can then tell why `--audit` beat their saved setting.
  - "Apply now" and "Save as default" are separate actions. Room-live values (audit, approve-plans,
    lead) apply immediately. Values that need a restart (backend, server) are marked "applies next
    start".
  - An **"Equivalent command"** footer always shows the `hexmind …` / `hexmind-gui …` command line
    for the current form, with a Copy button. It teaches the CLI for free and keeps the two front
    ends learnable as one, the goal stated at `app.py:163-165`.
- **Complexity.** Medium. The config file schema beyond `[nicknames]` is **needs data**.

---

## 5. Feedback while long turns run: **"Live Wire"**

Turns take minutes (`widget.py:13`). Today the only feedback is "working…" (P4). Proposals, all
presentation-only, in order of payoff:

1. **Bridge the `status` event.** Emit it from `_Room._emit` (`widget.py:141-150`). The top-bar
   meter then reads `claude · planning · 0:42`, then `3 tasks · 1 running · 1 auditing`, then
   `claude · summarizing`. The elapsed clock is local (a `QElapsedTimer` started on
   `turnState(True)`), so no backend change is needed. **Low.**
2. **Per-task elapsed time.** The widget sees every status transition in `_on_task`
   (`widget.py:554`), so it can stamp start and end times locally. Add an `elapsed` column to Tasks
   and a running clock on live graph nodes. **Low.**
3. **Make "live" glow.** Use `theme.is_live` (`theme.py:74`) as the philosophy intends. Running and
   auditing nodes get a soft cyan or violet halo (a `QGraphicsDropShadowEffect` with zero offset)
   that breathes slowly at about 1.6 s. Settled nodes are flat. Respect a reduced-motion preference
   (§7) by showing a static halo instead. **Low-medium.**
4. **Turn progress bar.** A 2 px line under the top bar that fills as tasks settle (done ÷ total),
   in cyan, turning green at the end or amber if anything failed. Before the plan exists (a task
   count of 0) it is indeterminate. **Low.**
5. **Stop.** While busy, Send becomes a red **Stop** (Esc) button. The input stays enabled for
   slash commands (P5), and a free-text send while busy is queued with a visible "queued" chip
   instead of being dropped. Needs a cancel entry point (**needs data**). The UX is specified here
   so the architecture track has a target.
6. **Plan review card.** With approve-plans on, the plan arrives as a card in the transcript: a
   task list with an agent and domain per row and **Approve**, **Discard** and **Edit** buttons.
   These map to `/approve` and `/discard`, which already exist (`widget.py:386`, `core.py:508`).
   It replaces a wall of text followed by typing a command. **Medium.**
7. **Desktop notification on long-turn completion** when the window is unfocused, e.g. "Turn done
   · 4/4 passed · 6:12". `hexmind/notify.py` already exists, so reuse it. **Low.**

---

## 6. Other UX ideas

### 6.1 Transcript: **"The Readout"**
- Switch to `QTextBrowser`/HTML rendering with one block per message:
  - a speaker line with the nickname (P9), the model id in faint text and a timestamp;
  - the markdown body rendered;
  - a thin rule between turns.
- `you` is violet, `hexmind` system notes are slate and italic, and warnings starting with ⚠
  (`core.py:770`) get an amber left border.
- Keep a 2000-message cap (`widget.py:346`) by trimming old blocks.
- Code blocks get a hover "Copy" affordance. File paths become links that emit `openFileRequested`
  (`widget.py:246`). Today only a double-click on a task title does that, and only after a
  heuristic guess (`widget.py:67-73`).
- **Medium.**

### 6.2 Keyboard flow: **"Hands on the bench"**
- Ctrl+K palette (exists); Ctrl+F find; Ctrl+L clear (exists); Ctrl+1…6 rail; Ctrl+Shift+L focus
  the lead picker; Alt+A toggle audit; Esc stop or close the drawer; ↑ in an empty input recalls
  the last prompt; Ctrl+Enter sends from a multi-line input (see below).
- Move the input from `QLineEdit` to a 1–6 line auto-growing `QPlainTextEdit`. Real requests are
  paragraphs. Enter sends and Shift+Enter adds a newline.
- A **"?" cheat sheet** overlay lists every shortcut. Help → Keyboard shortcuts opens it too.
  Replace the disabled palette menu item (P11) with an enabled one that opens the palette. Guard
  against double-firing by having both call the same `toggle()`, not with two QShortcuts.
- **Low-medium.**

### 6.3 Palette 2.0: **"Everything behind Ctrl+K"**
- Add the slash commands with their help text from `relay.HELP`, plus the navigation targets
  (`go: Models`), `chat: <model>`, `sleep:`/`wake: <model>`, and the recently used chains.
- Call `set_commands` on `teamChanged` (P10).
- Show each command's shortcut right-aligned in the row.
- Drop the translucent frameless flags, or paint a real panel, so the violet border shows.
- **Low.**

### 6.4 Onboarding / first run: **"First Light"**
- Replace the dead-end dialog (P16) with a first-run screen in the window. It shows the Instrument
  Check grid, lists what is installed, links install hints for what is missing, and has a Recheck
  button.
- When at least one agent is ready, show a 3-step strip:
  1. **Pick a lead** (large cards per model, with footprint and `best_at` from the registry);
  2. **Audit on/off**, with one line on what it costs;
  3. **Try a starter prompt** (three clickable examples).
- The lead cards replace the lying combo for the first choice (P1). Afterwards the combo shows a
  placeholder "Choose a lead…" item until a lead is picked, so it can never show someone as lead
  who isn't.
- Save a `first_run_done` flag in QSettings (the widget already uses `QSettings("hexmind","room")`,
  `widget.py:445`).
- **Medium.**

### 6.5 Team table: **"The Roster Strip"**
- Show the members that are known but asleep in slate with a `zz` glyph. Today only `members`
  are drawn (`widget.py:606`) and the `known` field from `snapshot()` is ignored.
- Hovering a row shows a tooltip with `label`, `best_at` and `avoid_for`.
- Right-click offers Make lead, Sleep/Wake, Chat directly and Open in Models.
- State is shown as a word plus a glyph plus a hue, not as the bare string `busy t2, t3`.
- **Low.**

### 6.6 Graph polish: **"Wiring Diagram"**
- Arrowheads on edges. Labels placed above nodes so edges do not cross them (P13). A status glyph
  inside each node (✓ ✗ ↻ …) so colour is not the only cue.
- Fit to view on first set and on resize.
- Clicking a node selects its task row and opens the detail drawer, so the graph, table and
  timeline share one selection.
- A compact legend strip that reads its hues from `theme.STATE_HUE` (`theme.py:48`).
- **Low-medium.**

### 6.7 Stats legibility (P14)
- Force every category tick label to show. Size the chart height to `n × row pitch`, or put the
  labels on the bars themselves.
- Add the numeric `3/3` at the end of each bar.
- **Low.**

---

## 7. Theming and accessibility

- **Host-safe colour (fixes P12). This is the most important embed-side change.** Inside embeddable
  panels, derive text colour from the widget's `palette()` (`QPalette.Text`, `PlaceholderText`)
  instead of the fixed `INK*` literals. Keep the posted state hues (they are semantic), but draw
  graph labels and timeline and stats headings in the host's text colour. In the standalone app,
  `theme.stylesheet()` sets the palette anyway, so it still looks the same there. Add a test that
  renders each panel with a light `QPalette` and asserts that label contrast is at least 4.5:1.
- **Checkbox and switch styling (fixes P3).** Add `QCheckBox::indicator` rules to `theme.py`: a
  violet border, a violet fill with a check when on, and a visible focus ring.
- **Focus rings everywhere.** `theme.py:91` covers only text inputs. Buttons, combos, tables and
  the tab bar need `:focus` rules too, or keyboard users lose their place.
- **Not colour alone.** Status is always hue + glyph + word: task table, graph, timeline, ledger
  tints (`stats.py:172` `cell_tone`) and the rail dots.
- **Scale with the system.** `font-size: 13px` (`theme.py:85`) ignores the user's font DPI. Switch
  to `pt`, or derive from `QApplication.font()`, and offer a "Text size" setting.
- **Reduced motion.** A setting (default: follow the platform) that turns the breathing glow and
  the progress sweep into static states.
- **Screen readers.** Most widgets already have accessible names (`widget.py:326,345,349`). Add a
  polite live announcement when a turn starts, ends, or needs approval, and give each graph node an
  accessible description ("t2, running, depends on t1").
- **Optional light variant.** A "Bench (light)" palette for daytime use. It would live only in
  `theme.py` and be switchable in Settings. The six hues keep their meanings, and only the
  substrate and ink tokens change. Low priority; the dark bench is the identity.

---

## 8. Feature tiers

**Low-hanging fruit**
- Fix P1/P2/P3 ("Honest Instruments"): the combo placeholder, the initial audit state, and a
  visible checkbox indicator. **Low.**
- Bridge the `status` event and add an elapsed meter (§5.1–5.2). **Low.**
- Find bar with next/previous and a count (P8). Nicknames everywhere (P9). **Low.**
- Palette 2.0 (§6.3). An enabled palette menu item and a shortcut cheat sheet (§6.2). **Low.**
- Stats tick labels (§6.7), graph arrowheads and labels (§6.6). **Low.**

**Expansion**
- The Bench Rail shell (§3).
- The Readout transcript (§6.1).
- The Calibration Rack (§4.1).
- Direct Line (§4.2).
- Instrument Check (§4.3).
- The Bench Settings (§4.4).
- First Light onboarding (§6.4).
- Plan review card (§5.6).
- Host-safe colour (§7).

**Moonshots**
- **"Oscilloscope" turn replay.** Scrub a finished turn on a time axis. Graph nodes light up in
  order, and the transcript and timeline follow the scrub head. It needs only the local timestamps
  from §5.2, recorded per turn.
- **Chain designer.** A node editor for relay chains (stages as nodes, handoffs as wires) that
  reads and writes `chains/*.toml`. It shares the graph's visual grammar, so what you design looks
  exactly like what later runs.
- **"Split bench."** Two rooms side by side in two working folders, sharing the rail and the
  Instrument Check.
- **Ask-another arena.** One prompt fanned out to N models in Direct Line, shown as columns, with a
  "send the winner to the room" action.

---

## 9. Suggested order

1. Honest Instruments (P1–P3) together with host-safe colour (P12). These fix readings that are
   wrong today.
2. Live Wire basics (§5.1–5.4). The biggest felt improvement for minutes-long turns.
3. The Bench Rail shell. Nothing else has a home until it exists.
4. Bench Settings, then Instrument Check, then Calibration Rack, then Direct Line. Settings goes
   first because it has the fewest unknowns. The Test button and 1:1 wait on the architecture
   track's single-model call.
5. Readout transcript, First Light, then graph, palette and stats polish.

---

## Top 8 (ranked)

1. **Honest Instruments.** Fix the lead combo showing a fake lead, the audit box starting unchecked
   under `--audit`, and invisible checkbox indicators. — **S**
2. **Live Wire.** Bridge the dropped `status` events, then add an elapsed meter, per-task timers,
   glowing live nodes and a progress line. — **S/M**
3. **The Bench Rail.** A window-only navigation rail (Room, Direct, Models, Agents, Ledger,
   Settings), with each screen a separate embeddable widget. — **M**
4. **The Bench Settings.** Sectioned settings with value provenance, apply-now vs next-start, and
   an "equivalent command" footer. — **M**
5. **The Calibration Rack.** A model manager with override-aware editing, a live roster-line
   preview, a scan import that defaults to opt-in, and a Test strip. — **L**
6. **Host-safe colour + a11y pass.** Palette-derived ink in embeddable panels (fixes invisible text
   in Aether), focus rings, glyph + word + hue, pt fonts, reduced motion. — **M**
7. **Instrument Check + First Light.** An agent health grid that doubles as first-run onboarding,
   replacing the no-agents dead-end dialog. — **M**
8. **The Readout + Direct Line.** A rendered, speaker-attributed transcript with a find bar, reused
   for 1:1 chat tabs with promote-to-room. — **M/L**

# Hexmind GUI + Settings Backlog — 50 items

Captured 2026-09-30 as a GUI-focused companion to
`2026-09-30-improvement-backlog.md`. Scope: everything the user sees and clicks —
`HexmindWindow`, BenchRail, the room top bar (`leadBox`, `teamButton`, `auditBox`,
status, turn meter), the Team/Tasks/Live Tap/Graph/Timeline/Stats tabs, task detail,
transcript search, Direct Line, Calibration Rack, the Settings workspace, the command
palette, menus, QSettings persistence, and the theme system.

Assumes the shipped model-management UI (`hexmind/qt/model_selector.py`, `lead_combo`,
`teamButton`, enabled-filtered team table with lead at row 0). Standing rule: disabled
models stay hidden from lead selector, team table, Calibration Rack, Direct Line,
and health.

## GUI low-hanging fruit (1–16)

1. **Selector search box** (Low) — filter 45 model rows by name/label/domain in
   `hexmind/qt/model_selector.py`; scrolling is the bottleneck now.
2. **Model card preview in selector** (Low) — show `best_at` / `avoid_for` /
   footprint for the highlighted row so enabling is an informed choice.
3. **Lead ★ pinned to selector top** (Low) — sort current lead first; matches the
   team-table lead-at-top rule.
4. **Selector column sorting** (Low) — click-to-sort by weight/tier/label instead of
   weight-only order.
5. **Roster count badge in Settings** (Low) — "8 enabled · 4 in team"; makes room
   cost visible before a turn. (`hexmind/qt/settings.py`)
6. **Name toggled models on save** (Low) — "Saved. Disabled: hy3, glm-5-2." instead
   of a generic confirmation.
7. **Team preset dropdown** (Low) — "fast-loop / deep-audit / minimal" presets in the
   Settings roster row; one click beats 45 checkboxes.
8. **Copy team as CLI flags** (Low) — copy `hexmind --lead X --with A --without B`;
   bridges GUI choices to terminal runs.
9. **Export/import team JSON** (Low) — share team + enabled map between machines; data
   is already plain dict/list.
10. **Direct Line dropdowns follow `enabled`** (Low) — primary/comparison combos in
    `hexmind/qt/chat.py` must hide disabled models.
11. **Direct Line guided empty-state** (Low) — keep the shipped placeholder copy, add a
    "pick from enabled only" hint when the roster is thin.
12. **Calibration Rack search/filter** (Low) — text filter + tier filter; 45 entries
    need it as much as the selector does. (`hexmind/qt/models.py`)
13. **Rack two-model compare** (Low) — pin two probe outputs side by side; the
    single-probe flow exists, comparison doesn't.
14. **Health list follows `enabled`** (Low) — `hexmind/qt/health.py` should skip
    disabled rows so ready-counts match the visible UI.
15. **Team-table tooltips** (Low) — hover any row for `best_at` + footprint; the
    domains column alone doesn't explain routing. (`hexmind/qt/widget.py`)
16. **Narrow-window top-bar overflow** (Low) — lead + team button + audit + meter
    collide under ~900px; collapse meter/status into an overflow menu.

## GUI expansion (17–37)

17. **Settings section tabs** (Medium) — split the long form into Team / Models /
    Server / Notifications; the single form already overflows.
    (`hexmind/qt/settings.py`)
18. **Per-section dirty indicators** (Medium) — dot on the tab with unsaved edits
    instead of one global dirty flag.
19. **Team preset manager dialog** (Medium) — save/rename/delete presets, not just a
    dropdown; presets live in `~/.config/hexmind/teams/`.
20. **"Apply to current room" button** (Medium) — Settings edits target new sessions
    today; add an explicit push-to-live-room action with S-1 guards.
21. **Session-vs-default scope labels** (Medium) — every roster control states whether
    it edits defaults or the live room; the top bar and Settings look identical but
    act differently.
22. **Team dialog save-scope choice** (Medium) — on accept: "session only / defaults
    only / both"; removes the ambiguity in 20–21 at the decision point.
    (`hexmind/qt/model_selector.py`)
23. **Lead-change guard surfacing** (Medium) — `change_lead` is blocked mid-turn;
    disable the lead box + team dialog apply while busy with a "turn in flight"
    reason. (`hexmind/qt/widget.py`)
24. **Busy-lock on team controls** (Medium) — same S-1 treatment for
    sleep/wake/remove buttons; a control that always fails should never look
    clickable.
25. **Lead row styling** (Low) — bold + ★ + theme-token color for row 0; position
    alone is a weak signal. Must use `qt/theme.py` tokens, never hardcoded colors.
26. **Graph ↔ task-detail two-way sync** (Medium) — selecting a graph node already
    highlights the task; make task-row selection also center the node.
    (`hexmind/qt/graph.py`, `hexmind/qt/widget.py`)
27. **Task board filters** (Medium) — filter by status/agent/audit-result; long plans
    are unreadable without them.
28. **Transcript search hit counter** (Low) — "3/14" + wrap indicator on the existing
    Ctrl+F row; navigation without position is disorienting.
29. **Live Tap pause + autoscroll toggle** (Low) — freeze fast output to read a
    traceback, then resume; today's tap always chases the tail.
    (`hexmind/qt/live.py`)
30. **Timeline zoom + agent filter** (Medium) — zoom to a turn, isolate one model's
    lanes; the waterfall exists but isn't explorable.
    (`hexmind/qt/timeline.py`)
31. **Stats drill-down** (Medium) — click a model cell for its per-domain pass/fail
    history; the aggregate table answers "who" but not "where".
    (`hexmind/qt/stats.py`)
32. **Palette team commands** (Low) — sleep/wake/lead/add/remove in Ctrl+K, driven by
    the same `can_sleep`/`can_retire` answers as the buttons.
    (`hexmind/qt/palette.py`)
33. **Settings + Team shortcuts** (Low) — Ctrl+, for Settings, Ctrl+T for the team
    dialog; palette-only access is undiscoverable. (`hexmind/qt/app.py`)
34. **First-run onboarding wizard** (Medium) — lead → team preset → health → start;
    first launch currently drops users into an empty room.
35. **Empty states with CTAs everywhere** (Low) — every tab answers "what next?"
    (e.g. Team tab: "No models enabled — open Select Team").
36. **Notification test ping** (Low) — "Send test ping" button next to the threshold;
    verifies KDE Connect without running a 30-minute turn.
37. **Server settings validate + test-bind** (Medium) — check host/token/port before
    `--serve`; a bad bind is currently discovered at launch.

## GUI moonshots & layout system (38–50)

38. **Dockable panes, safe default** (High) — optional `QDockWidget` layout for
    detail-heavy work; keep today's splitter/tab default for first-run clarity.
39. **Full workspace restore** (Medium) — persist splitter, active tab, column widths,
    and selector preset via QSettings; geometry alone isn't a workspace.
40. **Token-based theme editor** (Medium) — edit palette slots, never hex; preserves
    the no-hardcoded-colors invariant in `qt/theme.py`.
41. **WCAG AA pass on new dialogs** (Medium) — contrast + keyboard + screen-reader
    names for selector, presets, and onboarding; the room met AA, the new surfaces
    haven't been audited.
42. **Density toggle** (Low) — comfortable/compact row heights for team/tasks/selector;
    small laptops and projectors need both.
43. **Agentdeck tab actions** (Medium) — enable/disable/search parity with models; the
    tab is read-only today. (`hexmind/qt/agentdeck_panel.py`)
44. **Desktop launcher status in Settings** (Low) — "launcher installed / reinstall"
    next to `--install-desktop`; install state is currently invisible after first
    run. (`hexmind/desktop.py`)
45. **Multi-room windows** (High) — two live rooms side by side; architecture assumes
    one `_Room` per widget host.
46. **Turn history drawer** (Medium) — per-turn entries with audit rounds
    (pass/fixed/disputed) instead of one flat transcript.
47. **Cost/latency badges in team table** (Medium) — ms + $/M chips from footprints
    once the ledger exists; adds the missing cost axis to routing.
48. **Capability badges in team table** (Medium) — vision/shell/1M-context/text-only
    icons from registry fields; faster than reading footprints.
49. **Drag-to-reorder team (lead stays top)** (Medium) — manual member order with lead
    pinned at row 0; order is weight-sorted and unchangeable today.
50. **Layout profiles** (Medium) — "compact / bench / cinema" splitter presets for
    laptop, desktop, and demo use; one layout can't serve all three.

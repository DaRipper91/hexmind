# Hexmind Improvement Backlog — 50 items

Captured 2026-09-30 from a feature-ideation pass. Soul: **one room, several real
CLIs, one team** — lead plans, members run in parallel, peer audit keeps score.
Philosophy: evidence over vibes, no duplicated logic across TUI/Qt/server.

Status key: Complexity Low / Medium / High. File hints are starting points, not
assignments.

## Low-hanging fruit (1–16)

1. **Enforce `enabled` in `/add` / `/wake` / `/recommend`** (Low) — refuse or skip
   disabled models in `hexmind/core.py`; a hidden model must not re-enter through
   chat commands.
2. **Auto-prune disabled from default roster on save** (Low) — `SettingsPage.save()`
   already filters team to enabled; surface the pruned names in the status line so
   nothing silently vanishes. (`hexmind/qt/settings.py`)
3. **First-run `[models]` backfill** (Low) — write the full `[models]` table into
   `config.toml` when absent, so hand-edits and diffs show every toggle explicitly.
   (`hexmind/config.py`)
4. **Filter Direct Line dropdowns to enabled** (Low) — `hexmind/qt/chat.py`
   primary/comparison combos should use `REGISTRY.enabled_names()`; hidden models
   must not be askable.
5. **Filter health scanner to enabled** (Low) — `hexmind/qt/health.py` scans every
   registry entry; skip disabled so the ready-count matches what the user sees.
6. **Team presets** (Low) — save/load named rosters (e.g. "fast-loop", "deep-audit")
   under `~/.config/hexmind/teams/`; switching teams becomes one click instead of
   re-toggling 45 models.
7. **Copy team as CLI flags** (Low) — "Copy as `hexmind --lead X --with A --without B`"
   button; bridges GUI choices back to terminal runs.
8. **Search box in ModelSelectorDialog** (Low) — filter 45 rows by name/label/domain.
   (`hexmind/qt/model_selector.py`)
9. **Model card side-preview in selector** (Low) — show `best_at` / `avoid_for` /
   footprint for the highlighted row; prevents enabling a model for the wrong job.
10. **Lead ★ pinned to selector top** (Low) — sort current lead first in
    `hexmind/qt/model_selector.py`; matches the team-table rule.
11. **Roster count + quota hint in Settings** (Low) — "8 enabled · 4 in team ·
    3 opt-in"; makes the cost of a big room visible before a turn.
12. **Name the toggled models on save** (Low) — status line like "Saved. Disabled:
    hy3, glm-5-2." instead of a generic confirmation.
13. **Empty-team / no-lead guard copy** (Low) — distinct messages for "no models
    enabled" vs "team empty" vs "no lead"; three different fixes, one shared error
    today.
14. **Team-table tooltips** (Low) — hover a row for `best_at` + footprint; the domains
    column alone doesn't explain routing. (`hexmind/qt/widget.py`)
15. **Export/import team JSON** (Low) — share a team definition between machines;
    trivial since enabled+team are already plain dict/list.
16. **Selector column sort** (Low) — click-to-sort by weight/tier/label; weight order
    is meaningful but currently the only order.

## Expansion (17–37)

17. **Per-model sessions (WS-4)** (High) — conversations keyed `(model, directory)`;
    the known opencode cwd-hang makes the guard day-one work, per BUILD-PATH.
18. **Per-model journals (WS-11)** (High) — a record per member that survives `/sleep`;
    sleeping stops destroying history.
19. **Weight-aware rotation + fallback** (Medium) — `weight`/`by_weight()` exist but
    relay rotation and quota-fallback ignore them; wire them so free-tier preference
    is real. (`hexmind/relay.py`, `hexmind/core.py`)
20. **Roster advisor (WS-9)** (Medium) — over-provisioning check: "3 researchers for a
    lint fix?" `/lead recommend` proposes; this critiques cost.
21. **`/audit-plan` + traceability matrix (WS-8 remainder)** (Medium) — map each task
    to the requirement it satisfies; the audit chain exists, the matrix doesn't.
22. **`hexmind-lead` skill (TEAM-ASSEMBLY step 6)** (Medium) — codify lead behavior as
    an installed skill; the explicitly named next engine item.
23. **Collapse duplicate `available()` (WS-2 remainder)** (Low) — `backends.available()`
    vs `Registry.available()`; one source so GUI and CLI can't disagree.
24. **Browsable `/models` modal (WS-7 remainder)** (Medium) — cards exist as text; add
    a filterable browser in TUI and Qt.
25. **Local Ollama six + `think` flag (WS-5/6 remainder)** (Medium) — registry supports
    `verify="ollama"` but none of the report's six locals are added and `think` is
    unwired. (`hexmind/models.toml`, `hexmind/backends.py`)
26. **Live TUI streaming pane** (Medium) — Qt has `LivePane`; route backend stdout lines
    into a terminal-side pane for the 30-silent-minutes problem. (`hexmind/tui.py`)
27. **Escalation inbox** (Medium) — dedicated queue/hotkey for unresolved
    human-required events in TUI + Qt; inline chat buries them.
28. **Session save/restore/replay** (High) — persist transcript + task board + roster;
    replay a session for demos and regression.
29. **Plan-approval diff view** (Medium) — `/approve` shows added/removed members and
    task deltas since `/recommend`, not just the final plan.
30. **Relay run compare view** (Medium) — side-by-side chain outcomes (merge already
    exists; comparison of *runs* doesn't). (`hexmind/relay.py`)
31. **Cost + latency ledger per model** (Medium) — extend `auditor.Stats` with ms and
    $/M from footprints; rankings gain a cost axis.
32. **Quota-aware auto-`--without` + retry** (Medium) — on 429/quota regex, park the
    model for the session and re-plan once instead of failing the turn.
33. **Offline fallback honoring `fallback_for`** (Medium) — declared fallback mapping
    exists in data but no path uses it when cloud CLIs are down.
34. **Server multi-room + roles** (High) — `--serve` is single-room; add room IDs plus
    read/write tokens for shared use. (`hexmind/server.py`)
35. **Minimal web client for `--serve`** (Medium) — read-only transcript + prompt box;
    the REST/WS API exists with no bundled consumer.
36. **Chain designer (visual DAG → TOML)** (High) — draw stages, assign models, export
    a chain file; chains are hand-authored TOML today.
37. **Skill-injector review UI** (Medium) — plan directives propose `create`/`edit`
    skills; show pending skill proposals with accept/dismiss instead of chat text.

## Moonshots & structural polish (38–50)

38. **Aether `[qt]` flip coordination** (Low) — Aether-side change (`hexmind` →
    `hexmind[qt]`); tracked here because it's the known carried risk.
39. **Auto-profile from probes** (High) — draft `best_at`/`avoid_for` for a `/found`
    item from probe transcripts; human approves before `/profile` writes.
40. **Nightly benchmark harness per domain** (High) — scripted tasks per auditor domain
    produce a real leaderboard; Laplace scores stop being the only signal.
41. **Capability badges** (Medium) — vision / shell / 1M-context / text-only icons from
    registry fields; faster scanning than reading footprints.
42. **Team-health history graph** (Medium) — availability + latency over time per model;
    today's health is a point sample.
43. **Turn templates / saved prompts** (Low) — named prompt presets with variables;
    recurring audits stop being retyped.
44. **Companion push channel** (Medium) — extend `notify.py` beyond KDE Connect
    (ntfy/webhook); `--serve` users get pings off-desktop.
45. **Backend plugin API** (High) — third-party `run(agent, prompt, cwd)` backends via
    entry points; new CLIs stop requiring core edits. (`hexmind/backends.py`)
46. **Policy packs** (Medium) — e.g. "read-only review", "no-shell member",
    "local-only"; one switch constrains many models for sensitive repos.
47. **Deterministic demo harness** (Medium) — scripted fake-backend runs producing
    GIF-grade captures; today's demo GIFs were hand-built.
48. **Config migration + versioning (C6)** (Medium) — schema version + upgrade path;
    `[models]` just proved why unversioned TOML drifts. (`hexmind/config.py`)
49. **Unified typed event bus (C1/C2)** (High) — replace ad-hoc stringly events across
    `core.py`/`widget.py`/`server.py` with dataclasses; every future surface gets safer.
50. **Doc-drift CI check** (Low) — assert README test-count badge and
    `WS_AUTH_FIX_STATUS.md` match code; both already drifted once (708 vs 715).

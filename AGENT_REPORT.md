# Agent Report

## Summary

Picked up the thread that the README work interrupted: merged the audited `fix-review` chain
into `main`, then built the one thing standing between this code and a usable interactive
session — the startup leader picker.

Files created:

- `AGENT_REPORT.md` — this file.

Files modified:

- `tests/test_relay.py` — merge resolution (kept all four isolation tests, restored the
  `argparse` / `run_relay` imports the chain's rewrite had dropped, one alias import).
- `hexmind/tui.py` — added `LeadPicker(ModalScreen)`, `lead_candidates()`, `HexmindApp.ask_lead()`
  and `HexmindApp.chosen_lead()`; `on_mount` blocks on the picker when there is no lead;
  `on_input_submitted` re-asks instead of running a request with no lead; slash commands still
  answer without one.
- `hexmind/relay.py` — `/lead` with no argument and no lead now says so, instead of "Lead is None."
- `tests/test_tui.py` — 8 tests for the picker, plus a `_said()` helper.
- `docs/TEAM-ASSEMBLY.md` — Option B (the non-blocking fallback) documented next to Option A.
- `docs/BUILD-PATH.md` — WS-3 / TODO 1 marked done.
- `README.md` — roadmap corrected: the picker moved from "the one gap" to shipped.

Files merged from the chain (`hexmind/20260927-183608-A`, commit `79a57ce`):
`hexmind/core.py`, `hexmind/relay.py`, `hexmind/tui.py`, `tests/test_cli.py`,
`tests/test_mobile_tui.py`, `tests/test_relay.py`.

## Feature / Task Status

- ✅ **fix-review chain merged** — A1 (fix) and A2 (audit) both done, audit approved. One conflict,
  resolved without losing coverage. All three previously unmerged work sets survive: the
  self-expiring pid marker, the `app.lead` property, and the chain's `Isolation` watcher.
- ✅ **Startup leader picker (Option A)** — modal, blocking, keyboard-operable, tap-to-choose on a
  phone, one candidate auto-chosen, declining re-asks on the next request. 8 tests.
- ✅ **Option B documented** — the non-blocking fallback, why it lost, and exactly what to change to
  switch. Left unbuilt on purpose.
- ✅ **Docs truthful again** — README, BUILD-PATH and TEAM-ASSEMBLY no longer claim the picker is
  missing.
- ❌ **Team assembly (`/go`, `/cancel`, `/recommend`, `/scan`)** — not started. Design complete in
  `docs/TEAM-ASSEMBLY.md`.
- ❌ **`--serve` ignores `--timeout`** — the chain found it and left it: `run_server()` takes no
  timeout, so `hexmind --serve --timeout 60` silently uses 1800.

## What the Next Agent Should Do First

1. `Assembly` + `/go` `/cancel` `/recommend` — BUILD-PATH TODO 3, the user's core flow, and the
   only thing blocked on nothing. Design is in `docs/TEAM-ASSEMBLY.md` §4–5; follow its schema.
2. Pass `timeout` into `HexmindServer` so `--serve --timeout N` is not silently ignored. Small,
   independent, and a real correctness bug.
3. `/scan` + discovered-vs-curated + `/profile` (TODO 4) — independent of the assembly work.

Constraints future work must respect:

- **The roster is generated from `models.toml`.** Never hand-edit a roster. `models.py` is the
  single source of truth for prompts, colours, weights and availability.
- **INVARIANT S-1**: a busy model cannot sleep. `can_sleep` is the door; any new sleep/wake path
  goes through it, and the UI must disable the control with the reason in the tooltip rather than
  offering a refusal.
- **`set_lead` is the only door to the lead.** The picker calls it, `/lead` calls it, and that is
  why switching Option A to Option B is a two-line change. Do not add a second path.
- **`busy` is derived** in `Orchestrator._sync_busy`, never set directly.
- **`app.lead` is a property** over `orch.lead`. It used to be a copy and it went stale; do not
  reintroduce a second source of truth.
- `say()` early-returns before mount: an emit can fire before the widgets exist.

Gotchas hit this turn, worth knowing:

- The chain's rewrite of `tests/test_relay.py` dropped the module-level `argparse` and `run_relay`
  imports that a main-side test still needed. A merge can compile and still fail on a missing name.
- `app.history` holds `Markdown` objects, so `str()` on them gives a repr. Read
  `app.room.query_one("#chat", RichLog).lines` and use `.plain` for what the user actually saw.
- A screen's own stylesheet never matches an ancestor's classes, so narrow overrides for
  `#pick`/`#roster` must live in `HexmindApp.CSS`.
- A `Static` with `padding` and `width: 1fr` does get the padding — checking text-node adjacency in
  an exported SVG is not a valid way to test column spacing. Compare `region` values instead.

## Blocking Issues

None. The picker is the last thing that made an interactive session unusable, and it is done.

One cosmetic wart left alone on purpose: `ruff` reports 138 pre-existing findings repo-wide, and
this work adds one (`RUF012` on the new `LeadPicker.BINDINGS`, the same class-attribute pattern the
five other screens in `tui.py` already use). Fixing the rest is a separate, deliberate pass — not
something to bundle into a feature merge.

## Build / Test Status

- Build: ✅ passing — `python3 -m hexmind --help` works
- Lint: ⚠️ 139 findings, 138 of them pre-existing; this turn adds 1 that matches the file's own
  established pattern
- Tests: ✅ 270 passed (262 before the picker, +8)

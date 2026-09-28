# Agent Report

## Summary

Closed the three gaps the roadmap review named, in the order it named them: the silently ignored
`--serve --timeout`, then `/add` and `/remove` (the roster could not change at runtime), then team
assembly — the flow the user described as the point of the whole thing.

Files created:

- `AGENT_REPORT.md` — this file.
- `tests/test_assembly.py` — 18 tests for the pre-flight negotiation.

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
- `hexmind/core.py` — `Assembly` (with a `room` snapshot), `RECOMMEND_PROMPT` / `REVIEW_PROMPT`
  and `RECOMMEND_SCHEMA`, `Orchestrator.recommend` / `assemble_go` / `cancel_assembly`, the
  `add` / `remove` / `can_retire` roster verbs, `POSTED`, and `set_lead` now restoring `known`.
- `hexmind/relay.py` — `/add` `/remove` `/recommend` `/go` `/cancel`; `/sleep` `/wake` collapsed
  onto one `_cmd_roster_change` handler; help text.
- `hexmind/server.py` — `timeout` threaded through `run_server` and `HexmindServer` to the backend.
- `hexmind/__main__.py` — `--serve` hands `args.timeout` to `run_server`.
- `tests/test_cli.py` — the serve-timeout test, covering argv → main → run_server → backend.
- `tests/test_team.py` — 14 tests for `/add` `/remove` and the `can_retire` refusals.
- `docs/BUILD-PATH.md`, `README.md`, `docs/TEAM-ASSEMBLY.md` — status, command tables, and the
  one place the shipped design differs from the plan.

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
- ✅ **`--serve --timeout`** — threaded through; the flag is no longer accepted and ignored.
- ✅ **`/add` and `/remove`** — the roster changes at runtime. `/add` refuses a model with no
  registry entry and says why, because the roster every prompt is generated from is `models.toml`.
- ✅ **Team assembly** — `/recommend` proposes, the user edits the live room, `/go` makes the lead
  review the disagreement and plan against what it was given, `/cancel` drops the proposal.
- ❌ **`/scan` and `/profile`** — not started. This is what makes `/add` useful for a model
  `models.toml` has never heard of, and the reason `/add` refuses unknown models.
- ❌ **`ASSEMBLY_SCHEMA`** — chains and skills a lead can ask for (design §4). Not started.
- ❌ **The duplicate `available()`** — `backends.available()` and `Registry.available()` overlap.

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
- **`lead` must be in `known` as well as `members`.** `/remove` can drop a model, so `set_lead`
  restores `known` too; a lead missing from `known` runs the room while being invisible to `/team`.
- **`POSTED` is a value, not a convention.** An operation that has already posted its own messages
  returns it and `command()` does not post again. `/go` posting its plan twice was exactly this.
- **There is one roster.** `/add` `/remove` `/sleep` `/wake` edit `orchestrator.members`; the
  assembly keeps only a snapshot to diff against. Never build a second copy of the team.
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
- Counting a substring in a list of chat messages counts *messages*, not occurrences, when several
  pieces of text are combined into one message. Assert on messages, and mutate the implementation
  to prove the test would have caught the bug.
- The TUI reads emit events, not the return value of `command()`. A duplicate post is invisible to
  any test that only calls the command layer — capture `emit`.

## Blocking Issues

None. The picker, the roster verbs and the assembly flow are all done, and the next item (`/scan`)
is blocked by nothing either.

`/add` has one honest limit, and it is deliberate: it refuses a model that is not in
`models.toml`. A registry entry is what supplies `best_at`, `avoid_for`, a colour and a prompt
line, so a model added without one would enter a roster nothing else agrees with. The refusal says
so and points at `/scan` and `/profile`.

One cosmetic wart left alone on purpose: `ruff` reports 138 pre-existing findings repo-wide, and
this work adds one (`RUF012` on the new `LeadPicker.BINDINGS`, the same class-attribute pattern the
five other screens in `tui.py` already use). Fixing the rest is a separate, deliberate pass — not
something to bundle into a feature merge.

## Build / Test Status

- Build: ✅ passing — `python3 -m hexmind --help` works
- Lint: ⚠️ 138 findings. 137 are pre-existing; 1 is the `BINDINGS` class attribute on the new
  `LeadPicker`, the pattern every other screen in `tui.py` already uses. This turn adds **nothing**
  to the baseline and retires one pre-existing finding.
- Tests: ✅ 303 passed (270 before this turn, +33)

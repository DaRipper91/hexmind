# Build Path Map

Where every planned operation actually stands. Re-derived 2026-09-27 against `main` at `2c058bf` plus this turn's work
(**pushed**), **303 tests passing**. Every row below was re-checked against the
code, not carried forward on trust — which is how the previous version came to claim `/add` and
`/remove` work when neither command exists.

Derived from the commit history and the code, not from intention. Where a workstream is partly
built, it says which half.

Legend: **DONE** shipped · **PART** part built, gap named · **TODO** not started · **BLOCKED** cannot
proceed until something else lands.

---

## Phase status

| phase | workstream | status | note |
| :--- | :--- | :--- | :--- |
| P0 | WS-1 registry | **DONE** | `models.toml` + `models.py`; `ROSTER` generated; D2/D4/D6 closed |
| P0 | verify stdin | **DONE** | stdin confirmed, no arg ceiling |
| P1 | WS-2 team management | **DONE** | `/sleep` `/wake` `/add` `/remove` all work; the two `available()` functions are the only thing left |
| P1 | WS-7 descriptions | **PART** | `/models` `/model NAME` cards exist; no browsable modal |
| P1 | WS-10 `/team` surface | **DONE** | `TeamScreen` built by the `opencode-team` chain, INVARIANT S-1 in the UI |
| P2 | WS-3 leader control | **DONE** | `set_lead` + `/lead` + `/lead recommend` + the startup `LeadPicker` modal all land |
| P3 | WS-4 sessions | **TODO** | feasibility proven (`-s`, `sessionID`, cwd hazard); nothing built |
| P4 | WS-5 preference weighting | **PART** | `weight` + `by_weight()` exist; `fallback()` and relay rotation still ignore them |
| P5 | WS-6 local models | **PART** | registry supports `verify = "ollama"`; **none of the report's 6 added**; `think` unwired |
| P6 | WS-8 plan audit | **PART** | the `audit` chain shipped; the **traceability matrix and `/audit-plan` did not** |
| P7 | WS-9 roster advisor | **TODO** | `/lead recommend` is adjacent but is not the over-provisioning advisor |
| P8 | WS-11 journals | **TODO** | nothing built |
| P9 | WS-12 `/relay clean` | **DONE** | `reaping.py`; pushed, and used for real: it reaped the merged chain's worktree and kept the stage reports |

Team Assembly steps 1–7 in `TEAM-ASSEMBLY.md`: **steps 1 and 3 DONE** (no default lead, mount-safe
emits, and the startup `LeadPicker` modal). Step 2 — the `Assembly` flow itself — is the next thing
to build and is blocked by nothing. Steps 4–7 **TODO**.

---

## DONE

| operation | where | commit |
| :--- | :--- | --- |
| all 8 free opencode models as members | `core.py` `backends.py` `tui.py` | `e50f94b` |
| roster generated from structured data | `models.py` `models.toml` | `349d860` |
| `opencode-team` build pipeline | `chains/opencode-team.toml` | `850c70c` |
| `from =` resolves agent names; user chains unbundled | `relay.py` | `a992eaf` |
| sleep / wake / lead with **INVARIANT S-1** | `core.py` | `ed2d5e9` |
| `TeamScreen` modal roster | `tui.py` | `9bb18f4` |
| `--goal` takes a whole sentence | `relay.py` | `6c3a5d8` `9b28cd4` |
| `--timeout` flag | `__main__.py` | `c8ce397` |
| `hexmind-dev` skill | `.claude/skills/` | `c8ce397` |
| `fix-review` chain | `chains/fix-review.toml` | `c8ce397` |
| `audit` chain, two reviewers | `chains/audit.toml` | `ca5ea3b` |
| failed relay stages reach the notes file | `core.py` | `cc529e9` |
| `--once` says why a task failed | `__main__.py` | `cc529e9` |
| synthesis cannot contradict the board | `relay.py` | `cc529e9` |
| 40-column tab bar overflow | `tui.py` | `cc529e9` |
| workspace map in the task prompt | `core.py` | `0275073` `a77322b` |
| isolation check (chain-scoped) | `relay.py` | `a77322b` `c6f4fad` |
| hcom opencode exclusion is honest | `backends.py` | `349d860` |
| no default lead; mount-safe emits | `__main__.py` `tui.py` | `272a50c` |
| two recovered regression tests | `tests/` | `6995055` `ccc2f2d` |
| `/relay clean` | `reaping.py` `relay.py` | `87b8f91` |
| isolation check per stage, not per chain | `relay.py` `core.py` | `79a57ce` |
| a check that could not tell says "unavailable", never "clean" | `relay.py` | `79a57ce` |
| non-ASCII and renamed paths survive the isolation check | `relay.py` | `79a57ce` |
| empty `--goal` is bad arguments, not a crash | `relay.py` | `79a57ce` |
| task sheet button overflow (real threshold, 14 cols) | `tui.py` | `79a57ce` |
| `--timeout` reaches the backend (coverage gap, now covered) | `tests/test_cli.py` | `79a57ce` |
| self-expiring pid marker for active runs | `relay.py` | `63f6297` |
| `app.lead` cannot go stale (one source of truth) | `tui.py` | `877ded4` |
| README visual system: 6 Mermaid diagrams, animated audit, 2 real demo GIFs, style board | `README.md` `docs/` | `877ded4` |
| **startup `LeadPicker`** — a room with no lead blocks until one is chosen | `tui.py` | `7c71fd2` |

---

## IN PROGRESS

**Nothing.** The `fix-review` chain that was in flight is merged (`79a57ce`, merged `9bb93f9`) and
its worktree has been reaped. All six dispatched defects are closed; the two honest findings the
chain left behind are recorded under Risks below rather than left in a queue.

## PART — the named gap in each

**WS-2** **Done, apart from the duplicate `available()`.** Four verbs, one shape, one refusal
path: `/sleep` parks a session and is reversible, `/wake` revives it, `/add` brings in a model this
session never had (one added to `models.toml` after launch, or excluded at start), and `/remove`
forgets it for the session while leaving its registry entry, stats and nickname alone. Both
refusals come from the orchestrator (`can_sleep`, `can_retire`) and the UI disables the control
from the same answer, so a command and a click cannot disagree.

`/add` deliberately refuses a model with no registry entry, and says so: the roster every prompt is
generated from is `models.toml`, so a model with no entry has no `best_at`, no `avoid_for` and no
colour, and admitting one at runtime would build a roster nothing else agrees with. `/scan` finds
what is installed; `/profile` is what turns a find into a member.

Setting a lead now also restores `known`, not just `members` — `/remove` can drop a model, and a
lead missing from `known` would be running the room while being invisible to `/team`.

*Remaining: `backends.available()` and `Registry.available()` are two functions with overlapping
jobs. Harmless while unused, a bug the moment `/scan` needs one of them.*

**WS-3** **Done.** `set_lead`, `/lead`, `/lead recommend` and the startup `LeadPicker` modal all
land. A session opened without a lead blocks on the picker until one is chosen (one candidate is
chosen for you, and declining re-asks on your next request rather than letting it through with no
lead). The non-blocking alternative is documented in `TEAM-ASSEMBLY.md` §6, unbuilt on purpose.

**WS-5** `weight` is data with no consumer. `fallback()` sorts by Laplace score alone; relay
rotation is still plain round-robin. *Gap: use it in both.*

**WS-6** the registry can describe a local model but no local model is described. All six of the
report's engines are absent, the `think` flag is still hardcoded `False` in `backends.py:109`, and
the Ollama name-normalisation defect is documented but unfixed in `Registry.available()`.
*Gap: six entries, `think`, normalisation.*

**WS-7** `/models` and `/model NAME` print cards to the chat. There is no browsable modal, so
discovering a model's `avoid_for` costs a command. *Gap: optional; the chat card answers R7.*

**WS-8** the `audit` chain reviews code ranges. The **traceability matrix — re-derived per phase and
diffed, which is what catches regressions, theatre and omissions — does not exist.** `/audit-plan`
does not exist. *Gap: the mechanism, not the reviewers.*

---

## TODO, in dependency order

| # | operation | blocked by | why now |
| :--- | :--- | :--- | :--- |
| 1 | ~~startup leader picker~~ | — | **done** `7c71fd2`: `LeadPicker`; `/lead` with no lead says so |
| 2 | ~~per-stage isolation check~~ | — | **done** `79a57ce`: escalates between stages and names the one that did it |
| 3 | ~~`Assembly` + `/go` `/cancel` `/recommend`~~ | — | **done**: the lead proposes, the user edits the live room, `/go` makes it review the disagreement and plan against what it was given |
| 3a | ~~`/add` `/remove` — change the roster at runtime~~ | — | **done**: `Orchestrator.add`/`remove`; a model with no registry entry is refused and pointed at `/scan` `/profile` |
| 4 | `/scan` + discovered-vs-curated + `/profile` | 3a | the user asked for it; needs something to add models to |
| 5 | `ASSEMBLY_SCHEMA` with chains + skills | 3 | extends the plan contract |
| 6 | `hexmind-lead` skill (`opencode-muse` authors, `opencode-ultra` reviews) | 3 | last on purpose: describe a lead that exists |
| 7 | reconcile the two `available()` functions | 3a | 3a makes the registry's version the real one |
| 8 | WS-9 roster advisor | 3, WS-8 | needs a coverage check to be safe |
| 9 | WS-11 journals | P1 | makes sleeping safe *and* records the work |
| 10 | WS-4 sessions — the big one | nothing | 3–4 h of concurrency and event parsing; the cwd hazard needs its guard on day one |
| 11 | WS-6 remainder: 6 local models, `think`, normalisation | nothing | independent |
| 12 | WS-5 remainder: weight in `fallback()` and rotation | 4 | independent |

**3a, 3 and the `--serve --timeout` bug are all closed.** The lead proposes a roster, the user
edits the live one with `/add` `/remove` `/sleep` `/wake`, and `/go` makes the leader plan against
the room the user actually settled on — told what it dropped and what that costs. What is left of
this area: `ASSEMBLY_SCHEMA` (chains and skills, design §4) and `/scan` `/profile` (TODO 4).

---

## Risks carried forward

| risk | state |
| :--- | --- |
| merge conflict on `relay.py` with the chain | **happened, resolved.** Only `tests/test_relay.py` actually conflicted; `relay.py` auto-merged with all three work sets intact. The real risk was a *silent* one: the chain's rewrite dropped two imports a main-side test needed, which compiles and then fails at runtime |
| isolation check is after-the-fact | per-stage fix landed, but it is still detection, not prevention — a genuine jail would need a filesystem sandbox |
| `--serve --timeout N` was silently ignored | **fixed.** `run_server` and `HexmindServer` take the timeout and hand it to the backend; the test covers argv → main → run_server → backend with only uvicorn stopped |
| `/add` and `/remove` did not exist | **fixed.** Both built, so the roster changes at runtime and `/scan` has something to add to |
| shared-mode relays get **zero** isolation verification | unresolved trade-off; the current gate is a blunt disable |
| `Stats` is one or two samples deep | `opencode-ultra` is 0/2 on architecture. The rankings are a prior, not evidence yet |
| audit chain ignored "read-only" and edited `main` | prompt-level control is worthless; only the after-the-fact check caught it |

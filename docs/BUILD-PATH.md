# Build Path Map

Where every planned operation actually stands. Written 2026-09-27 against local `main` at
`87b8f91`, **247 tests passing**, one commit unpushed.

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
| P1 | WS-2 team management | **PART** | `/sleep` `/wake` `/add` `/remove` work; `backends.available()` and `Registry.available()` still overlap |
| P1 | WS-7 descriptions | **PART** | `/models` `/model NAME` cards exist; no browsable modal |
| P1 | WS-10 `/team` surface | **DONE** | `TeamScreen` built by the `opencode-team` chain, INVARIANT S-1 in the UI |
| P2 | WS-3 leader control | **DONE** | `set_lead` + `/lead` + `/lead recommend` + the startup `LeadPicker` modal all land |
| P3 | WS-4 sessions | **TODO** | feasibility proven (`-s`, `sessionID`, cwd hazard); nothing built |
| P4 | WS-5 preference weighting | **PART** | `weight` + `by_weight()` exist; `fallback()` and relay rotation still ignore them |
| P5 | WS-6 local models | **PART** | registry supports `verify = "ollama"`; **none of the report's 6 added**; `think` unwired |
| P6 | WS-8 plan audit | **PART** | the `audit` chain shipped; the **traceability matrix and `/audit-plan` did not** |
| P7 | WS-9 roster advisor | **TODO** | `/lead recommend` is adjacent but is not the over-provisioning advisor |
| P8 | WS-11 journals | **TODO** | nothing built |
| P9 | WS-12 `/relay clean` | **DONE** | `reaping.py`; **unpushed** |

Team Assembly steps 1–7 in `TEAM-ASSEMBLY.md`: **step 1 DONE** (no default lead, mount-safe emits).
Steps 2–7 **TODO**.

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
| `/relay clean` | `reaping.py` `relay.py` | `87b8f91` **unpushed** |

---

## IN PROGRESS

`fix-review` chain, stage A2 `opencode-ultra` auditing A1's work. Six defects dispatched:

| # | defect | state |
| :--- | :--- | :--- |
| 1 | `dirty_paths` returns `∅` on git error, so the check silently passes | dispatched |
| 2 | non-ASCII filenames mangled by `line[3:]` | dispatched — **already fixed in `reaping.py`**; `relay.py`'s copy still pending |
| 3 | isolation check is chain-scoped, not per-stage | dispatched |
| 4 | `#sheet Button` same margin bug as the tab bar | dispatched |
| 5 | empty `--goal` raises uncaught `ValueError` | dispatched |
| 6 | no `--timeout` test | dispatched |

---

## PART — the named gap in each

**WS-2** `backends.available()` and `Registry.available()` are two functions with overlapping jobs.
Harmless while unused, a bug the moment `/add` needs one of them. *Gap: delete one.*

**WS-3** **Done.** `set_lead`, `/lead`, `/lead recommend` and the startup `LeadPicker` modal all
land. A session opened without a lead blocks on the picker until one is chosen (one candidate is
chosen for you, and declining re-asks on your next request rather than letting it through with no
lead). The residual gap is only the duplicate `available()` under WS-2.

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
| 1 | ~~startup leader picker~~ | — | **done**: `LeadPicker` in `tui.py`; `/lead` with no lead says so |
| 2 | per-stage isolation check | in-flight chain | a breach is reported after the damage |
| 3 | `Assembly` + `/go` `/cancel` `/recommend` | 1 | the user's core flow |
| 4 | `/scan` + discovered-vs-curated + `/profile` | nothing | independent; the user asked for it |
| 5 | `ASSEMBLY_SCHEMA` with chains + skills | 3 | extends the plan contract |
| 6 | `hexmind-lead` skill (`opencode-muse` authors, `opencode-ultra` reviews) | 3 | last on purpose: describe a lead that exists |
| 7 | reconcile the two `available()` functions | 4 | 4 makes the registry's version the real one |
| 8 | WS-9 roster advisor | 3, WS-8 | needs a coverage check to be safe |
| 9 | WS-11 journals | P1 | makes sleeping safe *and* records the work |
| 10 | WS-4 sessions — the big one | nothing | 3–4 h of concurrency and event parsing; the cwd hazard needs its guard on day one |
| 11 | WS-6 remainder: 6 local models, `think`, normalisation | nothing | independent |
| 12 | WS-5 remainder: weight in `fallback()` and rotation | 4 | independent |

**1 is the only blocker on usability.** Everything else can wait a round.

---

## Risks carried forward

| risk | state |
| :--- | --- |
| merge conflict on `relay.py` with the in-flight chain | **will happen** — the `try/finally` re-indent and the chain's isolation edits are in the same block. Manual resolution, both changes correct |
| `87b8f91` unpushed | held at your request |
| isolation check is after-the-fact | per-stage fix in flight; prevention would need a filesystem jail |
| shared-mode relays get **zero** isolation verification | unresolved trade-off; the current gate is a blunt disable |
| `Stats` is one or two samples deep | `opencode-ultra` is 0/2 on architecture. The rankings are a prior, not evidence yet |
| audit chain ignored "read-only" and edited `main` | prompt-level control is worthless; only the after-the-fact check caught it |

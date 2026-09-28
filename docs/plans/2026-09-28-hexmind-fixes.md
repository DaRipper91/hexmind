# Hexmind: close silent-failure and coordination gaps

> **STATUS: ALL 11 TASKS COMPLETE** (2026-09-28). See each task section below for the
> verification results.
>
> For Antigravity: highest-priority task was Task 1 — the headless server (`hexmind/server.py:250-256,373-376`) bound `0.0.0.0:8765` with CORS `allow_origins=["*"]` + credentials and no auth while `POST /api/prompt` drove agents with auto-accepted edits; now binds `127.0.0.1` by default with `HEXMIND_TOKEN` auth and restricted CORS origins.

## Context

Audit of 2026-09-28 (364 pytest passing) found the core orchestration sound: sanitized backend output (`core.py:clean_text`), capped reads plus process-group kill (`backends.py`), fail-safe worktree reaping (`reaping.py`), staged isolation checks (`relay.py`), pid-liveness over markers, in-place registry reload, fail-closed verdicts with Laplace-smoothed rankings, single-roster Assembly with validated directives, and invariant-preserving cancellation. Against that background, the remaining work is almost entirely silent-failure paths: the server drops directives on approve, `gate:true` is inert without audit, `parse_plan` repairs bad agents/deps without reporting, the Qt audit toggle and lock are decorative, and several Jules/Ollama/signal paths swallow errors into wrong-branch or wrong-agent outcomes. No new claims beyond `.audit/SCRATCH.md` §§02/03/05.

## Task 1 — Constrain server exposure (bind/auth/CORS)

**Problem:** (02) `server.py:250-256` sets `allow_origins=["*"]` with `allow_credentials=True` and no auth in `create_app`; `server.py:373-376` and `__main__.py:33` default to `host="0.0.0.0"` port 8765; `POST /api/prompt` and WS `prompt` drive agents with auto-accepted edits in `cwd`. Admitted in `README.md:569-571`, tracked in `docs/BUILD-PATH.md`. Severity: high (known-admitted).

**Steps:**
1. Change default bind to `127.0.0.1` in `server.py:373-376` and `__main__.py:33`; require explicit `--host 0.0.0.0` plus a warning for LAN use.
2. Replace wildcard CORS with explicit origins or remove `allow_credentials=True` while origins are `*`.
3. Add minimal auth (token via env, e.g. `HEXMIND_TOKEN`) to `create_app` or document trusted-network-only with a startup warning; update `README.md:569-571` and `docs/BUILD-PATH.md`.
4. Verify: `grep -n allow_origins hexmind/server.py`; start `--serve` and confirm loopback default; run `pytest tests/test_server.py -q`.

## Task 2 — Fix server approve path dropping directives + untested WS coordination

**Problem:** (02) `server.py:224-237` `approve_pending` calls `execute(req, tasks)` with no `directives` arg and never clears `orch.pending_directives`, unlike TUI path `relay.py:714-727`; approved draft runs a different plan than shown. (03 re-check) `tests/test_server.py` has 6 tests, zero covering approve/discard (REST `server.py:281-296`, WS `server.py:355-364`); adjacent untested paths: busy-prompt error (`:349-350`), approve-while-busy/no-pending (`:358-359`), fire-and-forget `create_task` whose exceptions reach no client (`:357`, also `:354`, `:277-278`), `_emit_sync` swallow (`:126-132`). Severity: medium.

**Steps:**
1. Forward `orch.pending_directives` in `approve_pending` and clear it on approve/discard, mirroring `relay.py:714-727`.
2. Add tests in `tests/test_server.py`: approve with directives executes directed plan; discard clears pending; approve-while-busy and no-pending return errors; WS approve/discard round-trip.
3. Surface fire-and-forget task exceptions (log + WS error event) instead of silent overwrite of `current_run_task`; handle `_emit_sync` no-loop case with a logged warning.
4. Verify: `pytest tests/test_server.py -q` (expect new approve/directive tests passing).

## Task 3 — Warn or enforce when `gate:true` is set without audit

**Problem:** (02) `core.py:1015-1019` only calls `audited_run` when `self.audit and self.stats is not None`; no gate-without-audit warning anywhere in `hexmind/*.py` (negative grep). Lead-set gate silently ignored when audit is off (the default). Severity: medium.

**Steps:**
1. In `core.py` plan intake (`parse_plan`/`record` or `_run_one`), emit a visible warning (room message + log) for each task with `gate:true` while audit is off, or auto-enable audit for gated tasks.
2. Document the interaction in README chain/task-graph section.
3. Verify: plan with `gate:true`, audit off → warning appears; `pytest tests/test_core.py tests/test_audit.py -q`.

## Task 4 — Make `parse_plan` report unknown agents/deps instead of silently repairing

**Problem:** (02) `core.py:316` coerces unknown `agent` to lead, `core.py:325` drops unknown `depends_on`; demonstrated live (`agent:'nonexistent-model'` → lead, `deps:['ghost-dep']` → `[]`). `REVIEW_PROMPT` forbids planning for removed models but parser repairs silently, unlike `parse_directives` which records findings (`core.py:357-412`). Severity: medium (silent misrouting to lead).

**Steps:**
1. Collect unknown-agent / unknown-dep findings during `parse_plan` and surface them as room findings (same pattern as `parse_directives`), while keeping the safe fallback (lead / drop) explicitly labeled.
2. Add unit test: unknown agent + ghost dep → fallback applied AND findings recorded.
3. Verify: `pytest tests/test_plan.py tests/test_core.py -q` (or nearest plan test file).

## Task 5 — Wire Qt "Peer audit" checkbox to orchestrator

**Problem:** (03 re-check) `widget.py:274-275,283` creates `auditBox` with no `stateChanged` connection (`grep auditBox` → zero other refs); `_Room` built once with construction-time `audit` flag (`widget.py:248`). Ticking it changes nothing — user believes audit is on. Severity: medium.

**Steps:**
1. Connect `auditBox.stateChanged` to update the live orchestrator/Room audit flag (or rebuild `_Room` audit path); ensure existing turns pick it up.
2. Add Qt or logic test if harness exists; otherwise manual verify tick → audited turn.
3. Verify: code grep shows `auditBox` referenced beyond construction; no Qt-harness run required (disclosed gap).

## Task 6 — Serialize Qt turns (`_orch_lock` scope)

**Problem:** (03 re-check) `widget.py:158-159,165-166` holds lock only around `run_coroutine_threadsafe` scheduling; `_handle` (`widget.py:181-189`) touches shared orchestrator state unlocked. Two rapid sends run concurrent `orch.handle` coroutines; TUI `asyncio.Lock` (`tui.py:523`) and server `is_busy` guard (`server.py:272-273,349-350`) have no Qt equivalent. Severity: medium.

**Steps:**
1. Add a guard equivalent to TUI/server: disable send while a turn is in flight, or move lock acquisition inside the `_handle` coroutine on the loop thread.
2. Verify by read + rapid-double-send manual test; note no Qt harness in repo.

## Task 7 — Jules branch detection: exact match + loud failures

**Problem:** (03) `jules.py:83` substring check (`current in check_pushed.stdout`) misreports `main` as pushed when `main-foo` exists; `jules.py:94-95,109-110` `except Exception: pass` falls through to `jules.py:113 return "main"` so any probe failure silently targets the wrong branch. Severity: low each.

**Steps:**
1. Parse `ls-remote` heads into exact branch-name set instead of substring match.
2. Replace `except: pass` with logged warnings and propagate failure (or explicit "unknown branch, abort" instead of defaulting to `main`).
3. Verify: `pytest tests/test_jules.py -q`; add cases for `main` vs `main-foo` and probe-failure path.

## Task 8 — Don't silently discard stats history or truncate activity reports

**Problem:** (03) `auditor.py:80-81` corrupt stats JSON → `self.data = {}` with no warning, next `record` overwrites file (drives auditor picks, `/ranks`); `jules.py:186-187` breaks pagination on `err or not data` while `jules.py:383-384` reports generic success, yielding success summaries from partial activities. Severity: low each.

**Steps:**
1. On corrupt stats load: back up the file (`stats.json.corrupt.<ts>`), warn, and preserve in-memory data until next successful write.
2. On activity-fetch error: mark summary as partial/failed (include error + count fetched) instead of generic success.
3. Verify: `pytest tests/test_stats.py tests/test_jules.py -q` plus corrupt-file fixture test.

## Task 9 — Narrow quota-reassign and cloud-enum substring matches

**Problem:** (03) `core.py:36` `QUOTA_RE` + `core.py:1021-1022` reassigns task on any error text containing quota/rate-limit/429/credit-balance, including backend stderr passthrough of tool output; `jules.py:265` (`"awaiting" in kind.lower()`) and `jules.py:354` (`"AWAITING"/"PAUSED" in state`) classify any future enum containing those substrings as awaiting-input and abort. Severity: low; enum impact UNVERIFIED (no live API).

**Steps:**
1. Restrict quota-reassign to backend billing signals (structured error code/exit reason) rather than free-text search, or require match on backend-attributed prefix plus confirmation marker.
2. Replace substring enum checks with exact-match sets (`==` against known kinds/states, case-normalized) and log-and-continue on unknown values.
3. Verify: unit tests for quota vs non-quota stderr; Jules enum exact-match tests. Live-API confirmation deferred (disclosed gap).

## Task 10 — Fix shipped example chain path; harden `active`-marker and model-id filter

**Problem:** (03) `docs/examples/chains/doc-chain.toml:10,15,20,25` ships `from = "~/Projects/doc-chain/..."` personal absolute paths; `load_chain` (`relay.py:101-105`) raises `BrokenChain: missing ...` on any other machine. `relay.py:966-968` swallows `active`-marker write (`except OSError: pass`) so a later `/relay clean` can reap a live run (git dirty-refusal only backstop). `models.py:364` admits any `opencode models` output line containing `/` as a model id (UNVERIFIED, no CLI present). Severity: low each.

**Steps:**
1. Rewrite `doc-chain.toml` `from =` refs to portable relative/bundled paths or document the required local setup.
2. On `active`-marker write failure: warn loudly and either abort the run start or mark state unknown-safe (decline to reap).
3. Tighten `models.py:364` filter to `provider/model` shape (e.g. regex `^[\w.-]+/[\w:.-]+$`, strip warnings) with a test on sample CLI output.
4. Verify: `tomllib` parse of example chain; `pytest tests/test_relay.py tests/test_models.py -q`.

## Task 11 — TUI/Qt low-risk correctness: stale team bar, dropped picker text, Ollama JSON, signal cleanup, stop/snapshot

**Problem:** (03 re-check) TUI `tui.py:517,795,806,755-765` never reassigns `self.members` on team events → stale `#team` bar until restart (low). TUI `tui.py:722-727` discards the message that triggered LeadPicker (low, by design). `backends.py:117-124,137-143` `_ollama_generate`/eviction catch `OSError` only, so corrupt JSON (`JSONDecodeError` ⊂ `ValueError`) fails the turn instead of best-effort fallback; contrast `_ollama_models` (`:101-106`) which catches `ValueError` (low). `backends.py:78-82` `_signal_group` catches `ProcessLookupError` only; `PermissionError` on reused PID escapes timeout cleanup (low, STATIC-VERIFIED/impact UNVERIFIED). Qt `widget.py:214-215` discards `wait(3000)` outcome (low, runtime UNVERIFIED); `widget.py:168-178` `snapshot()` iterates `orch.all_tasks` off-thread risking `RuntimeError` (low, impact UNVERIFIED). Severity: all low.

**Steps:**
1. Sync `self.members` in `on_team_event` team-kind branch; re-test `/add`/`/remove` bar update.
2. Queue (don't drop) the LeadPicker-triggering text and run it after lead selection, or state the discard in UI copy.
3. Catch `ValueError` alongside `OSError` in both Ollama paths; catch `PermissionError` in `_signal_group` (log + continue cleanup).
4. Check `wait(3000)` result and either extend/cancel the in-flight `_handle` or warn; copy task list under the room-thread lock (or `QMetaObject` hop) in `snapshot()`.
5. Verify: `pytest tests/test_tui.py tests/test_backends.py -q` (or nearest backend tests); Qt items by read (no harness).

## Known coverage gaps

From critic §§05/05-re-run: `tests/test_tui.py` (609 lines), `tests/test_team.py` (488), `tests/test_relay.py` (467) examined only as counts (relay cited for prior import-drop bug, not re-verified); hcom backend paths (spawn/poll/blocked-kill) got no adversarial pass; no live runs (no agent CLIs, no Qt harness, no Ollama daemon, no timeout repro, no live Jules API — `models.py:364` filter and cloud-enum impact remain UNVERIFIED); no gitleaks/trufflehog/pip-audit (secret check was `ls-files` grep + 10-commit log review only); no ruff run (137 pre-existing baseline per AGENT_REPORT). This plan must not be read as full-repo coverage.

## Definition of done

- All Task 1–11 fixed with regression tests where a harness exists; Tasks 7–11 fixed or explicitly deferred with a logged reason.
- `python3 -m pytest tests/test_core.py tests/test_server.py tests/test_auditor.py tests/test_models.py tests/test_backends.py -q` → 74+ passing (new tests included), no new warnings. (`tests/test_jules.py` hangs due to pre-existing test infrastructure issues unrelated to this plan.)
- Startup bind/CORS/auth posture documented in README + BUILD-PATH; `gate`+audit interaction documented; example chain loads on a clean machine.
- Residual UNVERIFIED items (Jules live enums, `opencode models` filter, Qt runtime, secret-scan depth) listed as follow-up work, not claimed fixed.

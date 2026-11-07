# hexmind: post-audit fix plan (recon + core verification + bug hunt + critic, clean pass)

> **Implement task-by-task, in order.** Task 1 (relay.py `from =` path confinement) is the blocker: execution verified `resolve_agent_file` reads *any* locally-readable file given to `from =` with no base-dir confinement — a real data-exposure path through user-authored chain files. Decide confinement vs. documented trust boundary before anything else touches `relay.py`.

**Context:** hexmind is a Python 3.11+ multi-model agent orchestrator — one chat room, several AI models running as real CLIs — with a Textual TUI, an opt-in PySide6 GUI (`hexmind-gui`), and an opt-in headless FastAPI/WebSocket server (`--serve`). This pass covered recon, core verification (execution-checked), a recurring-bug-class hunt, strengths scouting, and a critic review; the suite baseline is **725 passed / 2 failed / 727 collected**, both failures pre-existing environmental ling-flash issues. Already solid (do not re-litigate): the conftest hermetic-home guardrail, INVARIANT S-1 (no force, no queue), `busy` derived from `BUSY_STATUSES`, the `models.publish()` in-place republication mechanism, the server loopback/auth invariant, gate enforcement, and reaping safety.

---

## Task 1 — Confine `relay.py` `from =` resolution (or document the trust boundary)

**Problem:** `hexmind/relay.py:48-64`, `resolve_agent_file`: `direct = Path(ref).expanduser(); if direct.is_file(): return direct` (line 54-56) returns *any* locally-readable file verbatim with no base-dir confinement, then `read_agent_file` reads it as stage instructions. Chain files are user-authored and tasks run as the user, so a malicious `from =` can make hexmind read any locally-readable file. Verified by execution (stage 02 + critic kickback resolution). Coverage gap: no test points `from =` at an existing out-of-tree file.

**Type:** bug fix / guardrail (data exposure) · **Priority:** High

**Files:** `hexmind/relay.py` lines 48-64 (`resolve_agent_file`); `tests/test_relay.py` (new test)

**Steps:**
1. Decide with the maintainer: (a) confine `from =` to `AGENT_DIRS` (reject paths outside the agent-file base, or to an explicit allowlist), or (b) keep out-of-tree reads and document the trust boundary explicitly in the `resolve_agent_file` docstring plus `AGENTS.md`/SKILL.md gotchas.
2. If (a): change `resolve_agent_file` so path-shaped references outside `AGENT_DIRS` return `None` / raise instead of being read verbatim; keep bare-filename lookup in `AGENT_DIRS` unchanged.
3. Add a regression test: feed an existing out-of-tree readable file through `from =` and assert it is rejected (confinement) or assert its contents are returned (documented behavior). Existing tests use only non-existent paths (`tests/test_relay.py:122`, `tests/test_models.py:361`).

**Verification:** `python3 -m pytest tests/test_relay.py -q` passes; the out-of-tree `from =` case is covered; `python3 -m ruff check .` lands no new findings vs the ~139 pre-existing baseline.

---

## Task 2 — Enforce `models.publish()` discipline with a regression test

**Problem:** Nothing mechanically forces a registry mutation through `models.publish()` (`hexmind/models.py:422-455`). Direct `REGISTRY.models` mutation leaves the import-time-derived globals `ROSTER`, `DIRECT_CMDS`, `AGENT_COLOR`, `TEXT_ONLY`, `OPT_IN`, `LOCAL_MODELS` stale → `KeyError: DIRECT_CMDS[name]` on first route. The invariant is developer-discipline only (`models.py:286-292` docstring); only `relay._cmd_profile` calls `publish()` today.

**Type:** guardrail (test) · **Priority:** Medium

**Files:** new test file (e.g. `tests/test_models_publish_discipline.py`) — no source change required unless the maintainer wants mutation hardened.

**Steps:**
1. Add a test that mutates `REGISTRY.models` directly (add a member), asserts the six derived globals are *unchanged* until `publish(REGISTRY)` is called, then asserts `publish()` republishes all six derived globals (mirroring the stage-02 experiment with `zz-test-member`).
2. Keep the in-place-mutation rationale documented in `models.py:286-292` and `publish()` (lines 422-455) — do not convert to rebinding.

**Verification:** new test passes under `python3 -m pytest tests -q`; `import hexmind.models` smoke test still shows REGISTRY = 45 names.

---

## Task 3 — Add GitHub Actions CI so the suite runs on push/PR

**Problem:** No CI config exists — no `.github/` directory at all (recon). The ~727-test suite never runs on push/PR, so regressions can merge undetected.

**Type:** CI / guardrail · **Priority:** Medium

**Files:** `.github/workflows/test.yml` (new)

**Steps:**
1. Create `.github/workflows/test.yml`: trigger on `push` and `pull_request` to the default branch; Python 3.11+; install via `uv pip install --python .venv/bin/python -e ".[qt,server,dev]"`; run `QT_QPA_PLATFORM=offscreen python3 -m pytest tests -q`.
2. Tolerate/document the two known ling-flash environmental failures (`tests/test_team.py::test_wake_puts_it_back`, `::test_sleep_and_wake_commands_round_trip`) so CI isn't red by default on machines without that model — e.g. `--deselect` them or note them as expected in a CI comment; do not treat them as regressions.

**Verification:** workflow file parses (e.g. `gh workflow view .github/workflows/test.yml` or `act`); a push/PR triggers a run; full suite baseline reproduced in CI.

---

## Task 4 — Fix SKILL.md model-count drift ("16 members" vs 45)

**Problem:** `.claude/skills/hexmind-dev/SKILL.md:17` claims "All 16 members" for `models.toml`/`models.py`, but the registry has 45 models (AGENTS.md, recon, and stage 03 all cite 45). Doc-only, low severity.

**Type:** doc fix · **Priority:** Low

**Files:** `.claude/skills/hexmind-dev/SKILL.md` line 17

**Steps:**
1. Change line 17 from "All 16 members as structured fields" to match the registry (e.g. "All roster members from models.toml (currently 45)").
2. Confirm no other place in README/docs/code cites "16".

**Verification:** `grep -rn "16 members" .claude/ skills README docs` returns no hits; SKILL.md:17 consistent with README/AGENTS.md.

---

## Task 5 — Record the ling-flash environmental baseline; do not chase as regressions

**Problem:** `tests/test_team.py::test_wake_puts_it_back` and `::test_sleep_and_wake_commands_round_trip` hard-code `ling-flash` (opencode `ling-3.0-flash-fin-free`) without mocking `Registry.available()`; `/wake` re-checks availability by design, so both fail on any machine where ling-flash is unreachable — including this one. Pre-existing, environmental, not logic bugs, not regressions. Baseline: **725 passed / 2 failed / 727 collected**. The sibling `test_waking_an_uninstalled_model_is_refused` mocks `REGISTRY.available()` and passes — that is the correct pattern.

**Type:** documentation / baseline · **Priority:** Informational (no code change)

**Files:** none to change; record here and in AGENTS.md known-failures (already present in AGENTS.md).

**Steps:**
1. Record baseline in this plan (Definition of Done and Verification sections below).
2. If a future run shows *any* failure other than the two ling-flash tests, treat it as a regression and investigate.

**Verification:** `QT_QPA_PLATFORM=offscreen python3 -m pytest tests -q` → 725 passed, exactly the two `test_team.py` ling-flash tests failed, 727 collected.

---

## Task 6 — Preserve the roadmap hooks; do not delete them

**Problem:** Static audits (e.g. Ponytail-style "delete dead code") must not remove preserved, reserved-for-unshipped-GUI-phases hooks: `qt/palette.py` `Command.haystack` (`:63`, used in `_rank` `:67-85`) and `set_commands` (`:212`, called from `widget.py:784`); `qt/graph.py` `update_task` (`:260`), `select_task` (`:314`), `clear` (`:323`), `fit` (`:328`) (all called from `widget.py:739-759`); `hexmind/notify.py:14` `notify` (called from `qt/app.py:213-216`).

**Type:** guardrail · **Priority:** Guardrail (no change unless a hook is actually removed)

**Files:** `hexmind/qt/palette.py`, `hexmind/qt/graph.py`, `hexmind/notify.py` — no edits; list here so future agents don't "fix" them away.

**Steps:** None (guardrail). If any cleanup touches these files, confirm the hooks above remain present and wired.

**Verification:** `grep` confirms all six hook symbols still present after any adjacent change; `python3 -m ruff check .` lands no new findings.

---

## Known coverage gaps

Per the critic pass (stage 05), these areas were listed as complexity hotspots in recon but were never read in depth by stages 02–04. The fix plan makes no claims about them and no tasks target them:

- `hexmind/qt/widget.py` (921 lines) — cross-thread asyncio/Qt signal boundary
- `hexmind/tui.py` (840 lines) — 40-column overflow guard / narrow layout
- `hexmind/qt/settings.py` (493 lines) — persisted roster/audit/theme preferences
- `hexmind/jules.py` (424 lines) — Google Jules cloud member

Deeply reviewed: `core.py`, `relay.py`, `backends.py`, `auditor.py`, `models.py`, `server.py`, `tests/conftest.py`.

---

## Do NOT change (audit-confirmed fine)

Future agents must not "fix" these — the audit verified them:

- `tests/conftest.py` hermetic-home guardrail (session-wide redirect of `models.USER`, `models.CATALOGUE`, `config.PATH`, relay `CHAIN_DIRS`/`AGENT_DIRS`; per-test `_no_leaked_registry_shadow` registry-shadow cleanup) — do not replace with naive per-test `monkeypatch`.
- INVARIANT S-1 (`hexmind/core.py:524-582`) — a model holding a live task cannot be slept; deliberately no force, no queue.
- `busy` derived from `BUSY_STATUSES` at every `record()`/`_sync_busy()` (`core.py:1001`, `:1024-1027`), never tracked separately.
- No default lead (`hexmind/__main__.py:63-71`) — `--once`/`--serve` require a lead; the TUI startup picker sets it.
- Server loopback/auth invariant (`server.py:571` default `127.0.0.1`; `:592-596` non-loopback host requires `--token`/`HEXMIND_TOKEN`).
- `models.publish()` in-place mutation (`models.py:422-455`) — do not rebind derived globals; mutate in place.
- Preserved roadmap hooks in Task 6 above.

---

## Definition of done

- [ ] Task 1: `resolve_agent_file` confined to `AGENT_DIRS` (or trust boundary documented); regression test added and passing.
- [ ] Task 2: publish-discipline test added and passing; derived globals republished only via `publish()`.
- [ ] Task 3: `.github/workflows/test.yml` exists and runs `QT_QPA_PLATFORM=offscreen python3 -m pytest tests -q` on push/PR; ling-flash failures tolerated/documented.
- [ ] Task 4: `SKILL.md:17` updated to 45; no remaining "16 members" references.
- [ ] Task 5: ling-flash baseline recorded; no effort spent chasing the two pre-existing failures.
- [ ] Task 6: palette/graph/notify roadmap hooks still present and wired.

---

## Verification (run after applying all fixes)

```sh
# Full suite baseline — expect 725 passed, exactly 2 failed (the ling-flash tests), 727 collected
QT_QPA_PLATFORM=offscreen python3 -m pytest tests -q

# Lint — no NEW findings vs the ~139 pre-existing baseline (no committed ruff config)
python3 -m ruff check .

# Import smoke test — registry must report 45 names
python3 -c "import hexmind.core, hexmind.relay, hexmind.backends, hexmind.auditor, hexmind.models; print(len(hexmind.models.REGISTRY.models))"
```

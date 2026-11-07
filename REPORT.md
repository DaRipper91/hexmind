# Rip-It-Apart Audit Report — hexmind

**Date:** 2026-10-17
**Repo:** /home/daripper/Projects/hexmind
**Branch at audit time:** `refactor/mission-hexmind-20261002` (remote: `https://github.com/DaRipper91/hexmind.git`)
**Auditor:** rip-it-apart audit chain (recon → core verify → bug hunt → strengths → critic → fix plan)

## What was audited

Full source audit of the `hexmind/` package plus `tests/`, `pyproject.toml`, `uv.lock`, docs, and the two instruction sources (`AGENTS.md` and `.claude/skills/hexmind-dev/SKILL.md`). Stages 1–4 deeply reviewed `core.py`, `relay.py`, `backends.py`, `auditor.py`, `models.py`, `server.py`, `conftest.py`; coverage gaps remain in `qt/widget.py`, `tui.py`, `qt/settings.py`, `jules.py` (known, listed below).

Full stage-by-stage scratch notes live in the gitignored `.audit/SCRATCH.md`. The task-by-task fix plan lives at `docs/plans/2026-10-17-rip-it-apart-fix-plan.md`.

## Headline findings (priority order)

| # | Severity | Finding | Location |
|---|----------|---------|----------|
| 1 | High / data exposure | `resolve_agent_file()` reads **any locally-readable file** from a chain's `from =` with no base-dir confinement — verified by execution (an out-of-tree `toml` file was accepted). | `hexmind/relay.py:48-64` |
| 2 | Medium | `models.publish()` discipline is developer-discipline only; direct registry mutation leaves derived globals (`ROSTER`, `DIRECT_CMDS`, …) stale → `KeyError: DIRECT_CMDS[name]` risk. No test guards this. | `hexmind/models.py` |
| 3 | Medium | **No CI workflow exists** — no `.github/` directory, so the 727-test suite never runs on push/PR. | (missing) |
| 4 | Low | Doc drift: `.claude/skills/hexmind-dev/SKILL.md:17` says "All 16 members" but the registry has **45** models (`models.toml`). | `SKILL.md:17` |
| 5 | Informational | Two pre-existing test failures are **environmental, not regressions**: `test_wake_puts_it_back` and `test_sleep_and_wake_commands_round_trip` hard-code `ling-flash` (not reachable on this machine). Baseline: 725 passed / 2 failed / 727 collected. | `tests/test_team.py` |

## What was confirmed GOOD (do not "fix" these)

- `tests/conftest.py` hermetic-home guardrail + self-tests that fail if removed
- INVARIANT S-1 (busy model can't be slept) enforced in code with `(allowed, reason)`
- `busy` derived from `BUSY_STATUSES`, never tracked separately
- No default lead (fails loudly instead of crashing missing-CLI users)
- Server loopback + token auth invariant is code, not docs
- `models.publish()` mutates globals in place (the only correct way for `from .core import ROSTER` importers)
- Preserved roadmap hooks: `qt/palette.py`, `qt/graph.py`, `notify.py` — **do not delete**

## Recommended project patches

See `docs/plans/2026-10-17-rip-it-apart-fix-plan.md` for 6 task-by-task changes, each with files, line numbers, and verification steps:

1. Confine `from =` resolution (or document the trust boundary) + regression test
2. Test proving `REGISTRY` mutation goes stale until `publish()`
3. Add `.github/workflows/test.yml` running the suite on push/PR (tolerate the 2 ling-flash failures)
4. Fix `SKILL.md:17` "16 members" → "45 members"
5. Record ling-flash baseline so the 2 failures aren't chased
6. Preserve roadmap hooks (guardrail, not a change)

## Post-fix verification

```sh
QT_QPA_PLATFORM=offscreen python3 -m pytest tests -q   # expect 725 passed / 2 failed / 727 collected
python3 -m ruff check .                                  # no NEW findings vs ~139 pre-existing
python3 -c "import hexmind.core, hexmind.relay, hexmind.backends, hexmind.auditor, hexmind.models"
```

## Coverage gaps (not reviewed in depth — review next)

- `hexmind/qt/widget.py` (921 lines, cross-thread Qt/asyncio boundary)
- `hexmind/tui.py` (840, 40-col overflow guard)
- `hexmind/qt/settings.py` (493)
- `hexmind/jules.py` (424)

# Agent Report

## Summary
Task **t3 — read-only UI/UX audit** of the hexmind Textual TUI and Qt frontend.
No source file was modified; the audit document is the deliverable.

**Created:**
- `docs/audits/UI_UX_AUDIT_2026-09-29.md` — full audit: per-facet verdict
  table for both front-ends, 10 numbered findings (F-1…F-10), 3 defects
  reproduced by execution (D-1…D-3), and 14 proposed atomic upgrades
  (`UI-1`…`UI-14`) with files/tests/cross-references so nothing is filed twice
  against the existing backlogs.
- `AGENT_REPORT.md` (this file); previous report rotated to
  `(OLD) AGENT_REPORT.md`.

**Modified:** nothing in `hexmind/`. `~/Projects/AGENTS.md` was *not* edited —
it is a protected file; its stale "No Qt front-end yet" line is raised as
**UI-13** (cross-ref backlog item 50) for the owner to fix via
`init-agent-rules.sh`.

## Feature / Task Status
- ✅ t3 audit delivered — every claim verified against the live tree (grep +
  executed repro), not taken from prior reports.
- ✅ Baseline captured before judgement: `1 failed, 723 passed, 3 skipped`
  (log: `/tmp/opencode/hexmind-baseline.txt`).
- ✅ Backlog cross-reference done — proposals that collide with existing items
  (26, 42, 43, 50, batch-roadmap line 227) are marked "attach, don't re-file".
- ❌ No implementation — explicitly out of scope for a read-only task.

## What the Next Agent Should Do First
1. Read `docs/audits/UI_UX_AUDIT_2026-09-29.md` §5 and §7 before touching UI
   code. Respect the conventions listed in §7 (one-way embedding, tokens only,
   modal/`QMessageBox` confirmation, `python3 -m pytest tests -q`).
2. **Start with UI-1.** `hexmind/qt/agentdeck_panel.py` raises
   `NameError: pyqtSignal is not defined` (line 24) on import, and
   `widget.py:531-535` imports it **unguarded** whenever `agentdeck` is
   importable — so `HexmindWidget.__init__` crashes on any machine that has
   agentdeck installed. Dormant here only because `import agentdeck` fails.
   Fix the three import faults, then guard the call site.
3. Then **UI-2 + UI-12** together: `qt/theme.py` has exactly one `:focus`
   selector (line 127, inputs only) — buttons, tabs, list items and table items
   have **no focus ring at all**, which is the most consequential accessibility
   defect found. Land the QSS fix with the test that pins it.
4. Then UI-4 / UI-5 / UI-6 (empty states, clear confirmations, TUI footer
   hints) — all small and independent.
5. Architectural decisions already made that must be respected:
   - **UI-7** must be filed as an attachment to backlog item **26**, not anew.
   - **UI-13** must go through backlog item **50**; AGENTS.md is protected.
   - **UI-4/UI-11** overlap the batch roadmap's empty-state phase — coordinate.

## Blocking Issues
- **D-1 (real crash, dormant on this machine):** `qt/agentdeck_panel.py` is
  unimportable (`pyqtSignal`/`QApplication` never imported; bogus class-body
  theme import at L42-45). Reachable unguarded from `widget.py:533`. No test
  covers `AgentdeckPanel`; backlog item 43 assumes the tab works.
- **Pre-existing test failure, NOT owned by t3:**
  `tests/test_qt_chat.py::test_direct_line_asks_primary_and_another`
  (`assert '' == 'big-pickle: answer'`). Present in the baseline before any
  work; do not attribute it to this audit.

## Build / Test Status
- Build: ✅ n/a (Python project, docs-only change; no build step run)
- Lint:  ✅ n/a (no source modified; only Markdown added)
- Tests: ❌ 1 failing / 723 passing / 3 skipping — the one failure
  (`test_qt_chat.py::test_direct_line_asks_primary_and_another`) is pre-existing
  and unrelated to t3. Full log at `/tmp/opencode/hexmind-baseline.txt`.

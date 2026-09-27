# Consolidation sort — hexmind, mobile work (CLOSED: superseded, not merged)

**Outcome:** `origin/mobile-touch-tui` (tip `44b5022`, archived at tag `archive/variant-mobile`)
was **not merged**. While this branch was being sorted, `main` independently gained its own
complete responsive-TUI implementation — commit `8f0cacb` and later — covering the same feature
with different class/method names, plus its own test suite (`tests/test_mobile_tui.py`, 10 tests)
and its own design doc (`docs/mobile-tui.md`). Attempting the merge produced 19 conflict hunks in
`hexmind/tui.py`; inspecting them showed two independently-built, competing implementations of the
same feature rather than a straightforward merge, so the merge was aborted rather than resolved
mechanically (which risked silently deleting main's already-shipped version).

Comparison confirmed nothing in `mobile-touch-tui` is missing from `main`:
- `main`'s responsive layout, breakpoints, touch-tap table selection, and help/task-detail modals
  already exist under different names (`HelpScreen`/`TaskScreen` vs. this branch's
  `HelpModal`/`TaskSheet`).
- `main`'s Termux clipboard copy is **more robust** — it's async (`@work(exclusive=True)`) with a
  timeout and proper cancellation if the sheet closes mid-copy; this branch's version is a blocking
  `subprocess.run(..., timeout=1)`.
- `main`'s own `tests/test_mobile_tui.py` and `docs/mobile-tui.md` already cover what this branch's
  `MOBILE_TUI_SPEC.md` and `tests/test_touch_matrix.py` document/test.

## Disposition
- No merge performed. `main` already has the equivalent (and in the clipboard case, better) feature.
- `archive/variant-mobile` tag should be moved to the true tip (`44b5022`, currently 2 commits
  behind) and `origin/mobile-touch-tui` deleted, since the tag preserves history either way.
  **Not done yet** — deleting a remote branch and force-moving a tag were blocked by the auto-mode
  permission classifier as destructive git operations; needs explicit approval to execute.
- No action needed on `MOBILE_TUI_SPEC.md`/`tests/test_touch_matrix.py` — they document/test an
  approach that shipped differently on `main`; safe to leave archived and unmerged.

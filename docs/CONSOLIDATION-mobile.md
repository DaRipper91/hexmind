# Consolidation sort — hexmind, mobile work

**Correction:** `archive/variant-mobile` (tag, `9a8e457`) is not the tip — `origin/mobile-touch-tui`
(`44b5022`) is two commits ahead of it (both mobile-only fixes) and is the actual superset. Sorting
against that tip instead.

Per `docs/VARIANTS-CONSOLIDATION.md` Step 2. Diff base: merge-base of `origin/main`
and `origin/mobile-touch-tui` (`a400e59`) against the branch tip.

## Files changed
`MOBILE_TUI_SPEC.md` (+277), `hexmind/tui.py` (+698/-36), `tests/test_mobile_tui.py` (+189),
`tests/test_touch_matrix.py` (+378, new)

## Sort

| Change | Bucket | Notes |
|---|---|---|
| `is_narrow`/`is_short`/`is_ultra_short` breakpoint classes + responsive CSS in `HexmindApp.CSS` | **Runtime-adaptive UI, stays in `hexmind/tui.py`** | Not split into a separate `ui/mobile/` module — it's gated inline by `update_responsive_layout()` on `on_resize`. That already satisfies the doc's "auto-detect at runtime" goal; splitting a tightly-coupled single-file Textual app into two files would add indirection without benefit. |
| `TaskTable` touch-tap row selection, `TaskSheet` modal (tap a row → full-detail sheet) | same bucket | Touch-specific, but harmless/inert on desktop — tapping works the same as clicking. |
| `HelpModal` (`?` key / touch help screen) | same bucket | New feature, useful on any platform, not mobile-exclusive. |
| `is_ascii()` (`FORCE_ASCII`/`NO_COLOR` env detection) | same bucket | Runtime env check, not a hardcoded path — no `host.toml` needed. |
| `copy_to_clipboard()` — OSC 52 escape + `termux-clipboard-set` fallback via `shutil.which` | same bucket | Soft-detects the binary; degrades silently everywhere it's absent. No machine-specific hardcoding. |
| Tab bar (Chat/Tasks), task badge count, chat replay on resize | same bucket | Needed once the layout can collapse to one column; harmless at full width. |
| `ChatLog` (re-wraps chat history on resize/rotation), `j`/`k`/`space` bindings on `TaskTable` | same bucket | Fixes chat text staying wrapped to a stale width after rotation; vim-style nav is inert on desktop. |
| `action_quit` → `self.exit()` fix on the touch quit button | same bucket | Was calling a method that didn't exist as written; harmless-looking but would have thrown at runtime on tap. |
| `MOBILE_TUI_SPEC.md` | **docs** | Design rationale — keep under `docs/`. |
| `tests/test_mobile_tui.py`, `tests/test_touch_matrix.py` | **tests** | New coverage (the latter is a pilot-mode acceptance matrix for phone sizes/taps/keys/resize), no changes needed. |

## Buckets not used
No core-logic bug fixes, no big-RAM/multi-monitor/host-profile code, nothing hardcoded to a specific
machine, nothing to drop — the whole change set is inert-on-desktop, additive UI.

## Recommendation
Merge as-is into `main`, no restructuring needed. Low conflict risk: `main` is currently 18 commits
ahead of this branch's base in unrelated areas (backends/members), all in different files.

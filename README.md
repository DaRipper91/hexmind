# Hexmind

A multi-model agent team in one chat room. You type a request once; the lead agent
decides which model is best for each piece, splits the work into a task chain, and the
team runs independent tasks at the same time and later phases after the earlier ones.

```
hexmind                         # open the TUI room in the current folder
hexmind --without codex         # leave an agent out (e.g. usage limits)
hexmind --lead agy              # let agy plan instead of claude
hexmind --cwd ~/Projects/foo    # folder the team works in
hexmind --once "request"        # headless: one request, print results
```

Team: `claude`, `agy`, `codex` (whichever CLIs are installed). Strengths live in
`ROSTER` in `hexmind/core.py`; the lead reads them when assigning tasks.

TUI keys: `enter` send · `ctrl+l` clear chat · `ctrl+q` quit. Arrow through the task
board to see each task's instructions and full output.

## Backends

- `--backend direct` (default): hexmind runs each CLI in print mode itself. No hcom needed.
- `--backend hcom`: phase 2 — agents live in hcom, optionally in visible split terminals.

## Roadmap

1. ✅ Core task chain + direct backend + TUI
2. hcom backend + split-terminal mode
3. Jules as a team member (via Nexus `nexus_jules_hcom.py`)
4. PySide6 GUI

Tests: `python3 -m pytest tests`

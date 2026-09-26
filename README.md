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

## Relay chains

A chain is an ordered list of stages. Each stage is done by a different model, which reads
every earlier stage's report (Hexmind keeps them in `.hexmind/runs/<run>/chain-X.md`).
Run several chains at once and the stages rotate across models, so all of them stay busy
and every model does every kind of stage somewhere.

```
/relay feature --goal "add CSV export" --assign pinned   # a saved chain
/relay rip-it-apart x3                                   # 3 audits, stages rotated across models
/relay "migrate the config to TOML" -n 2 --end compare   # lead designs the stages
/chains                                                  # list saved chains
```

| option | values |
|---|---|
| `-n` / `xN` | how many chains run in parallel |
| `--assign` | `rotate` (default) · `best` (lead picks per stage) · `pinned` (stage's `agent =`) |
| `--workspace` | `shared` · `worktree` (own git worktree + branch per chain; default when `-n > 1` in a git repo) |
| `--end` | `merge` (default, one combined result) · `compare` · `list` |

Chain files live in `~/.config/hexmind/chains/*.toml` (yours win) and `hexmind/chains/`.
A stage has `name` plus `instructions`, or `from = "<agent file>"` to import a Claude
(`.md`) or Codex (`.toml`) agent's instructions, and optional `agent =` for pinning.

## Backends

- `--backend direct` (default): hexmind runs each CLI in print mode itself. No hcom needed.
- `--backend hcom`: phase 2 — agents live in hcom, optionally in visible split terminals.

## Roadmap

1. ✅ Core task chain + direct backend + TUI
2. ✅ Relay chains (any workflow, N chains, rotating models)
3. hcom backend + split-terminal mode
4. Jules as a team member (via Nexus `nexus_jules_hcom.py`)
5. PySide6 GUI

Tests: `python3 -m pytest tests`

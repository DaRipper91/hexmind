# AGENTS.md

Hexmind is a Python 3.11+ package: a multi-model agent orchestrator where a lead model plans a
task graph, tasks fan out across real AI CLIs, and a peer auditor reviews each task. Three
surfaces share one `Orchestrator`: the Textual TUI (`hexmind`), the opt-in PySide6 GUI
(`hexmind-gui`), and a headless FastAPI/WebSocket server (`hexmind --serve`).

Read these when you need depth — don't duplicate them:
- `README.md` — behaviour, room commands, flags.
- `docs/plans/BUILD-PATH.md` — what is actually shipped vs planned, re-derived from the code
  (trust it over README prose when they disagree).
- `.claude/skills/hexmind-dev/SKILL.md` — the full conventions/invariants/traps list. It is also
  auto-loaded as the `hexmind-dev` skill.

## Commands

```sh
pip install -e ".[dev,qt,server]"      # base install is the TUI only; Qt/server/dev are opt-in extras
uv pip install --python .venv/bin/python -e ".[qt,server,dev]"   # for a fresh .venv (uv.lock is present)

QT_QPA_PLATFORM=offscreen python3 -m pytest tests -q   # FULL suite, ~2 min — run this, not just your file
python3 -m pytest tests/test_relay.py -q               # one file
python3 -m ruff check .                                # no committed config; compare before/after, land no NEW findings
```

- Qt tests `importorskip` PySide6, so a green run can still mean the widget was never exercised.
- No ruff/formatter config is committed on purpose (pre-existing findings are tolerated). Match
  surrounding style; do not add one unless asked.
- Always run the **full** suite: `tests/test_mobile_tui.py` asserts no widget overflows the
  terminal, so a new control in a narrow bar can break at 40 columns.

## Known test failures — environment-dependent, do not chase

`tests/test_team.py::test_wake_puts_it_back` and `::test_sleep_and_wake_commands_round_trip`
hard-code `ling-flash` and do **not** mock `Registry.available()`. `/wake` re-checks availability
by design, so both fail on any machine where `ling-flash` (opencode model
`ling-3.0-flash-fin-free`) is not reachable — including this one. This is pre-existing (the test
file is an ancestor of `main`), not a regression. The sibling refusal test monkeypatches
`REGISTRY.available`; copy that pattern instead of "fixing" the registry.

Baseline without ling-flash: **725 passed, 2 failed, 727 collected.**

## Source of truth and layout

- `hexmind/models.toml` is THE roster (45 models; `jules`, `qwen`, `qwen-large` are opt-in via
  `--with`). `models.py` generates the prose the lead reads, the per-CLI argv, the TUI colours
  and the hcom exclusion from it. **Never hand-write prose about a model — edit `models.toml`.**
  `test_roster_is_generated_from_the_registry_not_hand_written` guards this.
- `core.py` `Task`/`Orchestrator`/plan parsing/task graph/team state · `relay.py` chains, `from =`
  resolution, all `/commands` · `auditor.py` peer audit + `Stats` rankings · `backends.py`
  direct/hcom/ollama + process-group cleanup · `tui.py` Textual room · `server.py` headless
  daemon · `reaping.py` `/relay clean` · `qt/` the PySide6 suite.
- Entrypoints: `hexmind` → `hexmind/__main__.py:main`; `hexmind-gui` → `hexmind/qt/app.py:main`.

## Gotchas an agent would otherwise get wrong

- **Invariants that break the product** (full detail in the `hexmind-dev` skill): the roster is
  generated, never hand-written; **INVARIANT S-1** — a model holding a live task cannot be slept
  (no force, no queue); `Orchestrator.busy` is *derived* from `BUSY_STATUSES`, never tracked;
  runtime registry changes must go through `models.publish()`, because `ROSTER`, `DIRECT_CMDS`,
  `TEXT_ONLY`, `OPT_IN`, `LOCAL_MODELS`, `AGENT_COLOR` are computed once at import and bound by
  name in other modules; `HexmindWidget` must never call `QApplication.setStyleSheet` or touch the
  app palette; the server refuses a non-loopback `--host` without `--token`/`HEXMIND_TOKEN`.
- **Preserved roadmap hooks — static audits (e.g. Ponytail) must NOT delete them:**
  `qt/palette.py: set_commands` & `Command.haystack`; `qt/graph.py: select_task, fit, clear,
  update_task`; `notify.py`. They are reserved for unshipped GUI phases.
- **A relay `gate = true` stage only gates when peer audit is on** (`--audit` / `/audit on`);
  without it, gates are inert. An unresolved failure fails the stage and skips its dependents.
- **opencode specifics:** sessions are directory-bound — resuming one from another cwd *hangs*
  with no error, so key sessions by `(model, directory)`. `opencode run` reads the prompt from
  stdin (no argv ceiling), unlike `kimi`, whose `-p` takes it as an argv token. Do not pass
  `--pure`. Only the default opencode model is reachable over the `hcom` backend.
- **`--lead` has no default on purpose**; a session blocks on the startup picker until one is
  chosen, and `--once`/`--serve` require it.
- Long chains (TDD stages) can exceed the 30-min default: `hexmind --timeout 5400`.

# Session Report — 2026-09-28

Everything reported and decided in the 2026-09-28 Claude Code session on Hexmind, kept in one
place. The planning documents it produced are in `docs/plans/`. See [Index](#index) at the end.

---

## 1. Local vs remote review (start of session)

The remote was fetched first. Local `main` was **3 commits ahead of `origin/main`, 0 behind** (no
divergence), with a large uncommitted working tree.

| | Remote `origin/main` | Local `main` |
|---|---|---|
| HEAD | `e802d74` feat(qt): advanced room | `07e7394` feat(ws): origin check + opt-out |
| Commits ahead | — | 3 (`01be4ac`, `c88a5eb`, `07e7394`), +4341/−73 across 20 files |
| Uncommitted | — | 15 files, +260/−53 (the 2026-09-28 audit fixes) |
| Untracked | — | 7 files (audit reports, fix plan, WS auth design/status, `tools/serve_tui.py`) |
| Tests | — | 616 passed |

**Problems found in the unpushed work before pushing:**
1. **`QUOTA_RE` got looser in one place and tighter in another.** A bare `429` matched any number
   containing 429 (line numbers, IDs), which would wrongly reassign tasks. It had also dropped real
   billing phrases, so some genuine quota errors were no longer caught.
2. **`BUILD-PATH.md` credited the audit fixes to `bd0e7ce`**, a commit that was already on the
   remote and didn't contain them.
3. **`WS_AUTH_FIX_STATUS.md` said "Design only. No code changed"**, but WS auth was already
   implemented in `c88a5eb` and `07e7394`.
4. **Audit documents were in odd places.** Two were inside the `hexmind/` package and one was at
   the repo root. `.audit/` scratch notes were untracked.

## 2. What was fixed and pushed

| Commit | Change |
|---|---|
| `0d5755f` | Server binds `127.0.0.1` by default; `--token` flag |
| `4b3b6ff` | `parse_plan` repairs show up as findings; `QUOTA_RE` restored to `\b429\b` and billing phrases (with a regression test) |
| `a94a9a4` | Jules: exact session-state sets and exact pushed-branch match; swallowed errors are logged |
| `d407ba3` | `Model.ref` passes the opencode `#variant` (later found to break both opencode members, see §3) |
| `4fb60e3` | Corrupt stats are backed up; relay marker failures logged; TUI team bar refreshes; doc-chain example paths fixed |
| `e20f647` | Audit docs moved to `docs/audits/`; status doc corrected; `.audit/` added to `.gitignore` |
| `7921451` | `BUILD-PATH.md` row points at the real commits |
| `9468a39` | **`hexmind-gui` ignored every flag.** It parsed `--lead/--without/--with/--audit/--cwd`, then built `HexmindWindow()` without passing them on |
| `08a3fc0` | **Both opencode members failed on every call.** See §3 |
| `49e35ca` | The server **refuses** a non-loopback host without a token. Before, it only printed a warning |
| `6e61f18` | `ruff --fix`: lint went from 36 errors to 10 |
| `e7d9ba3` | opencode members renamed (§4) |
| `1a6c9ab` | GUI roadmap and idea docs |

The final state is **619 passed**, and local and remote are in sync.

## 3. Bugs found by live checks, not by tests

- **opencode variants.** `d407ba3` appended `#high` and `#minimal` to the opencode model IDs.
  opencode 2.0.18 answers `Variant unavailable` for both nemotron models, so every call failed. The
  tests passed because one of them read the user's personal
  `~/.config/hexmind/models.toml` (it contained a hand workaround). The fix removed both variants
  from the bundled registry, and the test now builds its own synthetic model.
  **Rule:** don't declare a variant until `opencode run -m id#variant` works live.
- **`ling-flash` (`opencode/ling-3.0-flash-fin-free`)** fails with
  `Upstream request failed: Endpoint is unavailable`. It fails the same way when opencode's ID is
  called directly, so this is a provider outage, not a naming issue.
- **`hexmind-gui` was not a command.** The pipx install predated the GUI entry point and had never
  installed the extras. It was reinstalled with
  `pipx uninstall hexmind && pipx install --editable ".[qt,server]"`, because pipx's `--force`
  failed on its uv backend. **The README should tell users to install with `[qt,server]`.**

## 4. opencode member rename (`e7d9ba3`)

The user's rule: use readable names, and fall back to opencode's ID if a name causes errors. None
did.

| Old | New | opencode ID (unchanged) |
|---|---|---|
| `opencode` | `nemotron-lightning` | `opencode/nemotron-3.5-lightning-free` |
| `opencode-ultra` | `nemotron-ultra` (default lead) | `opencode/nemotron-3-ultra-free` |
| `opencode-muse` | `muse-spark` | `opencode/muse-spark-1.3-contributor-free` |
| `opencode-mimo` | `mimo-flash` | `opencode/mimo-v2.6-flash-free` |
| `opencode-pickle` | `big-pickle` | `opencode/big-pickle` |
| `opencode-ling` | `ling-flash` | `opencode/ling-3.0-flash-fin-free` |
| `opencode-bunny` | `space-bunny` | `opencode/space-bunny-free` |
| `opencode-longcat` | `longcat-preview` | `opencode/longcat-2.5-preview-free` |

- **Why two names.** The member name is what you type (`--lead`, `/add`, `@mentions`, nicknames),
  and it keys the audit ledger. The ID is only passed to `opencode -m`. When a free model is
  replaced, you edit one `model =` line and the member keeps its history.
- **hcom** can only drive the `opencode` tool's default model. That member is now
  `nemotron-lightning`.
- **Dated documents** (audits, plans, `BUILD-PATH.md`, `model-updates.md`) keep the names of
  their time.
- **User overlay.** `~/.config/hexmind/models.toml` said `[models.opencode-ultra]`, which stopped
  the registry from loading after the rename. It was changed to `[models.nemotron-ultra]`, with a
  backup at `models.toml.bak-20260928`. Its override is redundant now and the file can be deleted.

## 5. Open items at end of session

- **Lint:** 10 minor errors (unused variables, variables named `l`, an import not at the top of a
  file, a lambda assigned to a name). None are real bugs.
- **Not verified live:** the WebSocket server with a client, the GUI in real use, a full
  multi-agent round, and Jules session-state names against the real API.
- **README:** document `pipx install --editable ".[qt,server]"`.
- **CLI health view:** planned as "show plus one-click fixes in a visible terminal" (D3 in the
  roadmap). The user didn't choose an option, so this can still change.

## 6. GUI flagship planning

The user's direction: **the GUI is the flagship**, the TUI is featureless and out of scope. They
want more interaction with the models and all setup settings in the GUI.

Two idea passes were run in parallel, and their key claims were spot-checked against the code:
- **Technical: `rip-it-apart-feature-forge`** → `docs/plans/2026-09-28-gui-feature-forge.md`.
  Its main point is that the orchestrator knows much more than the GUI shows. Top ideas: live
  output streaming (Live tap), Hand brake (cancel), Relay Runs desk, room-as-protocol.
- **Visuals/UX: `feature-ideator`** → `docs/plans/2026-09-28-gui-ux-ideas.md`. It lists 17
  observed UX problems (P1–P17); the confirmed ones include the lying lead combo, the audit box's
  starting state, and the greyed-out palette item. Its top ideas: Honest Instruments, Live Wire,
  Bench Rail, Bench Settings.

**Decisions recorded:**

| # | Decision |
|---|---|
| D1 | One shared `~/.config/hexmind/config.toml`, read by `hexmind`, `--serve` and `hexmind-gui`; flags override it |
| D2 | 1:1 chat is separate per model, with history and "Send to room" |
| D3 | CLI health shows problems plus safe one-click fixes in a visible terminal (default; user didn't choose) |
| D4 | The model manager writes only the user overlay, never the bundled registry |
| D5 | The TUI is out of scope |

The result is **`docs/plans/2026-09-28-gui-flagship-roadmap.md`**: 10 phases. Phases 0–2 are
written out as full test-first steps. Phases 3–9 are task specs, to be expanded with
`writing-plans` right before each is built.

---

## Index

| Document | What |
|---|---|
| `docs/reports/2026-09-28-session-report.md` | this report |
| `docs/plans/2026-09-28-gui-flagship-roadmap.md` | **the roadmap and build guide** |
| `docs/plans/2026-09-28-gui-feature-forge.md` | technical idea pass |
| `docs/plans/2026-09-28-gui-ux-ideas.md` | UX idea pass, P1–P17 |
| `docs/plans/2026-09-28-hexmind-fixes.md` | the audit fix plan (11 tasks) behind §2 |
| `docs/audits/ARCH_SECURITY_AUDIT.md`, `ARCH_SECURITY_AUDIT_T2B.md` | architecture/security audits |
| `docs/audits/WS_AUTH_FIX_DESIGN.md`, `WS_AUTH_FIX_STATUS.md` | WebSocket auth design and status |

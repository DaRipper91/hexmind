# Hexmind Architecture & Security Audit — T2B (Remaining Modules)

**Scope**: `hexmind/server.py` (440 lines), `hexmind/tui.py` (840), `hexmind/reaping.py` (192), `hexmind/jules.py` (424), `hexmind/config.py` (28), `hexmind/notify.py` (35), `hexmind/__main__.py` (142), `hexmind/qt/widget.py` (600), `hexmind/qt/graph.py` (326), `hexmind/qt/theme.py` (223) — everything under `hexmind/` except `core.py`, `relay.py`, `models.py` (audited in t2a) and `auditor.py`/`backends.py` (t2a §1.4–1.5).
**Date**: 2026-09-28
**Code state**: working tree at/after `bd0e7ce` (14 modified files vs HEAD — several t2a-scratch findings are already fixed here; see §6).

---

## 0. Execution Logs

### 0.1 opencode-ultra — t2/t2a failure record (team-lead handoff)

| Run | Model | Outcome |
|-----|-------|---------|
| t2 (full audit) | opencode-ultra | **exit 1** after 4x `[504] Upstream idle timeout exceeded` |
| t2a (core.py, relay.py, models.py) | opencode-ultra | 3x `[504]`; partial output only; **no findings for skipped modules** |

Net effect: `ARCH_SECURITY_AUDIT.md` (t2a, 306 lines) covers only `core.py`, `relay.py`, `models.py`. The remaining modules (server, TUI, reaping, jules, config, notify, `__main__`, `qt/*`) have no findings in t2a — not because they are clean, but because they were never reached before the upstream timeouts killed the run. This t2b run closes that scope gap.

### 0.2 opencode-longcat — t2b run log (this run)

- **Model**: opencode-longcat (provider `opencode`, model ID `longcat-2.5-preview-free`)
- **Exit code**: 0 (every tool call succeeded)
- **Duration**: ~15 min wall clock, ~40 tool calls (22 file reads, 9 grep, 9 shell — many parallel)
- **Timeouts**: none
- **stderr**: empty on every command
- **stdout tail** (representative, complete command list):
  ```
  $ ls -la hexmind/                     → 14 modules + qt/ + chains/ + models.toml + ARCH_SECURITY_AUDIT.md
  $ ls .audit/history/                  → SCRATCH-2026-09-28.md (35 KB, t2a scratch)
  $ git log --oneline -15               → bd0e7ce HEAD; 14 modified, 8 untracked in working tree
  $ grep -n "def test" tests/test_server.py → 12 tests (status/chains/stats/nicknames/ws×2/approve×3/discard×3)
  $ grep "check_origin|origin" server.py → only CORS allow_origins (localhost); NO WS origin check
  $ grep "textual" pyproject.toml        → textual>=0.80
  $ grep "stats is not None" core.py    → core.py:1045 (audit requires stats)
  $ grep "reaping|active_runs" relay.py → relay.py:824/857/883 (clean → classify → remove_one)
  $ grep "jules" backends.py            → backends.py:160-162, 356-358 (agent=="jules" → run_jules)
  ```
- No agent subprocess was spawned; all evidence gathered by direct file read + grep + ls. No live backend / Jules API / Qt harness runs — verification is static (code read) only, disclosed per finding where relevant.

---

## 1. Architecture Findings

### 1.1 Headless Server (server.py:1-440)

#### Request Surfaces
| Surface | Auth | Busy guard | Location |
|---------|------|-----------|----------|
| `GET /api/status`, `/api/history`, `/api/chains`, `/api/stats` | token if set | n/a | server.py:278-341 |
| `POST /api/prompt`, `/api/approve`, `/api/discard`, `/api/config/nicknames` | token if set | 409 on busy | server.py:290-348 |
| `WS /ws/room` | **none — even when token set** | in-band error message | server.py:350-397 |

**Finding A8: Token auth is opt-in and does not cover the WebSocket** (server.py:270-276, 350-397)
`auth_middleware` only fires when `server._token` is non-empty **and** only for paths starting with `/api/`. The default token is `""` (server.py:126, 432), so by default the entire server — REST and WS — is unauthenticated. Worse, even when `HEXMIND_TOKEN` is set, `/ws/room` is exempt: the middleware's `startswith("/api/")` guard skips it. A client that cannot call `POST /api/prompt` can drive the identical orchestrator path via `{"action":"prompt","text":...}` on the WS with no credential at all.

**Finding A9: No origin checking on the WebSocket** (server.py:350-397)
Starlette accepts WebSocket connections from any origin by default; there is no `check_origin` anywhere in the file (grep: zero matches). Browsers do not enforce CORS on WebSocket handshakes, so any web page the user visits can open `ws://127.0.0.1:8765/ws/room` and — combined with A8 — submit prompts that drive every agent in the room with full read/write access to `server.cwd`. This is the highest-severity finding in this audit.

**Finding A10: Fire-and-forget task management loses exceptions** (server.py:297-299, 307-309, 374-378)
`post_prompt`, `post_approve`, and the WS `prompt`/`approve` actions all do `asyncio.create_task(...)` and return immediately. `server.current_run_task` is overwritten by each new task and never awaited; a raising task's exception is never retrieved (asyncio logs "Task exception was never retrieved" at GC time). The WS done-callbacks (server.py:375-378, 382-385) send the error to the one websocket that started the task, but REST callers get `{"status":"started"}` and no error channel. `approve_pending` even raises `HTTPException(400)` internally (server.py:232) which, on the fire-and-forget path, never reaches the client.

#### Improvements over the t2a scratch audit (already fixed in this tree)
- CORS is **localhost-only**, not `*`: `origins = [f"http://127.0.0.1:{server._port or 8765}", "http://localhost:8765"]` (server.py:261-268).
- Default bind is **127.0.0.1**, not 0.0.0.0 (server.py:403), with explicit warnings when 0.0.0.0 is used, with or without a token (server.py:416-419, 434-436).
- `approve_pending` **does** forward `pending_directives` and clears them (server.py:235, 242) — the scratch audit's "silently drops directives" finding is fixed, and `tests/test_server.py` now has 12 tests including `test_approve_with_directives_clears_pending_directives` (tests/test_server.py:119-129).

**Finding A11: Token comparison is not constant-time** (server.py:274)
`provided != f"Bearer {server._token}"` is a plain string compare. Timing oracle against a loopback token is a theoretical vector; recorded for completeness.

**Finding A12: Info disclosure via status/chains endpoints** (server.py:182-203, 318-333)
`GET /api/status` returns the full roster (`all_roster: ROSTER`), pending plan contents, and nicknames; `GET /api/chains` returns absolute filesystem paths of every chain file. Low impact on a trusted network, but it hands a remote client the server's directory layout.

### 1.2 Textual TUI (tui.py:1-840)

#### Turn Serialization & Startup
| Mechanism | Implementation | Location |
|-----------|----------------|----------|
| One request at a time | `asyncio.Lock` + `@work(group="turns")` | tui.py:523, 738-747 |
| No-lead gate | modal `LeadPicker`, blocking; re-arms on next request | tui.py:340-454, 568-597, 722-727 |
| Team changes | all verbs route through `Orchestrator` (re-checks `can_sleep`) | tui.py:315-330 |

**Finding A13: Team-bar markup string is built from nicknames** (tui.py:806)
`refresh_team` builds `f"[{AGENT_COLOR.get(m, 'white')}]{dot} {self.orch.name(m)}[/]..."` and hands it to `Static.update()`. Textual `Static` renders markup by default, and `orch.name()` returns the raw nickname (core.py:621-623). A nickname containing `[/][bold]…[/]` injects arbitrary Rich markup into the team bar. The nickname source is the user's own `config.toml` (self-XSS) **or** `POST /api/config/nicknames` (server.py:343-348) — i.e. any client that can reach the server can inject markup into the user's TUI. Same root cause as t2a T10; this is the server-side vector.

**Finding A14: Untrusted model output rendered as Markdown into a markup-enabled log** (tui.py:548, 702-714, 828-836)
`RichLog(id="chat", markup=True)` and `say()` writes `Markdown(text)` for every non-user speaker; `write_task` writes `Markdown(t.output)`. Rich's Markdown renderer turns `[text](url)` into a link (OSC 8 hyperlink on capable terminals). Model output is untrusted (t2a T1), so a model can emit links/emphasis that render as clickable terminal escapes. Impact is terminal-only and requires a user click — Low.

**Finding A15: Declined-lead request text is discarded** (tui.py:722-727)
`on_input_submitted` calls `self.ask_lead(); return` — the user's request is neither run nor queued; they must retype after picking a lead. Documented as deliberate ("not lost and not run") but it is a one-message data loss. Low.

**Finding A16: `termux_copy` is the one place a subprocess is spawned from the TUI** (tui.py:104-115)
`termux-clipboard-set` via `create_subprocess_exec` with a 5 s `wait_for` and `kill()` in `finally`. Correctly bounded; no finding beyond noting it as the only TUI→OS bridge.

#### Fixed since the t2a scratch audit
- **Stale team bar after `/add` `/remove` is fixed**: `on_team_event` now does `self.members = list(self.orch.members)` (tui.py:764-765).

### 1.3 Reaping (reaping.py:1-192)

#### Classification Pipeline (reaping.py:127-165)
```
active run? → ACTIVE | gone? → MISSING | broken .git link? → DIRTY
→ unreadable status? → DIRTY (never SAFE) | dirty files? → DIRTY (names them)
→ unmerged commits? → UNMERGED (names them) | else → SAFE
```

**Finding A17: Fail-safe classification is the module's core strength** (reaping.py:140-158)
Every failure direction resolves to DIRTY/left-alone, never SAFE — including the subtle case where a broken `.git` link makes git report the *parent* repo's clean status; `worktree_is_itself()` re-asks git for `--show-toplevel` to catch it (reaping.py:56-73). `remove_one` uses no `--force`/`-D`, so git's own dirty/unmerged refusals are the backstop (reaping.py:175-192). The module docstring records the real incident (committed sources, tests left behind on a zero-unmerged-commits branch) that motivated the design.

**Finding A18: Narrow fail-unsafe window in `unmerged_commits`** (reaping.py:93-99)
`unmerged_commits` returns `[]` on `GitUnavailable`. If `git log` fails *after* `status` succeeded, a branch with unmerged commits would classify SAFE. Backstopped by `git branch -d` refusing unmerged branches in `remove_one` (reaping.py:186-191) — the second-opinion design the docstring promises. Low.

**Finding A19: `git()` is the correct subprocess pattern** (reaping.py:42-53)
argv list, `capture_output`, `timeout=20`, `stdin=DEVNULL`, raises `GitUnavailable` on any failure with the failing command and root in the message. No shell anywhere in the module.

### 1.4 Jules Integration (jules.py:1-424)

#### Execution Path
`backends.py:160-162 / 356-358` special-case `agent == "jules"` → `jules.run(prompt, cwd)` → `get_github_repo` (git remote origin must be github.com) → `get_starting_branch` → `create_session(AUTO_CREATE_PR)` → poll `get_session` → `fetch_activities` → return last Jules message + PR URL. Jules executes on the **remote GitHub repository**; local files are not modified (jules.py:419-422).

**Finding A20: State-enum handling is exact-set, learned from a real incident** (jules.py:26-39, 363-387)
The module docstring records that a substring `"AWAITING" in state` test missed the real API value `AWAITING_USER_FEEDBACK` and spun to timeout. Current code uses three frozensets (`_TERMINAL_STATES`, `_AWAITING_INPUT_STATES`, `_IN_PROGRESS_STATES`) with exact membership, plus an explicit "unrecognised state → keep polling but log" branch (jules.py:382-387). This is the correct fix pattern for opaque cloud enums.

**Finding A21: Poll loop bounds are sensible** (jules.py:339-390)
20 consecutive poll errors → `RuntimeError` with the last error (jules.py:354-357); backoff `2.0s × 1.5` capped at 15 s (jules.py:389-390); overall timeout 14400 s (4 h) (jules.py:346-348). Awaiting-input states fail fast with the session URL instead of polling to timeout (jules.py:376-381).

**Finding A22: API key handling is env-only** (jules.py:146, 320-322)
`JULES_API_KEY` read from env, sent as `X-Goog-Api-Key` header, never written to disk; `run()` raises if unset. `urllib` with default SSL verification, 30 s timeout, argv/headers only.

**Finding A23: Query params are not URL-encoded** (jules.py:142-144)
`query = "&".join(f"{k}={v}" for k, v in params.items())` — values are interpolated raw. Today's params (`pageSize`, `pageToken`) are Google-issued tokens, but a `pageToken` containing `&`/`=` would corrupt the query string. Low.

**Finding A24: `session_id` interpolated into URL paths** (jules.py:186-202, 335)
`f"sessions/{session_id}/activities"` — the id comes from the API response. Not attacker-controlled in practice (Google-issued), but there is no format validation. Low.

#### Fixed since the t2a scratch audit
- `get_starting_branch` pushed-branch check is now an **exact set match** (`pushed_heads` built from `ls-remote` lines, jules.py:97-103), not the substring `current in check_pushed.stdout` the scratch audit flagged.
- `_AWAITING_KINDS` check is exact set membership (jules.py:286-293), not `"awaiting" in kind.lower()`.

### 1.5 Config & Notify (config.py:1-28, notify.py:1-35)

**Finding A25: `save_nicknames` writes TOML via `json.dumps`** (config.py:23-28)
`f"{k} = {json.dumps(v)}"` — JSON string escaping is *mostly* TOML-compatible (both use `\"`, `\\`, `\n`, `\uXXXX`), so round-trips work for typical nicknames. Edge cases (TOML multi-line literals, literal strings) are not handled, and a nickname like `a"b` round-trips fine while exotic control-char escapes could produce a TOML the loader reads back differently. Low. `load_nicknames` fails safe to `{}` on missing/corrupt file (config.py:19-20).

**Finding A26: `notify` is a model never-raises phone ping** (notify.py:14-35)
`kdeconnect-cli` resolved via `shutil.which`, argv list, 5 s timeout per call, `stdin=DEVNULL`, every failure path returns 0. Correct best-effort design.

### 1.6 Entry Point (__main__.py:1-142)

**Finding A27: No default lead — headless surfaces require `--lead`, the TUI asks** (__main__.py:47-60)
The comment records the incident: a hardcoded `opencode-ultra` default made hexmind refuse to start for anyone without the opencode CLI. `--once`/`--serve` exit with the installed-member list if `--lead` is missing; the TUI defers to the startup picker. TEXT_ONLY and unknown leads are rejected with actionable messages.

**Finding A28: `--serve` dependency guard spans the call, not just the import** (__main__.py:73-98)
`run_server` imports uvicorn lazily, so the `try/from .server import run_server` guard catches a missing server extra and exits with `pip install 'hexmind[server]'` instead of a bare traceback.

**Finding A29: `--token` help text over-promises** (__main__.py:35-36 vs server.py:434-436)
Help says the token is "required if host is 0.0.0.0", but `run_server` only *prints a warning* and binds anyway. Either enforce or fix the text. Low (doc mismatch).

### 1.7 Qt Front-End (qt/widget.py:1-600, qt/graph.py:1-326, qt/theme.py:1-223)

#### Threading Architecture (qt/widget.py:106-151)
`_Room` is a `QThread` with its own asyncio loop holding the `Orchestrator`; the widget only sends text/lead changes and receives Qt signals (queued by Qt onto the GUI thread). `_LIVE_ROOMS` weakset + `atexit` hook stops live rooms (widget.py:99-105); `stop()` is idempotent and tolerates an already-closed loop (widget.py:211-231) — the docstring records the real "QThread destroyed while running" abort this defends against.

**Finding A30: Turns are serialized by dropping, not queueing** (widget.py:158-168)
`submit()` checks `_turn_in_flight` under `_orch_lock` and **returns** if a turn is running — the second send is silently discarded (no signal, no error). This fixes the scratch audit's "two concurrent `orch.handle` coroutines" finding, but replaces it with a silent drop. `change_lead` drops the same way (widget.py:170-177). Low (availability/UX).

**Finding A31: `snapshot()` is defined twice; the second wins** (qt/widget.py:179-189 vs 233-245)
Two methods with the same name; Python keeps the second. The live version takes `_orch_lock` only around the `all_tasks` copy — `lead`/`members`/`known`/`busy` are read lock-free from the GUI thread while the room thread mutates them. GIL makes this usually benign; mutation-during-iteration can raise `RuntimeError` on the GUI thread. Low.

**Finding A32: The audit checkbox is wired but inert — the Qt orchestrator has no Stats** (qt/widget.py:286, 297-300; core.py:457, 1045)
The scratch audit found the checkbox decorative (no `stateChanged` connection). It is now connected (`self.auditBox.stateChanged.connect(self._on_audit_toggle)`, widget.py:286) and the handler sets `orch.audit = state == 2`. **But** `_Room` constructs `Orchestrator(backend, list(members), lead, emit=self._emit, audit=audit)` with no `stats=` (widget.py:130), and `Orchestrator.__init__` defaults `stats=None` (core.py:457). `core.py:1045` gates audited runs on `self.audit and self.stats is not None` — so with `stats=None`, toggling the checkbox changes a flag that does nothing. The user believes peer audit is on; it is not. Low-Medium (integrity of a safety-relevant control).

**Finding A33: Model output rendered as Qt Markdown in the detail pane** (qt/widget.py:448-456, 479-498)
New in this tree: `_on_message` renders the latest room message via `self.detail.setMarkdown(f"**{label}**\n\n{text}")` and `_on_task_selected` renders the selected task's title/instructions/output the same way. The text is model-controlled (t2a T1). Mitigations present: `setOpenExternalLinks(False)` (widget.py:356) stops link auto-opening, and Qt Markdown is a no-script subset — but styling/spoofing of the detail view is possible. Low.

**Finding A34: Task-title path heuristic emits to the host** (qt/widget.py:66-75, 513-521)
Double-clicking a task whose title ends in a pathish token (`foo/bar.py`) emits `openFileRequested` to the host app. The heuristic is deliberately conservative (requires a separator and a code-ish extension), but the title is model-generated text, so a model can make the host open an arbitrary path the user double-clicks. The comment ("Guessing here would open nonsense in the host editor") acknowledges the tradeoff. Low.

**Finding A35: Graph tooltips no longer carry model output (fixed); layout is now recursive** (qt/graph.py:50-113, 149-159)
The rewritten graph panel's `Node` tooltip is only `f"{id} · {status}"` (graph.py:155, 159) and `Edge` has no tooltip — the old tooltip-HTML-from-model-output surface is gone. **However**, `compute_layers` is now a recursive `d(tid)` (graph.py:61-73): the previous version used an explicit stack with a comment explaining that "a relay chain can be hundreds of tasks deep and recursion would hit Python's limit on a legitimate plan." The rewrite regressed that — a deep plan raises `RecursionError` in the graph panel (opt-in Qt surface; the TUI is unaffected). Low-Medium (availability).

**Finding A36: Graph layout is deterministic; edges only drawn when both endpoints exist** (qt/graph.py:123-137, 214-234)
`layer_positions` sorts by (depth, id) — stable across runs; `set_tasks` skips edges whose dependency is not in the scene ("a wire to a node that does not exist is a lie about causality" — the comment survives the rewrite). `set_tasks` rebuilds per plan; `update_task` mutates nodes in place per status event. Sound design.

**Finding A37: Minor graph-code hygiene items** (qt/graph.py:140-146, 168, 266-270)
`_hue` falls back to a hardcoded status→color dict when the theme import fails (offscreen-safe, but the fallback can drift from `theme.STATE_HUE`); `Edge.__init__` contains dead code (`r = src.rect().center() + src.pos() if False else None`); `update_task`'s late-added-task edges are drawn as `(0,0)` stubs until the next full rebuild. All cosmetic; no security impact.

**Finding A38: Theme is constants-only** (qt/theme.py:1-223)
`STATE_HUE` is the single status→hue mapping (mirroring `BUSY_STATUSES` in core.py); `state_hue`/`is_live` degrade safely for unknown statuses (theme.py:68-76); `stylesheet()` interpolates only module constants. No attack surface.

---

## 2. Security Threat Model

### 2.1 Trust Boundaries (t2b view — front-ends and integrations)

```
┌─────────────────────────────────────────────────────────────┐
│              USER CONTROL PLANE (untrusted input)            │
│  TUI keys · /commands · WS /ws/room actions · REST /api/*    │
│  Model output (untrusted, t2a T1) · chain files · nicknames  │
└──────────────────────────┬──────────────────────────────────┘
                           │ user intent (trusted)
                           ▼
┌─────────────────────────────────────────────────────────────┐
│         FRONT-ENDS: tui.py · server.py · qt/widget.py        │
│  rendering (markup/Markdown) · turn serialization ·          │
│  signal marshalling · fire-and-forget tasks                  │
└──────────────────────────┬──────────────────────────────────┘
                           │ in-process calls (trusted code,
                           │ untrusted data)
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                   ORCHESTRATOR (core.py)                     │
│  plan parsing, task graph, team state, audit gating          │
└──────────────────────────┬──────────────────────────────────┘
            ┌──────────────┼──────────────┐
            ▼              ▼              ▼
     ┌────────────┐ ┌────────────┐ ┌────────────┐
     │   LEAD     │ │  WORKERS   │ │  AUDITOR   │
     └─────┬──────┘ └─────┬──────┘ └─────┬──────┘
           └──────────────┼──────────────┘
                          ▼
               ┌─────────────────────────┐
               │     BACKENDS            │
               │  (Direct / Hcom)        │
               └───────────┬─────────────┘
                           ▼
               ┌─────────────────────────┐
               │   EXTERNAL MODEL APIs   │
               └─────────────────────────┘

  Separate trust path (jules.py):
  orchestrator → backends.py: agent=="jules" → jules.run()
    → JULES_API_KEY (env) → Jules API → remote GitHub repo
    (local files NOT modified; PRs opened on the remote)
```

### 2.2 Threat Enumeration (STRIDE) — t2b series

| ID | Threat | Vector | Impact | Mitigation | Residual |
|----|--------|--------|--------|------------|----------|
| **T11** | **Unauthenticated room control via WebSocket** | Any local process — or any web page the user visits (browser WS to localhost is not CORS-restricted) — opens `ws://127.0.0.1:8765/ws/room` and sends `{"action":"prompt",…}` | Drives every agent in the room with full read/write access to `server.cwd`; plans, file edits, shell | None by default (token defaults to `""`, server.py:126/432); busy-guard returns an in-band error only when a turn is already running (server.py:369-370) | **High** — default configuration is one malicious web page away from full room compromise |
| **T12** | **Token auth bypass via WS path** | With `HEXMIND_TOKEN` set, REST `/api/*` requires the bearer token, but `auth_middleware` only covers `startswith("/api/")` (server.py:272) | Token gives false confidence; WS drives the same orchestrator with no credential | Path-prefix guard excludes `/ws/room` | **High** — same root cause as T11, distinct config regime |
| **T13** | **Nickname markup injection → TUI** | `POST /api/config/nicknames` (or user's own config.toml) sets a nickname containing `[/][bold]…[/]`; `refresh_team` interpolates it into a markup string rendered by `Static` (tui.py:806) | Markup injection in the user's TUI team bar; spoofed status text | None — no escaping before `Static.update()` | **Medium** — requires server exposure (or is self-XSS via own config) |
| **T14** | **Model output rendered as Markdown** | Model emits `[click](https://…)` or Rich-markup-ish text; `say()`/`write_task` render `Markdown(text)` into `markup=True` logs (tui.py:548, 706-710, 836) | Clickable OSC 8 hyperlinks / styled spoofing in the user's terminal | None | **Low** — terminal-only, requires user click |
| **T15** | **Fire-and-forget task exceptions lost** | `post_prompt`/`post_approve`/WS actions `create_task` and return; `current_run_task` overwritten, never awaited (server.py:297-299, 307-309) | Callers believe a run started; failures surface only as asyncio GC warnings or a WS error to the originating socket | WS done-callbacks (server.py:375-378) | **Low** — reliability/observability |
| **T16** | **Qt audit toggle inert** | User ticks "Peer audit"; `orch.audit=True` is set but `stats=None` in the Qt orchestrator (widget.py:130; core.py:457, 1045) | User believes tasks are peer-audited; they are not | None | **Low-Medium** — safety-relevant control that does nothing |
| **T17** | **Qt rapid-send turn drop** | Two quick submits: second is silently discarded by `_turn_in_flight` (widget.py:165-167) | Lost request, no error | None (by-design serialization) | **Low** |
| **T18** | **Jules `session_id` in URL path** | API response value interpolated into `f"sessions/{session_id}/…"` (jules.py:186-202) | Path manipulation if the API ever returned a hostile id | None — Google-issued id, not attacker-controlled | **Low** |
| **T19** | **Server info disclosure** | `GET /api/status` leaks full roster + pending plan + nicknames; `GET /api/chains` leaks absolute chain paths (server.py:182-203, 318-333) | Directory layout / internal state to any client | None | **Low** |
| **T20** | **Non-constant-time token compare** | `provided != f"Bearer {server._token}"` (server.py:274) | Timing oracle against loopback token | None | **Low** — theoretical |
| **T21** | **Model output rendered as Qt Markdown** | `_on_message`/`_on_task_selected` call `QTextBrowser.setMarkdown` with model-controlled text (widget.py:453-456, 490-494) | Styled spoofing of the detail view; no script execution | `setOpenExternalLinks(False)` (widget.py:356) | **Low** — tooltip-HTML vector from the old graph.py is fixed (tooltips now id+status only, graph.py:155, 159) |
| **T22** | **Task-title path heuristic → host file open** | Model puts `foo/bar.py` in a task title; user double-clicks; host opens the path (widget.py:66-75, 513-521) | Host app opens an arbitrary path | Conservative extension allow-list | **Low** — requires user double-click |
| **T23** | **Reaping fail-unsafe window** | `git log` fails after `status` succeeded → `unmerged_commits` returns `[]` → SAFE (reaping.py:93-99) | Branch deletion despite unmerged commits | `git branch -d` refuses unmerged branches (reaping.py:186-191) | **Low** — git is the backstop |
| **T24** | **TOML written via `json.dumps`** | Exotic nickname strings may not round-trip through `save_nicknames` (config.py:26) | Corrupted/misread config | `load_nicknames` fails safe to `{}` | **Low** |
| **T25** | **`--token` help over-promises** | Help says "required if host is 0.0.0.0"; code only warns (server.py:434-436) | User believes 0.0.0.0 is blocked without a token | Warning printed | **Low** — doc mismatch |

### 2.3 Attack Surface Details

#### 2.3.1 Server: WS/REST auth asymmetry (T11, T12)
The REST API and the WebSocket drive the *same* `HexmindServer.handle_prompt` → `Orchestrator.handle` path (server.py:205-228 vs 366-378). The auth middleware guards only `/api/*` and only when a token is configured. Two consequences:
1. **Default config (no token):** everything is open. On localhost this still includes *browser-originated* WebSocket connections — a visited web page can drive the room. Binding `0.0.0.0` without a token exposes it to the network (warning printed, server.py:434-436).
2. **Token config:** REST is guarded, WS is not. The token's value is defeated by using the other transport.

The busy-guard (`is_busy` → 409 / in-band error) is a concurrency guard, not an auth boundary — it only stops overlapping turns.

#### 2.3.2 Front-end rendering of untrusted model output (T13, T14, T21)
Model output reaches four renderers: RichLog-as-Markup/Markdown (TUI), `Static.update` markup strings (TUI team bar, nickname-bearing), `QTextBrowser.setMarkdown` (Qt detail pane, new in this tree), and — formerly — QToolTip HTML (fixed in the graph.py rewrite). None escape untrusted content. The nickname path is the only one reachable *without* a malicious model — via the server API or the user's own config.

#### 2.3.3 Jules trust path (T18)
`jules.run()` is reached from both backends (backends.py:160-162, 356-358) whenever a task is assigned to the `jules` member. The prompt (which may contain user + model text) is sent to the Jules API, which executes on the remote GitHub repo and opens a PR (`AUTO_CREATE_PR`). The `JULES_API_KEY` is the only credential; it is env-only and never logged. Residual concerns are the unencoded query params and unvalidated session id (both Google-issued values).

#### 2.3.4 Reaping safety (T23)
`relay.py:824-883` wires `_active_runs()` (pid-liveness markers) into `reaping.classify`, then `remove_one` for SAFE candidates. The pipeline fails safe in every direction except the narrow `git-log`-after-`status` window, which `git branch -d` backstops. This is the strongest cleanup design in the codebase.

### 2.4 Data Flow Security

| Flow | Direction | Validation | Risk |
|------|-----------|------------|------|
| Browser/malicious page → WS `/ws/room` | External → server | **none** (no auth, no origin check) | **High** |
| REST client → `/api/*` | External → server | bearer token if set; non-constant-time compare | Medium (when token set) |
| Server → TUI team bar | nickname → markup string | none | Medium — markup injection |
| Model output → TUI RichLog | untrusted → render | `clean_text` (control chars) only; Markdown rendered | Low |
| Model output → Qt detail pane | untrusted → Qt Markdown | `setOpenExternalLinks(False)`; no-script subset | Low |
| `/api/config/nicknames` → config.toml | client → disk | pydantic `Dict[str,str]`; no content validation | Medium — markup injection vector |
| Jules prompt → Jules API → GitHub | orchestrator → cloud | repo format validated (jules.py:42-53); API key env-only | Low |
| Reaping → git | cleanup → repo | fail-safe classify; no `--force`; git backstop | Low |
| `notify` → kdeconnect-cli | TUI → phone | argv list, 5 s timeout, never raises | Low |

---

## 3. Critical Findings Summary

| Severity | ID | Finding | File:Line |
|----------|-----|---------|-----------|
| **High** | T11 | Unauthenticated WebSocket drives the full room (default config) | server.py:270-276, 350-397 |
| **High** | T12 | Token auth does not cover `/ws/room` | server.py:272 |
| **Medium** | T13 | Nickname markup injection into TUI team bar | tui.py:806; server.py:343-348 |
| **Medium** | T16 | Qt audit toggle inert (orchestrator has no Stats) | qt/widget.py:130, 297-300; core.py:1045 |
| **Low** | T14 | Model output rendered as Markdown in markup-enabled logs | tui.py:548, 706-710 |
| **Low** | T15 | Fire-and-forget task exceptions never retrieved | server.py:297-299, 307-309 |
| **Low** | T17 | Qt rapid-send silently drops the second turn | qt/widget.py:165-167 |
| **Low** | T18 | Jules `session_id` interpolated into URL paths | jules.py:186-202 |
| **Low** | T19 | Server status/chains endpoints disclose internal state | server.py:182-203, 318-333 |
| **Low** | T20 | Non-constant-time token comparison | server.py:274 |
| **Low** | T21 | Model output rendered as Qt Markdown in detail pane | qt/widget.py:453-456, 490-494 |
| **Low** | T22 | Task-title path heuristic → host file open | qt/widget.py:66-75, 513-521 |
| **Low** | A35 | Graph `compute_layers` recursive — RecursionError on deep plans (regression) | qt/graph.py:61-73 |
| **Low** | T23 | Reaping `unmerged_commits` fail-unsafe window (git backstopped) | reaping.py:93-99 |
| **Low** | T24 | TOML values written via `json.dumps` | config.py:26 |
| **Low** | T25 | `--token` help text over-promises vs warn-only code | __main__.py:35-36; server.py:434-436 |

---

## 4. Recommended Hardening

### 4.1 Immediate (High Impact)
1. **Authenticate the WebSocket.** Apply the same bearer-token check inside `websocket_room` (reject before `accept()`), or move the auth middleware to cover `/ws/` as well as `/api/`. When no token is configured, refuse WS connections from non-localhost origins.
2. **Add `check_origin` to the WS endpoint.** Reject handshakes whose `Origin` header is not `http://127.0.0.1:<port>` / `http://localhost:<port>` — this closes the malicious-web-page vector (T11) even before auth is considered.
3. **Fail closed on missing token for mutating surfaces.** `POST /api/prompt`, `/api/approve`, and the WS `prompt`/`approve` actions should require a token when the server is bound to anything but loopback — or at minimum log a one-time warning per process.

### 4.2 Short-Term
4. **Escape nicknames at the render boundary.** In `refresh_team` (tui.py:806), build the team bar from `Text` objects (or `Text.from_markup` with escaped segments) instead of interpolating nicknames into a raw markup string. Same for any future nickname-bearing markup.
5. **Render model output as plain text or sanitized Markdown.** In `say()`/`write_task`, either drop `markup=True`/`Markdown` for model content or escape Rich markup before rendering (T14).
6. **Make the Qt audit toggle honest.** Pass a `Stats` instance into the Qt `_Room` orchestrator (widget.py:130) so the toggle works, or disable the checkbox with a tooltip when stats is unavailable (T16).
7. **Constant-time token comparison** via `hmac.compare_digest` (server.py:274).
8. **Track fire-and-forget tasks.** Keep a `set` of running tasks, `add_done_callback` that logs exceptions, and surface failure to REST callers via the `current_run_task` handle (T15).

### 4.3 Architectural
9. **Queue rather than drop Qt submits** (or emit a "queued" signal mirroring the TUI's busy message) so silent loss becomes visible (T17).
10. **URL-encode Jules query params** (`urllib.parse.urlencode`) and validate `session_id` against `^[\w-]+$` before path interpolation (T18, T23).
11. **Gate `/api/chains` path disclosure** behind the same token as mutating endpoints, or return names only (T19).
12. **Enforce or correct the `--token` contract** for `0.0.0.0` (T25).
13. **Remove the duplicate `snapshot()`** in qt/widget.py and take `_orch_lock` for the whole snapshot (A31-adjacent hygiene).
14. **Restore the iterative longest-path layout** in `compute_layers` (graph.py:61-73) — the previous explicit-stack version existed precisely because deep relay chains hit Python's recursion limit; the rewrite regressed it (A35).

---

## 5. Strengths Noted

| Area | Why It's Strong |
|------|----------------|
| **Reaping fail-safe design** | Every unreadable state classifies DIRTY/left-alone, never SAFE; `worktree_is_itself` defeats the broken-`.git`-link false-clean; no `--force` — git's own refusals are the backstop (reaping.py:56-73, 140-158, 175-192) |
| **Jules enum handling** | Exact frozensets with an explicit "unrecognised state → keep polling + log" branch; the substring-test incident is documented in the module docstring so the next reader does not regress it (jules.py:26-39, 382-387) |
| **Server hardening vs t2a scratch** | Localhost-only CORS, 127.0.0.1 default bind, 0.0.0.0 warnings, lazy uvicorn import guard, approve-directives forwarding — all fixed since the scratch audit (server.py:261-268, 403, 416-419, 235) |
| **TUI turn discipline** | `asyncio.Lock` + `@work(group="turns")` serializes requests; every team verb re-checked through the orchestrator; `LeadPicker` blocks startup and re-arms (tui.py:523, 568-597, 738-747) |
| **Qt lifecycle defense in depth** | `_LIVE_ROOMS` weakset + atexit + idempotent `stop()` + `aboutToQuit` hook — the docstring records the real "QThread destroyed while running" abort this defends against (widget.py:99-105, 211-231) |
| **Graph rendering integrity** | Deterministic (depth, id)-sorted layout; edges drawn only when both endpoints exist; unknown statuses degrade to a default hue instead of crashing; tooltips carry only id+status (graph.py:123-137, 149-159; theme.py:68-76) |
| **Entry-point honesty** | No default lead (the incident is commented); headless surfaces say what they need; `HEXMIND_TRACEBACK` escape hatch for debugging (__main__.py:47-60, 129-130) |
| **Subprocess hygiene everywhere** | argv lists, timeouts, `stdin=DEVNULL` in reaping/jules/notify/termux_copy; zero `shell=True` in the audited surface |
| **Config/notify fail-safe** | Missing/corrupt config → `{}`; phone ping never raises (config.py:19-20; notify.py:14-35) |

---

## 6. Delta from t2a Scratch Audit (fixed since)

The t2a scratch file (`.audit/history/SCRATCH-2026-09-28.md`, written 03:51 against an earlier tree) reported findings that **current working-tree code has since fixed** — this audit is against the current tree, so those items are closed:

| Scratch finding | Status now | Evidence |
|-----------------|------------|----------|
| Server CORS `allow_origins=["*"]` | **Fixed** — localhost-only | server.py:261-268 |
| Server default bind `0.0.0.0` | **Fixed** — 127.0.0.1 + warnings | server.py:403, 416-419, 434-436 |
| `approve_pending` drops chains/skills directives | **Fixed** — forwards + clears; tested | server.py:235, 242; tests/test_server.py:119-129 |
| Server approve/discard untested (6 tests) | **Fixed** — 12 tests incl. approve/discard/busy/no-pending | tests/test_server.py:53-184 |
| Jules `"AWAITING" in state` substring | **Fixed** — exact frozensets | jules.py:31-39, 363-387 |
| Jules `current in check_pushed.stdout` substring | **Fixed** — exact set membership | jules.py:97-103 |
| TUI team bar stale after `/add` `/remove` | **Fixed** — `self.members` synced | tui.py:764-765 |
| Qt audit checkbox decorative (no connection) | **Partially fixed** — connected (widget.py:286) but still inert: no `Stats` in Qt orchestrator (T16) | widget.py:130, 297-300; core.py:1045 |
| Qt `_orch_lock` does not serialize turns | **Fixed** — `_turn_in_flight` serializes (by dropping, T17) | widget.py:158-168 |
| Qt `_on_audit_toggle` duplicated `__init__` lines | **Fixed** — handler is now two lines | widget.py:297-300 |
| Qt tooltip HTML built from model output | **Fixed** — rewritten graph tooltips carry only id+status | graph.py:155, 159 |
| Graph iterative longest-path layout | **Regressed** — rewrite is recursive; deep plans can hit the recursion limit (A35) | graph.py:61-73 |

---

## 7. Files Not Audited (Out of Scope)
- `tests/` (25 files) — test code; `tests/test_server.py` read only to confirm coverage claims
- `docs/`, `tools/`, `chains/*.toml` (data), `models.toml` (data — audited in t2a §1.3)
- `hexmind/auditor.py`, `hexmind/backends.py` — covered in t2a §1.4-1.5
- `hexmind/core.py`, `hexmind/relay.py`, `hexmind/models.py` — covered in t2a
- No live backend / Jules API / Qt harness runs — all findings are static (code read + grep); runtime-impact items are tagged Low with the static-only caveat

---

*End of Report*

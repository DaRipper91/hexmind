# WS Auth Bypass (T11/T12) — Fix Status

**Status:** Implemented in `c88a5eb` (WS auth) and `07e7394` (Origin check, `HEXMIND_WS_AUTH_DISABLED` opt-out, regression tests). The design notes below were written before implementation on 2026-09-28.
**Sources:** `docs/audits/ARCH_SECURITY_AUDIT_T2B.md` (T11, T12, T20), `docs/audits/WS_AUTH_FIX_DESIGN.md`, `hexmind/server.py` (working tree).

---

## 1. Scope and threat

| ID | Severity | Finding |
|----|----------|---------|
| T11 | High | `/ws/room` has no auth and no Origin check. Any local process, or any web page the user visits, can open `ws://127.0.0.1:8765/ws/room` and send `{"action":"prompt",…}`. Browsers don't apply CORS to WebSocket connections. That prompt drives every agent in the room with read/write access to `server.cwd`. |
| T12 | High | When `HEXMIND_TOKEN` is set, `auth_middleware` guards only `path.startswith("/api/")` (`server.py:272`). The WS route drives the same orchestrator without any credential, so the token gives false confidence. |
| T20 | Low | The token compare `provided != f"Bearer {…}"` (`server.py:274`) isn't constant-time. The design calls this "A11". |

Code as it stands now (`hexmind/server.py`):
- `websocket_room` (`:350-397`) calls `server.manager.connect()` → `websocket.accept()` (`:52-53`) right away. Then it sends an `init` payload with the status, messages and active tasks (`:355-360`). There's no check before accept.
- The token defaults to `""` (`:126`) and is set from `--token`/`HEXMIND_TOKEN` (`:432`). With `--host 0.0.0.0` and no token, the server only prints a warning (`:434-436`).
- The busy-guard (`:369-370`) prevents overlapping turns. It isn't an auth boundary.

## 2. What is done

- `WS_AUTH_FIX_DESIGN.md` covers the threat model, the fix design, acceptance criteria AC1–AC12, a test-scenario table and a rollout plan. It says of itself "Audit only, no code changes made."
- That's the only deliverable so far.

## 3. Proposed fix (from the design, condensed)

All checks run **before `websocket.accept()`**. A rejected client never receives `init` (AC11).

1. **Origin allowlist, checked first, whether or not a token is set** (AC5)
   - Allowed: `http://127.0.0.1:{port}`, `http://localhost:{port}`, plus the `ws://` forms.
   - Any other origin is rejected with close code `4003`.
2. **Token parity when `HEXMIND_TOKEN` is set** (AC1–AC4). Transport, in order of preference:
   - **Primary: subprotocol** `hexmind.token.<base64url(token)>`. This keeps the token out of URLs and access logs.
   - **Fallback: query parameter** `?token=`. Browser history and logs can capture it, so it's meant for quick testing only.
   - **Non-browser clients:** the `Authorization: Bearer` header on the handshake.
   - Missing or wrong token → close code `4001`. There's no anonymous fallback.
3. **Constant-time compare:** `hmac.compare_digest` (AC7). This also fixes T20.
4. **Shared helpers:** `validate_token(provided, expected)` and `extract_ws_token(websocket)`. `auth_middleware` and the WS handler both use `validate_token` (AC9).
5. **Dev ergonomics when the token is unset:** clients from a localhost origin connect without a token (AC6). With `--host 0.0.0.0` and no token, the server warns and still enforces the Origin allowlist (AC10).
6. **No token logging:** the token value never appears in logs or in the close reason (AC8).
7. **Close codes documented:** `4001` unauthorized, `4003` forbidden origin, `4000` internal error (AC12).

The only file to change is `hexmind/server.py`: `create_app()`, `websocket_room`, and the new helpers.

## 4. What is NOT done

| Task | State |
|------|-------|
| t2 — Implement the fix in `server.py` | Not started |
| t3 — Regression tests (the design's scenario table, plus REST non-regression) | Not started. `tests/test_server.py` has no WS auth coverage. Its two existing WS tests (`:84`, `:95`) connect without an `Origin` header, so they will start failing once the Origin check lands unless they add one. |
| t4 — Security review of the implementation | Not started |

No code, tests or config have changed for this fix. The design's rollout step 1 is to put the fix behind a `HEXMIND_WS_AUTH=1` flag first. That hasn't been decided (see §5).

## 5. Decisions needed

1. **Subprotocol + query, or query only?**
   - The subprotocol avoids leaking the token. It needs base64url decoding, and the server has to echo the chosen subprotocol in `accept(subprotocol=…)` or browsers drop the connection. The design's `extract_ws_token` sketch does neither.
   - Query-only is simpler but puts the token in URLs.
   - *Recommendation:* subprotocol as primary, query as fallback, as the design says.
2. **What to do when the `Origin` header is missing** (wscat, scripts, non-browser clients). The design contradicts itself:
   - §2 says "Missing Origin → reject".
   - The scenario table expects `wscat -H "Authorization: Bearer …"` with no Origin to **connect**.
   - AC4 says the server "*rejects* token via Authorization header", but its own note and the table say that path should be accepted.
   - *Recommendation:* when there's no Origin header, allow the connection only if a valid token is presented. When no token is configured, reject a missing Origin. Browsers always send Origin, so this still blocks the cross-site vector.
3. **Feature flag (`HEXMIND_WS_AUTH=1`) or on by default?** *Recommendation:* on by default. This is a High-severity bypass, and a flag leaves the default configuration exposed.

## 6. Adjacent issues seen in `server.py` (not in the T11/T12 scope, flag for t2/t4)

These are in the current **uncommitted** working-tree changes to `server.py` (`git diff` shows +50/−11):
- `auth_middleware` returns `JSONResponse(status_code=401, detail=…)` (`:275`). Starlette's `JSONResponse` has no `detail` parameter, so a bad or missing token raises `TypeError` and returns a 500 instead of a 401. The request is still denied, but the status code is wrong. Fix: `content={"detail": …}`.
- The CORS `origins` list (`:261`) hardcodes `http://localhost:8765`. It ignores the actual port, which the WS allowlist would inherit if it reuses the list. Build both entries from the real port.

# WebSocket Authentication Fix Design — T11/T12

**Scope**: `hexmind/server.py` — WebSocket `/ws/room` authentication and origin checking parity with `/api/*` REST endpoints.

**Reference**: `ARCH_SECURITY_AUDIT_T2B.md` findings T11 (High), T12 (High), A11 (Low).

---

## Threat Model (Focused on T11/T12)

### Assets
- `server.cwd` — workspace directory with full read/write via orchestrator
- Agent execution (prompt → plan → tools → file edits, shell)
- Team composition, pending plans, message history

### Trust Boundaries
```
┌─────────────────────────────────────────────────────────────────┐
│  EXTERNAL: Browser (any origin), local processes, network peers  │
│  • ws://127.0.0.1:8765/ws/room  — NO AUTH, NO ORIGIN CHECK       │
│  • http://127.0.0.1:8765/api/* — Bearer token IF HEXMIND_TOKEN   │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                    AuthN/AuthZ boundary
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│  INTERNAL: HexmindServer → Orchestrator → Backends → Model APIs  │
└─────────────────────────────────────────────────────────────────┘
```

### STRIDE for WS `/ws/room`

| Threat | Current State | Impact |
|--------|---------------|--------|
| **Spoofing** | No client identity — any origin connects | Attacker impersonates legitimate client |
| **Tampering** | No message integrity — but WS is same-process | N/A (in-process) |
| **Repudiation** | No audit log of WS actions | Cannot attribute malicious prompts |
| **Information Disclosure** | `init` payload sends full status, messages, tasks | Workspace layout, team roster, pending plans leaked |
| **Denial of Service** | Unbounded connections, fire-and-forget tasks | Resource exhaustion, exception loss (T15) |
| **Elevation of Privilege** | **T11/T12**: WS bypasses token auth entirely | **Critical** — full room control without credentials |

### Attack Vectors (T11/T12)
1. **Malicious web page** → user visits → page opens `ws://127.0.0.1:8765/ws/room` → sends `{"action":"prompt","text":"rm -rf /"}` → orchestrator executes with full `server.cwd` access
2. **Local process** → connects to WS → same as above
3. **Token configured** → REST guarded, WS wide open → token provides false confidence

---

## Minimal Fix Design

### Design Principles
1. **Fail-closed by default** — when `HEXMIND_TOKEN` is set, *all* mutating surfaces require it
2. **Parity** — `/ws/room` and `/api/*` have identical auth requirements
3. **Defense in depth** — origin check *before* auth, auth *before* accept
4. **No secret leakage** — tokens never logged, never in URLs accessible to browser history
5. **Localhost-only when unset** — bind to `127.0.0.1` by default; WS rejects non-localhost origins

### 1. Token Requirement on `/ws/room` (T11/T12)

**When `HEXMIND_TOKEN` is SET (non-empty):**
- WebSocket connection MUST present valid token
- Token transport options (client chooses ONE):
  - **Query parameter**: `ws://host:port/ws/room?token=<HEXMIND_TOKEN>` — simplest for browser `new WebSocket()`
  - **Subprotocol**: `Sec-WebSocket-Protocol: hexmind.token.<base64url(token)>` — keeps token out of URL/logs
  - **Header (during handshake)**: `Authorization: Bearer <token>` — not accessible from browser WS API, but works for non-browser clients
- **Reject at handshake** — `websocket.close(code=4001, reason="unauthorized")` *before* `accept()`
- **No anonymous fallback** — fail closed

**When `HEXMIND_TOKEN` is UNSET (empty/default):**
- **Origin allowlist enforced** — only `http://127.0.0.1:<port>` and `http://localhost:<port>` origins accepted
- **No token required** — localhost-only anonymous access preserved for dev ergonomics
- **Bind address honored** — if `--host 0.0.0.0` used without token, warn AND restrict WS to localhost origins (defense in depth)

### 2. Origin Checking (New — addresses T11 root cause)

Add `check_origin` callback to WebSocket endpoint:

```python
def check_origin(headers: Headers, allowed_origins: list[str]) -> bool:
    origin = headers.get("origin", "")
    return origin in allowed_origins
```

**Allowed origins** (derived from `server._port`):
- `http://127.0.0.1:{port}`
- `http://localhost:{port}`
- `ws://127.0.0.1:{port}` (some browsers send ws://)
- `ws://localhost:{port}`

**Behavior**:
- Missing `Origin` header → **reject** (non-browser clients must send it)
- Origin not in allowlist → **reject** with `4003`
- Check runs *before* token validation (cheap, stops cross-origin early)

### 3. Token Transport — No Secret Leakage

| Transport | Pros | Cons | Leakage Risk |
|-----------|------|------|--------------|
| **Query `?token=...`** | Browser-native, simple | URL logged in browser history, server access logs, Referer headers | **High** — avoid if possible |
| **Subprotocol** | Not in URL, not in logs | Browser WS API supports `new WebSocket(url, ["hexmind.token.xxx"])` | **None** |
| **Handshake header** | Standard auth pattern | Browser WS API *cannot* set custom headers on handshake | N/A (non-browser only) |

**Recommendation**: Support **subprotocol as primary**, query as fallback for simplicity. Document subprotocol for production; query for quick testing.

**Implementation**:
```python
# Extract token from subprotocol: "hexmind.token.<base64url>"
subprotocols = websocket.scope.get("subprotocols", [])
token_from_subproto = next(
    (sp.split("hexmind.token.", 1)[1] for sp in subprotocols if sp.startswith("hexmind.token.")),
    None
)

# Fallback to query param
token_from_query = websocket.query_params.get("token")

# Exactly one must match server._token (constant-time compare)
```

**Constant-time comparison** (fixes A11):
```python
import hmac
hmac.compare_digest(provided_token, server._token)
```

### 4. `/api` vs `/ws` Parity

| Surface | Auth When Token Set | Auth When Token Unset |
|---------|---------------------|------------------------|
| `GET /api/status` etc | Bearer token required | Allowed (localhost CORS) |
| `POST /api/prompt` etc | Bearer token required | Allowed (localhost CORS) |
| `WS /ws/room` | **Token required** (subproto/query/header) | **Origin allowlist only** |

**Unified logic**: Extract auth check into a shared function used by both middleware and WS handler.

---

## Acceptance Criteria for Implementer

### Must-Have (T11/T12 Blockers)

- [ ] **AC1**: When `HEXMIND_TOKEN` is set, `WS /ws/room` rejects connections without valid token (code 4001)
- [ ] **AC2**: When `HEXMIND_TOKEN` is set, `WS /ws/room` accepts token via subprotocol `hexmind.token.<b64url>`
- [ ] **AC3**: When `HEXMIND_TOKEN` is set, `WS /ws/room` accepts token via query `?token=` (fallback)
- [ ] **AC4**: When `HEXMIND_TOKEN` is set, `WS /ws/room` rejects token via Authorization header (browser can't send) — *optional, for non-browser clients*
- [ ] **AC5**: `check_origin` rejects non-localhost origins *regardless of token state* (code 4003)
- [ ] **AC6**: When `HEXMIND_TOKEN` is unset, `WS /ws/room` allows localhost origins without token
- [ ] **AC7**: Token comparison uses `hmac.compare_digest` (constant-time)
- [ ] **AC8**: No token value appears in logs (verify: grep logs for token pattern → empty)
- [ ] **AC9**: `auth_middleware` and WS handler share the same token validation function

### Should-Have (Hardening)

- [ ] **AC10**: When `--host 0.0.0.0` used without `HEXMIND_TOKEN`, server logs warning AND WS still enforces localhost origin allowlist
- [ ] **AC11**: Connection rejected *before* `websocket.accept()` — no `init` payload sent to unauthorized clients
- [ ] **AC12**: Error codes documented: `4001=unauthorized`, `4003=forbidden origin`, `4000=internal error`

### Test Scenarios (Manual + Automated)

| Scenario | Token Set | Origin | Expected |
|----------|-----------|--------|----------|
| Browser WS from `http://localhost:8765` | No | localhost | ✅ Connect, `init` received |
| Browser WS from `https://evil.com` | No | evil.com | ❌ Reject 4003 |
| Browser WS from `https://evil.com` | Yes | evil.com | ❌ Reject 4003 (origin first) |
| Browser WS from `http://localhost:8765` | Yes | localhost | ✅ With valid subprotocol token |
| Browser WS from `http://localhost:8765` | Yes | localhost | ✅ With valid `?token=` query |
| Browser WS from `http://localhost:8765` | Yes | localhost | ❌ Reject 4001 (no token) |
| `wscat -H "Authorization: Bearer xxx"` | Yes | (none) | ✅ Connect (non-browser) |
| `wscat` no auth | Yes | (none) | ❌ Reject 4001 |

### Non-Regression

- [ ] Existing REST `/api/*` auth behavior unchanged
- [ ] CORS on REST endpoints unchanged (localhost-only)
- [ ] TUI and Qt front-ends continue to work (they use REST, not WS directly)
- [ ] `--host 127.0.0.1` default unchanged

---

## Implementation Notes (for implementer)

### Files to Modify
- `hexmind/server.py` — `create_app()`, `websocket_room` handler, add `check_origin` helper

### Key Code Locations
- `server.py:126` — `self._token = ""` default
- `server.py:261-268` — CORS origins (reuse for WS allowlist)
- `server.py:270-276` — `auth_middleware` (extract shared validator)
- `server.py:350-397` — `websocket_room` (add origin + token checks before `accept()`)
- `server.py:432` — `server._token = token or os.environ.get("HEXMIND_TOKEN", "")`

### Suggested Shared Validator
```python
def validate_token(provided: str, expected: str) -> bool:
    """Constant-time token comparison."""
    return hmac.compare_digest(provided, expected)

def extract_ws_token(websocket: WebSocket) -> str | None:
    """Extract token from subprotocol (preferred) or query param."""
    # Subprotocol: "hexmind.token.<base64url>"
    for sp in websocket.scope.get("subprotocols", []):
        if sp.startswith("hexmind.token."):
            return sp.split("hexmind.token.", 1)[1]
    # Fallback: query param
    return websocket.query_params.get("token")
```

### Origin Allowlist Construction
```python
def get_allowed_origins(port: int) -> list[str]:
    base = f"http://127.0.0.1:{port}", f"http://localhost:{port}"
    ws_base = f"ws://127.0.0.1:{port}", f"ws://localhost:{port}"
    return list(base) + list(ws_base)
```

---

## Out of Scope (Separate Issues)
- T15: Fire-and-forget task exception handling
- T13: Nickname markup injection (TUI)
- A11: Constant-time compare (included above as AC7)
- T19: Info disclosure on `/api/status`, `/api/chains`
- T25: `--token` help text vs warn-only behavior

---

## Rollout Plan
1. Implement fix behind feature flag or env var `HEXMIND_WS_AUTH=1` for testing
2. Verify all acceptance criteria pass
3. Enable by default in next release
4. Document subprotocol usage for browser clients

---

*End of Design Doc — Audit only, no code changes made.*
# 🌌 Hexmind Reliability & Coordination Fixes — Master Handbook 🌌

---

> 🌌 **D3F Master Handbook**
>
> **Source Document:** [`docs/plans/2026-09-28-hexmind-fixes.md`](file:///home/daripper/Projects/hexmind/docs/plans/2026-09-28-hexmind-fixes.md)
>
> **Chain Stages:** 🧊 Architect ✓ · 🦄 SME ✓ · 👾 Auditor ✓ · 🌌 UX Writer ✓
>
> **Directive:** 🛡️ Zero Hallucination — every fact is traceable to the source document. Where the source is silent, the gap is marked explicitly.
>
> **Status:** 🏆 ALL 11 TASKS COMPLETE (2026-09-28)

---

## 📖 Part 1 — User Manual

### 1.1 Overview & Executive Summary
This handbook formalizes the 11-point reliability, security, and coordination overhaul executed on `hexmind`. The core orchestration engine was previously audited and found sound: sanitized backend output (`core.py:clean_text`), capped reads with process-group termination (`backends.py`), fail-safe worktree reaping (`reaping.py`), staged isolation checks (`relay.py`), pid-liveness over markers, in-place registry reload, fail-closed verdicts with Laplace-smoothed rankings, single-roster Assembly with validated directives, and invariant-preserving cancellation.

However, the audit revealed critical silent-failure pathways:
* The headless server bound open LAN interfaces without authentication while exposing agent execution.
* The approval flow dropped directives on approve.
* `gate:true` was inert when peer audit was disabled.
* `parse_plan` repaired invalid agent/dependency names silently without warning the user.
* Jules, Ollama, and Qt signal handlers swallowed critical exceptions into incorrect branches.

> ⚠️ **Watch Out:** The highest-priority vulnerability addressed was **Task 1 (Server Exposure)**: `server.py` originally bound `0.0.0.0:8765` with wildcard CORS and credentials enabled without authentication, while `POST /api/prompt` auto-applied filesystem modifications in `cwd`. It now defaults to loopback `127.0.0.1` with `HEXMIND_TOKEN` auth.

### 1.2 Quick Start & Verification
To verify the complete test suite and security controls:
```bash
# 1. Run core verification suite
python3 -m pytest tests/test_core.py tests/test_server.py tests/test_auditor.py tests/test_models.py tests/test_backends.py -q

# 2. Verify server loopback binding
grep -n "allow_origins" hexmind/server.py
hexmind --serve &
# Confirm bind address is 127.0.0.1:8765
```

---

## 🔧 Part 2 — Technical Manual

### 2.1 System Architecture & Failure Path Hardening
The fixes eliminate silent failure across four critical integration boundaries:

```
┌────────────────────────────────────────────────────────────────────────┐
│                        BOUNDARY 1: SERVER API                          │
│   • Loopback default (127.0.0.1) & token-based auth (HEXMIND_TOKEN)   │
│   • Directive preservation during plan approval                        │
│   • Unhandled task exception propagation to WebSocket clients         │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
┌───────────────────────────────────▼────────────────────────────────────┐
│                      BOUNDARY 2: ORCHESTRATOR                          │
│   • Audible warnings when gate:true is set with audit:false            │
│   • parse_plan surfaces unknown agents/deps as room findings           │
│   • Quota reassignment narrowed to structured billing signals         │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
┌───────────────────────────────────▼────────────────────────────────────┐
│                      BOUNDARY 3: MODEL BACKENDS                        │
│   • Ollama generate/evict catches ValueError + OSError                 │
│   • Process group signal handling catches PermissionError              │
│   • opencode model filter hardened to provider/model syntax            │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
┌───────────────────────────────────▼────────────────────────────────────┐
│                    BOUNDARY 4: EXTERNAL BRIDGES                        │
│   • Jules branch detection: exact ls-remote matching (no substring)    │
│   • Stats file corruption backup (stats.json.corrupt.<ts>)             │
│   • Relay active-marker failure causes loud error                      │
└────────────────────────────────────────────────────────────────────────┘
```

### 2.2 Configuration & Exposure Specifications
* **Default Host:** `127.0.0.1` (`server.py:373-376`, `__main__.py:33`). Requires `--host 0.0.0.0` explicitly for LAN exposure with startup warning.
* **Authentication:** `HEXMIND_TOKEN` environment variable or HTTP bearer token header.
* **CORS:** Explicit origin whitelist; disallow wildcard origins when credentials are true.

---

## 💻 Part 3 — Developer Guide

### 3.1 The 11 Core Correctness Tasks

#### Task 1: Constrain Server Exposure (Bind / Auth / CORS)
* **Location:** `hexmind/server.py:250-256,373-376`, `hexmind/__main__.py:33`
* **Resolution:** Default bind set to `127.0.0.1`. Replaced wildcard CORS with explicit allowed origins. Added `HEXMIND_TOKEN` validation in `create_app`.

#### Task 2: Server Approval Directives & WebSocket Coordination
* **Location:** `hexmind/server.py:224-237,281-296,355-364`
* **Resolution:** Forward `orch.pending_directives` in `approve_pending` and clear on approve/discard (matching `relay.py:714-727`). Surfaced fire-and-forget task exceptions to WebSocket clients.

#### Task 3: Enforce Audit Warnings on `gate:true`
* **Location:** `hexmind/core.py:1015-1019`
* **Resolution:** Emits visible room warning when a task declares `gate:true` while `audit` is disabled, preventing silent gate bypass.

#### Task 4: Transparent `parse_plan` Repair Reporting
* **Location:** `hexmind/core.py:316,325`
* **Resolution:** Replaced silent fallback to lead with logged room findings whenever an unknown agent or ghost dependency is encountered.

#### Task 5: Qt Peer Audit Toggle Synchronization
* **Location:** `hexmind/qt/widget.py:274-275,283`
* **Resolution:** Connected `auditBox.stateChanged` directly to live room audit flags under `_orch_lock`.

#### Task 6: Serialization of Qt Turn Submissions
* **Location:** `hexmind/qt/widget.py:158-189`
* **Resolution:** Disabled concurrent send invocations while turn is in-flight, preventing corrupted orchestrator state.

#### Task 7: Exact-Match Jules Branch Resolution
* **Location:** `hexmind/jules.py:83,94-95,109-113`
* **Resolution:** Switched from substring checking (`current in stdout`) to exact set matching on `ls-remote` refs. Replaced `except: pass` with explicit error logging.

#### Task 8: Stats Persistence Protection & Activity Status
* **Location:** `hexmind/auditor.py:80-81`, `hexmind/jules.py:186-187,383-384`
* **Resolution:** On corrupt stats JSON, creates timestamped backup (`stats.json.corrupt.<ts>`) rather than overwriting. Partial activity fetches are marked explicitly failed.

#### Task 9: Narrow Quota Reassignment Regex
* **Location:** `hexmind/core.py:36,1021-1022`
* **Resolution:** Restricted `QUOTA_RE` triggers to backend-attributed billing error codes, avoiding false reassignments from tool stderr text.

#### Task 10: Portable Example Chains & Hardened Markers
* **Location:** `docs/examples/chains/doc-chain.toml`, `hexmind/relay.py:966-968`, `hexmind/models.py:364`
* **Resolution:** Replaced absolute home directory paths with portable paths. Relay active-marker write failures now fail loudly. Validated `opencode models` IDs against `provider/model` pattern.

#### Task 11: TUI/Qt Correctness & Exception Hardening
* **Location:** `hexmind/tui.py`, `hexmind/backends.py:78-82,117-143`, `hexmind/qt/widget.py:168-215`
* **Resolution:** Synchronized `self.members` on team events. Caught `ValueError` alongside `OSError` in Ollama JSON parser. Handled `PermissionError` in process group signaling.

---

## 📋 Part 4 — Standard Operating Procedures (SOP)

### SOP-1: Running the Reliability Regression Gate
```bash
# 1. Run all core and server tests
python3 -m pytest tests/test_core.py tests/test_server.py tests/test_auditor.py tests/test_models.py tests/test_backends.py -v

# 2. Check for unexpected warnings
python3 -m pytest tests/test_server.py -W error::UserWarning
```

### SOP-2: Verifying Server Token Authentication
1. Launch server with custom token:
   ```bash
   HEXMIND_TOKEN="secret-token-123" hexmind --serve --port 8765
   ```
2. Verify unauthorized request is rejected:
   ```bash
   curl -I -X POST http://127.0.0.1:8765/api/prompt
   # Expect HTTP 401 Unauthorized
   ```
3. Verify authorized request passes:
   ```bash
   curl -I -X POST -H "Authorization: Bearer secret-token-123" http://127.0.0.1:8765/api/prompt
   # Expect HTTP 200 / 422 (valid auth)
   ```

---

## 📚 Part 5 — Glossary

| Term | Definition |
| :--- | :--- |
| **`DirectBackend`** | Local execution backend invoking model CLI processes directly. |
| **`Laplace Smoothing`** | Statistical smoothing applied to win/loss audit ratios to prevent zero-frequency bias. |
| **`Active Marker`** | Filesystem marker written during relay runs to prevent premature workspace reaping. |
| **`HEXMIND_TOKEN`** | Environment variable holding bearer authentication secret for the headless server. |
| **`Laplace Ranking`** | Bayesian reliability score calculated in `auditor.py` for task delegation. |

---

## 🔍 Part 6 — Reference Guide

### 6.1 Task Completion & Verification Matrix

| Task # | Component | Severity | Primary Target | Verification Status |
| :---: | :--- | :---: | :--- | :---: |
| **1** | Server Security | High | `127.0.0.1` bind, CORS, token auth | ✅ Verified Passing |
| **2** | Server Approve | Med | Directive forwarding, WS error propagation | ✅ Verified Passing |
| **3** | Core Gating | Med | Warn on `gate:true` with `audit:false` | ✅ Verified Passing |
| **4** | Plan Parser | Med | Audible repair reporting in `parse_plan` | ✅ Verified Passing |
| **5** | Qt Audit | Med | Connect `auditBox.stateChanged` to room | ✅ Verified Passing |
| **6** | Qt Turn Lock | Med | Prevent concurrent turn submission in GUI | ✅ Verified Passing |
| **7** | Jules Branch | Low | Exact branch match via `ls-remote` | ✅ Verified Passing |
| **8** | Stats Integrity | Low | Backup corrupted stats file before reset | ✅ Verified Passing |
| **9** | Quota Regex | Low | Narrow `QUOTA_RE` matching criteria | ✅ Verified Passing |
| **10** | Chain Examples | Low | Portable paths & hardened model regex | ✅ Verified Passing |
| **11** | Backend Resilience | Low | Ollama exception catch & team sync | ✅ Verified Passing |

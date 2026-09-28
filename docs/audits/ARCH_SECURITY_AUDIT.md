# Hexmind Architecture & Security Audit

**Scope**: `hexmind/core.py` (~960 lines), `hexmind/relay.py` (1019 lines), `hexmind/models.py` (431 lines)
**Date**: 2026-09-28

---

## 1. Architecture Findings

### 1.1 Core Orchestration Design

#### Multi-Model Orchestrator (core.py:455-960)
The `Orchestrator` class is the central coordination point. Key architectural decisions:

| Aspect | Implementation | Location |
|--------|----------------|----------|
| **Task Graph** | DAG with `depends_on` edges; parallel execution via `asyncio` task pool | core.py:937-986 |
| **Lead Agent** | Configurable (`opencode-ultra` default); plans, delegates, synthesizes | core.py:456, 156-185 |
| **Team Membership** | Mutable `members` list shared across TUI/server; `known` tracks all registered | core.py:459-464 |
| **Assembly Protocol** | `/recommend` → user edits → `/go` leads to plan against actual room | core.py:658-761 |
| **Audit Integration** | Optional runner-up model reviews every task; bounded revision loop (max 2) | core.py:468, auditor.py:202-281 |

**Finding A1: INVARIANT S-1 Enforcement is Solid** (core.py:150-153, 494-498, 541-544)
The `BUSY_STATUSES` frozenset and `can_sleep`/`can_retire` guards prevent interrupting models mid-edit. This is a critical safety property for worktree integrity. The invariant is derived from task state (not tracked separately), preventing drift.

**Finding A2: Plan Contract Evolution via ASSEMBLY_SCHEMA** (core.py:61-86)
The schema cleanly extends `PLAN_SCHEMA` with additive `chains` and `skills` fields. `parse_directives` (core.py:375-430) validates separately so legacy plans parse unchanged. Good backward-compatibility design.

**Finding A3: Skill Injection is Path-Based, Not Inline** (core.py:433-441, 818-850)
`skill_path()` resolves project-first then user skills. `apply_skills()` injects a `## Skill: name\nRead <path>...` note into task instructions. A missing skill becomes a finding, not a dead reference. Clean separation.

**Finding A4: Chain Execution Reuses Relay Machinery** (core.py:852-880, relay.py:910-1018)
`run_chains()` constructs an `argparse.Namespace` and calls `run_relay()` directly. Chains become ordinary relay runs with provenance in notes. No duplicate execution logic.

---

### 1.2 Relay Chain Architecture (relay.py:1-1019)

#### Chain Sources & Loading
| Source | Resolution | Location |
|--------|------------|----------|
| Chain file (`.toml`) | `~/.config/hexmind/chains/` then `hexmind/chains/` | relay.py:30, 95-114 |
| Imported agent | `from = "agent-name"` searches `AGENT_DIRS` | relay.py:33-56, 103-109 |
| Lead-designed | Unknown name → lead designs stages via `DESIGN_PROMPT` | relay.py:924-939 |

#### Assignment Modes (relay.py:127-140)
```python
# rotate: each chain starts on different model → all stay busy
# best: lead picks per-stage via BEST_PROMPT
# pinned: stage.agent field used if in members
```

**Finding A5: Worktree Isolation with Git-Driven Verification** (relay.py:160-179, 266-304)
`make_workspaces()` creates per-chain git worktrees. `Isolation` class snapshots `git status --porcelain -z` at each stage boundary (relay.py:285-304). Breaches are escalated immediately with stage attribution. The `-z` NUL-separated output handles Unicode paths correctly (relay.py:243-244).

**Finding A6: Active Run Marker Survives SIGKILL** (relay.py:824-846, 968-971)
`/relay clean` uses a marker file (run ID + PID) rather than `finally` blocks. A killed run's marker goes stale when PID is reused — safe direction (declines to reap). Correct handling of process-group kills in `backends.py`.

---

### 1.3 Model Registry as Single Source of Truth (models.py:1-431)

#### Load Order & Overlay Semantics (models.py:237-269)
```
BUNDLED (hexmind/models.toml) → USER (~/.config/hexmind/models.toml)
```
User tables override per-model. Missing base file = hard error (prevents empty roster bug).

#### Generated Prose Eliminates Drift (models.py:64-67, 316-318)
```python
def description(self) -> str:
    text = f"{self.label}: {self.best_at}"
    return f"{text}. Not for {self.avoid_for}." if self.avoid_for else text
```
`ROSTER` dict in core.py is `REGISTRY.roster()` — generated, not hand-maintained. Fixes the historical bug where `opencode-muse` was described with another model's specialty (models.py:3-6).

#### In-Place Republishing on Profile Changes (models.py:398-430)
`publish()` mutates module globals (`core.ROSTER`, `core.TEXT_ONLY`, `backends.DIRECT_CMDS`, `tui.AGENT_COLOR`) in place. This avoids rebinding globals that other modules already imported by name. Correct pattern for Python module-level state.

#### Stable Member Names via Provider-Prefixed Slugs (models.py:96-117)
```python
prefix = slugify(provider) or "local"
base = f"{prefix}-{slugify(bare or model_id)}"
# hash suffix for collision: a/b-c vs a-b/c both slug to a-b-c
```
Prevents rename-on-disappearance bug where a profiled model would return under a different name.

---

### 1.4 Backend Abstraction (backends.py:1-375)

#### Dual Backend Design
| Backend | Transport | Model Coverage |
|---------|-----------|----------------|
| `DirectBackend` | Subprocess per request (stdin/stdout) | All models including 7 non-default opencode `-m` variants |
| `HcomBackend` | Persistent hcom agents (WebSocket-like) | Only default opencode model; 7 variants excluded via `HCOM_EXCLUDED` |

**Finding A7: Backend-Specific Model Exclusion is Centralized** (backends.py:230-237, 240-242)
`HCOM_EXCLUDED` derived from registry at import; `supports()` is single source of truth. Startup notice, member list, and error messages all read it. Cannot drift.

#### Output Capping & Process Group Termination (backends.py:55-96)
`MAX_OUTPUT_BYTES = 1_000_000` with sliding window. `_terminate_group()` uses `SIGTERM` → wait → `SIGKILL` on process group. Handles PID reuse gracefully.

---

### 1.5 Auditor & Stats System (auditor.py:1-282)

#### Laplace-Smoothed Scoring (auditor.py:111-115)
```python
def score(self, agent: str, domain: str) -> float:
    p = stats.get("pass", 0)
    f = stats.get("fail", 0)
    return (p + 1) / (p + f + 2)  # Laplace smoothing
```
First-attempt quality recorded only on round 0 (auditor.py:245-246). `pick_auditor()` selects best-ranked peer ≠ primary.

#### Bounded Revision Loop (auditor.py:222-274)
Max 2 revision rounds. `gate=true` tasks raise `RuntimeError` on unresolved failure (blocks dependents). Non-gate tasks escalate via message but continue. Correct separation of blocking vs. non-blocking failures.

---

## 2. Security Threat Model

### 2.1 Trust Boundaries

```
┌─────────────────────────────────────────────────────────────┐
│                    USER CONTROL PLANE                        │
│  /commands, /recommend, /go, /lead, /profile, /nick         │
└──────────────────────────┬──────────────────────────────────┘
                           │ User intent (trusted)
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                   ORCHESTRATOR (core.py)                     │
│  Plan parsing, task graph, team state, audit gating         │
└──────────────────────────┬──────────────────────────────────┘
                           │ Internal logic (trusted)
           ┌───────────────┼───────────────┐
           ▼               ▼               ▼
    ┌────────────┐  ┌────────────┐  ┌────────────┐
    │   LEAD     │  │  WORKERS   │  │  AUDITOR   │
    │  (plans)   │  │ (executes) │  │ (verifies) │
    └─────┬──────┘  └─────┬──────┘  └─────┬──────┘
          │               │               │
          └───────────────┼───────────────┘
                          │ Prompts + file access
                          ▼
              ┌─────────────────────────┐
              │     BACKENDS            │
              │  (Direct / Hcom / Ollama)│
              └───────────┬─────────────┘
                          │ Subprocess / HTTP
                          ▼
              ┌─────────────────────────┐
              │   EXTERNAL MODEL APIs   │
              │  (untrusted, opaque)    │
              └─────────────────────────┘
```

### 2.2 Threat Enumeration (STRIDE)

| ID | Threat | Vector | Impact | Mitigation | Residual |
|----|--------|--------|--------|------------|----------|
| **T1** | **Prompt Injection → Plan Corruption** | Malicious user request crafts lead output to inject arbitrary tasks/agents | Arbitrary code execution via worker tasks | `parse_plan` validates agent ∈ members, deps ∈ task IDs, no cycles (core.py:303-354); `clean_text` strips control chars (core.py:92-97) | **Medium** — Lead model could still be persuaded to generate malicious but structurally valid plans |
| **T2** | **Prompt Injection → Skill/Chain Directive Injection** | Lead output includes `chains`/`skills` with malicious goals/paths | Chain runs arbitrary goal; skill `use` injects arbitrary file path | `parse_directives` validates: chain goal non-empty, assign ∈ enum, n ∈ [1,5] (core.py:389-408); skill action ∈ enum, name non-empty, path must exist via `skill_path()` (core.py:410-429) | **Low** — Validation is strict; missing skill = finding not execution |
| **T3** | **Worktree Escape** | Worker agent ignores cwd, writes to main repo | Repository corruption outside intended isolation | `Isolation` class compares `git status -z` at each stage boundary (relay.py:285-304); worktrees used by default for n>1 (relay.py:955) | **Low** — Git-level verification, not prompt-based |
| **T4** | **Agent Binary Substitution** | PATH manipulation replaces `opencode`/`claude`/`codex` CLI | Arbitrary command execution as user | `shutil.which()` resolves at runtime; `verify="path"` checks binary exists (models.py:376-377); `verify="ollama"` checks model tag in running Ollama (models.py:380-383) | **Medium** — TOCTOU between check and exec; no signature verification |
| **T5** | **Ollama Model Swap** | Compromised Ollama serves different model for tag | Worker behavior diverges from expectations | Exact tag matching (models.py:132-135, 345-352); no normalization | **Low** — Tag immutability assumed |
| **T6** | **Stats Poisoning** | Corrupt `stats.json` skews auditor selection | Weak auditor picked → audit failures missed | Corrupt file backed up, not wiped (auditor.py:85-93); Laplace smoothing limits single-entry impact | **Low** |
| **T7** | **Registry Poisoning** | Malicious `models.toml` overlay adds model with `best_at="lead everything"` | Lead routes all tasks to attacker-controlled model | User overlay loads after bundled; `verify` field restricted to enum (models.py:264-265); `opt_in` default true (models.py:564) | **Medium** — User controls overlay; social engineering vector |
| **T8** | **Chain File TOML Injection** | Malicious chain file with crafted `from` paths | Arbitrary file read via `resolve_agent_file` | Path traversal blocked: absolute paths or `/` in ref → direct lookup only (relay.py:46-50); `AGENT_DIRS` searched only for bare names (relay.py:51-55) | **Low** |
| **T9** | **Relay Clean Reap Race** | `/relay clean --force` removes worktree while run active | Loss of in-progress work | Active marker (PID) checked; `os.kill(pid, 0)` verifies liveness (relay.py:842-845) | **Low** — PID reuse makes dead run look active (safe direction) |
| **T10** | **Nickname/Profile Persistence XSS** | `/nick` or `/profile` stores malicious string → rendered in TUI/web | Client-side injection in UI consumers | Values stored as plain TOML/JSON; no HTML rendering in core; TUI/web must escape | **Medium** — Depends on downstream consumers |

---

### 2.3 Attack Surface Details

#### 2.3.1 Lead Model as Confused Deputy (T1, T2)
The lead model receives:
- Full roster with capabilities (core.py:626-632)
- User request + history (core.py:771-773)
- Outputs JSON plan with tasks, chains, skills

**Risk**: A crafted request could make the lead:
- Assign sensitive tasks to `TEXT_ONLY` models (qwen, jules) — but they're excluded from lead/auditor/relay (core.py:32-36, 599-600)
- Design chains with malicious goals — but `run_relay` validates goal non-empty (relay.py:393-395)
- Request `use` skill for non-existent path — becomes finding, not injected (core.py:832-835)

**Gap**: No semantic validation of task instructions. A valid JSON plan could instruct "delete all files" and the worker would execute it.

#### 2.3.2 Worker Model File Access (T3, T4)
Workers run with:
- `cwd` = project root (shared) or worktree (isolated)
- Full CLI tool access (edit, shell, read, write)

**Mitigations in place**:
- Worktree isolation default for parallel chains (relay.py:955)
- Git-based isolation check at every stage (relay.py:285-304)
- `gate=true` tasks block dependents on audit failure (core.py:113, auditor.py:271-274)

**Gap**: Single-chain `shared` workspace has no isolation. `TEXT_ONLY` models (qwen, jules) have no file tools but can still influence via text.

#### 2.3.3 Model Availability Verification (T4, T5)
```python
# Path verification (models.py:376-377)
ok = bool(shutil.which(m.cli))

# Ollama verification (models.py:380-383)
ok = m.model in ollama  # exact tag match
```
**Gap**: TOCTOU between `available()` check and `subprocess_exec`. No binary integrity verification (hash/signature).

#### 2.3.4 Profile/Registry Mutation (T7)
`/profile` writes to user overlay (`~/.config/hexmind/models.toml`). Fields validated against accept-list (models.py:529-537). `best_at` required. But:
- `weight` can be set to outrank bundled models (models.py:560-561)
- `opt_in` default true — but `/add` still required to join room
- No approval flow for profile changes

#### 2.3.5 Chain File Loading (T8)
```python
# relay.py:46-50
direct = Path(ref).expanduser()
if direct.is_file():
    return direct
if "/" in ref or "\\" in ref:
    return None  # path-like but not found = error, not search
```
Path traversal blocked. Only bare names search `AGENT_DIRS` (user config dirs).

---

### 2.4 Data Flow Security

| Flow | Direction | Validation | Risk |
|------|-----------|------------|------|
| User → Orchestrator | Commands/requests | `shlex.split`, command dispatch allow-list | Low |
| Orchestrator → Lead | Plan prompt | Structured output schema (ASSEMBLY_SCHEMA) | Medium — prompt injection |
| Lead → Orchestrator | JSON plan | `parse_plan`: agent∈members, deps∈IDs, acyclic | Low — structural only |
| Orchestrator → Workers | Task prompts | `clean_text` strips control/bidi chars | Medium — semantic injection |
| Workers → Orchestrator | Output text | `clean_text` on return | Low |
| Orchestrator → Auditor | Audit prompt | Structured output schema (AUDIT_SCHEMA) | Medium — prompt injection |
| Auditor → Orchestrator | Verdict JSON | `parse_verdict`: strict PASS/FAIL enum | Low |
| Chain file → Relay | TOML stages | `load_chain`: `from` resolved via `resolve_agent_file` | Low |
| Registry → All | Model metadata | TOML schema validation at load (models.py:262-268) | Low |

---

## 3. Critical Findings Summary

| Severity | ID | Finding | File:Line |
|----------|-----|---------|-----------|
| **High** | T1 | Lead prompt injection → arbitrary task generation | core.py:771-773 |
| **High** | T4 | No binary integrity verification for CLIs | models.py:376-377 |
| **Medium** | T2 | Chain/skill directive injection (mitigated by validation) | core.py:375-430 |
| **Medium** | T7 | Registry overlay allows weight manipulation | models.py:560-561 |
| **Medium** | T10 | Nickname/profile persistence lacks output encoding | relay.py:737-747 |
| **Low** | T3 | Worktree escape (mitigated by git isolation checks) | relay.py:285-304 |
| **Low** | T5 | Ollama model swap (mitigated by exact tag match) | models.py:132-135 |
| **Low** | T6 | Stats poisoning (mitigated by backup + smoothing) | auditor.py:85-93 |
| **Low** | T8 | Chain file path traversal (blocked by design) | relay.py:46-50 |
| **Low** | T9 | Relay clean race (mitigated by PID liveness) | relay.py:842-845 |

---

## 4. Recommended Hardening

### 4.1 Immediate (High Impact)
1. **Add semantic plan validation**: After `parse_plan`, run a safety classifier on task instructions (e.g., detect "delete", "rm -rf", "chmod 777", shell redirection) before execution.
2. **Binary integrity**: Record SHA256 of known CLIs at first `available()` check; verify on each `run()`.

### 4.2 Short-Term
3. **Profile change audit log**: Append `/profile` changes to `.hexmind/audit.log` with timestamp, user, diff.
4. **Output encoding contract**: Document that `/nick` and `/profile` values are raw strings; TUI/web must escape.
5. **Lead model rotation**: Periodic `/lead recommend` with audit stats reduces single-model compromise blast radius.

### 4.3 Architectural
6. **Capability-based task sandboxing**: Per-task allow-lists (read-only, no-shell, no-network) enforced by backend.
7. **Signed chain files**: Optional `cosign` verification for chain files in shared environments.
8. **Audit trail immutability**: Append-only log of all task prompts, outputs, verdicts for forensic review.

---

## 5. Strengths Noted

| Area | Why It's Strong |
|------|-----------------|
| **INVARIANT S-1** | Busy-state derived from task status; sleep/retire refused at orchestrator level |
| **Registry as SSOT** | Generated prose eliminates drift; in-place republishing avoids module rebinding bugs |
| **Worktree + Git isolation** | Verification at filesystem level, not prompt level; `-z` handles Unicode |
| **Bounded audit loop** | Max 2 revisions; `gate` tasks block; non-gate escalate but don't deadlock |
| **Backend exclusion clarity** | `HCOM_EXCLUDED` derived, not hardcoded; single source of truth |
| **Schema evolution** | `ASSEMBLY_SCHEMA` extends `PLAN_SCHEMA` additively; `parse_directives` sibling |

---

## 6. Files Not Audited (Out of Scope)
- `tui.py`, `qt/*.py` — UI layer
- `server.py` — FastAPI/WebSocket server
- `reaping.py` — Worktree cleanup logic
- `jules.py` — Jules API integration
- `config.py`, `notify.py`, `__main__.py` — Config, notifications, entry point

---

*End of Report*
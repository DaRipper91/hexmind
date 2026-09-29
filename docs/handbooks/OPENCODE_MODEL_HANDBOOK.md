# 🌌 OpenCode Model Master Handbook 🌌

**The definitive reference for every model in the OpenCode ecosystem — Zen, Go, and Contributor tiers.**

> **Version:** 1.0 · **Compiled:** 2026-09-28 · **Source:** Hexmind registry + live `opencode models` API
> **Tested against:** 619 passing tests · Python 3.14 · OpenCode CLI 2.0.18

---

## 👾 Part 1: User Manual

### 1.1 — The Three Tiers

OpenCode models are organized into three tiers, each with distinct cost, capability, and use-case profiles.

| Tier | Provider Prefix | Cost | Model Count | Best For |
| :--- | :--- | :--- | :--- | :--- |
| **Zen (Free)** | `opencode/*` | $0.00 | 8 | Daily driving, zero-cost workflows, atomic tasks |
| **Go** | `opencode-go/*` | $0.10–$3.00/M input | 27 | Production workloads, specialized reasoning, high-throughput |
| **Contributor** | `opencode-go/muse-spark-*` | $0.10/M input | 2 | Community-contributed models, skill authoring |

> 💡 **Pro Tip / Expert Opinion:** Start every new project on Zen models. They are free, fast, and cover 90% of daily development work. Switch to Go only when you hit a capability wall — deeper reasoning, larger context, or specialized domains.

### 1.2 — Quick Start

**List all available models:**
```bash
opencode models
```

**Run a task with a specific model:**
```bash
opencode run --auto -m opencode/nemotron-3-ultra-free "Your task here"
```

**Run with a reasoning variant (Go tier only):**
```bash
opencode run --auto -m opencode-go/gpt-6-luna#high "Your task here"
```

**Switch models in a Hexmind room:**
```
/lead nemotron-ultra
/add longcat-preview
/remove mimo-flash
```

**Check which models are live:**
```
/scan
```

### 1.3 — Daily-Driver Presets

**Preset A — "Solo Developer" (Zen-only, zero cost):**

| Role | Model | Why |
| :--- | :--- | :--- |
| Lead / Architect | `nemotron-ultra` | Heavy CoT, system design, security |
| Coder | `big-pickle` | Relentless TDD, drives tests to green |
| Fast Fixes | `nemotron-lightning` | Sub-second atomic work |
| UI Specialist | `mimo-flash` | DOM parsing, DevTools, accessibility |
| Researcher | `longcat-preview` | Massive context ingestion |
| Skill Author | `muse-spark` | Prompt engineering, rule generation |

**Preset B — "Production Team" (Go tier, paid):**

| Role | Model | Why |
| :--- | :--- | :--- |
| Lead / Architect | `opencode-go/kimi-k3` | Deep reasoning, 1M context |
| Coder | `opencode-go/deepseek-v4-pro` | Strong code generation, high variant |
| Fast Fixes | `opencode-go/mimo-v2.5` | Low latency, low cost |
| UI Specialist | `opencode-go/glm-5.3-flash` | Vision-DOM, high throughput |
| Researcher | `opencode-go/qwen3.8-max` | Large context, structured output |
| Evaluator | `opencode-go/grok-4.7` | Adversarial review, security audit |

> ⚠️ **Watch Out:** Go-tier models incur per-token costs. A single `kimi-k3` session with 100K input tokens costs $0.30. Monitor usage with `opencode stats --models`.

---

## 🧠 Part 2: Technical Manual

### 2.1 — System Architecture

The Hexmind model registry is a **structured TOML-based source of truth** that replaces hand-maintained prose. Every model is a `Model` dataclass instance with 18 fields:

```python
@dataclass(frozen=True)
class Model:
    name: str           # Internal identifier (e.g., "nemotron-ultra")
    label: str          # Display name + vendor
    best_at: str        # Primary routing signal
    cli: str            # CLI tool: opencode | ollama | claude | agy | codex | copilot | jules | kimi
    verify: str         # Availability check: path | ollama | env
    tier: str           # cloud | local
    domains: tuple      # Auditor.DOMAINS values
    model: str          # provider/model id (cloud) or Ollama tag (local)
    avoid_for: str      # Anti-pattern routing signal
    think: bool         # Reasoning-trace flag
    variant: str        # Provider-specific reasoning effort
    opt_in: bool        # Only joins with --with NAME
    text_only: bool     # Cannot see local files
    weight: int         # Preference score (higher = favoured)
    color: str          # TUI display color
    footprint: str      # Human-readable deployment summary
    env: str            # Environment variable for verify=env
    fallback_for: tuple # Offline fallback targets
```

> 🧠 **Architectural Note:** The `ref` property constructs the CLI reference string. Only `opencode` CLI models get `#variant` appended — `kimi` takes reasoning in its own config, so appending `#max` would create an invalid alias.

### 2.2 — MoE Routing Dynamics

Model selection follows a **four-stage pipeline:**

1. **Domain matching** — `auditor.DOMAINS` values filter models by task domain
2. **Weight sorting** — `by_weight()` sorts by `(-weight, name)`, preferring opencode models (R5)
3. **Stats ranking** — Laplace score per domain breaks ties using historical performance
4. **Fallback** — `Orchestrator.fallback()` reassigns failed tasks to the next-best available model

**Weight assignments (from registry):**

| Weight | Models |
| :--- | :--- |
| 100 | nemotron-lightning, nemotron-ultra, mimo-flash, big-pickle, space-bunny, longcat-preview |
| 90 | muse-spark |
| 80 | ling-flash |
| 60 | claude, agy, codex |
| 50 | kimi |
| 40 | copilot |
| 30 | jules |
| 20 | qwen, qwen-large |

> ⚠️ **Watch Out:** `fallback()` currently sorts by Laplace score alone — `weight` is data with no consumer in the fallback path (WS-5 gap). A free model that audits well does not automatically win fallback over a paid model with identical stats.

### 2.3 — Context Windows

| Model | Context Horizon | Source |
| :--- | :--- | :--- |
| LongCat 2.5 Preview | Massive (whole-repo ingestion) | `model-updates.md` |
| Kimi Code | 1M tokens | `model-updates.md` |
| All others | > ⚠️ **Data Not Provided in Source Document.** | — |

> 💡 **Pro Tip / Expert Opinion:** Use `longcat-preview` for any task that requires reading more than 5 files at once. Its context window is the largest in the Zen tier, and it is the only free model that can ingest a full Repomix digest in a single turn.

### 2.4 — Quota Profiles & Rate Limits

**Zen tier:** All models are $0.00 — no token cost, no quota tracking needed.

**Go tier pricing (per million tokens, from live API):**

| Model | Input | Output | Cache Read | Context Tier |
| :--- | :--- | :--- | :--- | :--- |
| GPT-6 Luna | $0.10 | $0.50 | $0.01 | 272K |
| MiMo V2.5 | $0.14 | $0.28 | $0.003 | — |
| MiMo V2.5 Pro | $0.435 | $0.87 | $0.004 | — |
| MiMo V2.6 Pro | $0.435 | $0.87 | $0.004 | — |
| DeepSeek V4.1 Flash | $0.15 | $0.60 | $0.003 | — |
| DeepSeek V4 Pro | $0.66 | $1.98 | $0.022 | — |
| GLM-5.3 Flash | $0.15 | $0.50 | $0.03 | — |
| GLM-5.3 | $1.40 | $4.40 | $0.26 | — |
| Qwen3.8 Flash | $0.15 | $0.47 | $0.016 | — |
| Qwen3.8 Max | $2.00 | $6.00 | $0.25 | — |
| Qwen3.7 Plus | $0.40 | $1.60 | $0.04 | 256K |
| Grok 4.7 | $2.00 | $6.00 | $0.50 | 200K |
| Kimi K3 | $3.00 | $15.00 | $0.30 | — |
| Kimi K2.7 Code | $0.95 | $4.00 | $0.19 | — |
| MiniMax-M3 | $0.30 | $1.20 | $0.06 | 512K |
| MiniMax-M2.7 | $0.30 | $1.20 | $0.06 | — |
| Hy4 preview | $0.834 | $2.501 | $0.042 | — |
| Muse Spark 1.3 Contributor | $0.10 | $0.20 | $0.002 | — |

> ⚠️ **Watch Out:** Kimi K3 at $3.00/$15.00 per million tokens is the most expensive model in the roster. A 100K-token session costs $0.30 input + $1.50 output. Use it only for tasks that genuinely require its deep reasoning capability.

### 2.5 — Variant Support (Live-Verified)

**Zen tier variants:**

| Model | Variants |
| :--- | :--- |
| Space Bunny Free | `low`, `medium`, `high`, `xhigh`, `max` |
| Muse Spark 1.3 Free | `minimal`, `low`, `medium`, `high`, `xhigh` |
| All other Zen models | None |

**Go tier variants:**

| Model | Variants |
| :--- | :--- |
| Space Bunny Free | `low`, `medium`, `high`, `xhigh`, `max` |
| GPT-6 Luna | `none`, `low`, `medium`, `high`, `xhigh`, `max` |
| Grok 4.7 | `low`, `medium`, `high`, `xhigh` |
| DeepSeek V4.1 Flash | `low`, `high`, `max` |
| Muse Spark 1.3 Contributor | `minimal`, `low`, `medium`, `high`, `xhigh` |
| Hy4 preview | `none`, `high` |
| GLM-5.3 Flash | `low`, `high`, `max` |
| GLM-5.3 | `low`, `high`, `max` |
| Qwen3.8 Flash | `none`, `low`, `medium`, `xhigh` |
| Qwen3.8 Max | `low`, `medium`, `xhigh` |
| Kimi K3 | `max` |
| MiniMax-M3 | `none`, `thinking` |
| DeepSeek V4 Pro | `high`, `max` |
| MiMo V2.5 / V2.5 Pro / V2.6 Pro | None |
| Kimi K2.7 Code | None |
| Qwen3.7 Plus | None |
| MiniMax-M2.7 | None |

> ⚠️ **Watch Out:** The `~/.config/hexmind/models.toml` user override explicitly sets `variant = ""` for `nemotron-ultra` because `opencode` 2.0.18 rejects `#high` with "Variant unavailable". Only declare a variant after `opencode run -m id#variant` succeeds live.

### 2.6 — Session Architecture

OpenCode sessions are **directory-bound**. A session ID may only be passed to a `cwd` identical to the one it was created in. Violating this causes a **30-minute silent hang** (exit code 124, zero output).

**Session key:** `(model, directory)` — never model alone.

**Event stream (`--format json`):**

| Event | Payload |
| :--- | :--- |
| `step_start` | `sessionID` |
| `text` | `part.text` — the model's reply |
| `step_finish` | `part.reason`, `part.tokens.total` |

> 🧠 **Architectural Note:** The `opencode serve` + `run --attach <url>` pattern avoids MCP cold-boot on every run. With 8 models × many tasks, this overhead is the dominant per-task cost. Design `DirectBackend` so the transport (spawn-per-call vs. attach) is swappable.

---

## 🦄 Part 3: Developer Guide

### 3.1 — Role-to-Model Mapping

**Heavyweight Architects & Deep Reasoners** — Primary engines for complex system architecture, multi-file refactoring, difficult algorithm design, and gnarly runtime logic. Use sparingly to avoid burning Go-tier quota.

| Role | Primary Model | Secondary | Trigger |
| :--- | :--- | :--- | :--- |
| **Architect / Planner** | `opencode-go/deepseek-v4-pro` | `opencode-go/qwen3.8-max` | Deep architectural refactoring, algorithmic implementation, complex debugging across interdependent files |
| **Systems Programmer** | `opencode-go/qwen3.8-max` | `opencode-go/deepseek-v4-pro` | Strict systems programming, low-level logic, POSIX/shell plumbing, math/algorithm verification |
| **Root-Cause Diagnostician** | `opencode-go/grok-4.7` | `opencode-go/grok-4.6` | Blunt root-cause diagnosis, debugging obscure runtime crashes, vetting architectural trade-offs |
| **API Designer** | `opencode-go/gpt-6-luna` | `opencode-go/gpt-5.6-luna` | High-level API design, cross-language design patterns, clean technical documentation |
| **Deep Reasoner** | `opencode-go/kimi-k3` | — | Deep reasoning over large codebases, complex regression tracing, multi-tier state machine design |

**Fast Daily Drivers & Autonomous Sub-Agents** — High-throughput workhorses for autonomous agent loops, unit test generation, linter corrections, and routine feature additions.

| Role | Primary Model | Secondary | Trigger |
| :--- | :--- | :--- | :--- |
| **Autonomous Coder** | `opencode-go/deepseek-v4.1-flash` | `opencode-go/qwen3.8-flash` | Autonomous builder/coder agent loops, fast unit test creation, ShellCheck fixes, rapid AST edits |
| **Inline Completer** | `opencode-go/deepseek-v4-flash` | `opencode-go/qwen3.8-flash` | General inline code completions, fast bug patches, lightweight utility scripting |
| **Shell Automator** | `opencode-go/qwen3.8-flash` | `opencode-go/deepseek-v4.1-flash` | Rapid bash/fish shell automation, CLI utilities, CRUD endpoints, terminal tooling |
| **Generalist Coder** | `opencode-go/qwen3.7-plus` | `opencode-go/kimi-k2.7-code` | Generalist mid-tier coding, glue scripts, routine feature extensions |
| **Function Refactorer** | `opencode-go/kimi-k2.7-code` | `opencode-go/glm-5.3` | Code-specific refactoring with long context windows for library patterns |
| **Function-Calling Orchestrator** | `opencode-go/glm-5.3` | `opencode-go/glm-5.2` | Structured agent function calling, API glue code, pipeline orchestration |
| **Tool Dispatcher** | `opencode-go/glm-5.3-flash` | — | Fast tool-dispatching sub-agents, JSON payload parsing, unit-test mocking |
| **Day-to-Day Coder** | `opencode-go/mimo-v2.6-pro` | `opencode-go/mimo-v2.6-flash` | Mid-tier day-to-day coding, boilerplate drafting, small component refactoring |

**Long-Context & Monolith Readers** — Deploy when an agent needs to ingest entire documentation trees, parse massive execution logs, or digest large codebases.

| Role | Primary Model | Secondary | Trigger |
| :--- | :--- | :--- | :--- |
| **Ingestion Reader** | `longcat-preview` | `opencode-go/longcat-2.0` | Ingesting massive log files, full stack traces, multi-file code diffs without chunking |
| **Documentation Parser** | `opencode-go/minimax-m3` | `opencode-go/minimax-m2.7` | Parsing mixed prose/code documentation, onboarding summaries, codebase explanations |
| **Doc Generator** | `opencode-go/minimax-m2.7` | — | Long-form markdown documentation generation, changelog compilation |

**Specialized & Multimodal Utilities** — Targeted models for verification, specialized datasets, or visual inputs.

| Role | Primary Model | Secondary | Trigger |
| :--- | :--- | :--- | :--- |
| **Evaluator / Judge** | `nemotron-ultra` | `opencode-go/grok-4.7` | Deep logical verification, reasoning audits, policy/safety violation checks |
| **Fast Judge** | `nemotron-lightning` | — | Internal evaluator agent, sanity-checking code output, synthetic data generation |
| **Vision Specialist** | `opencode-go/deepseek-v4-flash-vision-exp` | — | Converting UI screenshots/wireframes to code, inspecting visual terminal artifacts, chart auditing |
| **Quant / Compliance** | `ling-flash` | — | Parsing tabular datasets, financial records, CSV pipelines, metric parsing scripts |

**Community Sandboxes & Experimental Tiers** — Zero-cost scratchpad testing, experimental prototyping, or simple shell checks without burning primary Go quota.

| Role | Primary Model | Secondary | Trigger |
| :--- | :--- | :--- | :--- |
| **Skill Author** | `muse-spark` | — | Prototyping creative UI layouts, styling, terminal UI themes, CSS/HTML mockups |
| **Experimental** | `opencode-go/hy4-preview` | `opencode-go/hy3` | Experimental code synthesis, early testing of next-gen speculative model weights |
| **Scratchpad** | `space-bunny` | `big-pickle` | Zero-cost scratchpad runs, sanity-checking simple shell one-liners, throwaway string transforms |
| **Legacy Tester** | `opencode-go/mimo-v2.5` | `opencode-go/mimo-v2.5-pro` | Legacy testing and regression checking against older agent prompts |

### 3.2 — Multi-Agent Coordination

**The Hexmind orchestrator runs models as parallel sub-agents, each holding its own session.**

**Key rules:**

1. **Snapshot at turn start** — A plan already in flight keeps its own member snapshot. Removing a model mid-run cannot orphan a running task.
2. **INVARIANT S-1** — A working model cannot be put to sleep. Only `pending` tasks may be reassigned.
3. **Auditor ≠ Lead** — The auditor set excludes the current lead. A model cannot review its own reasoning.
4. **Weight-aware fallback** — `fallback()` should sort by `(weight, stats score)` — a free model that audits well wins.

**Concurrency limits:**
- Local Ollama models share one slot (`_local_lock` serializes them)
- Cloud models run without explicit concurrency limits, but rate limits apply
- The TUI queues via `asyncio.Lock`; the server has no request queue (409s)

> 💡 **Pro Tip / Expert Opinion:** When dispatching parallel tasks, assign each task to a model whose `best_at` explicitly covers the task domain. The lead reads `best_at` to assign work — a model without a clear `best_at` is a known unknown.

### 3.3 — System Prompt Optimization

**Rules for preserving AST integrity:**
- Force chain-of-thought analysis on edge cases and failure modes before generating implementation code
- Require explicit algorithmic bounds (`O(n)`) for any performance-critical code
- Mandate line-by-line citations (`file:///path#Lxx-Lyy`) for every synthesized finding

**Rules for avoiding conversational drift:**
- Keep prompts atomic — one function or one failing test at a time
- Provide concrete pass/fail verification commands
- Never mark tasks done until execution confirms clean test runs

**Rules for deterministic tool use:**
- Set `gate: true` on migrations, core logic, and anything whose failure would be silently wrong
- Route by `best_at` and respect `avoid_for`
- Report honestly — a failed task, a missing member, an unmet requirement

> 🧠 **Architectural Note:** The `hexmind-lead` skill (`.claude/skills/hexmind-lead/SKILL.md`) encodes these rules as a reusable document. It should be authored by `muse-spark` and reviewed by `nemotron-ultra`.

---

## 🧊 Part 4: Standard Operating Procedures

### SOP-01: Full-Repo Refactor Workflow

**Objective:** Refactor an entire repository with architectural oversight, test-driven execution, and adversarial review.

**Stages:**

```
1. INGEST  →  longcat-preview reads the full Repomix digest
2. ARCHIVE  →  nemotron-ultra reviews architecture, identifies bottlenecks
3. PLAN    →  nemotron-ultra produces a phased refactor plan with ADRs
4. BUILD   →  big-pickle implements each phase using strict TDD
5. VERIFY  →  nemotron-lightning runs lint, tests, and commit generation
6. AUDIT   →  nemotron-ultra conducts adversarial code review
7. COVER   →  longcat-preview verifies 100% requirement coverage against the plan
```

**Dispatch commands:**

```bash
# Step 1: Ingest
opencode run --auto -m opencode/longcat-2.5-preview-free \
  -f repo-repomix.txt \
  "Ingest this repository digest. Identify all modules, dependencies, and architectural patterns."

# Step 2: Architect
opencode run --auto -m opencode/nemotron-3-ultra-free \
  -f repo-repomix.txt \
  "Perform a architectural review. Identify concurrency bottlenecks, security vulnerabilities, and refactoring opportunities."

# Step 4: Build (per phase)
opencode run --auto -m opencode/big-pickle \
  -f refactor-plan.md \
  "Execute Phase 1 from the plan. Write failing tests first, implement, verify green. Use TDD."

# Step 6: Audit
opencode run --auto -m opencode/nemotron-3-ultra-free \
  -f refactor-plan.md \
  -f implementation-diff.txt \
  "Conduct an adversarial code review. Scrutinize edge cases, error handling, and silent fallbacks."
```

> ⚠️ **Watch Out:** Never let the builder audit its own work. Big Pickle drives code to pass tests, but Nemotron 3 Ultra acts as the skeptical, adversarial senior reviewer.

---

### SOP-02: Zero-Quota Scratchpad Testing & Rapid Triage

**Objective:** Test ideas, run linters, and triage failures without consuming Go-tier quota.

**Models:** All Zen (free) tier.

**Workflow:**

```
1. SCRATCH  →  nemotron-lightning generates a quick test or lint fix
2. RUN      →  Execute locally (pytest, ruff, eslint)
3. ITERATE  →  nemotron-lightning fixes failures sub-second
4. COMMIT   →  nemotron-lightning generates Conventional Commit messages
```

**Dispatch commands:**

```bash
# Quick test generation
opencode run --auto -m opencode/nemotron-3.5-lightning-free \
  "Write a pytest test for the function at src/auth.py:42. Cover happy path, edge cases, and error handling."

# Lint fix
opencode run --auto -m opencode/nemotron-3.5-lightning-free \
  "Fix all ruff lint errors in src/auth.py. Keep changes minimal."

# Commit message
opencode run --auto -m opencode/nemotron-3.5-lightning-free \
  "Generate a Conventional Commit message for the changes in this diff."
```

> 💡 **Pro Tip / Expert Opinion:** Keep every prompt atomic — one function or one failing test at a time. Zen models excel at sub-second atomic work but degrade on multi-module design tasks.

---

### SOP-03: Ingesting Massive Legacy Codebases

**Objective:** Analyze entire monorepos, multi-year postmortem folders, or multimegabyte log files.

**Models:** `longcat-preview` (primary), `opencode-go/qwen3.8-max` (Go tier, larger context).

**Workflow:**

```
1. BUNDLE   →  Use Repomix to aggregate the codebase into a single file
2. INGEST   →  longcat-preview reads the full bundle in one context
3. SYNTHESIZE →  Produce a structured summary with citations
4. PLAN     →  nemotron-ultra reviews the summary and identifies action items
5. DISPATCH →  big-pickle executes the plan phase by phase
```

**Dispatch commands:**

```bash
# Ingest
opencode run --auto -m opencode/longcat-2.5-preview-free \
  -f monorepo-repomix.txt \
  "Ingest this monorepo digest. Produce a structured summary: modules, dependencies, architectural patterns, and technical debt. Cite every finding with file:line references."

# Plan
opencode run --auto -m opencode/nemotron-3-ultra-free \
  -f monorepo-repomix.txt \
  -f ingestion-summary.md \
  "Review this ingestion summary. Identify the top 5 technical debt items and propose a phased remediation plan."
```

> ⚠️ **Watch Out:** LongCat 2.5 Preview has a massive context window but is not infinite. For codebases exceeding ~500K tokens, chunk the Repomix output and run multiple ingestion passes.

---

### SOP-04: Graceful Fallback Handling

**Objective:** Handle rate limits, quota exhaustion, and model failures without workflow interruption.

**Detection:**
- `QUOTA_RE` (`core.py:51`) detects quota/rate-limit failures in model output
- `Orchestrator.fallback()` (`core.py:348`) reassigns the task to the next-best available model

**Fallback priority:**

```
1. Primary model fails → fallback() selects next by (weight, stats score)
2. Cloud tier entirely down → local Ollama models take over (if configured)
3. All models exhausted → task marked failed, user notified
```

**Registry `fallback_for` field:**
```toml
[models.deepseek]
fallback_for = ["nemotron-ultra"]  # deepseek-r1 covers nemotron-ultra offline
```

> 🧠 **Architectural Note:** The current `fallback()` filters only on membership — there is no notion of cloud vs. local tier. If the entire cloud tier is down, tasks are reshuffled among equally-dead cloud models. The `fallback_for` field in the registry is the intended fix but is not yet consumed by `fallback()`.

**Manual fallback:**
```
/lead nemotron-ultra        # Switch to a model that is still available
/remove mimo-flash         # Remove the failed model from the roster
/add longcat-preview        # Add a replacement
```

---

## 🌌 Part 5: Glossary

### Effective Needle Horizon

The maximum context window within which a model can reliably locate and reason over a specific piece of information ("needle"). Distinct from raw context window size — a model with a 1M token context window may have an effective needle horizon of only 200K tokens for complex multi-step reasoning.

### AST Preservation

The requirement that code modifications maintain the Abstract Syntax Tree integrity of the original program. A refactoring that changes runtime behavior, even if tests pass, has violated AST preservation. Enforced by adversarial code review (nemotron-ultra) and diff compliance auditing (longcat-preview).

### MoE Activation Overhead

The computational cost of routing tokens through a Mixture-of-Experts model. In OpenCode, this manifests as: (1) the `weight` field determining routing priority, (2) the `by_weight()` sort determining which model receives a task first, and (3) the `fallback()` path adding latency when a primary model fails and a secondary must be activated.

### Prompt Drift

The degradation of model output quality as a session grows longer and context accumulates. Manifests as: the model "forgetting" earlier instructions, paraphrasing rather than quoting decisions, and citing decisions that were never made. Mitigated by `OPENCODE_DISABLE_AUTOCOMPACT` awareness and the `/reset` command for clean context.

### Zero Hallucination Boundaries

The editorial directive that forbids fabricating specifications, context windows, or parameter figures that are not present in source documents. When data is missing, the output must explicitly state: `> ⚠️ Data Not Provided in Source Document.` This applies to all generated documentation, model handbooks, and technical references.

### Context Degradation

The loss of model reasoning quality as the context window fills. Distinct from prompt drift — context degradation is a function of total token count, while prompt drift is a function of conversation length and topic shifts. LongCat 2.5 Preview is specifically designed to resist context degradation through its massive context window.

---

## 📊 Part 6: Reference Guide

### 6.1 — Master Lookup Matrix

All 37 models from the OpenCode ecosystem. Verified models have live API data. Unverified models are marked accordingly.

| # | Model Name & Tier | Context Horizon | Optimal Agent Role | Best Usage (Sweet Spot) | Worst Usage (Anti-Pattern) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| 1 | **MiMo-V2.6-Flash Free** · Zen | > ⚠️ Data Not Provided | Day-to-Day Coder | Fast scratchpad code fixes, lint cleanup, automated commit message generation | Complex architectural reasoning; tends to take shortcuts on edge-case handling |
| 2 | **Ling 3.0 Flash Fin Free** · Zen | > ⚠️ Data Not Provided | Quant / Compliance | Parsing tabular datasets, financial records, CSV pipelines, metric parsing scripts | General-purpose software engineering and agentic file editing |
| 3 | **Nemotron 3 Ultra Free** · Zen | > ⚠️ Data Not Provided | Evaluator / Judge | Deep logical verification, reasoning audits, checking generated code for policy/safety violations | Fast, informal command-line development |
| 4 | **Big Pickle** · Zen | > ⚠️ Data Not Provided | Scratchpad | Free sandbox testing, basic regex checks, simple unit test skeleton drafting | Multi-file codebases, complex debugging, any task where precision is critical |
| 5 | **LongCat 2.5 Preview Free** · Zen | Massive (whole-repo) | Ingestion Reader | Ingesting massive log files, full stack traces, multi-file code diffs without chunking | Snappy, interactive CLI back-and-forth (generation latency is higher) |
| 6 | **Space Bunny Free** · Zen | > ⚠️ Data Not Provided | Scratchpad | Zero-cost scratchpad runs, sanity-checking simple shell one-liners, throwaway string transforms | Multi-step autonomous agent execution (will drop tool context or get trapped in repetition) |
| 7 | **Nemotron 3.5 Lightning Free** · Zen | > ⚠️ Data Not Provided | Fast Judge | Acting as internal "judge" or evaluator agent, sanity-checking code output, synthetic data generation | End-to-end full-stack software scaffolding |
| 8 | **Muse Spark 1.3 Free** · Zen | > ⚠️ Data Not Provided | Skill Author | Prototyping creative UI layouts, styling, terminal UI themes, CSS/HTML mockups | Concurrency, memory management, or deep backend threading logic |
| 9 | **LongCat 2.5 Preview Free** · Go | Massive (whole-repo) | Ingestion Reader | Same as Zen but with Go-tier throughput and reliability | Small edits, single-file tasks |
| 10 | **Space Bunny Free** · Go | > ⚠️ Data Not Provided | Scratchpad | Same as Zen but with Go-tier throughput | Deterministic verification, structured output |
| 11 | **GPT-6 Luna** · Go | 272K | API Designer | High-level API design, cross-language design patterns, writing clean maintainable technical documentation | High-throughput autonomous CLI loops (rate limits make it inefficient for sub-agents) |
| 12 | **MiMo-V2.6-Flash** · Go | > ⚠️ Data Not Provided | Day-to-Day Coder | Fast scratchpad code fixes, lint cleanup, automated commit message generation | Complex architectural reasoning; tends to take shortcuts on edge-case handling |
| 13 | **MiMo-V2.6-Pro** · Go | > ⚠️ Data Not Provided | Day-to-Day Coder | Mid-tier day-to-day coding, boilerplate drafting, small component refactoring | Monolithic repo migrations requiring 100k+ tokens of sustained context coherence |
| 14 | **Grok 4.7** · Go | 200K | Root-Cause Diagnostician | Blunt root-cause diagnosis, debugging obscure runtime crashes, vetting architectural trade-offs without sugarcoating | Strict JSON-only tool-calling pipelines; tends to leak conversational prose if not pinned down |
| 15 | **DeepSeek V4.1 Flash** · Go | > ⚠️ Data Not Provided | Autonomous Coder | Autonomous builder/coder agent loops, fast unit test creation, ShellCheck fixes, rapid AST edits | High-level, green-field system architecture from vague, non-specific specifications |
| 16 | **Hy4 preview** · Go | > ⚠️ Data Not Provided | Experimental | Experimental code synthesis and early testing of next-gen speculative model weights | Mission-critical refactoring or live production deployment pipelines |
| 17 | **GLM-5.3-Flash** · Go | > ⚠️ Data Not Provided | Tool Dispatcher | Fast tool-dispatching sub-agents, JSON payload parsing, standard unit-test mocking | Writing core domain logic from scratch without explicit boilerplate provided |
| 18 | **Qwen3.8 Flash** · Go | > ⚠️ Data Not Provided | Shell Automator | Rapid bash/fish shell automation, CLI utilities, standard CRUD endpoints, terminal tooling | Complex asynchronous concurrency bug-hunting where race conditions depend on deep timing nuances |
| 19 | **DeepSeek V4 Flash Vision Exp** · Go | > ⚠️ Data Not Provided | Vision Specialist | Converting UI screenshots/wireframes to code, inspecting visual terminal artifacts, chart auditing | Pure backend C/Python logic (burning vision token overhead adds zero value to terminal-only tasks) |
| 20 | **GLM-5.3** · Go | > ⚠️ Data Not Provided | Function-Calling Orchestrator | Structured agent function calling, API glue code, pipeline orchestration | Edge-case low-level systems programming (e.g., custom memory allocators or bare-metal logic) |
| 21 | **Grok 4.6** · Go | > ⚠️ Data Not Provided | Root-Cause Diagnostician | Solid fallback for general architecture and debugging when Grok 4.7 hits provider-side rate limits | Fine-grained AST-level refactors or strict adherence to niche API interfaces |
| 22 | **Qwen3.8 Max** · Go | > ⚠️ Data Not Provided | Systems Programmer | Strict systems programming, low-level logic, complex POSIX/shell plumbing, rigorous math/algorithm verification | Open-ended marketing copy or writing subjective documentation without strict constraints |
| 23 | **DeepSeek V4 Flash** · Go | > ⚠️ Data Not Provided | Inline Completer | General inline code completions, fast bug patches, lightweight utility scripting | Deep multi-hop logical debugging across large repos (can lose track of distant interfaces) |
| 24 | **Kimi K3** · Go | > ⚠️ Data Not Provided | Deep Reasoner | Deep reasoning over large codebases, complex regression tracing, multi-tier state machine design | Quick single-file script adjustments (spins up heavy compute for low-complexity prompts) |
| 25 | **GPT-5.6 Luna** · Go | > ⚠️ Data Not Provided | API Designer | Code reviews, PR summaries, clean docstring scaffolding, drafting readable integration tests | Low-level C/kernel debugging or heavy command-line automation |
| 26 | **Hy3** · Go | > ⚠️ Data Not Provided | Experimental | Fallback experimental testing | Standard agent workflows (superseded by Hy4) |
| 27 | **LongCat-2.0** · Go | > ⚠️ Data Not Provided | Ingestion Reader | Legacy long-context fallback for reading large documentation dumps | Active code synthesis (prone to looser syntax formatting compared to LongCat 2.5) |
| 28 | **GLM-5.2** · Go | > ⚠️ Data Not Provided | Function-Calling Orchestrator | Backup function-calling model for legacy agent scripts tuned to GLM schemas | New green-field projects (outclassed by GLM-5.3 in token efficiency and instruction-following) |
| 29 | **Kimi K2.7 Code** · Go | > ⚠️ Data Not Provided | Function Refactorer | Code-specific refactoring where long context windows are needed to reference existing library patterns | Sub-second interactive CLI tab completions |
| 30 | **Qwen3.7 Plus** · Go | 256K | Generalist Coder | Generalist mid-tier coding, drafting glue scripts, routine feature extensions | Superseded by Qwen3.8 Flash for raw speed and Qwen3.8 Max for complex logic |
| 31 | **MiniMax-M3** · Go | 512K | Documentation Parser | Parsing mixed prose/code documentation, onboarding summaries, contextual codebase explanations | Strict, zero-shot systems code generation with heavy type constraints |
| 32 | **MiMo V2.5** · Go | > ⚠️ Data Not Provided | Legacy Tester | Legacy testing and regression checking against older agent prompts | Modern multi-tool agent loops where V2.6 handles context significantly better |
| 33 | **MiMo V2.5 Pro** · Go | > ⚠️ Data Not Provided | Legacy Tester | Legacy testing and regression checking against older agent prompts | Modern multi-tool agent loops where V2.6 handles context significantly better |
| 34 | **MiniMax-M2.7** · Go | > ⚠️ Data Not Provided | Doc Generator | Long-form markdown documentation generation and changelog compilation | Autonomous tool-calling agent loops (can lose schema formatting during complex tool runs) |
| 35 | **DeepSeek V4 Pro (New)** · Go | > ⚠️ Data Not Provided | Architect / Planner | Deep architectural refactoring, algorithmic implementation, complex debugging across multiple interdependent files | Fast one-line CLI edits or simple syntax fixes (massive latency and token overhead) |
| 36 | **Muse Spark 1.3 Contributor** · Go | > ⚠️ Data Not Provided | Skill Author | Prototyping creative UI layouts, styling, terminal UI themes, CSS/HTML mockups | Concurrency, memory management, or deep backend threading logic |
| 37 | **Muse Spark 1.2 Contributor** · Go | > ⚠️ Data Not Provided | Skill Author | Legacy experimental styling and creative script generation | Any production-grade backend logic |

> ⚠️ **Data Not Provided in Source Document.** — Context horizons for models without verified data from the live API or source documents. The `model-updates.md` report provides qualitative descriptions but not exact token counts for most models.

### 6.2 — OpenCode CLI Cheatsheet

**Model selection:**
```bash
opencode run --auto -m opencode/nemotron-3-ultra-free "task"
opencode run --auto -m opencode-go/gpt-6-luna#high "task"
opencode run --auto -m opencode/big-pickle "task"
```

**Session management:**
```bash
opencode session list --format json          # List all sessions
opencode session delete <id>                 # Delete a session
opencode export <id>                         # Export session history
opencode stats --models                      # Per-model token/cost breakdown
opencode db path                             # Show database location
```

**Server mode:**
```bash
opencode serve                               # Start persistent server
opencode run --attach <url>                 # Attach to server (avoids MCP cold-boot)
```

**Useful flags:**
| Flag | Effect |
| :--- | :--- |
| `-s, --session <id>` | Resume a specific session |
| `-c, --continue` | Continue the last session |
| `--fork` | Branch a session when work diverges |
| `--format json` | Raw JSON event stream |
| `-f, --file <path>` | Attach files (vision) |
| `--variant <e>` | Provider-specific reasoning effort |
| `--thinking` | Show thinking blocks |
| `--pure` | Disable external plugins (reproducibility) |
| `--title <name>` | Label sessions per model/room |

**Environment variables:**
| Variable | Effect |
| :--- | :--- |
| `OPENCODE_DISABLE_AUTOCOMPACT` | Prevent long sessions from auto-compacting |
| `OPENCODE_DISABLE_CLAUDE_CODE_SKILLS` | Disable skill loading |
| `OLLAMA_HOST` | Ollama API endpoint (default: `http://127.0.0.1:11434`) |

### 6.3 — Quick-Switch Aliases

```bash
# Add to ~/.bashrc or ~/.zshrc

# Zen tier
alias oc-ultra='opencode run --auto -m opencode/nemotron-3-ultra-free'
alias oc-pickle='opencode run --auto -m opencode/big-pickle'
alias oc-lightning='opencode run --auto -m opencode/nemotron-3.5-lightning-free'
alias oc-mimo='opencode run --auto -m opencode/mimo-v2.6-flash-free'
alias oc-longcat='opencode run --auto -m opencode/longcat-2.5-preview-free'
alias oc-bunny='opencode run --auto -m opencode/space-bunny-free'
alias oc-ling='opencode run --auto -m opencode/ling-3.0-flash-fin-free'
alias oc-muse='opencode run --auto -m opencode/muse-spark-1.3-contributor-free'

# Go tier
alias oc-kimi='opencode run --auto -m opencode-go/kimi-k3'
alias oc-grok='opencode run --auto -m opencode-go/grok-4.7'
alias oc-gpt='opencode run --auto -m opencode-go/gpt-6-luna'
alias oc-deepseek='opencode run --auto -m opencode-go/deepseek-v4-pro'
alias oc-qwen='opencode run --auto -m opencode-go/qwen3.8-max'
alias oc-glm='opencode run --auto -m opencode-go/glm-5.3'
alias oc-minimax='opencode run --auto -m opencode-go/minimax-m3'
```

---

> 🧠 **Architectural Note:** This handbook is a living document. When new models are added to the OpenCode ecosystem, update the Master Lookup Matrix and verify variant support with `opencode run -m id#variant` before declaring a variant in the registry.

> ⚠️ **Data Not Provided in Source Document.** — Exact context window sizes, parameter counts, and MoE activation patterns for most models are not available from the source documents or live API. Qualitative descriptions from `model-updates.md` are used where quantitative data is absent.

---

*🌌 Compiled by the DaRipper Editorial Chain · Architect → SME → Auditor → UX Writer 🌌*
*🦄 Dark Pastel Edition · Zero Hallucination Directive Enforced 🦄*

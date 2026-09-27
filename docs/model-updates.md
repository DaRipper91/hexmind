# Hybrid Intelligence Blueprint & Model Operational Report
## Opencode-CLI Free Endpoints, Local Ollama Engines, and Cross-Tier Symbiosis

This document is the master operational blueprint for local and cloud AI inference across your Fedora Asahi ARM64 environment. It covers the **8 free models in `opencode-cli`**, the **6 active local Ollama models**, their mappings to your installed skill ecosystem in [`/home/daripper/.agents/skills`](file:///home/daripper/.agents/skills), and the **Hybrid Local-to-API Synergy Architecture**.

---

## ⚡ Hybrid Local-to-API Synergy Architecture

Rather than treating local models and cloud API endpoints as isolated silos, your environment operates as a **3-Tier Asymmetric Hybrid Network**. Local models handle low-latency intake, privacy redaction, and offline loops on Apple Silicon Unified Memory; remote cloud models provide brute-force reasoning, massive context ingestion, and complex system design.

```mermaid
flowchart TD
    subgraph Tier 1: Local Ingestion & Privacy Filter (Apple Silicon)
        INPUT["User Input / Phone Dictation / Garage Snap\n(Pixel 10 Pro via kdeconnect-cli)"] --> TIER1_ROUTER{"Input Classifier"}
        TIER1_ROUTER -->|Visual / Pinout / Schematic| MOON["moondream:latest\n(Fast 1.7GB VLM)"]
        TIER1_ROUTER -->|Messy Stream-of-Thought| SAM["samantha-mistral:latest\n(Conversational Intent Parser)"]
        TIER1_ROUTER -->|Symbolic Node / Quick Logic| PHI["phi3:mini\n(Lightweight Logic Engine)"]
    end

    subgraph Tier 2: Heavy Cloud Reasoning & Synthesis (Opencode-CLI Free APIs)
        MOON -->|Structured Vision Spec| CLOUD_ROUTER{"Task Dispatcher"}
        SAM -->|Clean PRD / Feature Spec| CLOUD_ROUTER
        PHI -->|Architectural Spike| CLOUD_ROUTER
        
        CLOUD_ROUTER -->|Heavy Architecture / Security| ULTRA["Nemotron 3 Ultra\n(System Design / ADR)"]
        CLOUD_ROUTER -->|Massive Monorepo Context| CAT["LongCat2.5 Preview\n(Multi-doc Synthesis)"]
        CLOUD_ROUTER -->|Quant / Compliance / VPAT| LING["Ling 3.0 Flash Fin\n(Regulatory / Financial)"]
        CLOUD_ROUTER -->|Lateral Ideation| BUNNY["Space Bunny\n(Creative Mechanics)"]
        CLOUD_ROUTER -->|Autonomous TDD Execution| PICKLE["Big Pickle\n(Aggressive Builder)"]
    end

    subgraph Tier 3: Local Deterministic Execution & Verification
        ULTRA -->|Targeted Phase Spec| LOCAL_EXEC{"Local Code Loop"}
        CAT -->|Digest Insights| LOCAL_EXEC
        PICKLE -->|Failing Test / Patch| LOCAL_EXEC
        
        LOCAL_EXEC -->|Fast Syntax / Unit Tests| QWEN["qwen2.5-coder:1.5b\n(Syntax Precision)"]
        LOCAL_EXEC -->|Compact Reasoning / AST| QWEN3["qwen3:4b\n(Multimodal & Code Logic)"]
        LOCAL_EXEC -->|Deep CoT Debugging / Fallback| DEEPSEEK["deepseek-r1:1.5b\n(Local Logic Verification)"]
        LOCAL_EXEC -->|Sub-second CI Micro-fixes| LIGHT["Nemotron 3.5 Lightning\n(Remote Fast Worker)"]
    end

    LOCAL_EXEC -->|Verification Status / Alerts| NOTIF["kdeconnect-cli Alert\n(Pixel 10 Pro)"]
```

### Key Principles of the Hybrid Symbiosis

1. **The "Greasy Hands" Garage Pipeline:**
   - **Intake:** You dictate messy instructions or snap photos of wiring/OBD-II hardware under a vehicle via your Pixel 10 Pro.
   - **Local Pre-Processing:** `samantha-mistral` parses conversational intent into structured tasks, while `moondream` extracts OCR labels and pinouts locally—preventing private camera data or incoherent audio transcripts from being shipped to cloud APIs.
   - **Cloud Escalation:** The distilled JSON/Markdown spec is pushed to `Big Pickle` or `Nemotron 3 Ultra` in `opencode-cli` for heavy codebase modification.
   - **Local Feedback:** Test results and build alerts are dispatched back to your phone via `kdeconnect-cli`.

2. **Cost, Privacy & Token Budgeting:**
   - Pre-filtering and summarizing large logs locally on Apple Silicon reduces cloud token overhead to zero while preventing sensitive environment variables (`.env`), SSH keys, or private diagnostics from leaving the machine.

3. **Offline Survivability & Air-Gapped Fallback:**
   - If internet access drops or remote API rate limits are hit, your system immediately degrades to pure local execution without workflow interruption:

| Cloud API Role (Opencode) | Primary Offline Fallback (Local Ollama) | Functional Delta / Trade-off |
| :--- | :--- | :--- |
| **Nemotron 3 Ultra** | `deepseek-r1:1.5b` + `qwen3:4b` | Slower CoT reasoning; smaller context window, but maintains high logical rigor. |
| **Big Pickle** | `qwen2.5-coder:1.5b` (with Ralph mode) | Requires smaller single-file atomic tasks rather than whole-repo generation. |
| **Nemotron 3.5 Lightning** | `qwen2.5-coder:1.5b` | Identical sub-second speed; runs locally on CPU/NPU unified memory. |
| **Space Bunny** | `samantha-mistral:latest` / `phi3:mini` | Less divergent coding slop; more structured philosophical brainstorming. |
| **LongCat2.5 Preview** | `repomix` + `qwen3:4b` chunked | Chunked multi-pass analysis rather than single-turn massive ingestion. |
| **Ling 3.0 Flash Fin** | `phi3:mini` + local Python/SQL scripts | Deterministic Python scripts take over arithmetic calculations. |

---

## 📊 Complete Model Roster & Comparison Matrix

| Model Identifier | Deployment Type | Footprint / Latency | Primary Operational Specialty | Top Target Installed Skills |
| :--- | :--- | :--- | :--- | :--- |
| **Ling 3.0 Flash Fin** | Cloud (Opencode Free) | Low Latency / Fast RPM | Quant, Financial Accounting, VPAT/Section 508 | `compliance-mapping`, `financial-report-search`, `quantitative-analysis` |
| **MiMo-V2.6-Flash** | Cloud (Opencode Free) | High Throughput / Vision-DOM | Frontend UI/UX, DOM parsing, DevTools loops | `frontend-design`, `chrome-devtools`, `screen-reader-lab`, `webapp-testing` |
| **Space Bunny** | Cloud (Opencode Free) | Balanced / High Divergence | Lateral Thinking, Game Mechanics, Creative Spikes | `brainstorming`, `feature-ideator`, `lateral-thinking`, `game-engine` |
| **LongCat2.5 Preview** | Cloud (Opencode Free) | Massive Context Window | Monorepo Ingestion, Cross-Doc Synthesis, Postmortems | `cross-document-analyzer`, `postmortem-aggregator`, `repomix-manager` |
| **Nemotron 3.5 Lightning**| Cloud (Opencode Free) | Sub-Second / Real-time | Atomic Unit Tests, Git Commits, Quick Fixes | `quick-fix`, `test-generation`, `pytest-coverage`, `git-commit` |
| **Nemotron 3 Ultra** | Cloud (Opencode Free) | Heavy CoT / Deep Reasoning | System Architecture, Security Audits, Concurrency | `plan-author`, `system-design`, `security`, `ruthless-refactorer` |
| **Big Pickle** | Cloud (Opencode Free) | Autonomous Iterative Loop | God-Mode Implementation, Relentless TDD, Refactoring | `code-implementer`, `load-pickle-persona`, `ralph-mode`, `rip-it-apart` |
| **Muse Spark 1.3** | Cloud (Opencode Free) | Precision Syntax / Structured | Agent Skills Authoring, Prompt Eng, Rule Generation | `skills-author`, `skill-creator`, `writing-rules`, `prompt_engineering` |
| **`qwen3:4b`** | Local (Ollama) | 2.5 GB / Fast Local | Compact Multimodal Reasoning, General Logic | `python-specialist`, `database-analyst`, `refactor` |
| **`phi3:mini`** | Local (Ollama) | 2.2 GB / Ultra-Fast | Lightweight Symbolic Logic, Aether Core Engine | `using-co-researcher`, `what-context-needed`, `eli5` |
| **`moondream:latest`** | Local (Ollama) | 1.7 GB / <400ms VLM | Fast Image-to-Text, Hardware OCR, Pinouts, UI Layouts | `media-accessibility`, `screen-reader-lab`, `penpot-uiux-design` |
| **`deepseek-r1:1.5b`** | Local (Ollama) | 1.1 GB / High-Rigor CoT | Local Chain-of-Thought Debugging, Logic Verification | `systematic-debugging`, `debug-error`, `verification-before-completion` |
| **`qwen2.5-coder:1.5b`** | Local (Ollama) | 986 MB / Instant Speed | Precision Syntax, Unit Tests, Terminal CLI Automation | `quick-fix`, `pytest-coverage`, `javascript-typescript-jest` |
| **`samantha-mistral`** | Local (Ollama) | 4.1 GB / Conversational | Voice Dictation Parsing, Dialectic Feedback, UX Review | `comment-code-generate-a-tutorial`, `eli5`, `presentation` |

---

## 🔬 In-Depth Model Breakdowns

### 🌐 Cloud Models (Opencode-CLI Free Endpoints)

#### 1. Ling 3.0 Flash Fin
* **Architecture & Focus:** Fine-tuned specifically for quantitative rigor, financial accounting, regulatory compliance, and structured tabular reasoning.
* **Best Usages:**
  - Auditing VPAT tables and mapping accessibility criteria against Section 508 / EN 301 549.
  - Analyzing financial earnings transcripts, SEC 10-K filings, and balance sheets.
  - Generating structured SQL aggregation queries, database normalization audits, and indexing performance models.
* **Recommended Skills:** [`compliance-mapping`](file:///home/daripper/.agents/skills/compliance-mapping/SKILL.md), [`legal-compliance-mapping`](file:///home/daripper/.agents/skills/legal-compliance-mapping/SKILL.md), [`financial-report-search`](file:///home/daripper/.agents/skills/financial-report-search/SKILL.md), [`quantitative-analysis`](file:///home/daripper/.agents/skills/quantitative-analysis/SKILL.md), [`database-analyst`](file:///home/daripper/.agents/skills/database-analyst/SKILL.md), [`sql-optimization`](file:///home/daripper/.agents/skills/sql-optimization/SKILL.md).
* **Operational Guidelines:** Enforce strict JSON or Markdown table schemas; never allow ungrounded open-ended arithmetic estimates.

#### 2. MiMo-V2.6-Flash
* **Architecture & Focus:** High-throughput multi-modal and DOM-native Flash model designed for rapid structural parsing, live DevTools event triage, and CSS layout reconciliation.
* **Best Usages:**
  - Rapid UI component prototyping and front-end auditing.
  - Ingesting raw Chrome DevTools performance traces, DOM node trees, and accessibility trees.
  - Driving fast browser automation scripts (Playwright) and step-by-step screen reader narration loops.
* **Recommended Skills:** [`frontend-design`](file:///home/daripper/.agents/skills/frontend-design/SKILL.md), [`chrome-devtools`](file:///home/daripper/.agents/skills/chrome-devtools/SKILL.md), [`screen-reader-lab`](file:///home/daripper/.agents/skills/screen-reader-lab/SKILL.md), [`webapp-testing`](file:///home/daripper/.agents/skills/webapp-testing/SKILL.md), [`playwright-explore-website`](file:///home/daripper/.agents/skills/playwright-explore-website/SKILL.md), [`web-component-specialist`](file:///home/daripper/.agents/skills/web-component-specialist/SKILL.md).
* **Operational Guidelines:** Keep conversational turns short and focused on atomic DOM or UI components; pipe raw DevTools selector dumps directly into context.

#### 3. Space Bunny
* **Architecture & Focus:** High-entropy, lateral-thinking creative engine. Optimized for unblocking technical deadlocks, divergent feature ideation, and gamified mechanics.
* **Best Usages:**
  - Brainstorming novel features, mechanics, and game engine rendering architectures.
  - Breaking through architectural roadblocks via cross-domain analogies and lateral thinking.
  - Generating engaging technical tutorials, narrative repository commit stories, and presentation slide decks.
* **Recommended Skills:** [`brainstorming`](file:///home/daripper/.agents/skills/brainstorming/SKILL.md), [`feature-ideator`](file:///home/daripper/.agents/skills/feature-ideator/SKILL.md), [`lateral-thinking`](file:///home/daripper/.agents/skills/lateral-thinking/SKILL.md), [`game-engine`](file:///home/daripper/.agents/skills/game-engine/SKILL.md), [`repo-story-time`](file:///home/daripper/.agents/skills/repo-story-time/SKILL.md), [`comment-code-generate-a-tutorial`](file:///home/daripper/.agents/skills/comment-code-generate-a-tutorial/SKILL.md).
* **Operational Guidelines:** Use high temperature settings when unblocking creative deadlocks; mandate first-principles constraints to keep ideas physically implementable.

#### 4. LongCat2.5 Preview
* **Architecture & Focus:** Ultra-large context window engine. Built to ingest and reason over massive single-pass payloads—entire monorepos, multi-year postmortem folders, and comprehensive dependency graphs.
* **Best Usages:**
  - Analyzing entire Repomix / aggregated codebase bundles in one context.
  - Postmortem aggregation across multiple historical incident files (`POMO_AGGREGATED.md`).
  - Cross-referencing disparate documentation, academic literature, and multi-file dependency trees.
* **Recommended Skills:** [`cross-document-analyzer`](file:///home/daripper/.agents/skills/cross-document-analyzer/SKILL.md), [`cross-page-analyzer`](file:///home/daripper/.agents/skills/cross-page-analyzer/SKILL.md), [`postmortem-aggregator`](file:///home/daripper/.agents/skills/postmortem-aggregator/SKILL.md), [`repomix-manager`](file:///home/daripper/.agents/skills/repomix-manager/SKILL.md), [`literature-review`](file:///home/daripper/.agents/skills/literature-review/SKILL.md), [`research-synthesis`](file:///home/daripper/.agents/skills/research-synthesis/SKILL.md).
* **Operational Guidelines:** Combine multiple files into single structured blocks with explicit headers; require line-by-line citations (`file:///path#Lxx-Lyy`) for every synthesized finding.

#### 5. Nemotron 3.5 Lightning
* **Architecture & Focus:** NVIDIA-optimized hyper-speed execution model. Sub-second latency with sharp adherence to single-turn instructions.
* **Best Usages:**
  - Rapidly generating pytest, Jest, and unittest suites for newly implemented modules.
  - Automated formatting, lint rule remediation, and micro-complexity reduction.
  - Generating Conventional Git commit messages and handling GitHub CLI triage (`gh-cli`, `actions-manager`).
* **Recommended Skills:** [`quick-fix`](file:///home/daripper/.agents/skills/quick-fix/SKILL.md), [`test-generation`](file:///home/daripper/.agents/skills/test-generation/SKILL.md), [`pytest-coverage`](file:///home/daripper/.agents/skills/pytest-coverage/SKILL.md), [`javascript-typescript-jest`](file:///home/daripper/.agents/skills/javascript-typescript-jest/SKILL.md), [`git-commit`](file:///home/daripper/.agents/skills/git-commit/SKILL.md), [`fedora-linux-triage`](file:///home/daripper/.agents/skills/fedora-linux-triage/SKILL.md).
* **Operational Guidelines:** Keep prompts atomic (one function or one failing test at a time); chain immediately into test runner commands for instant validation.

#### 6. Nemotron 3 Ultra
* **Architecture & Focus:** Heavyweight reasoning and enterprise systems architecture engine. Excels at deep algorithmic complexity, security threat modeling, database locking/concurrency strategies, and high-stakes code audits.
* **Best Usages:**
  - Formulating multi-phase architectural blueprints and formal ADRs (Architectural Decision Records).
  - Deep security vulnerability scanning (AST injection, auth bypass, secret leakage).
  - High-performance concurrency tuning (Rust async runtimes, Python asyncio/multiprocessing, ARM64 memory models).
  - Ruthless code reviews and dismantling architectural anti-patterns.
* **Recommended Skills:** [`plan-author`](file:///home/daripper/.agents/skills/plan-author/SKILL.md), [`plan-reviewer`](file:///home/daripper/.agents/skills/plan-reviewer/SKILL.md), [`technical-planning`](file:///home/daripper/.agents/skills/technical-planning/SKILL.md), [`system-design`](file:///home/daripper/.agents/skills/system-design/SKILL.md), [`create-architectural-decision-record`](file:///home/daripper/.agents/skills/create-architectural-decision-record/SKILL.md), [`ruthless-refactorer`](file:///home/daripper/.agents/skills/ruthless-refactorer/SKILL.md), [`security`](file:///home/daripper/.agents/skills/security/SKILL.md).
* **Operational Guidelines:** Force chain-of-thought analysis on edge cases and failure modes before generating implementation code; require explicit algorithmic bounds ($O(n)$).

#### 7. Big Pickle
* **Architecture & Focus:** Unrelenting, zero-fluff autonomous implementation engine. Embodying the "Pickle Rick" / "Ralph Mode" philosophy, it operates without conversational hesitation, driving full-stack features from PRD to passing test suite.
* **Best Usages:**
  - Full-throttle feature implementation following a validated technical plan.
  - Relentless bug hunting and regression fixing where other models stall ("Ralph mode").
  - Test-Driven Development (TDD) cycles: writing failing tests, writing code, verifying green tests.
  - Tearing down and replacing legacy codebases (`rip-it-apart`).
* **Recommended Skills:** [`code-implementer`](file:///home/daripper/.agents/skills/code-implementer/SKILL.md), [`load-pickle-persona`](file:///home/daripper/.agents/skills/load-pickle-persona/SKILL.md), [`ralph-mode`](file:///home/daripper/.agents/skills/ralph-mode/SKILL.md), [`persistence`](file:///home/daripper/.agents/skills/persistence/SKILL.md), [`test-driven-development`](file:///home/daripper/.agents/skills/test-driven-development/SKILL.md), [`rip-it-apart`](file:///home/daripper/.agents/skills/rip-it-apart/SKILL.md), [`verification-before-completion`](file:///home/daripper/.agents/skills/verification-before-completion/SKILL.md).
* **Operational Guidelines:** Provide concrete pass/fail verification commands; never mark tasks done until execution confirms clean test runs.

#### 8. Muse Spark 1.3
* **Architecture & Focus:** Meta-programming and prompt engineering specialist. Built specifically to understand agent system prompts, tool schemas, MCP configurations, and Agent Skill specifications (`SKILL.md`, `RULE.md`, `AGENTS.md`).
* **Best Usages:**
  - Authoring and maintaining custom Agent Skills conforming to the open standard.
  - Designing and refining system instructions, hookify rules, and Cursor/Gemini rule sets.
  - Converting skills between platforms (Codex to Gemini CLI / opencode-cli extensions).
* **Recommended Skills:** [`skills-author`](file:///home/daripper/.agents/skills/skills-author/SKILL.md), [`skill-creator`](file:///home/daripper/.agents/skills/skill-creator/SKILL.md), [`writing-skills`](file:///home/daripper/.agents/skills/writing-skills/SKILL.md), [`writing-rules`](file:///home/daripper/.agents/skills/writing-rules/SKILL.md), [`prompt_engineering`](file:///home/daripper/.agents/skills/prompt_engineering/SKILL.md), [`prompt-builder`](file:///home/daripper/.agents/skills/prompt-builder/SKILL.md).
* **Operational Guidelines:** Require strict adherence to YAML frontmatter and standard skill directory structures; benchmark prompt refinements against concrete evaluation suites.

---

### 💻 Local Ollama Engines (Fedora Asahi ARM64)

#### 9. `qwen3:4b` (2.5 GB)
* **Architecture & Focus:** Next-generation 4B parameter compact multimodal and reasoning powerhouse. Punches far above its weight class in AST analysis, Python/Rust syntax, and multi-step logic.
* **Best Usages:**
  - Primary offline generalist and logic engine when disconnected from cloud endpoints.
  - Local multi-turn code refactoring and dependency graph analysis.
  - Intermediate synthesis step between raw local data and high-level architectural plans.
* **Recommended Skills:** [`python-specialist`](file:///home/daripper/.agents/skills/python-specialist/SKILL.md), [`database-analyst`](file:///home/daripper/.agents/skills/database-analyst/SKILL.md), [`refactor`](file:///home/daripper/.agents/skills/refactor/SKILL.md), [`code-simplifier`](file:///home/daripper/.agents/skills/code-simplifier/SKILL.md).

#### 10. `phi3:mini` (2.2 GB)
* **Architecture & Focus:** Microsoft's 3.8B parameter heavily-curated synthetic reasoning engine. Optimized for fast logic, symbolic representation, and compact reasoning steps.
* **Best Usages:**
  - Default reasoning backbone for **Aether** symbolic AI node graphs.
  - Fast context interrogation and decision trees without overhead.
  - Lightweight logic sanity checks before launching heavy background tasks.
* **Recommended Skills:** [`using-co-researcher`](file:///home/daripper/.agents/skills/using-co-researcher/SKILL.md), [`what-context-needed`](file:///home/daripper/.agents/skills/what-context-needed/SKILL.md), [`explain-concept`](file:///home/daripper/.agents/skills/explain-concept/SKILL.md).

#### 11. `moondream:latest` (1.7 GB)
* **Architecture & Focus:** Ultra-compact 1.86B parameter Vision-Language Model with sub-400ms inference on Apple Silicon Unified Memory.
* **Best Usages:**
  - **Garage / Vehicle Diagnostics:** Snapping photos of fuse box diagrams, wire harnesses, connector pinouts, and multimeter/OBD readouts via Pixel 10 Pro $\rightarrow$ `kdeconnect-cli`.
  - **Visual-to-UI Ingestion:** Parsing Penpot wireframes and terminal screenshot mockups into structural component hierarchies.
  - **A11y Alt-Text:** Generating automated visual descriptions for charts and non-semantic SVGs.
* **Recommended Skills:** [`media-accessibility`](file:///home/daripper/.agents/skills/media-accessibility/SKILL.md), [`screen-reader-lab`](file:///home/daripper/.agents/skills/screen-reader-lab/SKILL.md), [`penpot-uiux-design`](file:///home/daripper/.agents/skills/penpot-uiux-design/SKILL.md).

#### 12. `deepseek-r1:1.5b` (1.1 GB)
* **Architecture & Focus:** Distilled 1.5B reasoning model exhibiting raw chain-of-thought `<think>` logic traces.
* **Best Usages:**
  - Deep local debugging of tricky runtime exceptions, race conditions, and off-by-one errors.
  - Verifying edge cases and mathematical logic locally without cloud round-trips.
  - Offline fallback for `Nemotron 3 Ultra` planning and review loops.
* **Recommended Skills:** [`systematic-debugging`](file:///home/daripper/.agents/skills/systematic-debugging/SKILL.md), [`debug-error`](file:///home/daripper/.agents/skills/debug-error/SKILL.md), [`edge-cases`](file:///home/daripper/.agents/skills/edge-cases/SKILL.md), [`verification-before-completion`](file:///home/daripper/.agents/skills/verification-before-completion/SKILL.md).

#### 13. `qwen2.5-coder:1.5b` (986 MB)
* **Architecture & Focus:** Hyper-specialized code syntax model. Blazing fast token generation optimized for precision code completion and lint fixing.
* **Best Usages:**
  - Local test generation (`pytest`, `jest`) and automated test runner remediation.
  - Generating Conventional Commit messages and fast bash/fish automation scripts.
  - Offline fallback for `Nemotron 3.5 Lightning`.
* **Recommended Skills:** [`quick-fix`](file:///home/daripper/.agents/skills/quick-fix/SKILL.md), [`test-generation`](file:///home/daripper/.agents/skills/test-generation/SKILL.md), [`pytest-coverage`](file:///home/daripper/.agents/skills/pytest-coverage/SKILL.md), [`git-commit`](file:///home/daripper/.agents/skills/git-commit/SKILL.md).

#### 14. `samantha-mistral:latest` (4.1 GB)
* **Architecture & Focus:** 7B Mistral fine-tune engineered for empathic dialogue, conversational pacing, and psychological reflection.
* **Best Usages:**
  - **Voice/Dictation Triage Proxy:** Ingesting messy voice dictations from the garage via KDE Connect, stripping verbal fluff, and structuring thoughts into technical requirements.
  - **Aether Dialectic Mirror:** Challenging architectural assumptions, evaluating cognitive load, and preventing over-engineering in Seer/Aether scripts.
  - **Developer UX & Tutorial Evaluation:** Reviewing technical guides and CLI interactions for human clarity and ergonomics.
* **Recommended Skills:** [`comment-code-generate-a-tutorial`](file:///home/daripper/.agents/skills/comment-code-generate-a-tutorial/SKILL.md), [`eli5`](file:///home/daripper/.agents/skills/eli5/SKILL.md), [`presentation`](file:///home/daripper/.agents/skills/presentation/SKILL.md).

---

## 🛠️ Integrated End-to-End Hybrid Recipes

### Recipe 1: The "Greasy Hands" Garage Hardware Handoff
1. **Intake (Pixel 10 Pro):** Snap a wiring photo and dictate a quick note: *"Pin 4 is grounded, need a Python CAN bus listener script."*
2. **Local Pre-Processing (Asahi Box):**
   - `kdeconnect-cli` drops the image and audio transcript into `~/Inbox`.
   - `moondream` reads the connector pin numbers and wire color codes.
   - `samantha-mistral` parses the dictation into a clean feature specification.
3. **Cloud Heavy Lifting (`opencode-cli`):**
   - `Big Pickle` (`opencode/big-pickle`) implements the CAN-bus socket listener with robust error handling and writes the unit tests.
4. **Local Verification & Alert:**
   - `qwen2.5-coder` runs `pytest` locally.
   - `kdeconnect-cli --ping-msg "CAN listener built & tests passing"` sends the notification back to the Pixel 10 Pro.

### Recipe 2: Full-Scale Monorepo Refactor & Security Audit
1. **Ingestion:** `LongCat2.5 Preview` ingests the complete Repomix digest of the target project.
2. **Audit & Threat Model:** `Nemotron 3 Ultra` reviews the architecture for concurrency bottlenecks and security vulnerabilities.
3. **Execution:** `Big Pickle` refactors the codebase following the audit recommendations using strict TDD.
4. **Micro-Triage:** `Nemotron 3.5 Lightning` or local `qwen2.5-coder` cleans up linting, generates git commit diffs, and updates [`AGENTS.md`](file:///home/daripper/AGENTS.md).

---
---

# PART II — HEXMIND CODE REVIEW

> Everything above this line is the original report, unmodified.
> Everything below is a code review of the report against the Hexmind source tree and the
> actual local machine, added 2026-09-27 after commit `0897b1c`.
>
> **Baseline at time of review:** `107 passed, 1 skipped` (Python 3.14.7, textual 8.2.7).
> **Reviewed tree:** `hexmind/{core,backends,tui,relay,auditor,server,jules,notify,config}.py`

## 1. Verification Method

Every claim below was checked against the source tree or a live query, not inferred:

| Check | Method |
| :--- | :--- |
| Ollama inventory | `GET http://127.0.0.1:11434/api/tags` |
| Roster / routing text | `hexmind/core.py` (`ROSTER`, `TEXT_ONLY`, `OPT_IN`, `QUOTA_RE`) |
| Model IDs actually invoked | `hexmind/backends.py` (`DIRECT_CMDS`, `LOCAL_MODELS`) |
| Fallback behaviour | `hexmind/core.py` (`Orchestrator.fallback`) |
| Skill paths | `ls -d /home/daripper/.agents/skills` |

## 2. The Local Model Inventory Is Not Real

The report describes 6 local Ollama engines. **4 are not installed, and 2 are installed under
names Ollama does not report.**

| Report claims | Present on this machine | Status |
| :--- | :--- | :--- |
| `qwen3:4b` (2.5 GB) | — | ❌ not installed |
| `phi3:mini` (2.2 GB) | `phi3-mini:latest` | ⚠️ name mismatch (`.` vs `-`) |
| `moondream:latest` (1.7 GB) | — | ❌ not installed |
| `deepseek-r1:1.5b` (1.1 GB) | `deepseek-r1-1.5b:latest` | ⚠️ name mismatch (`.` vs `-`) |
| `qwen2.5-coder:1.5b` (986 MB) | — | ❌ not installed |
| `samantha-mistral:latest` (4.1 GB) | — | ❌ not installed |

**9 installed models appear nowhere in the report at all:**

`continuum-architect:latest` · `deepseek-coder-v2:16b` · `deepseek-coder:6.7b` · `hermes3:8b` ·
`llama3.2-3b:latest` · `marco-o1:7b` · `nomic-embed-text:latest` · `omnimap-architect:latest` ·
`orca-mini:latest`

Two of these matter more than the report's own picks:

- **`deepseek-coder-v2:16b` and `deepseek-coder:6.7b`** are far stronger code models than the
  `qwen2.5-coder:1.5b` (986 MB) the report nominates for "Precision Syntax, Unit Tests". The
  report recommends a 1.5B model for a job a 16B model is already installed to do.
- **`nomic-embed-text:latest`** is an embedding model. Hexmind's conversation history is a flat
  list of the last 3 exchanges (`core.py:230`); an embedding model is the natural fix for
  semantic recall, and it is sitting unused.

`continuum-architect` and `omnimap-architect` appear to be Aether-related (the report scopes
`phi3:mini` to "Aether Core Engine") but are undocumented.

### 2.1 The name mismatch is a live bug, not a typo

`backends.py:104` gates membership on an exact string-set lookup:

```python
return [m for m in members if (m in DIRECT_CMDS and shutil.which(DIRECT_CMDS[m][0]))
        or LOCAL_MODELS.get(m) in pulled
        or (m == "jules" and bool(os.environ.get("JULES_API_KEY")))]
```

`pulled` is the verbatim name set from `/api/tags`. Add a member using the report's spelling
(`"deepseek": "deepseek-r1:1.5b"`) and **`available()` returns `False` with no error** — the
member silently never joins the room, and the roster looks merely quiet rather than broken.
Ollama normalises `deepseek-r1:1.5b` to `deepseek-r1-1.5b:latest`, so the report's spelling can
never match.

**Fix:** normalise before comparing, and warn loudly on a near-miss instead of dropping silently.

## 3. Roster Descriptions Have Drifted From Real Model Strengths

`_roster()` (`core.py:221`) is interpolated straight into `LEAD_PROMPT`, so these strings *are*
the routing logic — the lead assigns work by reading them. Three are wrong or undersold:

| Member | Report says it is for | `core.py` ROSTER says | Effect |
| :--- | :--- | :--- | :--- |
| `opencode-muse` | Meta-prompting, **skill authoring**, agent schemas, rule generation | "massive 1M context repo scanning and cross-file documentation analysis" | ❌ **Wrong.** That description belongs to LongCat2.5. Repo-scan work routes to the one model the report says is bad at it. |
| `opencode-mimo` | **Frontend UI/UX, DOM parsing, DevTools, vision** | "low-latency small tasks — quick edits, short scripts" | ⚠️ Undersold. It is the only UI specialist in the report. |
| `opencode-pickle` | **Relentless autonomous TDD, Ralph mode**, won't abandon a failing test | "deliberate reasoning model for multi-step problem solving" | ⚠️ Undersold. Reads as a generic reasoner rather than the aggressive builder. |

**Consequence for the `ui` domain:** `auditor.DOMAINS` includes `ui`, and `Stats` scores per
domain — but nothing in the roster advertises UI strength except `agy`. So every `ui`-domain
task routes to `agy` by default while the model's actual UI specialist sits idle.

**Root cause:** the roster is hand-maintained free text that has drifted from the report.
Fixing the three strings treats the symptom; see §7 for the structural fix.

## 4. Architecture Mismatches Between the Report and the Code

### 4.1 Vision / multimodal intake is unsupported end to end

The report makes visual intake the **entry point of the whole pipeline** (snap a wiring photo →
`moondream` reads the pinouts → structured spec → cloud escalation).

Hexmind cannot express this. `_ollama_generate` (`backends.py:108`) posts text-only:

```python
body = {"model": model, "prompt": prompt, "stream": False, "think": False}
```

Moondream requires an `images: [base64]` field. Supporting it means changing the contract that
runs through every layer — `backend.run(agent, prompt, cwd) -> str`, the `Task` dataclass, the
prompt templates, and the TUI (which has no way to attach an image). This is a real feature,
not a config change.

### 4.2 `"think": False` is hardcoded, defeating `deepseek-r1`

`backends.py:109` hardcodes `think: False`. `deepseek-r1-1.5b` **is installed**, and the report
sells it on exactly one thing: "raw chain-of-thought `<think>` logic traces" and "Deep CoT
Debugging, Logic Verification."

Hexmind would suppress the single capability that justifies the model. The flag needs to be
per-agent (derived from the registry in §7), not a global constant.

### 4.3 The offline-fallback table has no implementation

The report's central thesis is graceful degradation: when the network drops or rate limits hit,
fall through to local engines. Hexmind already owns the scaffolding — `QUOTA_RE` (`core.py:51`)
detects quota/rate-limit failures and `Orchestrator.fallback()` (`core.py:348`) reassigns the
task. But `fallback()` filters only on membership:

```python
spares = [m for m in self.members if m not in tried and m not in TEXT_ONLY]
return self.stats.ranked(spares, t.domain)[0] if self.stats else spares[0]
```

There is **no notion of cloud vs. local tier.** If the entire cloud tier is down, tasks are
reshuffled among equally-dead cloud models by Laplace score. The report's fallback table is a
ready-made priority order that the code never consults.

### 4.4 `notify.py` is implemented, tested, and called by nothing

The report terminates *every* workflow at `kdeconnect-cli` → phone: Tier 3 output, the garage
recipe, and Recipe 2's verification step all end in a ping.

`hexmind/notify.py` implements exactly that and is fully covered by `tests/test_notify.py` —
but **no module imports it.** Verified: the only references outside the file itself are the
tests. The report makes it load-bearing; the code leaves it orphaned.

### 4.5 Two of the eight cloud models are still not team members

`backends.py:28-33` wires six: `opencode`, `-ultra`, `-muse`, `-mimo`, `-pickle`, `-ling`.
**Missing: Space Bunny** (Tier 2's lateral-ideation node) and **LongCat2.5 Preview** (monorepo
ingestion, and the model whose specialty `opencode-muse` is currently mislabelled as).

## 5. Documentation Defects

- **All ~50 skill links are dead.** Every one resolves to
  `file:///home/daripper/.agents/skills/<name>/SKILL.md`; that directory **does not exist**.
  Skills actually live under `/home/daripper/.claude/skills/synced/<uuid>/<name>/SKILL.md`.
- **README contradicts the code on `qwen`.** `README.md:68` documents `qwen` as `qwen3:4b`;
  `backends.py:44` and `core.py:32` both say `qwen2.5-coder:7b`. Only the latter is installed,
  so **the README is stale, not the code** — and `qwen3:4b` was evidently never pulled.
- **The old report's 3 pipeline recipes were deleted** in `0897b1c` and replaced by 2 hybrid
  recipes. The 4-step autonomous pipeline (Ideate → Architect → Implement → Micro-fix) that
  matched Hexmind's own architecture is gone. Worth restoring as a Hexmind-shaped recipe.

## 6. Adjacent Code Findings (unrelated to models, found during review)

Not model-related, but surfaced by the same review and worth tracking:

| # | Finding | Location |
| :--- | :--- | :--- |
| 1 | `fastapi`, `pydantic`, `uvicorn` imported but **not declared** in `pyproject.toml` — `--serve` fails on a clean install | `pyproject.toml:6`, `server.py:14` |
| 2 | Server binds `0.0.0.0` with `allow_origins=["*"]` **and** `allow_credentials=True`, no auth — anyone on the LAN can drive agents running with auto-accepted edits | `server.py:28`, `server.py:250` |
| 3 | Server **404s every slash command** — `Orchestrator.handle()` returns immediately for `/`-prefixed input | `core.py:238`, `server.py:267` |
| 4 | `Task.status` declared without `auditing`/`revising`; `AGENT_COLOR` hardcodes 13 names — a new ROSTER member silently gets no colour | `core.py:84`, `tui.py:22` |
| 5 | No streaming: `backend.run` returns one string after up to 30 min of silence, though `agy`/`kimi` already parse stream-json and discard it | `backends.py:186` |
| 6 | `Stats._save()` rewrites the whole JSON per audit, no locking | `auditor.py:83` |
| 7 | No lint config committed (`.ruff_cache` exists, no `ruff.toml`); no `AGENT_REPORT.md` — both required by `AGENTS.md` | repo root |
| 8 | Server has no request queue (409s); the TUI queues via `asyncio.Lock`. README's "it queues" is only half true | `server.py:269`, `tui.py:161` |

## 7. Recommended Structural Fix

Every drift in §3 and §4 traces back to one root cause: **`ROSTER` is hand-maintained free text
with no schema.** The report is a rich structured matrix that the code cannot read.

A single declarative registry would fix the naming bug, make routing deterministic, and give the
hybrid architecture an actual implementation surface:

```toml
# ~/.config/hexmind/models.toml  (user-overridable, like chains/)
[models.deepseek]
ollama   = "deepseek-r1-1.5b"   # exact name from /api/tags
tier     = "local"              # local | cloud
domains  = ["debugging", "review"]
think    = true                 # per-agent, replaces the hardcoded False
fallback_for = ["opencode-ultra"]   # implements the report's fallback table
```

Benefits, mapped to the findings above:

| Registry field | Fixes |
| :--- | :--- |
| `ollama` + name normalisation | §2.1 silent-drop bug |
| `tier` | §4.3 tier-aware fallback |
| `domains` | §3 roster drift; makes `ui` routing deterministic |
| `think` | §4.2 hardcoded `False` |
| `fallback_for` | §4.3 offline degradation, straight from the report's table |

Then generate `ROSTER` prose from `domains` so the lead's prompt can never drift again, and add
a `/models` command that prints the live team against this report's matrix.

### Suggested order of work

1. **Registry + name normalisation** — fixes a real silent bug, unblocks everything else.
2. **Correct the three ROSTER strings** (`-muse`, `-mimo`, `-pickle`) — one-line each, immediate
   routing win.
3. **Wire `notify.py` into escalation + run-finished** — already written and tested.
4. **Add Space Bunny and LongCat2.5 as members** — completes the report's cloud tier.
5. **Per-agent `think` flag** — one-line change, unlocks `deepseek-r1`.
6. **Fix the README `qwen` row and the dead skill paths.**
7. **Then** the larger items: tier-aware `fallback()`, streaming output, multimodal intake.

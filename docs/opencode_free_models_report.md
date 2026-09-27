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

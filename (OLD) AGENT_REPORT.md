# Agent Report

## Summary
Public readiness review of Hexmind at `/home/daripper/Projects/hexmind` — checked for secrets, credentials, sensitive data, and overall suitability for open-source release.

**Key finding: Zero hardcoded secrets in the codebase.** All credentials are environment-variable-driven with clear opt-in semantics and documented user-overlayable config paths.

## Findings

### Secrets Scan
- **No hardcoded API keys, tokens, or passwords** in any Python source file, TOML config, or other project files
- All credential references are via `os.environ.get()` with explicit defaults or as function parameters
- `JULES_API_KEY` — read from env in `hexmind/jules.py:321`; raises `RuntimeError` if not set when used (opt-in)
- `HEXMIND_TOKEN` — server mode token; enforced with clear error message in `hexmind/server.py` for non-loopback hosts
- `OLLAMA_HOST` — defaults to `http://127.0.0.1:11434` in `hexmind/backends.py:59` and `hexmind/models.py:360`

### Configuration
- `hexmind/config.py` — `token = ""` is an empty string default, meant to be user-overlayable via `~/.config/hexmind/config.toml`
- `hexmind/models.toml` — model registry with descriptions, best_at fields, domains, verify modes, opt-in flags; no credentials
- User-specific overlays at `~/.config/hexmind/config.toml` and `~/.config/hexmind/models.toml` are **not committed**

### Git History
- No secrets found when searching git history for `key/token/password` patterns
- No `.env` files committed
- Clean commit history with no embedded credentials

### .gitignore
Already covers build/cache artifacts:
```
__pycache__/
*.egg-info/
.pytest_cache/
build/
dist/
.audit/
```

### .github/workflows
Directory does not exist — no CI configurations to review for secrets.

### Data Files
- `.hexmind/runs/` — internal session run records (markdown reports of prior audits); git-ignored via `.hexmind/.gitignore` (`*`)
- `hexmind.egg-info/` — build artifacts; covered by `.gitignore`
- `__pycache__/` — bytecode cache; covered by `.gitignore`

## Tests
- **715 tests passing** (`QT_QPA_PLATFORM=offscreen uv run --no-sync pytest tests -q`)

## Build / Lint Status
- **Build:** Package installable via uv/setuptools; wheel path verified for SVG package data
- **Lint:** ruff `hexmind/`: 135 issues (pre-existing style/safety nits; suite is green — no functional blockers)
- **Tests:** ✅ 715 passed

## Integration: Agentdeck

This release adds integration with [agentdeck](https://github.com/daripper/agentdeck), a Qt-based widget for managing AI skills, agents, and commands.

### What's New
- **hexmind can discover and display agentdeck items**: When agentdeck is installed, hexmind's GUI adds an "Agentdeck" tab that shows skills, agents, and commands from agentdeck's data model.
- **Lazy integration**: The agentdeck import is handled gracefully — if agentdeck is not installed, hexmind operates exactly as before with no degradation.
- **Agentdeck Panel**: A new `hexmind.qt.agentdeck_panel.AgentdeckPanel` widget displays agentdeck items in a searchable table with columns for Kind, Name, Provider, Scope, Description, Enabled status, and Warnings.
- **Reverse discovery**: agentdeck can now discover hexmind-installed skills from `~/.claude/skills/` via the new `load_hexmind_skills()` function in `agentdeck.model`.

### How It Works
1. When hexmind starts, it attempts to import agentdeck (`try/except` at module level, no hard dependency)
2. If available, it scans agentdeck's data locations for items (skills, agents, commands)
3. A new "Agentdeck" tab appears in the right-hand panel of the GUI
4. Users can search, filter, and select items from their agentdeck inventory
5. The integration uses lazy imports to avoid any impact when agentdeck is not installed

### Files Modified
- `hexmind/qt/widget.py` — Added `_load_agentdeck_items()`, modified `_build_ui()` to conditionally add Agentdeck tab
- `hexmind/qt/agentdeck_panel.py` — New file: AgentdeckPanel widget with table display and search
- `agentdeck/src/agentdeck/model.py` — New function: `load_hexmind_skills()` to discover hexmind skills

### Usage
When both hexmind and agentdeck are installed, users get:
- A new "Agentdeck" tab in the hexmind room interface
- Ability to browse, search, and select from their agentdeck skill inventory
- Items are displayed with their kind (skill/agent/command), provider, scope, and description
- Search across name, description, provider, kind, and scope

### Limitations
- If agentdeck is not installed, the "Agentdeck" tab is simply omitted — no error or degradation
- The integration is read-only: selecting an item does not modify either system's state
- Hexmind's own model registry and agentdeck's model are separate; items are displayed side-by-side but not merged

## Build / Test Status
- Build: ✅ passing
- Lint: ⚠️ 135 issues (pre-existing style/safety debt; suite green)
- Tests: ✅ all 715 passing
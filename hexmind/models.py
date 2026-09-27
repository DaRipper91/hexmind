"""The model registry: one structured source of truth for the team roster.

`ROSTER` used to be a hand-maintained dict of prose that the lead reads to assign work. That is
how `opencode-muse` ended up described with another model's specialty, and nothing caught it. The
prose is now *generated* from the fields in `models.toml`, so the room and `/models` cannot
disagree about what a model is for.

Load order mirrors the chain files: bundled `hexmind/models.toml` first, then
`~/.config/hexmind/models.toml`, so a user override wins per table.
"""
from __future__ import annotations

import json
import os
import shutil
import tomllib
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

BUNDLED = Path(__file__).parent / "models.toml"
USER = Path.home() / ".config/hexmind/models.toml"
TIERS = ("cloud", "local")
VERIFIERS = ("path", "ollama", "env")


@dataclass(frozen=True)
class Model:
    """One team member. `description()` is what the lead actually reads."""

    name: str
    label: str
    best_at: str
    cli: str
    verify: str
    tier: str
    domains: tuple[str, ...] = ()
    model: str = ""
    avoid_for: str = ""
    think: bool = False
    variant: str = ""
    opt_in: bool = False
    text_only: bool = False
    weight: int = 50
    color: str = "white"
    footprint: str = ""
    env: str = ""
    fallback_for: tuple[str, ...] = field(default_factory=tuple)

    @property
    def is_local(self) -> bool:
        return self.tier == "local"

    def description(self) -> str:
        """The roster line for this model. Generated, so it cannot drift from best_at/avoid_for."""
        text = f"{self.label}: {self.best_at}"
        return f"{text}. Not for {self.avoid_for}." if self.avoid_for else text

    def card(self) -> str:
        """Full reference card — the `/model <name>` surface."""
        lines = [f"**{self.label}** (`{self.name}`)", ""]
        if self.footprint:
            lines.append(f"- **Deployment:** {self.footprint}")
        lines.append(f"- **Best at:** {self.best_at}")
        if self.avoid_for:
            lines.append(f"- **Not for:** {self.avoid_for}")
        if self.domains:
            lines.append(f"- **Domains:** {', '.join(self.domains)}")
        if self.model:
            lines.append(f"- **Model id:** `{self.model}`")
        if self.think:
            lines.append("- **Reasoning:** emits thinking traces (`think = true`)")
        if self.variant:
            lines.append(f"- **Variant:** `{self.variant}`")
        lines.append(f"- **Weight:** {self.weight}"
                     + ("  · text-only: never leads, never audits" if self.text_only else ""))
        if self.fallback_for:
            lines.append(f"- **Offline fallback for:** {', '.join(self.fallback_for)}")
        return "\n".join(lines)


class Registry:
    def __init__(self, models: dict[str, Model], sources: tuple[Path, ...] = ()):
        self.models = models
        self.sources = sources

    # ---------- loading ----------
    @classmethod
    def load(cls, paths: list[Path] | None = None) -> "Registry":
        """The first path is the base registry and must exist; later paths are optional overlays.

        Bundled first, then the user's overrides, so a user table wins per model. A missing *base*
        file is a hard error: it would leave the app with no roster at all and fail silently as an
        empty team — the exact bug class this registry exists to remove. Overlays are optional
        because `~/.config/hexmind/models.toml` is not expected to exist.
        """
        chain = list(paths) if paths is not None else [BUNDLED, USER]
        if not chain:
            raise ValueError("no model registry paths given")
        if not chain[0].is_file():
            raise FileNotFoundError(f"model registry not found: {chain[0]}")
        merged: dict[str, dict] = {}
        sources = []
        for path in chain:
            if not path.is_file():
                continue
            data = tomllib.loads(path.read_text())
            sources.append(path)
            for name, spec in data.get("models", {}).items():
                merged[name] = {**merged.get(name, {}), **spec} if name in merged else spec
        models = {}
        for name, spec in merged.items():
            if spec.get("tier") not in TIERS:
                raise ValueError(f"model '{name}': tier must be one of {TIERS}")
            if spec.get("verify") not in VERIFIERS:
                raise ValueError(f"model '{name}': verify must be one of {VERIFIERS}")
            for key in ("domains", "fallback_for"):
                spec[key] = tuple(spec.get(key, ()))
            models[name] = Model(name=name, **spec)
        return cls(models, tuple(sources))

    # ---------- lookup ----------
    def get(self, name: str) -> Model:
        try:
            return self.models[name]
        except KeyError:
            raise KeyError(f"unknown model '{name}'. Known: {', '.join(sorted(self.models))}") from None

    def __contains__(self, name: str) -> bool:
        return name in self.models

    def names(self) -> list[str]:
        return list(self.models)

    def members(self, include_opt_in: bool = False) -> list[str]:
        return [n for n, m in self.models.items() if include_opt_in or not m.opt_in]

    def text_only(self) -> set[str]:
        return {n for n, m in self.models.items() if m.text_only}

    def opt_in(self) -> set[str]:
        return {n for n, m in self.models.items() if m.opt_in}

    def colors(self) -> dict[str, str]:
        return {n: m.color for n, m in self.models.items()}

    def by_weight(self, names: list[str] | None = None) -> list[str]:
        """Preferred-first ordering: the opencode models are favoured (plan R5)."""
        pool = names if names is not None else list(self.models)
        return sorted(pool, key=lambda n: (-self.models[n].weight, n))

    # ---------- generated prose ----------
    def roster(self) -> dict[str, str]:
        """name -> description. Replaces the hand-maintained ROSTER."""
        return {n: m.description() for n, m in self.models.items()}

    def describe(self, name: str) -> str:
        return self.get(name).card()

    def matrix(self, live: set[str] | None = None, team: set[str] | None = None,
               lead: str | None = None) -> str:
        """The report's comparison table, rendered from the registry (plan R7)."""
        head = "| model | tier | footprint | best at | status |"
        sep = "| :--- | :--- | :--- | :--- | :--- |"
        rows = [head, sep]
        for name in self.by_weight():
            m = self.models[name]
            if live is None:
                status = ""
            elif team is not None and name in team:
                status = "**LEAD**" if name == lead else "awake"
            elif name in live:
                status = "asleep"
            else:
                status = "not installed"
            rows.append(f"| `{name}` | {m.tier} | {m.footprint or '—'} | {m.best_at} | {status or '—'} |")
        return "\n".join(rows)

    # ---------- availability ----------
    @staticmethod
    def _ollama_models() -> set[str]:
        """Exact tags from /api/tags. Ollama normalises `deepseek-r1:1.5b` to
        `deepseek-r1-1.5b:latest`, so callers must match exactly or normalise first."""
        url = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
        try:
            with urllib.request.urlopen(f"{url}/api/tags", timeout=3) as r:
                return {m["name"] for m in json.load(r).get("models", [])}
        except (OSError, ValueError, KeyError):
            return set()

    @staticmethod
    def _opencode_models() -> set[str]:
        """provider/model ids the opencode CLI will accept, so a typo cannot join the team."""
        if not shutil.which("opencode"):
            return set()
        import subprocess
        try:
            out = subprocess.run(["opencode", "models"], capture_output=True, text=True, timeout=30)
        except (OSError, subprocess.SubprocessError):
            return set()
        return {line.strip() for line in out.stdout.splitlines() if "/" in line}

    def available(self) -> list[str]:
        """Members whose backing tool is actually present, in preference order."""
        ollama: set[str] | None = None
        opencode: set[str] | None = None
        found = []
        for name, m in self.models.items():
            if m.verify == "path":
                ok = bool(shutil.which(m.cli))
            elif m.verify == "env":
                ok = bool(os.environ.get(m.env))
            else:  # ollama
                if ollama is None:
                    ollama = self._ollama_models()
                ok = m.model in ollama
            if ok and m.cli == "opencode":
                if opencode is None:
                    opencode = self._opencode_models()
                ok = not opencode or m.model in opencode
            if ok:
                found.append(name)
        return self.by_weight(found)

    async def detect(self) -> list[str]:
        """Async wrapper for runtime re-detection (`/add`, `/remove`) — never blocks the loop."""
        import asyncio
        return await asyncio.to_thread(self.available)

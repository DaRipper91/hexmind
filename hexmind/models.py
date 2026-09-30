"""The model registry: one structured source of truth for the team roster.

`ROSTER` used to be a hand-maintained dict of prose that the lead reads to assign work. That is
how `muse-spark` ended up described with another model's specialty, and nothing caught it. The
prose is now *generated* from the fields in `models.toml`, so the room and `/models` cannot
disagree about what a model is for.

Load order mirrors the chain files: bundled `hexmind/models.toml` first, then
`~/.config/hexmind/models.toml`, so a user override wins per table.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tomllib
import urllib.request
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

BUNDLED = Path(__file__).parent / "models.toml"
USER = Path.home() / ".config/hexmind/models.toml"
# The catalogue is a cache of what a scan *found*, never a roster. It lives under the data dir
# beside the audit stats, not under config, because it is machine state that a later scan
# overwrites — a profile the user wrote does not belong in a file a scan rewrites.
CATALOGUE = Path.home() / ".local/share/hexmind/catalogue.json"
TIERS = ("cloud", "local")
VERIFIERS = ("path", "ollama", "env")
# Discovered models get a stable colour from their slug, so a promoted model is recognisable in the
# room rather than arriving as the white that a missing colour field would silently give it.
DISCOVERED_COLORS = ("cyan", "magenta", "bright_cyan", "bright_magenta", "spring_green2", "gold3")


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
    enabled: bool = True

    @property
    def is_local(self) -> bool:
        return self.tier == "local"

    @property
    def ref(self) -> str:
        """The `provider/model[#variant]` string a CLI takes for this member.

        Only the opencode family is wired, because only opencode documents a reasoning effort on the
        model flag itself (`-m provider/model#variant`); kimi takes reasoning in its own config, so
        appending `#max` there would be an invalid alias. A member with no variant yields the bare id
        it declares, so adding the field cannot change a model that never had one.
        """
        if self.variant and self.cli == "opencode" and self.model:
            return f"{self.model}#{self.variant}"
        return self.model

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


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def assign_slugs(ids: list[str]) -> dict[str, str]:
    """model id -> hexmind member name.

    Always provider-prefixed, and that is the whole design: the name is what a profile, a nickname,
    a chain file and every past task's `agent` field refer to, so it must be a function of the id
    alone. A pretty bare slug (`big-pickle`) looked better and was wrong twice over — it collides
    when two providers offer the same model name, and it *renames itself* when one of them
    disappears, so a model you had already profiled would come back under a different name than the
    profile it was profiled with. A hash suffix is the fallback for the one case a prefix cannot
    disambiguate (`a/b-c` and `a-b/c` both slug to `a-b-c`).
    """
    out: dict[str, str] = {}
    for model_id in sorted(ids):
        provider, sep, bare = model_id.partition("/")
        if not sep:  # an Ollama tag, not a provider/model pair: partition hands the whole string
            provider, bare = "local", model_id  # back as the provider, which then gets prefixed too
        prefix = slugify(provider) or "local"
        base = f"{prefix}-{slugify(bare or model_id)}"
        if base in out.values():
            base = f"{base}-{hashlib.sha1(model_id.encode()).hexdigest()[:6]}"
        out[model_id] = base
    return out


def discover() -> list[dict]:
    """Everything a scan can see, from both slow sources. Blocking (subprocess + HTTP); callers on
    the event loop must use `Registry.detect`-style wrapping.

    A source that cannot be reached is reported as an empty list rather than an error: a machine
    with no Ollama running is the normal case, and a scan that fails wholesale because one of two
    sources is down would make the other one unusable."""
    found: dict[str, dict] = {}
    for model_id in Registry._opencode_models():
        found[model_id] = {"model": model_id, "provider": model_id.partition("/")[0],
                           "cli": "opencode", "verify": "path", "tier": "cloud"}
    for tag in Registry._ollama_models():
        # the exact tag, verbatim: Ollama normalises names on the way out, and matching a
        # normalised string against a real tag is how a local model silently never matches
        found[tag] = {"model": tag, "provider": "ollama",
                      "cli": "ollama", "verify": "ollama", "tier": "local"}
    for model_id, name in assign_slugs(list(found)).items():
        found[model_id]["name"] = name
        found[model_id]["label"] = (found[model_id]["model"].partition("/")[2]
                                    or found[model_id]["model"]).replace("-", " ").title()
        found[model_id]["color"] = DISCOVERED_COLORS[
            int(hashlib.sha1(model_id.encode()).hexdigest(), 16) % len(DISCOVERED_COLORS)]
    return sorted(found.values(), key=lambda e: e["model"])


def align_entries(entries: list[dict], models: dict[str, Model]) -> list[dict]:
    """Reuse the registry's own name for a find that is already a member.

    The eight curated opencode models are called `big-pickle`, `nemotron-ultra` and so on in
    models.toml, but a scan of `opencode/big-pickle` slugs to `opencode-big-pickle`. Without this,
    `/found` reports eight already-curated models as unpromoted finds, and `/profile` on one would
    create a second member for a model the room already has. Matched on the provider/model id, which
    is the identity; the member name is just a label for it."""
    by_id = {m.model: name for name, m in models.items() if m.model}
    out = []
    for entry in entries:
        member = by_id.get(entry["model"])
        if member:
            entry = {**entry, "name": member, "label": models[member].label,
                     "curated": True, "color": models[member].color}
        else:
            entry = {**entry, "curated": False}
        out.append(entry)
    return out


def save_catalogue(entries: list[dict], path: Path | None = None) -> Path:
    # resolved at call time, not bound as a default: a default argument is evaluated once at import,
    # so a frozen Path would keep writing to the first HOME this interpreter ever saw
    path = path or CATALOGUE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "scanned_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "models": entries,
    }, indent=1) + "\n")
    return path


def load_catalogue(path: Path | None = None) -> dict:
    path = path or CATALOGUE
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, ValueError):
        return {}


def _table_text(name: str, fields: dict) -> str:
    """One `[models.NAME]` block, TOML-quoted the same way config.py writes its values."""
    key = name if re.fullmatch(r"[A-Za-z0-9_-]+", name) else json.dumps(name)
    lines = [f"[models.{key}]"]
    for field_name, value in fields.items():
        if isinstance(value, bool):
            lines.append(f"{field_name} = {'true' if value else 'false'}")
        elif isinstance(value, (list, tuple)):
            lines.append(f"{field_name} = [{', '.join(json.dumps(str(v)) for v in value)}]")
        elif isinstance(value, int):
            lines.append(f"{field_name} = {value}")
        else:
            lines.append(f"{field_name} = {json.dumps(str(value))}")
    return "\n".join(lines) + "\n"


def upsert_profile(name: str, fields: dict, path: Path | None = None) -> str:
    """Write (or replace) one `[models.NAME]` table in the user overlay, leaving every other table
    in that file exactly as it was.

    Text-level block surgery rather than a parse-and-reserialise: there is no TOML writer in the
    dependency list, and `config.py` already established the pattern of hand-writing the few values
    this project emits with `json.dumps`. A user overlay is also the one file a hand-edited profile
    lives in, so it has to survive a rewrite that only meant to touch one table."""
    path = path or USER
    try:
        text = path.read_text() if path.is_file() else ""
    except OSError as e:
        raise OSError(f"cannot read {path}: {e}") from None
    key = name if re.fullmatch(r"[A-Za-z0-9_-]+", name) else json.dumps(name)
    header = f"[models.{key}]"
    kept, skipping = [], False
    for line in text.splitlines(keepends=True):
        stripped = line.strip()
        if stripped.startswith("["):
            skipping = stripped == header
        if not skipping:
            kept.append(line)
    body = "".join(kept).rstrip("\n")
    block = _table_text(name, fields)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text((body + "\n\n" + block) if body else block)
    return str(path)


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
            spec["enabled"] = spec.get("enabled", True)
            models[name] = Model(name=name, **spec)
        return cls(models, tuple(sources))

    def reload(self, paths: list[Path] | None = None) -> list[str]:
        """Re-read the registry into *this* object and return the member names that changed.

        In place, deliberately. `REGISTRY` is imported by name in four modules, so rebuilding it and
        rebinding the global would leave every one of them pointing at the old models dict — and a
        model that is in the registry but not in the module that already derived its prompt line is
        worse than one that is absent, because the failure shows up as a KeyError mid-task."""
        fresh = Registry.load(paths)
        before = dict(self.models)
        self.models.clear()
        self.models.update(fresh.models)
        self.sources = fresh.sources
        return sorted(n for n in set(before) | set(self.models) if before.get(n) != self.models.get(n))

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

    # ---------- enabled models ----------
    def enabled_names(self) -> list[str]:
        """All model names that are enabled, in preference order."""
        return self.by_weight([n for n, m in self.models.items() if m.enabled])

    def enabled_and_available(self) -> list[str]:
        """Enabled models whose backing tool is actually present, in preference order."""
        return self.by_weight([n for n in self.available() if self.models[n].enabled])

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
        import re
        import subprocess
        try:
            out = subprocess.run(["opencode", "models"], capture_output=True, text=True, timeout=30)
        except (OSError, subprocess.SubprocessError):
            return set()
        # Match provider/model shape (e.g. "anthropic/claude-sonnet-4-20250514"),
        # stripping any warning or header lines the CLI may emit.
        _model_re = re.compile(r"^[\w.-]+/[\w:.-]+$")
        return {line.strip() for line in out.stdout.splitlines() if _model_re.match(line.strip())}

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


def publish(registry: Registry, paths: list[Path] | None = None) -> list[str]:
    """Re-read the registry and republish every value derived from it at import time. Returns the
    member names that changed.

    Everything here is mutated *in place* for the reason `Registry.reload` gives: `ROSTER`,
    `TEXT_ONLY`, `OPT_IN`, `DIRECT_CMDS`, `LOCAL_MODELS` and `AGENT_COLOR` are all module globals
    that other modules hold by name, and all six are computed once at import. A model promoted
    mid-session without this step is present in the registry and absent everywhere else: it appears
    in `/models`, the lead's roster has no line for it, and the first task routed to it raises
    `KeyError: DIRECT_CMDS[name]`. Lazy imports keep models.py free of a cycle with core."""
    changed = registry.reload(paths)
    if not changed:
        return []
    from . import backends, core, tui

    core.ROSTER.clear()
    core.ROSTER.update(registry.roster())
    core.TEXT_ONLY.clear()
    core.TEXT_ONLY.update(registry.text_only())
    core.OPT_IN.clear()
    core.OPT_IN.update(registry.opt_in())
    for name in backends.GENERATED:
        backends.DIRECT_CMDS.pop(name, None)  # only the generated keys; the bespoke CLIs stay
    backends.GENERATED.clear()
    for name, model in registry.models.items():
        if model.cli == "opencode" and model.model:
            backends.DIRECT_CMDS[name] = ["opencode", "run", "--auto", "-m", model.ref]
            backends.GENERATED.add(name)
    backends.LOCAL_MODELS.clear()
    backends.LOCAL_MODELS.update({n: m.model for n, m in registry.models.items() if m.verify == "ollama"})
    tui.AGENT_COLOR.clear()
    tui.AGENT_COLOR.update(registry.colors())
    tui.AGENT_COLOR["you"] = "bold white"
    return changed

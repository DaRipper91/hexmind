"""Centralized user configuration for Hexmind in ~/.config/hexmind/config.toml.

Governed by Phase 1 of the Flagship GUI Roadmap:
[room]
lead = "nemotron-lightning"                  # default lead model ID or empty
members = ["nemotron-lightning", "big-pickle"]
audit = true               # default peer audit toggle
theme = "measured-dark"    # UI theme

[server]
host = "127.0.0.1"
port = 8765
token = ""

[notifications]
phone_buzz = false         # KDE Connect ping via notify.py
threshold_seconds = 30     # only notify if turn took longer than 30s

[models]
# model-name = true/false  (enabled state controls UI visibility)
# Only free OpenCode models that opencode offers are enabled by default.
# claude-code, agy, codex and other paid/non-opencode tools are disabled.
beam-free = true
big-pickle = true
deepseek-v4-1-flash-free = true
glm-5-3-flash-free = true
longcat-preview = true
mimo-flash = true
nemotron-3-5-super-vl-free = true
nemotron-lightning = true
nemotron-ultra = true
space-bunny = true
"""
from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import tomllib
from typing import Any

PATH: str | Path = os.path.expanduser("~/.config/hexmind/config.toml")


@dataclass
class RoomDefaults:
    lead: str = "nemotron-lightning"
    members: list[str] = field(default_factory=lambda: ["nemotron-lightning", "big-pickle"])
    audit: bool = True
    theme: str = "measured-dark"
    # "system" follows the desktop font; a number is the GUI's base text size in px.
    text_size: str = "14"


TEXT_SIZES = ("system", "12", "14", "16", "18", "20")


@dataclass
class ServerDefaults:
    host: str = "127.0.0.1"
    port: int = 8765
    token: str = ""


@dataclass
class NotificationDefaults:
    phone_buzz: bool = False
    threshold_seconds: int = 30


def _resolve_path(path: str | Path | None = None) -> Path:
    if path is None:
        p = PATH
    else:
        p = path
    return Path(p).expanduser()


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    """Load the full config.toml dictionary. Returns empty dict if missing or invalid."""
    p = _resolve_path(path)
    try:
        with open(p, "rb") as f:
            data = tomllib.load(f)
            return data if isinstance(data, dict) else {}
    except (FileNotFoundError, tomllib.TOMLDecodeError, OSError):
        return {}


def _format_value(val: Any) -> str:
    if isinstance(val, bool):
        return "true" if val else "false"
    if isinstance(val, (int, float)):
        return str(val)
    if isinstance(val, (list, tuple)):
        return "[" + ", ".join(_format_value(x) for x in val) + "]"
    return json.dumps(str(val))


def _format_toml(config_data: dict[str, Any]) -> str:
    """Format dictionary as clean TOML without external dependencies."""
    blocks: list[str] = []
    order = ["room", "server", "notifications", "nicknames"]
    extra = sorted(s for s in config_data if s not in order)
    for section in order + extra:
        if section not in config_data:
            continue
        sec_data = config_data[section]
        if not isinstance(sec_data, dict):
            continue
        lines = [f"[{section}]"]
        for k, v in sorted(sec_data.items()):
            lines.append(f"{k} = {_format_value(v)}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks) + ("\n" if blocks else "")


def save_section(section: str, data: dict[str, Any], path: str | Path | None = None) -> None:
    """Update or insert a section in config.toml, preserving all other existing sections."""
    p = _resolve_path(path)
    current = load_config(p)
    current[section] = dict(data)

    p.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = p.with_suffix(".tmp")
    text = _format_toml(current)
    tmp_path.write_text(text, encoding="utf-8")
    tmp_path.replace(p)


def get_defaults(path: str | Path | None = None) -> RoomDefaults:
    """Get validated RoomDefaults dataclass from config.toml [room] section."""
    cfg = load_config(path).get("room", {})
    defaults = RoomDefaults()
    members = cfg.get("members")
    if not isinstance(members, list) or not all(isinstance(m, str) for m in members):
        members = defaults.members
    return RoomDefaults(
        lead=str(cfg.get("lead", defaults.lead)),
        members=members,
        audit=bool(cfg.get("audit", defaults.audit)),
        theme=str(cfg.get("theme", defaults.theme)),
        text_size=text_size if (text_size := str(cfg.get("text_size", defaults.text_size)))
        in TEXT_SIZES else defaults.text_size,
    )


def get_server_defaults(path: str | Path | None = None) -> ServerDefaults:
    """Get validated ServerDefaults dataclass from config.toml [server] section."""
    cfg = load_config(path).get("server", {})
    port = cfg.get("port")
    try:
        port_int = int(port) if port is not None else 8765
    except (ValueError, TypeError):
        port_int = 8765
    return ServerDefaults(
        host=str(cfg.get("host", "127.0.0.1")),
        port=port_int,
        token=str(cfg.get("token", "")),
    )


def get_notification_defaults(path: str | Path | None = None) -> NotificationDefaults:
    """Get validated NotificationDefaults dataclass from config.toml [notifications] section."""
    cfg = load_config(path).get("notifications", {})
    threshold = cfg.get("threshold_seconds")
    try:
        threshold_int = int(threshold) if threshold is not None else 30
    except (ValueError, TypeError):
        threshold_int = 30
    return NotificationDefaults(
        phone_buzz=bool(cfg.get("phone_buzz", False)),
        threshold_seconds=threshold_int,
    )


def get_enabled_models(path: str | Path | None = None) -> dict[str, bool]:
    """Get enabled models dictionary from config.toml [models] section.

    Returns a dict mapping model name -> enabled state (True/False).
    If the section is missing or invalid, returns an empty dict (caller should
    fall back to registry defaults where all models are enabled).
    """
    cfg = load_config(path).get("models", {})
    if not isinstance(cfg, dict):
        return {}
    return {k: bool(v) for k, v in cfg.items() if isinstance(v, bool)}


def save_enabled_models(enabled: dict[str, bool], path: str | Path | None = None) -> None:
    """Save enabled models dictionary to config.toml [models] section.

    Preserves all other existing sections.
    """
    save_section("models", enabled, path)


def load_nicknames(path: str | Path = PATH) -> dict[str, str]:
    """Load nicknames dictionary from config.toml. Preserves backwards compatibility."""
    return {k: str(v) for k, v in load_config(path).get("nicknames", {}).items()}


def save_nicknames(nicks: dict[str, str], path: str | Path = PATH) -> None:
    """Save nicknames dictionary to config.toml without overwriting other sections."""
    save_section("nicknames", nicks, path)

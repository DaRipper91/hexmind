"""User settings in ~/.config/hexmind/config.toml. Currently just model nicknames:

[nicknames]
claude = "Rex"
"""
from __future__ import annotations

import json
import os
import tomllib

PATH = os.path.expanduser("~/.config/hexmind/config.toml")


def load_nicknames(path: str = PATH) -> dict[str, str]:
    try:
        with open(path, "rb") as f:
            return {k: str(v) for k, v in tomllib.load(f).get("nicknames", {}).items()}
    except (FileNotFoundError, tomllib.TOMLDecodeError):
        return {}


def save_nicknames(nicks: dict[str, str], path: str = PATH) -> None:
    # ponytail: rewrites the whole file; fine while nicknames are the only setting
    os.makedirs(os.path.dirname(path), exist_ok=True)
    lines = ["[nicknames]"] + [f"{k} = {json.dumps(v)}" for k, v in sorted(nicks.items())]
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")

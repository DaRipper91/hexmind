"""Phone ping when the room needs you back (a run finished, an ESCALATION). Uses KDE Connect if present.

Blocking but short (a few seconds at most); from async code call it with `await asyncio.to_thread(notify, ...)`.
Never raises: a missing, unpaired or unreachable phone just means no ping.
"""
from __future__ import annotations

import shutil
import subprocess

TIMEOUT = 5  # seconds per kdeconnect-cli call


def notify(title: str, body: str = "") -> int:
    """Ping every paired, reachable KDE Connect device. Returns how many were pinged."""
    cli = shutil.which("kdeconnect-cli")
    if not cli:
        return 0
    message = f"{title}: {body}" if body else title
    try:
        found = subprocess.run([cli, "--list-available", "--id-only"], capture_output=True, text=True,
                               timeout=TIMEOUT, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError):
        return 0
    sent = 0
    for device in (line.strip() for line in found.stdout.splitlines()):
        if not device:
            continue
        try:
            r = subprocess.run([cli, "--device", device, "--ping-msg", message], capture_output=True,
                               timeout=TIMEOUT, stdin=subprocess.DEVNULL)
        except (OSError, subprocess.SubprocessError):
            continue
        sent += r.returncode == 0
    return sent

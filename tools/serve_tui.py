#!/usr/bin/env python3
"""Serve the existing Textual TUI in a browser, as a stopgap while a real GUI is designed.

This is deliberately NOT a product feature. It adds zero UI code: `textual-serve` runs the very
same `HexmindApp` inside a PTY and mirrors the terminal into a browser canvas. The point is that
you get all 22 room commands, on a phone, today, for a one-file script — instead of the real GUI
being rushed.

    python3 tools/serve_tui.py                  # http://127.0.0.1:8000
    python3 tools/serve_tui.py --port 9000
    python3 tools/serve_tui.py --host 0.0.0.0   # LAN/phone; prints a security warning

What it is good for: reaching the room from a second machine or a phone while the TUI occupies
your terminal.

What it is NOT: a rich GUI. There is no task graph, no streaming, no diffs, and a few Textual
facilities (clipboard in particular) do not work in the browser. See `docs/GUI-OPTIONS.md`.
"""
from __future__ import annotations

import argparse
import sys


def main() -> None:
    p = argparse.ArgumentParser(
        prog="serve_tui",
        description="Serve the hexmind Textual TUI in a browser (development stopgap).",
    )
    p.add_argument("--host", default="127.0.0.1",
                   help="bind address (default: 127.0.0.1, loopback only)")
    p.add_argument("--port", type=int, default=8000, help="bind port (default: 8000)")
    p.add_argument("--title", default="Hexmind", help="browser tab title")
    args = p.parse_args()

    try:
        from textual_serve.server import Server
    except ImportError:
        sys.exit("This stopgap needs textual-serve, which is not a runtime dependency:\n"
                 "    pip install textual-serve\n"
                 "It is intentionally left out of pyproject.toml — hexmind itself does not need it.")

    if args.host not in ("127.0.0.1", "localhost", "::1"):
        # Same posture as `hexmind --serve` after the 2026-09-28 audit: the agents behind this port
        # write real files, with edits auto-accepted. Loopback is the default for that reason.
        print(f"WARNING: binding {args.host} exposes the room to your network. "
              "Anyone who can reach it can drive agents that write files. "
              "Use a trusted network, or put it behind an authenticating proxy.", file=sys.stderr)

    # `python -m hexmind` is the real entry point, so the browser gets the identical room the
    # terminal does — same roster, same lead picker, same commands. No second implementation.
    command = f"{sys.executable} -m hexmind"
    print(f"Serving {command} at http://{args.host}:{args.port}  (Ctrl+C to stop)")
    Server(command, host=args.host, port=args.port, title=args.title).serve()


if __name__ == "__main__":
    main()

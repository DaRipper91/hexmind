"""hexmind entry point: `hexmind` opens the TUI room, `hexmind --once "..."` runs one request headless."""
from __future__ import annotations

import argparse
import asyncio
import os
import sys

from .backends import DirectBackend, available
from .core import ROSTER, Orchestrator


def main() -> None:
    p = argparse.ArgumentParser(prog="hexmind", description="Multi-model agent team in one chat room.")
    p.add_argument("--backend", choices=["direct", "hcom"], default="direct",
                   help="direct: hexmind runs agent CLIs itself; hcom: agents live in hcom (phase 2)")
    p.add_argument("--lead", default="claude", help="agent that plans and summarizes (default: claude)")
    p.add_argument("--without", action="append", default=[], metavar="AGENT",
                   help="leave an agent out, e.g. --without codex (repeatable)")
    p.add_argument("--cwd", default=os.getcwd(), help="folder the team works in (default: current)")
    p.add_argument("--once", metavar="REQUEST", help="run one request without the TUI and print the result")
    args = p.parse_args()

    if args.backend == "hcom":
        sys.exit("hcom backend lands in phase 2; use --backend direct for now.")
    members = [m for m in available(list(ROSTER)) if m not in args.without]
    if args.lead not in members:
        sys.exit(f"lead '{args.lead}' is not available (installed members: {', '.join(members) or 'none'})")
    backend = DirectBackend(os.path.abspath(args.cwd))

    if args.once:
        def emit(kind, data):
            if kind == "message":
                print(f"\n[{data['from']}] {data['text']}\n", flush=True)
            elif kind == "task":
                t = data["task"]
                print(f"  {t.id} {t.agent:<7} {t.status:<8} {t.title}", flush=True)
        asyncio.run(Orchestrator(backend, members, args.lead, emit).handle(args.once))
        return

    from .tui import HexmindApp
    HexmindApp(backend, members, args.lead, args.backend).run()


if __name__ == "__main__":
    main()

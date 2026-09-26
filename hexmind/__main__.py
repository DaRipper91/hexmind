"""hexmind entry point: `hexmind` opens the TUI room, `hexmind --once "..."` runs one request headless."""
from __future__ import annotations

import argparse
import asyncio
import os
import sys

from .backends import DirectBackend, HcomBackend, available
from .core import ROSTER, Orchestrator


def main() -> None:
    p = argparse.ArgumentParser(prog="hexmind", description="Multi-model agent team in one chat room.")
    p.add_argument("--backend", choices=["direct", "hcom"], default="direct",
                   help="direct: hexmind runs agent CLIs itself; hcom: models are persistent hcom agents")
    p.add_argument("--lead", default="claude", help="agent that plans and summarizes (default: claude)")
    p.add_argument("--without", action="append", default=[], metavar="AGENT",
                   help="leave an agent out, e.g. --without codex (repeatable)")
    p.add_argument("--with", dest="with_", action="append", default=[], metavar="AGENT",
                   help="add an opt-in member, e.g. --with qwen (local model; slow on small machines)")
    p.add_argument("--cwd", default=os.getcwd(), help="folder the team works in (default: current)")
    p.add_argument("--audit", action="store_true", help="runner-up model reviews every task (toggle in room: /audit on|off)")
    p.add_argument("--once", metavar="REQUEST", help="run one request without the TUI and print the result")
    args = p.parse_args()

    from .core import OPT_IN
    members = [m for m in available(list(ROSTER)) if m not in args.without
               and (m not in OPT_IN or m in args.with_)]
    from .core import TEXT_ONLY
    if args.lead in TEXT_ONLY:
        sys.exit(f"'{args.lead}' is text-only (no file or tool access) and can't lead; pick claude, agy or codex")
    if args.lead not in members:
        sys.exit(f"lead '{args.lead}' is not available (installed members: {', '.join(members) or 'none'})")
    # hcom: each model is a persistent headless hcom agent (started on first use)
    backend = (HcomBackend if args.backend == "hcom" else DirectBackend)(os.path.abspath(args.cwd))
    from .auditor import Stats
    stats = Stats(os.path.expanduser("~/.local/share/hexmind/stats.json"))

    if args.once:
        def emit(kind, data):
            if kind == "message":
                print(f"\n[{data['from']}] {data['text']}\n", flush=True)
            elif kind == "task":
                t = data["task"]
                print(f"  {t.id} {t.agent:<7} {t.status:<8} {t.title}", flush=True)
        asyncio.run(Orchestrator(backend, members, args.lead, emit, args.audit, stats).handle(args.once))
        return

    from .tui import HexmindApp
    HexmindApp(backend, members, args.lead, args.backend, audit=args.audit, stats=stats).run()


if __name__ == "__main__":
    main()

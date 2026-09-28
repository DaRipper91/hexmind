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
    p.add_argument("--lead", default=None, metavar="AGENT",
                   help="agent that plans and summarizes. The TUI asks for this at startup; it is "
                        "required for --once and --serve, where there is nobody to ask")
    p.add_argument("--without", action="append", default=[], metavar="AGENT",
                   help="leave an agent out, e.g. --without codex (repeatable)")
    p.add_argument("--with", dest="with_", action="append", default=[], metavar="AGENT",
                   help="add an opt-in member, e.g. --with qwen (local model; slow on small machines)")
    p.add_argument("--cwd", default=os.getcwd(), help="folder the team works in (default: current)")
    p.add_argument("--approve-plans", action="store_true",
                   help="the lead's plan waits for /approve or /discard (toggle in room: /drafts on|off)")
    p.add_argument("--audit", action="store_true", help="runner-up model reviews every task (toggle in room: /audit on|off)")
    p.add_argument("--once", metavar="REQUEST", help="run one request without the TUI and print the result")
    p.add_argument("--timeout", type=int, default=1800, metavar="SECONDS",
                   help="per-call agent timeout (default: 1800). A relay stage doing a full TDD cycle "
                        "can legitimately exceed 30 minutes, so raise this for long chains")
    p.add_argument("--serve", action="store_true", help="start headless WebSocket & REST API server")
    p.add_argument("--host", default="127.0.0.1", help="server host (default: 127.0.0.1)")
    p.add_argument("--port", type=int, default=8765, help="server port (default: 8765)")
    p.add_argument("--token", default=None, metavar="TOKEN",
                   help="auth token for the server; required off loopback (or set HEXMIND_TOKEN)")
    args = p.parse_args()

    from .core import OPT_IN
    members = [m for m in available(list(ROSTER)) if m not in args.without
               and (m not in OPT_IN or m in args.with_)]
    from .core import TEXT_ONLY
    if not members:
        sys.exit("No team members available. Install at least one agent CLI (claude, agy, codex, "
                 "opencode, copilot, kimi) and make sure it is on your PATH.")

    # No default lead. A hardcoded one is wrong twice over: it crashes when that model is not
    # installed (a commit set it to opencode-ultra and made hexmind refuse to start for anyone
    # without the opencode CLI), and it silently picks the room's spokesperson for the user. The
    # TUI asks; headless surfaces have nobody to ask, so they must say so.
    if args.lead is None:
        if args.once or args.serve:
            sys.exit(f"--lead is required for --{'once' if args.once else 'serve'}. "
                     f"Installed members: {', '.join(members)}")
        args.lead = None  # the TUI's startup picker sets it before the first request
    elif args.lead in TEXT_ONLY:
        sys.exit(f"'{args.lead}' is text-only (no file or tool access) and can't lead; "
                 f"pick one of: {', '.join(m for m in members if m not in TEXT_ONLY)}")
    elif args.lead not in members:
        sys.exit(f"lead '{args.lead}' is not available (installed members: {', '.join(members)})")

    if args.backend == "hcom":
        # hcom drives one agent per tool and cannot choose which model that tool uses, so the seven
        # non-default opencode models are unreachable here. Say so instead of silently running a
        # smaller team than the user expects.
        from .backends import hcom_unsupported
        dropped = hcom_unsupported(members)
        if dropped:
            print(f"note: --backend hcom cannot drive {len(dropped)} opencode model(s) "
                  f"(hcom picks a tool, not a model): {', '.join(dropped)}\n"
                  f"      use --backend direct for the full team.", file=sys.stderr)

    if args.serve:
        # The guard spans the call, not just the import: run_server does `import uvicorn` lazily, so
        # a missing uvicorn with fastapi present would otherwise escape as a bare traceback from
        # inside a function the user never called.
        try:
            from .server import run_server
            run_server(
                cwd=args.cwd,
                host=args.host,
                port=args.port,
                backend=args.backend,
                lead=args.lead,
                without=args.without,
                with_=args.with_,
                audit=args.audit,
                approve_plans=args.approve_plans,
                timeout=args.timeout,
                token=args.token,
            )
        except ImportError as e:
            # --serve is a documented surface, so its dependencies are an extra rather than base
            # weight. Say how to get them instead of letting an ImportError out of the argument
            # parser tell someone they are missing a module.
            sys.exit(f"--serve needs the server extra, which is not installed ({e}).\n"
                     f"      pip install 'hexmind[server]'")
        return

    # hcom: each model is a persistent headless hcom agent (started on first use)
    backend = (HcomBackend if args.backend == "hcom" else DirectBackend)(os.path.abspath(args.cwd),
                                                                       timeout=args.timeout)
    from .auditor import Stats
    stats = Stats(os.path.expanduser("~/.local/share/hexmind/stats.json"))

    if args.once:
        def emit(kind, data):
            if kind == "message":
                print(f"\n[{data['from']}] {data['text']}\n", flush=True)
            elif kind == "task":
                t = data["task"]
                print(f"  {t.id} {t.agent:<7} {t.status:<8} {t.title}", flush=True)
                if t.status == "failed":
                    # the status line alone says nothing went well but not what; the TUI posts the
                    # first line of the output on failure, so a headless caller learns the same thing
                    first = t.output.strip().splitlines()[0][:200] if t.output.strip() else ""
                    if first:
                        print(f"      {first}", flush=True)
        orch = Orchestrator(backend, members, args.lead, emit, args.audit, stats)
        try:
            asyncio.run(orch.handle(args.once))
        except KeyboardInterrupt:
            sys.exit(130)
        except Exception as e:
            # A blocked backend, an out-of-quota member or a malformed plan is an expected outcome of
            # a one-shot run, not a crash. Report it the way the TUI does and exit non-zero, instead
            # of dumping a traceback at someone calling hexmind from a script. Set HEXMIND_TRACEBACK=1
            # to get the traceback anyway when debugging.
            if os.environ.get("HEXMIND_TRACEBACK"):
                raise
            print(f"\nhexmind: {e}", file=sys.stderr)
            sys.exit(1)
        return

    from .tui import HexmindApp
    app = HexmindApp(backend, members, args.lead, args.backend, audit=args.audit, stats=stats)
    app.orch.approve_plans = args.approve_plans  # set here so tui.py stays untouched
    app.run()


if __name__ == "__main__":
    main()

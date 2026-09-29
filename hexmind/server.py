"""Hexmind Headless Server: FastAPI and WebSocket Daemon.

Provides a full-duplex WebSocket event stream and REST API for remote clients
(native Android app, Web UI, terminal remotes).
"""
from __future__ import annotations

import asyncio
import base64
import logging
import os
import secrets
import time
from dataclasses import asdict
from typing import Any, Callable, Dict, List, Optional, Tuple

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from .backends import DirectBackend, HcomBackend, available
from .core import ROSTER, OPT_IN, Orchestrator, Task
from .auditor import Stats, DOMAINS
from .config import save_nicknames
from .relay import list_chains, load_chain

logger = logging.getLogger(__name__)


class PromptRequest(BaseModel):
    text: str
    lead: Optional[str] = None
    audit: Optional[bool] = None
    approve_plans: Optional[bool] = None


class NicknamesRequest(BaseModel):
    nicknames: Dict[str, str]


class ChainRunRequest(BaseModel):
    chain_name: str
    n: int = 1
    assign: str = "rotate"  # rotate | best | pinned
    workspace: str = "worktree"  # shared | worktree


class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, subprotocol: Optional[str] = None):
        await websocket.accept(subprotocol=subprotocol)
        async with self._lock:
            self.active_connections.append(websocket)

    async def disconnect(self, websocket: WebSocket):
        async with self._lock:
            if websocket in self.active_connections:
                self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        async with self._lock:
            dead = []
            for connection in self.active_connections:
                try:
                    await connection.send_json(message)
                except Exception:
                    dead.append(connection)
            for d in dead:
                if d in self.active_connections:
                    self.active_connections.remove(d)


_SUBPROTOCOL_PREFIX = "hexmind.token."


def validate_token(provided: str, expected: str) -> bool:
    """Constant-time comparison; both sides must be non-empty."""
    if not provided or not expected:
        return False
    return secrets.compare_digest(provided.encode("utf-8"), expected.encode("utf-8"))


def _b64url(value: str) -> str:
    """Unpadded base64url encoding (RFC 2616 tokens forbid '=')."""
    return base64.urlsafe_b64encode(value.encode("utf-8")).decode("ascii").rstrip("=")


def token_to_subprotocol(token: str) -> str:
    """Wrap a token into the subprotocol form clients offer during handshake."""
    return _SUBPROTOCOL_PREFIX + _b64url(token)


def subprotocol_to_token(value: str) -> str:
    """Decode a hexmind.token.* subprotocol back into the raw token, or ''."""
    if not value.startswith(_SUBPROTOCOL_PREFIX):
        return ""
    encoded = value[len(_SUBPROTOCOL_PREFIX):]
    encoded += "=" * (-len(encoded) % 4)
    try:
        return base64.urlsafe_b64decode(encoded.encode("ascii")).decode("utf-8")
    except Exception:
        return ""


def bearer_token(header: str) -> str:
    """Extract the token from an 'Authorization: Bearer <token>' header."""
    scheme, _, value = header.partition(" ")
    if scheme.lower() != "bearer":
        return ""
    return value.strip()


def extract_ws_token(websocket: WebSocket) -> Tuple[str, Optional[str]]:
    """Pull the token from the subprotocol, query string, or Authorization header.

    Returns (token, subprotocol_to_echo); the second element is set only when
    the token arrived via a subprotocol, so the server can echo that exact
    value back in the accept handshake.
    """
    for sub in websocket.headers.getlist("sec-websocket-protocol"):
        for piece in sub.split(","):
            piece = piece.strip()
            token = subprotocol_to_token(piece)
            if token:
                return token, piece
    token = websocket.query_params.get("token", "")
    if token:
        return token, None
    auth = websocket.headers.get("authorization", "")
    if auth:
        token = bearer_token(auth)
        if token:
            return token, None
    return "", None


def allowed_origins(host: str, port: int) -> List[str]:
    """Origins a browser may connect from, derived from the bound host/port.

    Localhost aliases are always permitted; a concrete bind host (e.g. a LAN
    IP) is added unless it is the wildcard 0.0.0.0/:: form.
    """
    names = ["127.0.0.1", "localhost"]
    if host and host not in ("0.0.0.0", "::"):
        names.append(host)
    origins: List[str] = []
    for name in dict.fromkeys(names):
        origins.append(f"http://{name}:{port}")
        origins.append(f"ws://{name}:{port}")
    return origins


def ws_auth_disabled() -> bool:
    """Opt-out kill switch for WS origin/token checks (on by default)."""
    return os.environ.get("HEXMIND_WS_AUTH_DISABLED", "").strip().lower() in ("1", "true", "yes", "on")


def authorize_ws(
    websocket: WebSocket,
    expected_token: str,
    allowed: List[str],
) -> Tuple[str, Optional[str], Optional[Tuple[int, str]]]:
    """Inspect a handshake before it is accepted.

    Returns (token, subprotocol, rejection); rejection is None when the
    handshake may proceed, otherwise a (close_code, reason) pair.
    """
    origin = websocket.headers.get("origin", "")
    token, subprotocol = extract_ws_token(websocket)

    if origin:
        if origin not in allowed:
            return token, subprotocol, (4003, "Origin not allowed")
    else:
        # Browsers always send an Origin on WS connects; its absence means a
        # non-browser client. It may connect only when it proves it holds the
        # token (the documented exception), otherwise reject.
        if not validate_token(token, expected_token):
            if expected_token:
                return token, subprotocol, (4001, "Missing or invalid token")
            return token, subprotocol, (4003, "Origin header required")

    if expected_token and not validate_token(token, expected_token):
        return token, subprotocol, (4001, "Missing or invalid token")

    return token, subprotocol, None


class HexmindServer:
    def __init__(
        self,
        cwd: str,
        backend_name: str = "direct",
        lead: str = "nemotron-ultra",
        without: Optional[List[str]] = None,
        with_: Optional[List[str]] = None,
        audit: bool = False,
        approve_plans: bool = False,
        stats_path: Optional[str] = None,
        timeout: int = 1800,
    ):
        self.cwd = os.path.abspath(cwd)
        self.timeout = timeout
        self.backend_name = backend_name
        self.lead = lead
        self.without = without or []
        self.with_ = with_ or []
        self.audit = audit
        self.approve_plans = approve_plans
        
        self.members = [
            m for m in available(list(ROSTER))
            if m not in self.without and (m not in OPT_IN or m in self.with_)
        ]
        if self.lead not in self.members and self.members:
            self.lead = self.members[0]

        self.backend = (HcomBackend if self.backend_name == "hcom" else DirectBackend)(
            self.cwd, timeout=timeout)
        stats_file = stats_path or os.path.expanduser("~/.local/share/hexmind/stats.json")
        self.stats = Stats(stats_file)
        
        self.manager = ConnectionManager()
        self.messages: List[Dict[str, Any]] = []
        self.active_tasks: List[Dict[str, Any]] = []
        self.current_plan: List[Dict[str, Any]] = []
        self.is_busy = False
        self.current_run_task: Optional[asyncio.Task] = None

        self.orch = Orchestrator(
            backend=self.backend,
            members=self.members,
            lead=self.lead,
            emit=self._emit_sync,
            audit=self.audit,
            stats=self.stats,
        )
        self.orch.approve_plans = self.approve_plans
        self._port = 8765
        self._host = "127.0.0.1"
        self._token = ""

    def _task_to_dict(self, t: Task) -> dict:
        d = asdict(t)
        return d

    def _emit_sync(self, kind: str, data: dict) -> None:
        """Bridge orchestrator synchronous emit callbacks into the async event loop."""
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._emit_async(kind, data))
        except RuntimeError:
            logger.warning("_emit_sync called with no running event loop; %s event dropped", kind)

    async def _emit_async(self, kind: str, data: dict) -> None:
        timestamp = time.time()
        payload: Dict[str, Any] = {"kind": kind, "timestamp": timestamp}

        if kind == "status":
            payload.update(data)
            await self.manager.broadcast(payload)
        elif kind == "message":
            msg = {
                "id": f"msg-{len(self.messages) + 1}",
                "from": data.get("from", "hexmind"),
                "text": data.get("text", ""),
                "timestamp": timestamp,
            }
            self.messages.append(msg)
            payload.update(msg)
            await self.manager.broadcast(payload)
        elif kind == "plan":
            tasks = data.get("tasks", [])
            task_dicts = [self._task_to_dict(t) if isinstance(t, Task) else t for t in tasks]
            self.current_plan = task_dicts
            self.active_tasks = list(task_dicts)
            payload["tasks"] = task_dicts
            await self.manager.broadcast(payload)
        elif kind == "task":
            t = data.get("task")
            td = self._task_to_dict(t) if isinstance(t, Task) else t
            # update in active_tasks list
            found = False
            for i, existing in enumerate(self.active_tasks):
                if existing.get("id") == td.get("id"):
                    self.active_tasks[i] = td
                    found = True
                    break
            if not found:
                self.active_tasks.append(td)
            payload["task"] = td
            await self.manager.broadcast(payload)
        else:
            payload.update(data)
            await self.manager.broadcast(payload)

    def get_status_summary(self) -> dict:
        return {
            "cwd": self.cwd,
            "lead": self.orch.lead,
            "members": self.orch.members,
            "roster_info": {m: ROSTER.get(m, "") for m in self.orch.members},
            "all_roster": ROSTER,
            "nicknames": self.orch.nicknames,
            "audit": self.orch.audit,
            "approve_plans": self.orch.approve_plans,
            "is_busy": self.is_busy,
            "backend": self.backend_name,
            "pending_plan": (
                {
                    "request": self.orch.pending[0],
                    "tasks": [self._task_to_dict(t) for t in self.orch.pending[1]],
                }
                if self.orch.pending
                else None
            ),
            "active_tasks": self.active_tasks,
        }

    async def handle_prompt(self, text: str, audit: Optional[bool] = None, approve_plans: Optional[bool] = None) -> str:
        if audit is not None:
            self.orch.audit = audit
        if approve_plans is not None:
            self.orch.approve_plans = approve_plans

        self.is_busy = True
        await self.manager.broadcast({"kind": "busy_state", "is_busy": True})
        # Add user prompt to messages
        user_msg = {
            "id": f"msg-{len(self.messages) + 1}",
            "from": "user",
            "text": text,
            "timestamp": time.time(),
        }
        self.messages.append(user_msg)
        await self.manager.broadcast({"kind": "message", **user_msg})

        try:
            result = await self.orch.handle(text)
            return result
        except asyncio.CancelledError:
            cancel_msg = {
                "id": f"msg-{len(self.messages) + 1}",
                "from": "hexmind",
                "text": "⏹️ Turn cancelled.",
                "timestamp": time.time(),
            }
            self.messages.append(cancel_msg)
            await self.manager.broadcast({"kind": "message", **cancel_msg})
            raise
        finally:
            self.is_busy = False
            await self.manager.broadcast({"kind": "busy_state", "is_busy": False})

    async def approve_pending(self) -> Optional[str]:
        if not self.orch.pending:
            raise HTTPException(status_code=400, detail="No pending plan to approve")
        req, tasks = self.orch.pending
        # Forward directives (chains, skills) to execute(), mirroring relay.py:714-727
        directives, self.orch.pending_directives = self.orch.pending_directives, None
        self.orch.pending = None
        await self.manager.broadcast({"kind": "pending_cleared"})

        self.is_busy = True
        await self.manager.broadcast({"kind": "busy_state", "is_busy": True})
        try:
            return await self.orch.execute(req, tasks, directives)
        except asyncio.CancelledError:
            cancel_msg = {
                "id": f"msg-{len(self.messages) + 1}",
                "from": "hexmind",
                "text": "⏹️ Turn cancelled.",
                "timestamp": time.time(),
            }
            self.messages.append(cancel_msg)
            await self.manager.broadcast({"kind": "message", **cancel_msg})
            raise
        finally:
            self.is_busy = False
            await self.manager.broadcast({"kind": "busy_state", "is_busy": False})

    def cancel_current_turn(self) -> bool:
        """Cancel in-flight task if any."""
        if self.current_run_task and not self.current_run_task.done():
            self.current_run_task.cancel()
            return True
        return False

    def discard_pending(self) -> bool:
        if not self.orch.pending:
            return False
        # Clear pending_directives too, mirroring relay.py:718
        self.orch.pending_directives = None
        self.orch.pending = None
        self.orch.emit("message", {"from": "hexmind", "text": "Plan discarded."})
        return True


def create_app(server: HexmindServer, token: str | None = None) -> FastAPI:
    app = FastAPI(title="Hexmind API & Realtime Room", version="0.1.0")
    app._hexmind_server = server
    if token is not None:
        server._token = token

    origins = allowed_origins(server._host or "127.0.0.1", server._port or 8765)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def auth_middleware(request: Request, call_next: Callable):
        if server._token and request.url.path.startswith("/api/"):
            provided = request.headers.get("Authorization", "")
            if not validate_token(bearer_token(provided), server._token):
                return JSONResponse(status_code=401, content={"detail": "Missing or invalid token"})
        return await call_next(request)

    @app.get("/api/status")
    async def get_status():
        return server.get_status_summary()

    @app.get("/api/history")
    async def get_history():
        return {
            "messages": server.messages,
            "history": server.orch.history,
            "active_tasks": server.active_tasks,
        }

    @app.post("/api/prompt")
    async def post_prompt(req: PromptRequest):
        if server.is_busy:
            raise HTTPException(status_code=409, detail="Room is currently busy executing a task")
        if req.lead and req.lead in server.orch.members:
            server.orch.lead = req.lead
        
        task = asyncio.create_task(server.handle_prompt(req.text, req.audit, req.approve_plans))
        server.current_run_task = task
        return {"status": "started", "prompt": req.text}

    @app.post("/api/approve")
    async def post_approve():
        if server.is_busy:
            raise HTTPException(status_code=409, detail="Room is currently busy")
        if not server.orch.pending:
            raise HTTPException(status_code=400, detail="No pending plan to approve")
        task = asyncio.create_task(server.approve_pending())
        server.current_run_task = task
        return {"status": "executing"}

    @app.post("/api/discard")
    async def post_discard():
        discarded = server.discard_pending()
        if not discarded:
            raise HTTPException(status_code=400, detail="No pending plan to discard")
        return {"status": "discarded"}

    @app.post("/api/turn/cancel")
    async def post_turn_cancel():
        if not server.is_busy or server.current_run_task is None or server.current_run_task.done():
            raise HTTPException(status_code=400, detail="No active turn to cancel")
        server.current_run_task.cancel()
        return {"status": "cancelling"}

    @app.get("/api/chains")
    async def get_chains():
        chains_map = list_chains()
        result = []
        for name, path in chains_map.items():
            try:
                c = load_chain(path)
                result.append({
                    "name": c.name,
                    "description": c.description,
                    "stages": [{"name": s.name, "domain": s.domain, "agent": s.agent} for s in c.stages],
                    "path": str(path),
                })
            except Exception as e:
                result.append({"name": name, "error": str(e), "path": str(path)})
        return {"chains": result}

    @app.get("/api/stats")
    async def get_stats():
        return {
            "table": server.stats.table(server.orch.members),
            "data": server.stats.data,
            "domains": DOMAINS,
        }

    @app.post("/api/config/nicknames")
    async def update_nicknames(req: NicknamesRequest):
        server.orch.nicknames = req.nicknames
        save_nicknames(req.nicknames)
        await server.manager.broadcast({"kind": "nicknames_updated", "nicknames": req.nicknames})
        return {"status": "ok", "nicknames": req.nicknames}

    @app.websocket("/ws/room")
    async def websocket_room(websocket: WebSocket):
        token, subprotocol, rejection = authorize_ws(
            websocket,
            server._token or "",
            allowed_origins(server._host or "127.0.0.1", server._port or 8765),
        )
        if rejection and ws_auth_disabled():
            logger.warning("HEXMIND_WS_AUTH_DISABLED set: accepting WS despite (%s)", rejection[1])
            rejection = None
        if rejection:
            code, reason = rejection
            logger.warning("WS rejected (%s) origin=%r", reason, websocket.headers.get("origin", ""))
            await websocket.close(code=code, reason=reason)
            return
        await server.manager.connect(websocket, subprotocol=subprotocol)
        try:
            # Send initial state sync immediately upon connection
            await websocket.send_json({
                "kind": "init",
                "status": server.get_status_summary(),
                "messages": server.messages,
                "active_tasks": server.active_tasks,
            })
            while True:
                data = await websocket.receive_json()
                action = data.get("action")
                if action == "ping":
                    await websocket.send_json({"kind": "pong", "timestamp": time.time()})
                elif action == "prompt":
                    text = data.get("text", "").strip()
                    if text:
                        if server.is_busy:
                            await websocket.send_json({"kind": "error", "message": "Room is currently busy"})
                        else:
                            audit_val = data.get("audit")
                            approve_val = data.get("approve_plans")
                            task = asyncio.create_task(server.handle_prompt(text, audit_val, approve_val))
                            task.add_done_callback(
                                lambda t: websocket.send_json({"kind": "error", "message": f"Task failed: {t.exception()}"})
                                if t.exception() else None
                            )
                elif action == "approve":
                    if server.orch.pending and not server.is_busy:
                        task = asyncio.create_task(server.approve_pending())
                        task.add_done_callback(
                            lambda t: websocket.send_json({"kind": "error", "message": f"Approval failed: {t.exception()}"})
                            if t.exception() else None
                        )
                    else:
                        await websocket.send_json({"kind": "error", "message": "Cannot approve: no pending plan or busy"})
                elif action == "discard":
                    if server.orch.pending:
                        server.discard_pending()
                    else:
                        await websocket.send_json({"kind": "error", "message": "Cannot discard: no pending plan"})
        except WebSocketDisconnect:
            await server.manager.disconnect(websocket)
        except Exception:
            await server.manager.disconnect(websocket)

    return app


def run_server(
    cwd: str,
    host: str = "127.0.0.1",
    port: int = 8765,
    backend: str = "direct",
    lead: str = "nemotron-ultra",
    without: Optional[List[str]] = None,
    with_: Optional[List[str]] = None,
    audit: bool = False,
    approve_plans: bool = False,
    timeout: int = 1800,
    token: str | None = None,
) -> None:
    import uvicorn

    from . import config

    srv_cfg = config.get_server_defaults()
    if host == "127.0.0.1" and srv_cfg.host != "127.0.0.1":
        host = srv_cfg.host
    if port == 8765 and srv_cfg.port != 8765:
        port = srv_cfg.port
    token = token or os.environ.get("HEXMIND_TOKEN", "") or srv_cfg.token
    # Off loopback, anyone who can reach the port can drive agents that write files, so a token
    # is a precondition rather than a warning that scrolls past.
    if host not in ("127.0.0.1", "localhost", "::1") and not token:
        raise SystemExit(f"hexmind: refusing to serve on {host} without a token. "
                         "Pass --token or set HEXMIND_TOKEN, or use --host 127.0.0.1.")

    server = HexmindServer(
        cwd=cwd,
        backend_name=backend,
        lead=lead,
        without=without,
        with_=with_,
        audit=audit,
        approve_plans=approve_plans,
        timeout=timeout,
    )
    server._port = port
    server._host = host
    server._token = token
    app = create_app(server, token=server._token)
    print(f"🚀 Hexmind server listening on http://{host}:{port} (ws://{host}:{port}/ws/room)")
    print(f"📁 Workspace: {server.cwd}")
    print(f"🤖 Team: {', '.join(server.orch.members)} (Lead: {server.orch.lead})")
    uvicorn.run(app, host=host, port=port, log_level="info")

"""Hexmind Headless Server: FastAPI and WebSocket Daemon.

Provides a full-duplex WebSocket event stream and REST API for remote clients
(native Android app, Web UI, terminal remotes).
"""
from __future__ import annotations

import asyncio
import os
import time
from dataclasses import asdict
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .backends import DirectBackend, HcomBackend, available
from .core import ROSTER, OPT_IN, TEXT_ONLY, Orchestrator, Task
from .auditor import Stats, DOMAINS
from .config import load_nicknames, save_nicknames
from .relay import list_chains, load_chain


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

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
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


class HexmindServer:
    def __init__(
        self,
        cwd: str,
        backend_name: str = "direct",
        lead: str = "opencode-ultra",
        without: Optional[List[str]] = None,
        with_: Optional[List[str]] = None,
        audit: bool = False,
        approve_plans: bool = False,
        stats_path: Optional[str] = None,
    ):
        self.cwd = os.path.abspath(cwd)
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

        self.backend = (HcomBackend if self.backend_name == "hcom" else DirectBackend)(self.cwd)
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

    def _task_to_dict(self, t: Task) -> dict:
        d = asdict(t)
        return d

    def _emit_sync(self, kind: str, data: dict) -> None:
        """Bridge orchestrator synchronous emit callbacks into the async event loop."""
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._emit_async(kind, data))
        except RuntimeError:
            pass

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
        finally:
            self.is_busy = False
            await self.manager.broadcast({"kind": "busy_state", "is_busy": False})

    async def approve_pending(self) -> Optional[str]:
        if not self.orch.pending:
            raise HTTPException(status_code=400, detail="No pending plan to approve")
        req, tasks = self.orch.pending
        self.orch.pending = None
        await self.manager.broadcast({"kind": "pending_cleared"})
        
        self.is_busy = True
        await self.manager.broadcast({"kind": "busy_state", "is_busy": True})
        try:
            return await self.orch.execute(req, tasks)
        finally:
            self.is_busy = False
            await self.manager.broadcast({"kind": "busy_state", "is_busy": False})

    def discard_pending(self) -> bool:
        if not self.orch.pending:
            return False
        self.orch.pending = None
        self.orch.emit("message", {"from": "hexmind", "text": "Plan discarded."})
        return True


def create_app(server: HexmindServer) -> FastAPI:
    app = FastAPI(title="Hexmind API & Realtime Room", version="0.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

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
        await server.manager.connect(websocket)
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
                            asyncio.create_task(server.handle_prompt(text, audit_val, approve_val))
                elif action == "approve":
                    if server.orch.pending and not server.is_busy:
                        asyncio.create_task(server.approve_pending())
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
    host: str = "0.0.0.0",
    port: int = 8765,
    backend: str = "direct",
    lead: str = "opencode-ultra",
    without: Optional[List[str]] = None,
    with_: Optional[List[str]] = None,
    audit: bool = False,
    approve_plans: bool = False,
) -> None:
    import uvicorn

    server = HexmindServer(
        cwd=cwd,
        backend_name=backend,
        lead=lead,
        without=without,
        with_=with_,
        audit=audit,
        approve_plans=approve_plans,
    )
    app = create_app(server)
    print(f"🚀 Hexmind server listening on http://{host}:{port} (ws://{host}:{port}/ws/room)")
    print(f"📁 Workspace: {server.cwd}")
    print(f"🤖 Team: {', '.join(server.orch.members)} (Lead: {server.orch.lead})")
    uvicorn.run(app, host=host, port=port, log_level="info")

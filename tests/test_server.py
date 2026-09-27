"""Tests for hexmind headless FastAPI and WebSocket server."""
import os
import pytest
from starlette.testclient import TestClient

from hexmind.core import Task
from hexmind.server import HexmindServer, create_app


class FakeBackend:
    def __init__(self, cwd="."):
        self.cwd = cwd
        self.calls = []

    async def run(self, agent: str, prompt: str, cwd: str | None = None, schema: dict | None = None) -> str:
        self.calls.append((agent, prompt))
        if "Decide how the team should handle this" in prompt:
            return '{"reply": "Roger that, starting tests.", "tasks": [{"id": "t1", "title": "Run tests", "agent": "codex", "instructions": "run unit tests", "depends_on": []}]}'
        if "Write the final answer" in prompt:
            return "All tasks passed with flying colors."
        return f"Output from {agent}"


@pytest.fixture
def mock_server(tmp_path, monkeypatch):
    stats_file = str(tmp_path / "stats.json")
    config_file = str(tmp_path / "config.toml")
    monkeypatch.setattr("hexmind.config.PATH", config_file)
    monkeypatch.setattr("hexmind.server.save_nicknames", lambda nicks: None)

    server = HexmindServer(
        cwd=str(tmp_path),
        backend_name="direct",
        lead="claude",
        without=[],
        with_=[],
        stats_path=stats_file,
    )
    # Inject fake backend & members
    server.backend = FakeBackend(str(tmp_path))
    server.members = ["claude", "agy", "codex"]
    server.orch.backend = server.backend
    server.orch.members = ["claude", "agy", "codex"]
    return server


@pytest.fixture
def client(mock_server):
    app = create_app(mock_server)
    return TestClient(app)


def test_status_endpoint(client):
    res = client.get("/api/status")
    assert res.status_code == 200
    data = res.json()
    assert "lead" in data
    assert "members" in data
    assert data["backend"] == "direct"
    assert data["is_busy"] is False


def test_chains_endpoint(client):
    res = client.get("/api/chains")
    assert res.status_code == 200
    data = res.json()
    assert "chains" in data


def test_stats_endpoint(client):
    res = client.get("/api/stats")
    assert res.status_code == 200
    data = res.json()
    assert "table" in data
    assert "domains" in data


def test_nicknames_update(client):
    res = client.post("/api/config/nicknames", json={"nicknames": {"agy": "GeminiPro"}})
    assert res.status_code == 200
    assert res.json()["nicknames"]["agy"] == "GeminiPro"


def test_websocket_room_connection_and_ping(client):
    with client.websocket_connect("/ws/room") as ws:
        init_data = ws.receive_json()
        assert init_data["kind"] == "init"
        assert "status" in init_data

        ws.send_json({"action": "ping"})
        pong_data = ws.receive_json()
        assert pong_data["kind"] == "pong"


def test_websocket_prompt_execution(client):
    with client.websocket_connect("/ws/room") as ws:
        init_data = ws.receive_json()
        assert init_data["kind"] == "init"

        # Send a prompt action over websocket
        ws.send_json({"action": "prompt", "text": "Build a widget"})
        
        events = []
        # Receive broadcast events until completion
        for _ in range(10):
            try:
                msg = ws.receive_json()
                events.append(msg)
                if msg.get("kind") == "busy_state" and msg.get("is_busy") is False:
                    break
            except Exception:
                break

        kinds = [e.get("kind") for e in events]
        assert "message" in kinds
        assert any(e.get("kind") == "plan" or e.get("kind") == "task" for e in events)

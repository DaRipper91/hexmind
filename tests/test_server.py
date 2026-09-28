"""Tests for hexmind headless FastAPI and WebSocket server."""
import os
import pytest
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from hexmind.core import Task
from hexmind.server import HexmindServer, create_app, token_to_subprotocol


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
    with client.websocket_connect("/ws/room", headers={"origin": "http://127.0.0.1:8765"}) as ws:
        init_data = ws.receive_json()
        assert init_data["kind"] == "init"
        assert "status" in init_data

        ws.send_json({"action": "ping"})
        pong_data = ws.receive_json()
        assert pong_data["kind"] == "pong"


def test_websocket_prompt_execution(client):
    with client.websocket_connect("/ws/room", headers={"origin": "http://127.0.0.1:8765"}) as ws:
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
# ---- WS auth + API bearer auth (findings T11/T12/T20) ----


def _expect_ws_reject(client, url, code, subprotocols=None, headers=None):
    """Assert the server closes the handshake with the given close code."""
    kwargs = {}
    if subprotocols is not None:
        kwargs["subprotocols"] = subprotocols
    if headers is not None:
        kwargs["headers"] = headers
    with pytest.raises(WebSocketDisconnect) as excinfo:
        with client.websocket_connect(url, **kwargs):
            pass
    assert excinfo.value.code == code


@pytest.fixture
def authed_client(mock_server):
    app = create_app(mock_server, token="sekrit")
    return TestClient(app)


# -- Origin policy: no token configured (server._token == "") --

def test_ws_no_origin_no_token_rejected(client):
    """Missing Origin is rejected with 4003 when no token is configured."""
    _expect_ws_reject(client, "/ws/room", 4003)


def test_ws_cross_origin_no_token_rejected(client):
    """Cross-origin handshake is rejected with 4003."""
    _expect_ws_reject(
        client, "/ws/room", 4003,
        headers={"origin": "http://evil.example"},
    )


def test_ws_local_origin_accepted(client):
    """A browser connecting from the derived local origin is accepted."""
    with client.websocket_connect(
        "/ws/room", headers={"origin": "http://127.0.0.1:8765"}
    ) as ws:
        init = ws.receive_json()
        assert init["kind"] == "init"


# -- Token policy: token configured (create_app(..., token="sekrit")) --

def test_ws_no_origin_no_token_configured_rejected(authed_client):
    """No Origin, token configured, no token offered -> 4001."""
    _expect_ws_reject(authed_client, "/ws/room", 4001)


def test_ws_token_via_subprotocol_no_origin_accepted(authed_client):
    """Missing Origin is allowed when the caller proves the token via subprotocol."""
    sub = token_to_subprotocol("sekrit")
    with authed_client.websocket_connect("/ws/room", subprotocols=[sub]) as ws:
        assert ws.accepted_subprotocol == sub
        init = ws.receive_json()
        assert init["kind"] == "init"


def test_ws_token_via_subprotocol_accepted(authed_client):
    """Valid token offered as a subprotocol is accepted and echoed."""
    sub = token_to_subprotocol("sekrit")
    with authed_client.websocket_connect(
        "/ws/room",
        subprotocols=[sub],
        headers={"origin": "http://127.0.0.1:8765"},
    ) as ws:
        assert ws.accepted_subprotocol == sub
        init = ws.receive_json()
        assert init["kind"] == "init"


def test_ws_token_via_query_accepted(authed_client):
    """Valid token in the query string is accepted."""
    with authed_client.websocket_connect(
        "/ws/room?token=sekrit", headers={"origin": "http://127.0.0.1:8765"}
    ) as ws:
        init = ws.receive_json()
        assert init["kind"] == "init"


def test_ws_token_via_bearer_header_accepted(authed_client):
    """Valid Authorization: Bearer token is accepted."""
    with authed_client.websocket_connect(
        "/ws/room",
        headers={
            "origin": "http://127.0.0.1:8765",
            "Authorization": "Bearer sekrit",
        },
    ) as ws:
        init = ws.receive_json()
        assert init["kind"] == "init"


@pytest.mark.parametrize(
    "url,subprotocols,headers",
    [
        (
            "/ws/room",
            [token_to_subprotocol("wrong")],
            {"origin": "http://127.0.0.1:8765"},
        ),
        (
            "/ws/room?token=wrong",
            None,
            {"origin": "http://127.0.0.1:8765"},
        ),
        (
            "/ws/room",
            None,
            {
                "origin": "http://127.0.0.1:8765",
                "Authorization": "Bearer wrong",
            },
        ),
        (
            "/ws/room",
            None,
            {
                "origin": "http://127.0.0.1:8765",
                "Authorization": "wrong-scheme sekrit",
            },
        ),
    ],
)
def test_ws_wrong_token_rejected(authed_client, url, subprotocols, headers):
    """Wrong or malformed tokens are rejected with 4001 via every channel."""
    _expect_ws_reject(
        authed_client, url, 4001, subprotocols=subprotocols, headers=headers
    )


def test_ws_cross_origin_beats_valid_token(authed_client):
    """Origin policy is enforced before the token: cross-origin + valid token -> 4003."""
    _expect_ws_reject(
        authed_client,
        "/ws/room",
        4003,
        subprotocols=[token_to_subprotocol("sekrit")],
        headers={"origin": "http://evil.example"},
    )


# -- API bearer auth (findings T11/T12) --

def test_api_missing_token_401(authed_client):
    resp = authed_client.get("/api/status")
    assert resp.status_code == 401
    assert resp.json() == {"detail": "Missing or invalid token"}


def test_api_wrong_token_401(authed_client):
    resp = authed_client.get("/api/status", headers={"Authorization": "Bearer wrong"})
    assert resp.status_code == 401


def test_api_valid_token_200(authed_client):
    resp = authed_client.get("/api/status", headers={"Authorization": "Bearer sekrit"})
    assert resp.status_code == 200

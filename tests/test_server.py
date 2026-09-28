"""Tests for hexmind headless FastAPI and WebSocket server."""
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


def test_approve_with_directives_clears_pending_directives(mock_server):
    """Task 2: approve_pending forwards pending_directives and clears them."""
    app = create_app(mock_server)
    from starlette.testclient import TestClient
    client = TestClient(app)
    mock_server.orch.pending_directives = type("Directives", (), {"chains": [], "skills": [], "findings": []})()
    mock_server.orch.pending = ({"text": "test"}, [Task(id="t1", title="test", agent="claude", instructions="test", depends_on=[])])
    result = client.post("/api/approve")
    assert result.status_code == 200
    assert mock_server.orch.pending_directives is None
    assert mock_server.orch.pending is None


def test_discard_clears_pending_directives(mock_server):
    """Task 2: discard_pending clears pending_directives."""
    app = create_app(mock_server)
    from starlette.testclient import TestClient
    client = TestClient(app)
    mock_server.orch.pending_directives = type("Directives", (), {"chains": [], "skills": [], "findings": []})()
    mock_server.orch.pending = ({"text": "test"}, [Task(id="t1", title="test", agent="claude", instructions="test", depends_on=[])])
    result = client.post("/api/discard")
    assert result.status_code == 200
    assert mock_server.orch.pending_directives is None
    assert mock_server.orch.pending is None


def test_approve_while_busy_returns_error(mock_server):
    """Task 2: approve-while-busy returns HTTP 409."""
    app = create_app(mock_server)
    from starlette.testclient import TestClient
    client = TestClient(app)
    mock_server.is_busy = True
    mock_server.orch.pending = ({"text": "test"}, [])
    result = client.post("/api/approve")
    assert result.status_code == 409


def test_approve_no_pending_returns_error(mock_server):
    """Task 2: approve with no pending returns HTTP 400."""
    app = create_app(mock_server)
    from starlette.testclient import TestClient
    client = TestClient(app)
    result = client.post("/api/approve")
    assert result.status_code == 400


def test_discard_no_pending_returns_error(mock_server):
    """Task 2: discard with no pending returns HTTP 400."""
    app = create_app(mock_server)
    from starlette.testclient import TestClient
    client = TestClient(app)
    result = client.post("/api/discard")
    assert result.status_code == 400


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


def test_ws_no_origin_valid_bearer_accepted(authed_client):
    """Missing Origin is allowed for a non-browser client proving the Bearer token."""
    with authed_client.websocket_connect(
        "/ws/room", headers={"Authorization": "Bearer sekrit"}
    ) as ws:
        assert ws.receive_json()["kind"] == "init"


# -- Token transport precedence: subprotocol > ?token= > Authorization --

def test_ws_token_precedence_subprotocol_beats_query(authed_client):
    """A valid subprotocol wins over a wrong ?token=; the subprotocol is echoed."""
    sub = token_to_subprotocol("sekrit")
    with authed_client.websocket_connect(
        "/ws/room?token=wrong",
        subprotocols=[sub],
        headers={"origin": "http://127.0.0.1:8765"},
    ) as ws:
        assert ws.accepted_subprotocol == sub
        assert ws.receive_json()["kind"] == "init"


def test_ws_token_precedence_bad_subprotocol_beats_valid_query(authed_client):
    """A wrong subprotocol is authoritative: no fallback to a valid ?token= -> 4001."""
    _expect_ws_reject(
        authed_client,
        "/ws/room?token=sekrit",
        4001,
        subprotocols=[token_to_subprotocol("wrong")],
        headers={"origin": "http://127.0.0.1:8765"},
    )


def test_ws_token_precedence_query_beats_bearer(authed_client):
    """A valid ?token= wins over a wrong Authorization header."""
    with authed_client.websocket_connect(
        "/ws/room?token=sekrit",
        headers={
            "origin": "http://127.0.0.1:8765",
            "Authorization": "Bearer wrong",
        },
    ) as ws:
        assert ws.receive_json()["kind"] == "init"


def test_ws_token_precedence_bad_query_beats_valid_bearer(authed_client):
    """A wrong ?token= is authoritative: no fallback to a valid Bearer -> 4001."""
    _expect_ws_reject(
        authed_client,
        "/ws/room?token=wrong",
        4001,
        headers={
            "origin": "http://127.0.0.1:8765",
            "Authorization": "Bearer sekrit",
        },
    )


def test_ws_malformed_subprotocol_falls_back_to_query(authed_client):
    """A subprotocol that decodes to nothing is skipped, not treated as a token."""
    with authed_client.websocket_connect(
        "/ws/room?token=sekrit",
        subprotocols=["hexmind.token.!!!!"],
        headers={"origin": "http://127.0.0.1:8765"},
    ) as ws:
        assert ws.accepted_subprotocol is None
        assert ws.receive_json()["kind"] == "init"


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


# -- Feature flag: HEXMIND_WS_AUTH_DISABLED opt-out --

def test_ws_auth_disabled_flag_restores_open_ws(authed_client, monkeypatch):
    """Opt-out flag accepts a cross-origin, tokenless WS (legacy behavior)."""
    _expect_ws_reject(authed_client, "/ws/room", 4003, headers={"origin": "http://evil.example"})
    monkeypatch.setenv("HEXMIND_WS_AUTH_DISABLED", "1")
    with authed_client.websocket_connect("/ws/room", headers={"origin": "http://evil.example"}) as ws:
        assert ws.receive_json()["kind"] == "init"
    # REST bearer auth is unaffected by the WS flag.
    assert authed_client.get("/api/status").status_code == 401


def test_api_bearer_still_401_when_ws_auth_disabled(authed_client, monkeypatch):
    """The WS opt-out flag must not widen REST: the token is still required."""
    monkeypatch.setenv("HEXMIND_WS_AUTH_DISABLED", "1")
    missing = authed_client.get("/api/status")
    assert missing.status_code == 401
    assert missing.json() == {"detail": "Missing or invalid token"}

    wrong = authed_client.get("/api/status", headers={"Authorization": "Bearer wrong"})
    assert wrong.status_code == 401

    valid = authed_client.get("/api/status", headers={"Authorization": "Bearer sekrit"})
    assert valid.status_code == 200

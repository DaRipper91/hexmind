import asyncio
import os
import json
import pytest
import subprocess
from unittest.mock import patch, MagicMock

from hexmind.jules import (
    parse_github_repo,
    get_github_repo,
    get_starting_branch,
    create_session,
    get_session,
    fetch_activities,
    parse_activity,
    run,
)
from hexmind.auditor import (
    parse_verdict,
    audited_run,
    AUDIT_SCHEMA,
    Stats,
)


@pytest.fixture
def anyio_backend():
    return "asyncio"


def test_parse_github_repo():
    assert parse_github_repo("https://github.com/DaRipper91/hexmind.git") == "DaRipper91/hexmind"
    assert parse_github_repo("https://github.com/DaRipper91/hexmind") == "DaRipper91/hexmind"
    assert parse_github_repo("git@github.com:DaRipper91/hexmind.git") == "DaRipper91/hexmind"
    assert parse_github_repo("git@github.com:DaRipper91/hexmind") == "DaRipper91/hexmind"
    assert parse_github_repo("ssh://git@github.com/DaRipper91/hexmind.git") == "DaRipper91/hexmind"
    assert parse_github_repo("git://github.com/DaRipper91/hexmind.git") == "DaRipper91/hexmind"
    assert parse_github_repo("https://gitlab.com/owner/repo.git") is None
    assert parse_github_repo("") is None
    assert parse_github_repo(None) is None


def test_get_github_repo_and_branch(tmp_path):
    repo_dir = tmp_path / "my_repo"
    repo_dir.mkdir()
    subprocess.run(["git", "-C", str(repo_dir), "init", "-b", "main"], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(repo_dir), "remote", "add", "origin", "https://github.com/DaRipper91/test-repo.git"],
        check=True,
        capture_output=True,
    )

    repo = get_github_repo(str(repo_dir))
    assert repo == "DaRipper91/test-repo"

    # Non-git dir raises RuntimeError
    non_git = tmp_path / "non_git"
    non_git.mkdir()
    with pytest.raises(RuntimeError, match="not a GitHub repository"):
        get_github_repo(str(non_git))


def test_parse_activity_kinds():
    # planGenerated
    a1 = {
        "createTime": "2026-09-26T10:00:00Z",
        "originator": "agent",
        "planGenerated": {
            "plan": {
                "steps": [{"title": "Step 1"}, {"title": "Step 2"}]
            }
        }
    }
    r1 = parse_activity(a1)
    assert r1["kind"] == "plan"
    assert "1. Step 1\n2. Step 2" in r1["content"]

    # agentMessaged
    a2 = {
        "createTime": "2026-09-26T10:01:00Z",
        "originator": "agent",
        "agentMessaged": {"agentMessage": "Task completed successfully"}
    }
    r2 = parse_activity(a2)
    assert r2["kind"] == "message"
    assert r2["content"] == "Task completed successfully"

    # progressUpdated
    a3 = {
        "createTime": "2026-09-26T10:00:30Z",
        "progressUpdated": {"title": "Building", "description": "Compiling assets"}
    }
    r3 = parse_activity(a3)
    assert r3["kind"] == "progress"
    assert "Building\nCompiling assets" in r3["content"]


@pytest.mark.anyio
async def test_jules_run_success(tmp_path, monkeypatch):
    repo_dir = tmp_path / "mock_repo"
    repo_dir.mkdir()
    subprocess.run(["git", "-C", str(repo_dir), "init", "-b", "main"], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(repo_dir), "remote", "add", "origin", "git@github.com:DaRipper91/hexmind.git"],
        check=True,
        capture_output=True,
    )

    monkeypatch.setenv("JULES_API_KEY", "test-key-12345")

    # Mock HTTP _request
    def mock_request(method, path, api_key, params=None, body=None, timeout=30):
        if method == "POST" and path == "sessions":
            assert body["automationMode"] == "AUTO_CREATE_PR"
            assert body["sourceContext"]["source"] == "sources/github/DaRipper91/hexmind"
            return {"id": "session-999", "name": "sessions/session-999"}, None
        elif method == "GET" and path == "sessions/session-999":
            return {
                "id": "session-999",
                "state": "COMPLETED",
                "outputs": [{"pullRequest": {"url": "https://github.com/DaRipper91/hexmind/pull/42"}}],
            }, None
        elif method == "GET" and path == "sessions/session-999/activities":
            return {
                "activities": [
                    {
                        "createTime": "2026-09-26T10:05:00Z",
                        "originator": "agent",
                        "agentMessaged": {"agentMessage": "Implemented requested changes and created PR."},
                    }
                ]
            }, None
        return {}, None

    with patch("hexmind.jules._request", side_effect=mock_request):
        out = await run("Add new feature", cwd=str(repo_dir), timeout=60)
        assert "Implemented requested changes and created PR." in out
        assert "Pull Request: https://github.com/DaRipper91/hexmind/pull/42" in out
        assert "Local files were not modified directly" in out


@pytest.mark.anyio
async def test_jules_run_missing_api_key(tmp_path, monkeypatch):
    repo_dir = tmp_path / "mock_repo"
    repo_dir.mkdir()
    subprocess.run(["git", "-C", str(repo_dir), "init", "-b", "main"], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(repo_dir), "remote", "add", "origin", "https://github.com/DaRipper91/hexmind.git"],
        check=True,
        capture_output=True,
    )

    monkeypatch.delenv("JULES_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="JULES_API_KEY environment variable is not set"):
        await run("Prompt", cwd=str(repo_dir))


@pytest.mark.anyio
async def test_jules_run_session_failure(tmp_path, monkeypatch):
    repo_dir = tmp_path / "mock_repo"
    repo_dir.mkdir()
    subprocess.run(["git", "-C", str(repo_dir), "init", "-b", "main"], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(repo_dir), "remote", "add", "origin", "https://github.com/DaRipper91/hexmind.git"],
        check=True,
        capture_output=True,
    )

    monkeypatch.setenv("JULES_API_KEY", "test-key")

    # Test error as dict
    def mock_request_dict(method, path, api_key, params=None, body=None, timeout=30):
        if method == "POST" and path == "sessions":
            return {"id": "session-fail-1"}, None
        elif method == "GET" and path == "sessions/session-fail-1":
            return {
                "id": "session-fail-1",
                "state": "FAILED",
                "error": {"message": "Repository permission denied"},
            }, None
        return {}, None

    with patch("hexmind.jules._request", side_effect=mock_request_dict):
        with pytest.raises(RuntimeError, match="Jules session session-fail-1 failed: Repository permission denied"):
            await run("Prompt", cwd=str(repo_dir))

    # Test error as string
    def mock_request_str(method, path, api_key, params=None, body=None, timeout=30):
        if method == "POST" and path == "sessions":
            return {"id": "session-fail-2"}, None
        elif method == "GET" and path == "sessions/session-fail-2":
            return {
                "id": "session-fail-2",
                "state": "FAILED",
                "error": "Direct string error from API",
            }, None
        return {}, None

    with patch("hexmind.jules._request", side_effect=mock_request_str):
        with pytest.raises(RuntimeError, match="Jules session session-fail-2 failed: Direct string error from API"):
            await run("Prompt", cwd=str(repo_dir))


@pytest.mark.parametrize("state", [
    "AWAITING_USER_FEEDBACK",   # the value the live API actually sends
    "AWAITING",                # the short form
    "AWAITING_USER_INPUT",
    "PAUSED",
    "NEEDS_INPUT",
])
@pytest.mark.anyio
async def test_every_awaiting_variant_is_recognised_and_stops(state, tmp_path, monkeypatch):
    """The audit called the old `"AWAITING" in state` substring test fragile and it was, but the
    first fix — an exact `== "AWAITING"` — was worse: it no longer matched the real API's
    `AWAITING_USER_FEEDBACK`, so a session blocked on a human was polled silently to the timeout
    and reported as a generic failure. This test is the reason that regression cannot come back:
    every spelling the enum has plausibly used must terminate the poll immediately, not spin.
    """
    repo_dir = tmp_path / "mock_repo"
    repo_dir.mkdir()
    subprocess.run(["git", "-C", str(repo_dir), "init", "-b", "main"], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(repo_dir), "remote", "add", "origin", "https://github.com/DaRipper91/hexmind.git"],
        check=True, capture_output=True,
    )
    monkeypatch.setenv("JULES_API_KEY", "test-key")

    def mock_request(method, path, api_key, params=None, body=None, timeout=30):
        if method == "POST" and path == "sessions":
            return {"id": "s1"}, None
        if method == "GET" and path == "sessions/s1":
            return {"id": "s1", "state": state}, None
        return {}, None

    with patch("hexmind.jules._request", side_effect=mock_request):
        with pytest.raises(RuntimeError, match="is waiting for your input"):
            await asyncio.wait_for(run("Prompt", cwd=str(repo_dir)), timeout=20)


@pytest.mark.anyio
async def test_an_unrecognised_state_is_logged_but_still_polled(tmp_path, monkeypatch, caplog):
    """An unknown state must not be mistaken for a blocked session (which would fail the turn) nor
    silently swallowed (which is how a renamed enum turns into a 1800s timeout with no clue why).
    It keeps polling and says so."""
    repo_dir = tmp_path / "mock_repo"
    repo_dir.mkdir()
    subprocess.run(["git", "-C", str(repo_dir), "init", "-b", "main"], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(repo_dir), "remote", "add", "origin", "https://github.com/DaRipper91/hexmind.git"],
        check=True, capture_output=True,
    )
    monkeypatch.setenv("JULES_API_KEY", "test-key")
    calls = {"n": 0}

    def mock_request(method, path, api_key, params=None, body=None, timeout=30):
        if method == "POST" and path == "sessions":
            return {"id": "s2"}, None
        if method == "GET" and path == "sessions/s2":
            calls["n"] += 1
            # an unknown state, then COMPLETED, so the run ends promptly
            return ({"id": "s2", "state": "SOME_NEW_STATE"} if calls["n"] < 2
                    else {"id": "s2", "state": "COMPLETED"}), None
        return {}, None

    with caplog.at_level("WARNING", logger="hexmind.jules"):
        with patch("hexmind.jules._request", side_effect=mock_request):
            out = await asyncio.wait_for(run("Prompt", cwd=str(repo_dir)), timeout=30)

    assert "SOME_NEW_STATE" in caplog.text, "an unknown state must be logged, not swallowed"
    assert "completed" in out.lower()


@pytest.mark.anyio
async def test_jules_run_awaiting_user_input(tmp_path, monkeypatch):
    repo_dir = tmp_path / "mock_repo"
    repo_dir.mkdir()
    subprocess.run(["git", "-C", str(repo_dir), "init", "-b", "main"], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(repo_dir), "remote", "add", "origin", "https://github.com/DaRipper91/hexmind.git"],
        check=True,
        capture_output=True,
    )

    monkeypatch.setenv("JULES_API_KEY", "test-key")

    def mock_request(method, path, api_key, params=None, body=None, timeout=30):
        if method == "POST" and path == "sessions":
            return {"id": "session-await-123"}, None
        elif method == "GET" and path == "sessions/session-await-123":
            return {
                "id": "session-await-123",
                "state": "AWAITING_USER_FEEDBACK",
            }, None
        return {}, None

    with patch("hexmind.jules._request", side_effect=mock_request):
        with pytest.raises(
            RuntimeError,
            match="jules session session-await-123 is waiting for your input: https://jules.google.com/session/session-await-123",
        ):
            await run("Prompt", cwd=str(repo_dir))


@pytest.mark.anyio
async def test_jules_run_consecutive_poll_errors(tmp_path, monkeypatch):
    repo_dir = tmp_path / "mock_repo"
    repo_dir.mkdir()
    subprocess.run(["git", "-C", str(repo_dir), "init", "-b", "main"], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(repo_dir), "remote", "add", "origin", "https://github.com/DaRipper91/hexmind.git"],
        check=True,
        capture_output=True,
    )

    monkeypatch.setenv("JULES_API_KEY", "test-key")

    def mock_request(method, path, api_key, params=None, body=None, timeout=30):
        if method == "POST" and path == "sessions":
            return {"id": "session-err-1"}, None
        elif method == "GET" and path == "sessions/session-err-1":
            return None, "HTTP 500: internal server error"
        return {}, None

    with patch("hexmind.jules._request", side_effect=mock_request), \
         patch("asyncio.sleep", return_value=None):
        with pytest.raises(RuntimeError, match="failed after 20 consecutive poll errors"):
            await run("Prompt", cwd=str(repo_dir))


def test_get_starting_branch_fallbacks(tmp_path):
    repo_dir = tmp_path / "fallback_repo"
    repo_dir.mkdir()
    subprocess.run(["git", "-C", str(repo_dir), "init", "-b", "feature-x"], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(repo_dir), "remote", "add", "origin", "https://github.com/DaRipper91/hexmind.git"],
        check=True,
        capture_output=True,
    )

    # When branch is unpushed, falls back to ls-remote --symref or main
    branch = get_starting_branch(str(repo_dir))
    assert isinstance(branch, str)
    assert len(branch) > 0


def test_auditor_json_verdict_parsing():
    json_pass = '{"verdict": "PASS", "issues": []}'
    p, issues = parse_verdict(json_pass)
    assert p is True
    assert issues == ""

    json_fail = '```json\n{\n  "verdict": "FAIL",\n  "issues": ["missing input validation", "unhandled exception"]\n}\n```'
    p, issues = parse_verdict(json_fail)
    assert p is False
    assert "- missing input validation" in issues
    assert "- unhandled exception" in issues

    # Verify fallback to text format still works
    text_pass = "VERDICT: PASS\nAll requirements met."
    p, issues = parse_verdict(text_pass)
    assert p is True
    assert issues == "All requirements met."

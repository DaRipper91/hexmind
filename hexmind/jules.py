"""hexmind/jules.py — Jules autonomous agent member integration.

Provides:
- parse_github_repo: extracts OWNER/REPO from origin git URL
- get_github_repo: derives GitHub repo from git remote origin in cwd
- get_starting_branch: detects pushed branch or default branch
- run: async runner creating session, polling activities, and returning output + PR URL.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess
import time
import urllib.error
import urllib.request
from typing import Any

API_BASE = "https://jules.googleapis.com/v1alpha"


def parse_github_repo(url: str | None) -> str | None:
    """Extract 'OWNER/REPO' from GitHub git or HTTPS/SSH URLs."""
    if not url:
        return None
    url = url.strip()
    m = re.search(r"github\.com[:/]([a-zA-Z0-9_.-]+)/([a-zA-Z0-9_.-]+?)(?:\.git)?/?$", url)
    if m:
        owner, repo = m.group(1), m.group(2)
        if repo.endswith(".git"):
            repo = repo[:-4]
        return f"{owner}/{repo}"
    return None


def get_github_repo(cwd: str) -> str:
    """Derive GitHub 'OWNER/REPO' from 'git -C cwd remote get-url origin'."""
    try:
        proc = subprocess.run(
            ["git", "-C", cwd, "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            err = proc.stderr.strip() or f"exit code {proc.returncode}"
            raise RuntimeError(
                f"cwd '{cwd}' is not a GitHub repository (git remote get-url origin failed: {err})"
            )
        url = proc.stdout.strip()
    except OSError as e:
        raise RuntimeError(f"failed to execute git in '{cwd}': {e}") from e

    repo = parse_github_repo(url)
    if not repo:
        raise RuntimeError(
            f"cwd '{cwd}' origin URL '{url}' is not a recognized GitHub repository (expected github.com/OWNER/REPO)"
        )
    return repo


def get_starting_branch(cwd: str) -> str:
    """Detect current branch if pushed to origin, otherwise origin default branch (fallback 'main')."""
    # 1. Check if current branch is pushed to origin
    try:
        proc = subprocess.run(
            ["git", "-C", cwd, "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode == 0:
            current = proc.stdout.strip()
            if current and current != "HEAD":
                check_pushed = subprocess.run(
                    ["git", "-C", cwd, "ls-remote", "--heads", "origin", current],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if check_pushed.returncode == 0 and current in check_pushed.stdout:
                    return current

                check_local = subprocess.run(
                    ["git", "-C", cwd, "rev-parse", "--verify", f"origin/{current}"],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if check_local.returncode == 0:
                    return current
    except Exception:
        pass

    # 2. Fall back to origin default branch via ls-remote --symref origin HEAD
    try:
        proc = subprocess.run(
            ["git", "-C", cwd, "ls-remote", "--symref", "origin", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode == 0:
            m = re.search(r"ref:\s*refs/heads/([^\s]+)\s+HEAD", proc.stdout)
            if m:
                return m.group(1).strip()
    except Exception:
        pass

    # 3. Last resort
    return "main"


def _request(
    method: str,
    path: str,
    api_key: str,
    params: dict[str, Any] | None = None,
    body: dict[str, Any] | None = None,
    timeout: int = 30,
) -> tuple[dict[str, Any] | None, str | None]:
    url = f"{API_BASE}/{path.lstrip('/')}"
    if params:
        query = "&".join(f"{k}={v}" for k, v in params.items())
        url = f"{url}?{query}"
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"X-Goog-Api-Key": api_key}
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            return (json.loads(raw.decode("utf-8")) if raw else {}), None
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")[:300]
        return None, f"HTTP {e.code}: {detail}"
    except urllib.error.URLError as e:
        return None, str(e.reason)
    except TimeoutError:
        return None, "timed out"


def create_session(
    api_key: str,
    repo: str,
    prompt: str,
    automation_mode: str = "AUTO_CREATE_PR",
    require_plan_approval: bool = False,
    starting_branch: str | None = None,
) -> tuple[dict[str, Any] | None, str | None]:
    branch = starting_branch or "main"
    body: dict[str, Any] = {
        "prompt": prompt,
        "sourceContext": {
            "source": f"sources/github/{repo}",
            "githubRepoContext": {"startingBranch": branch},
        },
    }
    if automation_mode:
        body["automationMode"] = automation_mode
    if require_plan_approval:
        body["requirePlanApproval"] = True
    return _request("POST", "sessions", api_key, body=body)


def get_session(api_key: str, session_id: str) -> tuple[dict[str, Any] | None, str | None]:
    return _request("GET", f"sessions/{session_id}", api_key)


def send_message(api_key: str, session_id: str, prompt: str) -> tuple[dict[str, Any] | None, str | None]:
    return _request("POST", f"sessions/{session_id}:sendMessage", api_key, body={"prompt": prompt})


def fetch_activities(api_key: str, session_id: str, page_size: int = 50) -> list[dict[str, Any]]:
    """Fetch all activities for a session with pagination."""
    activities = []
    page_token = None
    while True:
        params: dict[str, Any] = {"pageSize": page_size}
        if page_token:
            params["pageToken"] = page_token
        data, err = _request("GET", f"sessions/{session_id}/activities", api_key, params=params)
        if err or not data:
            break
        activities.extend(data.get("activities", []))
        page_token = data.get("nextPageToken")
        if not page_token:
            break
    return activities


def parse_activity(activity: dict[str, Any]) -> dict[str, Any]:
    """Normalize a raw Jules activity into structured record: {timestamp, speaker, kind, content}."""
    created = activity.get("createTime", "")
    originator = activity.get("originator", "")
    known_keys = {"name", "createTime", "id", "originator", "artifacts"}
    payload_keys = [k for k in activity.keys() if k not in known_keys]

    if not payload_keys:
        return {
            "timestamp": created,
            "speaker": "system",
            "kind": "unknown",
            "content": "(empty activity)",
        }

    kind = payload_keys[0]
    payload = activity[kind]
    speaker = "you" if originator == "user" else "jules"

    if kind == "planGenerated":
        plan = payload.get("plan", {}) if isinstance(payload, dict) else {}
        steps = plan.get("steps", []) if isinstance(plan, dict) else []
        lines = [f"{i + 1}. {step.get('title', '')}" for i, step in enumerate(steps)]
        return {
            "timestamp": created,
            "speaker": speaker,
            "kind": "plan",
            "content": "\n".join(lines) or json.dumps(payload),
        }

    if kind == "planApproved":
        return {
            "timestamp": created,
            "speaker": speaker,
            "kind": "plan_approved",
            "content": "Plan approved.",
        }

    if kind == "progressUpdated":
        title = payload.get("title", "") if isinstance(payload, dict) else ""
        description = payload.get("description", "") if isinstance(payload, dict) else ""
        content = f"{title}\n{description}".strip()
        return {
            "timestamp": created,
            "speaker": speaker,
            "kind": "progress",
            "content": content or "(no details)",
        }

    if kind == "agentMessaged" and isinstance(payload, dict):
        return {
            "timestamp": created,
            "speaker": "jules",
            "kind": "message",
            "content": payload.get("agentMessage", ""),
        }

    if kind == "userMessaged":
        content = ""
        if isinstance(payload, dict):
            content = payload.get("userMessage") or payload.get("prompt", "")
        else:
            content = str(payload)
        return {
            "timestamp": created,
            "speaker": "you",
            "kind": "message",
            "content": content,
        }

    if "awaiting" in kind.lower():
        return {
            "timestamp": created,
            "speaker": speaker,
            "kind": "awaiting_input",
            "content": json.dumps(payload) if isinstance(payload, (dict, list)) else str(payload),
        }

    if kind in ("sessionCompleted", "outputsReady"):
        content = "Session completed." if not payload else (
            json.dumps(payload) if isinstance(payload, (dict, list)) else str(payload)
        )
        return {
            "timestamp": created,
            "speaker": "system",
            "kind": "completed",
            "content": content,
        }

    content = json.dumps(payload) if isinstance(payload, (dict, list)) else str(payload)
    return {"timestamp": created, "speaker": speaker, "kind": kind, "content": content}


async def run(prompt: str, cwd: str | None = None, timeout: int = 14400) -> str:
    """Execute a task via Jules on the remote GitHub repository corresponding to cwd.

    Creates a session with AUTO_CREATE_PR, polls activities until completed or failed,
    and returns the final message with PR URL.
    """
    target_cwd = os.path.abspath(cwd or os.getcwd())
    repo = get_github_repo(target_cwd)
    starting_branch = get_starting_branch(target_cwd)

    api_key = os.environ.get("JULES_API_KEY")
    if not api_key:
        raise RuntimeError("JULES_API_KEY environment variable is not set")

    create_res, err = await asyncio.to_thread(
        create_session,
        api_key=api_key,
        repo=repo,
        prompt=prompt,
        automation_mode="AUTO_CREATE_PR",
        starting_branch=starting_branch,
    )
    if err or not create_res:
        raise RuntimeError(f"failed to create Jules session for {repo}: {err}")

    session_id = create_res.get("id") or create_res.get("name", "").split("/")[-1]
    if not session_id:
        raise RuntimeError(f"Jules API did not return a session id: {create_res}")

    start_time = time.monotonic()
    poll_interval = 2.0
    session_data: dict[str, Any] = {}
    consecutive_poll_errors = 0
    last_poll_error = ""

    while True:
        elapsed = time.monotonic() - start_time
        if elapsed > timeout:
            raise RuntimeError(f"Jules session {session_id} timed out after {timeout}s")

        res, err = await asyncio.to_thread(get_session, api_key, session_id)
        if err:
            consecutive_poll_errors += 1
            last_poll_error = err
            if consecutive_poll_errors >= 20:
                raise RuntimeError(
                    f"Jules session {session_id} failed after 20 consecutive poll errors: {last_poll_error}"
                )
            await asyncio.sleep(poll_interval)
            continue

        consecutive_poll_errors = 0
        session_data = res or {}
        state = session_data.get("state", "").upper()

        if state == "COMPLETED":
            break
        elif state == "FAILED":
            err_obj = session_data.get("error")
            if isinstance(err_obj, dict):
                err_msg = err_obj.get("message") or str(err_obj)
            elif err_obj:
                err_msg = str(err_obj)
            else:
                err_msg = "unknown failure"
            raise RuntimeError(f"Jules session {session_id} failed: {err_msg}")
        elif "AWAITING" in state or "PAUSED" in state:
            raise RuntimeError(
                f"jules session {session_id} is waiting for your input: https://jules.google.com/session/{session_id}"
            )

        await asyncio.sleep(poll_interval)
        poll_interval = min(poll_interval * 1.5, 15.0)

    activities = await asyncio.to_thread(fetch_activities, api_key, session_id)
    records = [parse_activity(a) for a in activities]

    last_message = ""
    for r in reversed(records):
        if r["kind"] == "message" and r["speaker"] == "jules" and r["content"]:
            last_message = r["content"]
            break
        elif r["kind"] == "progress" and r["content"] and not last_message:
            last_message = r["content"]

    pr_url = None
    for output in session_data.get("outputs", []) or []:
        pr = output.get("pullRequest")
        if pr and pr.get("url"):
            pr_url = pr["url"]
            break

    parts = []
    if last_message:
        parts.append(last_message)
    else:
        parts.append(f"Jules session {session_id} completed successfully.")

    if pr_url:
        parts.append(f"Pull Request: {pr_url}")

    parts.append(
        f"Note: Jules executes on remote GitHub repository '{repo}' (branch: '{starting_branch or 'default'}'). "
        f"Local files were not modified directly."
    )

    return "\n\n".join(parts)

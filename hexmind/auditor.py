"""Hexmind Runner-Up Auditor and Evidence-Based Domain Stats.

Provides:
- DOMAINS: standardized evaluation domain taxonomy
- Stats: persistent Laplace-smoothed pass/fail tracker per agent/domain
- pick_auditor: selects best-ranked peer as auditor
- parse_verdict: extracts PASS/FAIL verdicts and issue descriptions
- audited_run: orchestrates the primary execution, auditor verification, and bounded revision loop
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from typing import Any, Callable

from .core import clip

logger = logging.getLogger(__name__)

DOMAINS: list[str] = [
    "architecture",
    "implementation",
    "refactor",
    "tests",
    "debugging",
    "research",
    "docs",
    "review",
    "shell",
    "ui",
    "general",
]

AUDIT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "verdict": {"enum": ["PASS", "FAIL"]},
        "issues": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["verdict", "issues"],
    "additionalProperties": False,
}

AUDIT_PROMPT = """You are {auditor}, auditing the work done by {agent} on task {id}: {title}.
Domain: {domain}
Task instructions:
{instructions}

Work report from {agent}:
{output}

Instructions for your audit:
1. Check the actual files and filesystem state in your current directory ({cwd}) to verify if the task was completed properly and accurately. Do not rely solely on {agent}'s report.
2. Check for bugs, syntax errors, regressions, security flaws, or incomplete work.
3. Your reply MUST start with exactly one of:
   VERDICT: PASS
   VERDICT: FAIL
4. If FAIL, follow the verdict with a clear bulleted list of the specific issues found and what must be corrected. If PASS, you may provide a brief summary."""

REVISE_PROMPT = """You are {agent}. Your work on task {id} ({title}) was audited by {auditor}, who rejected it with the following issues:

{issues}

Original prompt:
{prompt}

Your previous output:
{output}

Please inspect the directory, fix all identified issues, and provide your revised output."""


class Stats:
    def __init__(self, path: str):
        self.path = path
        self.data: dict[str, dict[str, dict[str, int]]] = {}
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    self.data = json.load(f)
            except Exception:
                # Corrupt stats file: back it up and start fresh rather than wiping
                # history silently (a corrupt stats.json drives auditor picks and /ranks).
                backup = f"{path}.corrupt.{int(time.time())}"
                try:
                    os.replace(path, backup)
                    logger.warning("Stats file %s was corrupt; backed up to %s", path, backup)
                except OSError:
                    logger.warning("Could not back up corrupt stats file %s", path)
                self.data = {}

    def _save(self) -> None:
        parent = os.path.dirname(os.path.abspath(self.path))
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2)

    def record(self, agent: str, domain: str, passed: bool) -> None:
        if agent not in self.data:
            self.data[agent] = {}
        if domain not in self.data[agent]:
            self.data[agent][domain] = {"pass": 0, "fail": 0}
        key = "pass" if passed else "fail"
        self.data[agent][domain][key] = self.data[agent][domain].get(key, 0) + 1
        self._save()

    def score(self, agent: str, domain: str) -> float:
        stats = self.data.get(agent, {}).get(domain, {})
        p = stats.get("pass", 0)
        f = stats.get("fail", 0)
        return (p + 1) / (p + f + 2)

    def ranked(self, members: list[str], domain: str) -> list[str]:
        return sorted(members, key=lambda m: self.score(m, domain), reverse=True)

    def table(self, members: list[str]) -> str:
        active_domains = [
            d
            for d in DOMAINS
            if any(
                self.data.get(m, {}).get(d, {}).get("pass", 0)
                + self.data.get(m, {}).get(d, {}).get("fail", 0)
                > 0
                for m in members
            )
        ]
        if not active_domains:
            for m in members:
                for d in self.data.get(m, {}):
                    if (
                        d not in active_domains
                        and self.data[m][d].get("pass", 0)
                        + self.data[m][d].get("fail", 0)
                        > 0
                    ):
                        active_domains.append(d)

        if not active_domains:
            return "No audit stats recorded yet."

        headers = ["Agent"] + active_domains
        header_row = "| " + " | ".join(headers) + " |"
        sep_row = "| " + " | ".join(["---"] * len(headers)) + " |"
        rows = [header_row, sep_row]
        for m in members:
            cells = [m]
            for d in active_domains:
                entry = self.data.get(m, {}).get(d, {})
                p = entry.get("pass", 0)
                f = entry.get("fail", 0)
                cells.append(f"{p}/{p+f}" if (p + f) > 0 else "-")
            rows.append("| " + " | ".join(cells) + " |")
        return "\n".join(rows)


def pick_auditor(primary: str, members: list[str], domain: str, stats: Stats) -> str | None:
    candidates = [m for m in members if m != primary]
    if not candidates:
        return None
    return stats.ranked(candidates, domain)[0]


def parse_verdict(text: str) -> tuple[bool, str]:
    # Try parsing JSON first (handling optional markdown code blocks)
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()

    try:
        data = json.loads(cleaned)
        if isinstance(data, dict) and "verdict" in data:
            passed = str(data.get("verdict", "")).upper() == "PASS"
            issues_val = data.get("issues", [])
            if isinstance(issues_val, list):
                issues_str = "\n".join(f"- {issue}" for issue in issues_val if issue)
            else:
                issues_str = str(issues_val).strip()
            return passed, issues_str
    except Exception:
        pass

    m = re.search(r"VERDICT:\s*(PASS|FAIL)", text, re.IGNORECASE)
    if not m:
        return False, text.strip()
    passed = m.group(1).upper() == "PASS"
    issues = text[m.end():].strip()
    return passed, issues


Emit = Callable[[str, dict], None]


async def audited_run(
    backend,
    task,
    prompt: str,
    members: list[str],
    stats: Stats,
    emit: Emit | None = None,
    max_rounds: int = 2,
) -> str:
    emit_fn = emit or (lambda kind, data: None)
    cwd = getattr(task, "cwd", None)
    out = await backend.run(task.agent, prompt, cwd=cwd)
    domain = getattr(task, "domain", None) or "general"
    auditor = pick_auditor(task.agent, members, domain, stats)
    if auditor is None:
        return out

    task.auditor = auditor
    last_issues = ""

    for round_idx in range(max_rounds + 1):
        task.status = "auditing"
        emit_fn("task", {"task": task})

        audit_prompt = AUDIT_PROMPT.format(
            auditor=auditor,
            agent=task.agent,
            id=task.id,
            title=task.title,
            domain=domain,
            instructions=task.instructions,
            output=out,
            cwd=cwd or "current directory",
        )
        try:
            audit_out = await backend.run(auditor, audit_prompt, cwd=cwd, schema=AUDIT_SCHEMA)
        except TypeError:
            audit_out = await backend.run(auditor, audit_prompt, cwd=cwd)

        passed, issues = parse_verdict(audit_out)
        last_issues = issues
        history = getattr(task, "audit_history", None)
        if isinstance(history, list):
            history.append({
                "round": round_idx + 1,
                "auditor": auditor,
                "verdict": "PASS" if passed else "FAIL",
                "issues": issues,
            })

        # Record stats only for the first verdict (first-attempt quality)
        if round_idx == 0:
            stats.record(task.agent, domain, passed)

        if passed:
            task.audit = "pass" if round_idx == 0 else "fixed"
            return out

        if round_idx < max_rounds:
            task.status = "revising"
            emit_fn("task", {"task": task})
            revise_prompt = REVISE_PROMPT.format(
                agent=task.agent,
                id=task.id,
                title=task.title,
                auditor=auditor,
                issues=issues,
                prompt=prompt,
                output=out,
            )
            out = await backend.run(task.agent, revise_prompt, cwd=cwd)

    # Unresolved after max_rounds revisions
    task.audit = "disputed"
    gate = getattr(task, "gate", False)
    clipped_issues = clip(last_issues, 2000)
    clipped_out = clip(out, 3000)
    if gate:
        raise RuntimeError(
            f"audit failed after {max_rounds} revisions; auditor {auditor} says: {clipped_issues}; last output: {clipped_out}"
        )

    escalation_text = (
        f"ESCALATION: Task {task.id} ({task.title}) disputed after {max_rounds} revisions between {task.agent} and {auditor}.\n\n"
        f"Auditor ({auditor}) issues:\n{clipped_issues}\n\n"
        f"Last output from {task.agent}:\n{clipped_out}"
    )
    emit_fn("message", {"from": "hexmind", "text": escalation_text})
    return out

import asyncio
from dataclasses import dataclass, field

import pytest

from hexmind.auditor import (
    Stats,
    audited_run,
    parse_verdict,
    pick_auditor,
)


@dataclass
class DummyTask:
    id: str = "t1"
    title: str = "Implement feature"
    agent: str = "claude"
    instructions: str = "Write a function"
    domain: str = "implementation"
    cwd: str | None = None
    gate: bool = False
    status: str = "pending"
    audit: str | None = None
    auditor: str | None = None
    output: str = ""
    audit_history: list[dict[str, object]] = field(default_factory=list)


class FakeBackend:
    def __init__(self, script: list[tuple[str, str]] | None = None):
        self.script = list(script or [])
        self.calls = []

    async def run(self, agent: str, prompt: str, cwd: str | None = None) -> str:
        self.calls.append((agent, prompt, cwd))
        if self.script:
            expected_agent, response = self.script.pop(0)
            assert agent == expected_agent, f"Expected agent {expected_agent}, got {agent}"
            return response
        return "DEFAULT_OUT"


def test_stats_laplace_and_persistence(tmp_path):
    p = str(tmp_path / "stats.json")
    stats = Stats(p)
    assert stats.score("claude", "tests") == 1 / 2  # (0+1)/(0+0+2)

    stats.record("claude", "tests", True)
    assert stats.score("claude", "tests") == 2 / 3  # (1+1)/(1+0+2)

    stats.record("claude", "tests", False)
    assert stats.score("claude", "tests") == 2 / 4  # (1+1)/(1+1+2)

    # Reload from disk
    stats2 = Stats(p)
    assert stats2.score("claude", "tests") == 0.5


def test_ranking_and_pick_auditor(tmp_path):
    stats = Stats(str(tmp_path / "stats.json"))
    stats.record("agy", "refactor", True)
    stats.record("agy", "refactor", True)
    stats.record("claude", "refactor", False)
    # agy = 3/4 = 0.75, codex = 1/2 = 0.5, claude = 1/3 = 0.333

    ranked = stats.ranked(["claude", "agy", "codex"], "refactor")
    assert ranked == ["agy", "codex", "claude"]

    auditor = pick_auditor("agy", ["claude", "agy", "codex"], "refactor", stats)
    assert auditor == "codex"

    # Solo returns None
    assert pick_auditor("agy", ["agy"], "refactor", stats) is None


def test_parse_verdict():
    p1, issues1 = parse_verdict("VERDICT: PASS\nAll good.")
    assert p1 is True
    assert issues1 == "All good."

    p2, issues2 = parse_verdict("Some reasoning...\nVERDICT: FAIL\n- missing edge case\n- syntax error")
    assert p2 is False
    assert "- missing edge case" in issues2

    p3, issues3 = parse_verdict("Unformatted prose with no verdict token")
    assert p3 is False
    assert "Unformatted prose" in issues3


def test_audited_run_first_round_pass(tmp_path):
    asyncio.run(_test_audited_run_first_round_pass(tmp_path))


async def _test_audited_run_first_round_pass(tmp_path):
    stats = Stats(str(tmp_path / "stats.json"))
    task = DummyTask(agent="claude")
    backend = FakeBackend([
        ("claude", "def hello(): pass"),
        ("agy", "VERDICT: PASS\nClean code."),
    ])
    events = []
    out = await audited_run(
        backend,
        task,
        "Write a function",
        ["claude", "agy"],
        stats,
        emit=lambda k, d: events.append((k, d)),
    )

    assert out == "def hello(): pass"
    assert task.audit == "pass"
    assert task.auditor == "agy"
    assert stats.score("claude", "implementation") == 2 / 3  # (1+1)/(1+2)


def test_audited_run_revision_and_fix(tmp_path):
    asyncio.run(_test_audited_run_revision_and_fix(tmp_path))


async def _test_audited_run_revision_and_fix(tmp_path):
    stats = Stats(str(tmp_path / "stats.json"))
    task = DummyTask(agent="claude")
    backend = FakeBackend([
        ("claude", "def hello(): return 1"),
        ("agy", "VERDICT: FAIL\n- should return 2"),
        ("claude", "def hello(): return 2"),
        ("agy", "VERDICT: PASS\nFixed."),
    ])
    events = []
    out = await audited_run(
        backend,
        task,
        "Write a function",
        ["claude", "agy"],
        stats,
        emit=lambda k, d: events.append((k, d)),
        max_rounds=2,
    )

    assert out == "def hello(): return 2"
    assert task.audit == "fixed"
    assert task.audit_history == [
        {"round": 1, "auditor": "agy", "verdict": "FAIL", "issues": "- should return 2"},
        {"round": 2, "auditor": "agy", "verdict": "PASS", "issues": "Fixed."},
    ]
    assert stats.score("claude", "implementation") == 1 / 3  # (0+1)/(0+1+2)


def test_audited_run_unresolved_ungated(tmp_path):
    asyncio.run(_test_audited_run_unresolved_ungated(tmp_path))


async def _test_audited_run_unresolved_ungated(tmp_path):
    stats = Stats(str(tmp_path / "stats.json"))
    task = DummyTask(agent="claude", gate=False)
    backend = FakeBackend([
        ("claude", "attempt 1"),
        ("agy", "VERDICT: FAIL\n- issue 1"),
        ("claude", "attempt 2"),
        ("agy", "VERDICT: FAIL\n- issue 2"),
        ("claude", "attempt 3"),
        ("agy", "VERDICT: FAIL\n- issue 3"),
    ])
    messages = []
    out = await audited_run(
        backend,
        task,
        "Write a function",
        ["claude", "agy"],
        stats,
        emit=lambda k, d: messages.append(d) if k == "message" else None,
        max_rounds=2,
    )

    assert task.audit == "disputed"
    assert out == "attempt 3"
    assert any("ESCALATION" in m.get("text", "") for m in messages)


def test_audited_run_unresolved_gated_raises(tmp_path):
    asyncio.run(_test_audited_run_unresolved_gated_raises(tmp_path))


async def _test_audited_run_unresolved_gated_raises(tmp_path):
    stats = Stats(str(tmp_path / "stats.json"))
    task = DummyTask(agent="claude", gate=True)
    backend = FakeBackend([
        ("claude", "attempt 1"),
        ("agy", "VERDICT: FAIL\n- blocking error 1"),
        ("claude", "attempt 2"),
        ("agy", "VERDICT: FAIL\n- blocking error 2"),
        ("claude", "attempt 3"),
        ("agy", "VERDICT: FAIL\n- blocking error 3"),
    ])

    with pytest.raises(RuntimeError, match="audit failed after 2 revisions"):
        await audited_run(backend, task, "Write a function", ["claude", "agy"], stats, max_rounds=2)


def test_stats_table_markdown(tmp_path):
    stats = Stats(str(tmp_path / "stats.json"))
    assert stats.table(["claude", "agy"]) == "No audit stats recorded yet."

    stats.record("claude", "refactor", True)
    stats.record("claude", "refactor", False)
    stats.record("agy", "refactor", True)

    tbl = stats.table(["claude", "agy"])
    assert "| Agent | refactor |" in tbl
    assert "| claude | 1/2 |" in tbl
    assert "| agy | 1/1 |" in tbl

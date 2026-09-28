"""Reaping finished relay runs: their git worktrees and branches.

`relay.make_workspaces` creates a worktree and a branch per chain and nothing removes them, so
every `/relay` leaves both behind forever. This module removes them — carefully.

Two rules, both learned the hard way in this repo:

1. **A commit-graph check is not enough.** Uncommitted work is invisible to `git log` by
   definition, and a relay worktree is exactly where uncommitted work lives. An audit chain's
   fixes were once committed with `git add` naming only the source files; the tests were left
   behind in the worktree, whose branch showed zero unmerged commits and so read as safe. The
   only reason that was caught was diffing the worktree against main by hand.

2. **Never override git's own guards.** `git worktree remove` already refuses a dirty worktree
   and `git branch -d` already refuses an unmerged branch. Using `--force` / `-D` replaces
   those checks with the assumption that we were careful, which is precisely what went wrong.

So: refuse and say why, name the files so the refusal is actionable, and let git be the
backstop. The naming of worktrees and branches stays in `relay.py`, beside the code that creates
them, so the two cannot drift; this module is handed candidates and knows nothing of layout.
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path

ACTIVE = "active"
UNMERGED = "unmerged"
DIRTY = "dirty"
MISSING = "missing"
SAFE = "safe"

# Long enough for a real status call, short enough that a wedged git does not hang the room.
GIT_TIMEOUT = 20


class GitUnavailable(Exception):
    """git could not be run, or the folder is not a repository. Never treat this as 'clean'."""


def git(root: str | Path, *args: str) -> str:
    """Run git in `root` and return stdout. Raises rather than returning empty on failure:
    a cleanup command that cannot see must not conclude there is nothing to do."""
    try:
        proc = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True,
                              timeout=GIT_TIMEOUT, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError) as e:
        raise GitUnavailable(f"git {' '.join(args)} failed in {root}: {e}") from e
    if proc.returncode != 0:
        raise GitUnavailable(f"git {' '.join(args)} exited {proc.returncode} in {root}: "
                             f"{(proc.stderr or proc.stdout).strip()[:200]}")
    return proc.stdout


def worktree_is_itself(wt: Path) -> bool:
    """Whether `wt` really is a worktree rooted at `wt`.

    Not paranoia. A worktree whose `.git` link is broken does not make git fail — it walks up and
    reports the *parent* repository's status, which is clean. So a broken worktree would be
    classified SAFE and removed with its uncommitted files still in it. Asking git where it thinks
    it is catches that.
    """
    if not (wt / ".git").exists():
        return False
    try:
        top = Path(git(wt, "rev-parse", "--show-toplevel").strip()).resolve()
    except GitUnavailable:
        return False
    try:
        return top == wt.resolve()
    except OSError:
        return False


def status_paths(root: str | Path) -> list[str]:
    """Modified and untracked paths, relative to `root`. Empty means genuinely clean.

    Uses `-z` so non-ASCII filenames arrive raw: git quotes paths containing unusual bytes by
    default, and naive `line[3:]` parsing then mangles them.
    """
    out = git(root, "status", "--porcelain", "-z")
    paths = []
    for entry in out.split("\0"):
        if len(entry) > 3:  # "XY path"
            path = entry[3:].strip()
            if " -> " in path:  # a rename reports "old -> new"
                path = path.split(" -> ")[-1]
            paths.append(path)
    return paths


def unmerged_commits(root: str | Path, branch: str, main: str = "main") -> list[str]:
    """Commits on `branch` that `main` does not have, as one-line subjects."""
    try:
        out = git(root, "log", "--oneline", f"{main}..{branch}")
    except GitUnavailable:
        return []
    return [line for line in out.splitlines() if line.strip()]


@dataclass
class Candidate:
    """One worktree/branch pair belonging to a finished run."""

    run: str
    label: str
    worktree: Path
    branch: str
    verdict: str = SAFE
    reason: str = ""


@dataclass
class Report:
    candidates: list[Candidate] = field(default_factory=list)
    removed: list[Candidate] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)

    def counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for c in self.candidates:
            out[c.verdict] = out.get(c.verdict, 0) + 1
        return out


def classify(root: str | Path, candidates: list[Candidate], main: str = "main",
             active_runs: set[str] | None = None) -> Report:
    """Decide what may be removed. The first failing check wins, and the reason names the
    evidence — a refusal the user cannot act on is not a refusal, it is a dead end."""
    report = Report(candidates=candidates)
    active = active_runs or set()
    for c in candidates:
        if c.run in active:
            c.verdict, c.reason = ACTIVE, "this run is in progress"
            continue
        if not c.worktree.is_dir() and not _branch_exists(root, c.branch):
            c.verdict, c.reason = MISSING, "already gone"
            continue
        if c.worktree.is_dir():
            if not worktree_is_itself(c.worktree):
                c.verdict, c.reason = DIRTY, (
                    "its .git link is broken or it belongs to another repository, so its state "
                    "cannot be read and it is left alone")
                continue
            try:
                dirty = status_paths(c.worktree)
            except GitUnavailable as e:
                # Never read as clean. An unreadable worktree is the case where a wrong
                # assumption is most expensive.
                c.verdict, c.reason = DIRTY, f"could not read its state, so it is left alone: {e}"
                continue
            if dirty:
                c.verdict = DIRTY
                shown = ", ".join(f"`{p}`" for p in dirty[:8])
                more = f" (+{len(dirty) - 8} more)" if len(dirty) > 8 else ""
                c.reason = f"uncommitted work: {shown}{more}"
                continue
        commits = unmerged_commits(root, c.branch, main) if _branch_exists(root, c.branch) else []
        if commits:
            c.verdict, c.reason = UNMERGED, f"{len(commits)} commit(s) not in {main}: " + \
                "; ".join(commits[:3])
            continue
        c.verdict, c.reason = SAFE, ""
    return report


def _branch_exists(root: str | Path, branch: str) -> bool:
    try:
        return bool(git(root, "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}").strip())
    except GitUnavailable:
        return False


def remove_one(root: str | Path, c: Candidate) -> str | None:
    """Remove one candidate's worktree and branch. Returns a problem string, or None on success.

    No `--force`, no `-D`. Git refuses a dirty worktree and an unmerged branch on its own; this
    relies on that rather than re-implementing the check and trusting it.
    """
    if c.worktree.is_dir():
        try:
            git(root, "worktree", "remove", str(c.worktree))
        except GitUnavailable as e:
            return f"could not remove worktree {c.worktree.name}: {e}"
    if _branch_exists(root, c.branch):
        try:
            git(root, "branch", "-d", c.branch)
        except GitUnavailable as e:
            # git re-checks mergedness here, so this is a second opinion rather than a repeat.
            return f"could not delete branch {c.branch}: {e}"
    return None

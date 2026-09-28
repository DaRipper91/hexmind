"""Reaping relay worktrees: WS-12.

The two properties that matter, both learned from a near-miss in this repo:

- a dirty worktree is refused **and the offending paths are named**, because a refusal you
  cannot act on is how an audit chain's regression tests were nearly deleted
- git's own guards are used, never overridden: no `--force`, no `-D`
"""
import subprocess as sp

import pytest

from hexmind.reaping import (ACTIVE, DIRTY, MISSING, SAFE, UNMERGED, Candidate, GitUnavailable,
                             classify, remove_one, status_paths, unmerged_commits)


def git(root, *args, check=True):
    return sp.run(["git", "-C", str(root), *args], capture_output=True, text=True, check=check)


def make_repo(tmp_path, name="repo"):
    root = tmp_path / name
    (root / "hexmind").mkdir(parents=True)
    (root / "hexmind" / "x.py").write_text("x = 1\n")
    (root / "README.md").write_text("hi\n")
    git(root, "init", "-q", "-b", "main")   # be explicit: this machine's default is `master`
    git(root, "add", "-A")
    git(root, "-c", "user.email=a@b", "-c", "user.name=a", "commit", "-qm", "init")
    (root / ".hexmind" / "worktrees").mkdir(parents=True)
    (root / ".hexmind" / "runs").mkdir(parents=True)
    (root / ".hexmind" / ".gitignore").write_text("*\n")
    return root


def add_worktree(root, run, label="A", content="x = 2\n"):
    """A linked worktree on its own branch, the way make_workspaces builds them."""
    name = f"{run}-{label}"
    wt = root / ".hexmind" / "worktrees" / name
    git(root, "worktree", "add", "-q", "-b", f"hexmind/{name}", str(wt))
    (wt / "hexmind" / "x.py").write_text(content)
    (root / ".hexmind" / "runs" / run).mkdir(parents=True, exist_ok=True)
    (root / ".hexmind" / "runs" / run / f"chain-{label}.md").write_text("# report\n")
    return Candidate(run=run, label=label, worktree=wt, branch=f"hexmind/{name}")


# ---------- the two properties that matter ----------

def test_a_dirty_worktree_is_refused_and_its_files_are_named(tmp_path):
    """The regression. An audit chain's tests sat uncommitted in a worktree whose branch showed
    zero unmerged commits; a bare 'dirty' verdict would have given no way to recover them."""
    root = make_repo(tmp_path)
    c = add_worktree(root, "run1")

    report = classify(root, [c])

    assert c.verdict == DIRTY
    assert "hexmind/x.py" in c.reason, f"the refusal must name the file: {c.reason}"
    assert "uncommitted work" in c.reason


def test_git_itself_refuses_to_remove_a_dirty_worktree(tmp_path):
    """The backstop. Even if the verdict were wrong, `git worktree remove` without --force will
    not delete a worktree with uncommitted changes."""
    root = make_repo(tmp_path)
    c = add_worktree(root, "run1")
    classify(root, [c])

    problem = remove_one(root, c)

    assert problem is not None, "git should have refused a dirty worktree"
    assert c.worktree.exists(), "the worktree and its files must survive"


def test_an_untracked_file_counts_as_dirty(tmp_path):
    root = make_repo(tmp_path)
    c = add_worktree(root, "run1")
    (c.worktree / "scratch.md").write_text("notes\n")

    classify(root, [c])

    assert c.verdict == DIRTY
    assert "scratch.md" in c.reason


def test_a_worktree_with_a_broken_git_link_is_never_read_as_clean(tmp_path):
    """The case where a wrong assumption is most expensive — and it is silent.

    Unlinking a worktree's .git does not make git fail: it walks up and reports the PARENT
    repository, which is clean. Without an identity check this worktree is classified safe and
    removed with its uncommitted files still in it. Found by writing the test, not by reading
    the code."""
    root = make_repo(tmp_path)
    c = add_worktree(root, "run1")
    (c.worktree / ".git").unlink()  # break it so git cannot read it

    classify(root, [c])

    assert c.verdict == DIRTY, "a broken worktree link must never read as clean"
    assert ".git link is broken" in c.reason, c.reason


def test_a_clean_merged_worktree_is_safe_and_removable(tmp_path):
    root = make_repo(tmp_path)
    c = add_worktree(root, "run1")
    base = sp.run(["git", "-C", str(root), "rev-parse", "main"],
                  capture_output=True, text=True).stdout.strip()
    # `main` is checked out in the parent, so a worktree cannot check it out; reset by sha.
    git(c.worktree, "reset", "-q", "--hard", base)  # clean AND identical to main

    classify(root, [c])
    assert c.verdict == SAFE, c.reason

    assert remove_one(root, c) is None
    assert not c.worktree.exists()
    gone = sp.run(["git", "-C", str(root), "branch", "--list", c.branch],
                  capture_output=True, text=True).stdout.strip()
    assert gone == "", "the branch must go with the worktree"
    # and git's own view must agree, or the listing lies
    listed = sp.run(["git", "-C", str(root), "worktree", "list"], capture_output=True, text=True).stdout
    assert "run1-A" not in listed


def test_removal_uses_git_branch_d_so_git_re_checks_mergedness(tmp_path, monkeypatch):
    """-d is not decoration: it re-verifies at delete time, so a run that gained a commit between
    the listing and the --force is still caught."""
    root = make_repo(tmp_path)
    c = add_worktree(root, "run1")
    git(c.worktree, "add", "-A")
    git(c.worktree, "-c", "user.email=a@b", "-c", "user.name=a", "commit", "-qm", "unmerged work")

    seen = []
    real = sp.run
    def spy(args, **kw):
        seen.append(args)
        return real(args, **kw)
    monkeypatch.setattr(sp, "run", spy)

    problem = remove_one(root, c)

    assert "-D" not in seen and "--force" not in seen, "must never use the forceful variants"
    assert any("branch" in a and "-d" in a for a in seen), seen
    assert problem is not None, "git should have refused an unmerged branch"
    assert "could not delete branch" in problem


def test_removal_uses_worktree_remove_without_force(tmp_path, monkeypatch):
    root = make_repo(tmp_path)
    c = add_worktree(root, "run1")
    base = sp.run(["git", "-C", str(root), "rev-parse", "main"],
                  capture_output=True, text=True).stdout.strip()
    git(c.worktree, "reset", "-q", "--hard", base)

    seen = []
    real = sp.run
    def spy(args, **kw):
        seen.append(args)
        return real(args, **kw)
    monkeypatch.setattr(sp, "run", spy)

    remove_one(root, c)

    wt_calls = [a for a in seen if "worktree" in a and "remove" in a]
    assert wt_calls, seen
    assert "--force" not in wt_calls[0], "git's dirty check is the backstop; do not override it"


# ---------- the other verdicts ----------

def test_an_unmerged_run_is_kept_and_its_commits_are_named(tmp_path):
    root = make_repo(tmp_path)
    c = add_worktree(root, "run1")
    git(c.worktree, "add", "-A")
    git(c.worktree, "-c", "user.email=a@b", "-c", "user.name=a", "commit", "-qm", "not in main")

    classify(root, [c])

    assert c.verdict == UNMERGED
    assert "not in main" in c.reason, c.reason
    assert "1 commit" in c.reason


def test_an_active_run_is_never_touched_even_when_otherwise_clean(tmp_path):
    root = make_repo(tmp_path)
    c = add_worktree(root, "run1")
    base = sp.run(["git", "-C", str(root), "rev-parse", "main"],
                  capture_output=True, text=True).stdout.strip()
    git(c.worktree, "reset", "-q", "--hard", base)

    classify(root, [c], active_runs={"run1"})

    assert c.verdict == ACTIVE
    assert "in progress" in c.reason


def test_a_run_already_gone_is_reported_rather_than_failing(tmp_path):
    root = make_repo(tmp_path)
    c = Candidate(run="ghost", label="A",
                  worktree=root / ".hexmind/worktrees/ghost-A", branch="hexmind/ghost-A")

    classify(root, [c])

    assert c.verdict == MISSING


def test_the_first_failing_check_wins(tmp_path):
    """A run that is both active and dirty is reported active — the stronger, cheaper reason."""
    root = make_repo(tmp_path)
    c = add_worktree(root, "run1")

    classify(root, [c], active_runs={"run1"})

    assert c.verdict == ACTIVE


# ---------- primitives ----------

def test_status_paths_handles_non_ascii_filenames(tmp_path):
    """git quotes paths with unusual bytes unless asked not to; naive line[3:] parsing then
    mangles them, and a mangled path is a path we cannot show the user."""
    root = make_repo(tmp_path)
    (root / "hexmind" / "café-日本.py").write_text("# hi\n")

    assert "hexmind/café-日本.py" in status_paths(root)


def test_status_paths_is_empty_for_a_clean_repo(tmp_path):
    root = make_repo(tmp_path)
    assert status_paths(root) == []


def test_an_unreadable_worktree_raises_rather_than_reading_as_clean(tmp_path):
    """status_paths decides SAFE-vs-DIRTY, so a failure there must never mean 'clean'."""
    plain = tmp_path / "not-a-repo"
    plain.mkdir()

    with pytest.raises(GitUnavailable):
        status_paths(plain)


def test_unmerged_commits_degrades_and_leaves_it_to_git_to_refuse(tmp_path):
    """Deliberately different from status_paths. It only softens the verdict; `git branch -d`
    re-checks mergedness at delete time, so a wrong [] here is still caught before anything is
    lost. Raising instead would make an unreadable branch block cleanup forever."""
    plain = tmp_path / "not-a-repo"
    plain.mkdir()

    assert unmerged_commits(plain, "nope") == []


def test_counts_summarise_the_verdicts(tmp_path):
    root = make_repo(tmp_path)
    a = add_worktree(root, "run1")
    b = add_worktree(root, "run2")

    report = classify(root, [a, b], active_runs={"run2"})

    assert report.counts() == {DIRTY: 1, ACTIVE: 1}


# ---------- the active marker and the command surface ----------

def test_the_active_marker_is_read_and_absent_is_fine(tmp_path):
    from hexmind.relay import _active_runs

    root = make_repo(tmp_path)
    assert _active_runs(str(root)) == set(), "no marker means nothing is running"

    (root / ".hexmind" / "active").write_text("run1\nrun2\n\n")
    assert _active_runs(str(root)) == {"run1", "run2"}


def test_a_missing_marker_never_raises(tmp_path):
    from hexmind.relay import _active_runs

    bare = tmp_path / "bare"
    bare.mkdir()
    assert _active_runs(str(bare)) == set()


def test_candidates_are_named_the_way_make_workspaces_names_them(tmp_path):
    """Built from the same layout make_workspaces writes, so the two cannot drift. The run id
    contains dashes, so the label is taken from the last segment, not the first."""
    from hexmind.relay import _run_candidates

    root = make_repo(tmp_path)
    add_worktree(root, "20260927-183608")
    add_worktree(root, "20260927-183608", label="B")

    found = _run_candidates(str(root))

    assert {(c.run, c.label) for c in found} == {("20260927-183608", "A"), ("20260927-183608", "B")}
    assert all(c.branch == f"hexmind/{c.run}-{c.label}" for c in found)


def test_clean_lists_without_changing_anything(tmp_path):
    """Listing first is the whole safety story: the user must be able to see the verdicts before
    anything is removed."""
    import asyncio

    from hexmind.core import Orchestrator
    from hexmind.relay import command

    root = make_repo(tmp_path)
    c = add_worktree(root, "run1")

    class B:
        cwd = str(root)

        async def run(self, agent, prompt, cwd=None, schema=None):
            return ""

    reply = asyncio.run(command(Orchestrator(B(), ["claude"], "claude"), "/relay clean"))

    assert "uncommitted work" in reply and "hexmind/x.py" in reply
    assert c.worktree.exists(), "listing must not remove anything"
    assert "could be removed" in reply


def test_clean_outside_a_git_repo_refuses_rather_than_guessing(tmp_path):
    """No git, no worktrees, no work to lose — but it must refuse rather than assume. The identity
    check catches this before the outer handler, which is the better outcome: the reason names the
    worktree instead of reporting a generic failure."""
    import asyncio

    from hexmind.core import Orchestrator
    from hexmind.relay import command

    plain = tmp_path / "plain"
    (plain / ".hexmind" / "worktrees" / "run1-A").mkdir(parents=True)

    class B:
        cwd = str(plain)

        async def run(self, agent, prompt, cwd=None, schema=None):
            return ""

    reply = asyncio.run(command(Orchestrator(B(), ["claude"], "claude"), "/relay clean"))

    assert ".git link is broken" in reply
    assert "run1" in reply
    assert "0** run(s) could be removed" in reply

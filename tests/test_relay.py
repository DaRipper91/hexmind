import argparse
import asyncio
import json
import subprocess
from pathlib import Path

from hexmind.core import Orchestrator
import pytest

from hexmind.relay import Chain, Stage, assign, read_agent_file, run_relay


class RelayFake:
    """Lead designs a 3-stage chain; stage workers report which stage they did."""
    def __init__(self, cwd):
        self.cwd = cwd
        self.prompts = []

    async def run(self, agent, prompt, cwd=None):
        self.prompts.append((agent, prompt, cwd))
        if prompt.startswith("Design a relay chain"):
            return json.dumps({"name": "demo", "stages": [
                {"name": "one", "instructions": "do one"}, {"name": "two", "instructions": "do two"},
                {"name": "three", "instructions": "do three"}]})
        if "relay chain(s) of" in prompt:
            return "merged"
        await asyncio.sleep(0.01)
        return f"{agent} finished {prompt.split('Your task (')[1].split(':')[0]}"


def run(orch, text):
    return asyncio.run(orch.handle(text))


def test_rotation_gives_every_chain_a_different_model_per_stage():
    chain = Chain("c", "", [Stage("s1", ""), Stage("s2", ""), Stage("s3", "")])
    grid = assign(chain, 3, ["claude", "codex", "agy"], "rotate")
    assert grid == [["claude", "codex", "agy"], ["codex", "agy", "claude"], ["agy", "claude", "codex"]]
    for i in range(3):  # at each stage position, all three models are in use
        assert sorted(row[i] for row in grid) == ["agy", "claude", "codex"]


def test_pinned_falls_back_to_rotation_for_unknown_model():
    chain = Chain("c", "", [Stage("s1", "", agent="agy"), Stage("s2", "", agent="gpt9")])
    assert assign(chain, 1, ["claude", "agy"], "pinned") == [["agy", "agy"]]


def test_lead_designed_relay_shared_workspace_writes_notes(tmp_path):
    backend = RelayFake(str(tmp_path))
    events = []
    orch = Orchestrator(backend, ["claude", "agy"], "claude", emit=lambda k, d: events.append((k, d)))
    final = run(orch, "/relay refactor the parser x2 --workspace shared")
    tasks = next(d["tasks"] for k, d in events if k == "plan")
    assert [t.id for t in tasks] == ["A1", "A2", "A3", "B1", "B2", "B3"]
    assert all(t.status == "done" for t in tasks)
    assert tasks[1].depends_on == ["A1"] and tasks[3].depends_on == []
    notes = Path(tasks[0].notes).read_text()
    assert "A·one" in notes and "A·three" in notes and "B·" not in notes
    assert final.startswith("merged")
    assert (tmp_path / ".hexmind/.gitignore").read_text() == "*\n"


class MidChainFailure(RelayFake):
    """Stage two dies, so stage three is skipped: the shape a `gate = true` stage produces."""

    async def run(self, agent, prompt, cwd=None):
        if "Your task (A2:" in prompt:
            raise RuntimeError("agy: audit could not clear the migration, see tests/test_db.py")
        return await super().run(agent, prompt, cwd)


def test_the_merge_prompt_is_told_how_each_stage_ended(tmp_path):
    """The synthesis sees only the last *done* stage's report, so it has no way to know a stage
    was gated off. Given the board's own status lines it cannot call a failed stage a success."""
    backend = MidChainFailure(str(tmp_path))
    orch = Orchestrator(backend, ["claude", "agy"], "claude")
    run(orch, "/relay fix the parser --workspace shared")

    merge = next(p for _, p, _ in backend.prompts if "relay chain(s) of" in p)
    assert "A1 done" in merge and "A2 failed" in merge and "A3 skipped" in merge
    assert "audit could not clear the migration" not in merge  # statuses, not the whole error


def test_multi_chain_in_git_repo_defaults_to_worktrees(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "-c", "user.name=t", "-c", "user.email=t@t",
                    "commit", "-q", "--allow-empty", "-m", "init"], check=True)
    backend = RelayFake(str(tmp_path))
    orch = Orchestrator(backend, ["claude", "agy"], "claude")
    run(orch, "/relay anything -n 2 --end list")
    cwds = {cwd for _, p, cwd in backend.prompts if "Your task (" in p}
    assert len(cwds) == 2 and all("/.hexmind/worktrees/" in c for c in cwds)


def test_bad_args_show_help(tmp_path):
    orch = Orchestrator(RelayFake(str(tmp_path)), ["claude"], "claude")
    assert "Commands" in run(orch, "/relay x --assign nope")


def test_reads_claude_and_codex_agent_files(tmp_path):
    md = tmp_path / "a.md"
    md.write_text("---\nname: a\n---\n\nDo the thing.")
    tm = tmp_path / "a.toml"
    tm.write_text('name = "a"\ndeveloper_instructions = """Codex thing."""\n')
    assert read_agent_file(str(md)) == "Do the thing."
    assert read_agent_file(str(tm)) == "Codex thing."


def test_apostrophe_in_relay_goal_does_not_crash(tmp_path):
    backend = RelayFake(str(tmp_path))
    orch = Orchestrator(backend, ["claude", "agy"], "claude")
    assert run(orch, "/relay fix the user's login bug --workspace shared").startswith("merged")
    design = next(p for _, p, _ in backend.prompts if p.startswith("Design a relay chain"))
    assert "fix the user's login bug" in design


def _chain_dir(tmp_path, monkeypatch):
    import hexmind.relay as relay
    d = tmp_path / "chains"
    d.mkdir()
    (d / "good.toml").write_text('description = "fine"\n[[stages]]\nname = "a"\ninstructions = "x"\n')
    (d / "gone.toml").write_text('[[stages]]\nname = "a"\nfrom = "/nope/missing-agent.md"\n')
    monkeypatch.setattr(relay, "CHAIN_DIRS", [d])


def test_chains_lists_broken_chain_instead_of_crashing(tmp_path, monkeypatch):
    _chain_dir(tmp_path, monkeypatch)
    orch = Orchestrator(RelayFake(str(tmp_path)), ["claude"], "claude")
    reply = run(orch, "/chains")
    assert "**good** (1 stages): fine" in reply
    assert "**gone** (broken: missing /nope/missing-agent.md)" in reply


def test_relay_of_broken_chain_names_missing_file(tmp_path, monkeypatch):
    _chain_dir(tmp_path, monkeypatch)
    backend = RelayFake(str(tmp_path))
    orch = Orchestrator(backend, ["claude"], "claude")
    reply = run(orch, "/relay gone")
    assert "broken" in reply and "/nope/missing-agent.md" in reply
    assert backend.prompts == []  # nothing was sent to a model


class OddLead(RelayFake):
    def __init__(self, cwd, design):
        super().__init__(cwd)
        self.design = design

    async def run(self, agent, prompt, cwd=None):
        if prompt.startswith("Design a relay chain"):
            return self.design
        return await super().run(agent, prompt, cwd)


def test_lead_designed_stages_tolerate_strings_and_junk(tmp_path):
    design = json.dumps({"name": "odd", "stages": ["plan it", 42, {"name": "b", "instructions": "do b"}]})
    events = []
    orch = Orchestrator(OddLead(str(tmp_path), design), ["claude"], "claude",
                        emit=lambda k, d: events.append((k, d)))
    run(orch, "/relay something --workspace shared --end list")
    tasks = next(d["tasks"] for k, d in events if k == "plan")
    assert [t.title for t in tasks] == ["A·stage 1", "A·b"]
    assert "plan it" in tasks[0].instructions


def test_unusable_lead_design_replies_with_error(tmp_path):
    for design in ("sorry, no JSON here", json.dumps({"stages": "nope"})):
        orch = Orchestrator(OddLead(str(tmp_path), design), ["claude"], "claude")
        assert run(orch, "/relay something --workspace shared").startswith("Relay failed:")


# ---------- /relay argument parsing ----------

def test_goal_accepts_a_whole_sentence_without_quoting():
    """A person types `/relay feature --goal add CSV export and tests`. With a single-value
    --goal, argparse swallows one token and then cannot match the rest against the already
    satisfied `target`, so the command fails with 'unrecognized arguments'."""
    from hexmind.relay import _parse_relay

    ns = _parse_relay(["feature", "--goal", "add", "CSV", "export", "and", "tests"])

    assert ns.target == ["feature"]
    assert ns.goal == "add CSV export and tests"


def test_the_quoted_single_token_form_still_works():
    from hexmind.relay import _parse_relay

    ns = _parse_relay(["feature", "--assign", "pinned", "--goal", "add CSV export"])

    assert ns.goal == "add CSV export"
    assert ns.assign == "pinned"


def test_options_must_come_before_the_goal_which_takes_the_rest_of_the_line():
    from hexmind.relay import _parse_relay

    ns = _parse_relay(["f", "-n", "2", "--end", "compare", "--goal", "do", "the", "thing"])

    assert (ns.goal, ns.chains, ns.end) == ("do the thing", 2, "compare")


def test_a_goal_containing_a_flag_like_word_is_not_parsed_as_a_flag():
    """A goal is a sentence and may name a flag. nargs="+" swallowed the real options, and a
    single-value --goal called it 'unrecognized arguments'; taking the rest of the line is the
    only reading that survives."""
    from hexmind.relay import _parse_relay

    ns = _parse_relay(["fix-review", "--assign", "pinned",
                       "--goal", "print the first line on --once, and use -k carefully"])

    assert ns.assign == "pinned"
    assert ns.goal == "print the first line on --once, and use -k carefully"


def test_an_empty_goal_is_rejected_rather_than_silently_dropped():
    from hexmind.relay import _parse_relay

    with pytest.raises(ValueError, match="--goal needs"):
        _parse_relay(["f", "--assign", "pinned", "--goal"])


def test_an_empty_goal_replies_like_the_other_bad_arguments(tmp_path):
    """`_parse_relay` raises a plain ValueError and `command` only caught argparse's, so typing
    `/relay fix-review --goal` took the TUI's message handler down with a traceback instead of
    printing the line the user just typed. Every other bad argument already answers."""
    said = []
    orch = Orchestrator(RelayFake(str(tmp_path)), ["claude"], "claude",
                        emit=lambda k, d: said.append(d.get("text", "")) if k == "message" else None)

    reply = run(orch, "/relay fix-review --assign pinned --goal")

    assert reply.startswith("Bad /relay arguments")
    assert "--goal needs some text after it" in reply
    assert "Commands" in reply  # the help, as for any other bad /relay arguments
    assert said == [reply]  # it is reported in the room, not raised into the message loop


def test_no_goal_is_still_none():
    from hexmind.relay import _parse_relay

    assert _parse_relay(["opencode-team", "--assign", "pinned"]).goal is None


# ---------- worktree isolation: told where to work, and checked afterwards ----------

def _repo(root: Path) -> Path:
    """A git repo with a commit, so the isolation check has something to compare against."""
    (root / "hexmind").mkdir(parents=True)
    (root / "hexmind" / "x.py").write_text("x = 1\n")
    for cmd in (["init", "-q"], ["add", "-A"], ["-c", "user.email=a@b", "-c", "user.name=a", "commit", "-qm", "x"]):
        subprocess.run(["git", "-C", str(root), *cmd], check=True, capture_output=True)
    return root


def test_dirty_paths_reports_worktree_changes_but_not_ignored_run_files(tmp_path):
    """The isolation check is only usable if `.hexmind/` is invisible: the notes files and the
    per-chain worktrees live there and would otherwise read as leaks on every single run."""
    import subprocess as sp
    root = tmp_path / "repo"
    (root / "hexmind").mkdir(parents=True)
    (root / "hexmind" / "x.py").write_text("x = 1\n")
    (root / ".hexmind").mkdir()
    (root / ".hexmind" / ".gitignore").write_text("*\n")
    (root / ".hexmind" / "runs").mkdir()
    (root / ".hexmind" / "runs" / "chain-A.md").write_text("stage report\n")
    for cmd in (["init", "-q"], ["add", "-A"], ["-c", "user.email=a@b", "-c", "user.name=a", "commit", "-qm", "x"]):
        sp.run(["git", "-C", str(root), *cmd], capture_output=True, check=True)

    from hexmind.relay import dirty_paths

    assert dirty_paths(str(root)) == set(), "a clean repo with run files must report nothing"

    (root / "hexmind" / "x.py").write_text("x = 2\n")
    assert dirty_paths(str(root)) == {"hexmind/x.py"}, "a real edit must be reported"


def test_dirty_paths_says_it_could_not_tell_instead_of_reporting_clean(tmp_path):
    """An empty set means "clean". A folder that is not a git repo, a git error and a timeout all
    used to produce one, so a check that could not answer was indistinguishable from a check that
    passed — and a broken git made every relay report a clean run. The caller needs the difference."""
    from hexmind.relay import dirty_paths

    assert dirty_paths(str(tmp_path)) is None


def test_a_git_that_times_out_is_not_a_clean_folder(tmp_path, monkeypatch):
    from hexmind import relay

    def never_returns(*a, **k):
        raise subprocess.TimeoutExpired("git status", 20)

    monkeypatch.setattr(relay.subprocess, "run", never_returns)

    assert relay.dirty_paths(str(tmp_path)) is None


def test_a_non_ascii_path_comes_back_as_written(tmp_path):
    """git quotes a path that isn't plain ASCII — `naïve.py` arrives as `"na\\303\\257ve.py"` —
    so `line[3:]` reported the leak under a path that does not exist, quotes and octal escapes
    included. `-z` prints paths NUL-separated and unmunged, which is what makes the check point at
    a file a person can open."""
    from hexmind.relay import dirty_paths

    root = _repo(tmp_path / "repo")
    (root / "naïve.py").write_text("x = 2\n")

    assert dirty_paths(str(root)) == {"naïve.py"}


def test_a_renamed_path_is_reported_as_its_destination(tmp_path):
    """`-z` puts a rename's two paths in separate NUL fields, destination first, so the source has
    to be skipped: a file that was moved away is not a leak. The old `" -> "` split was a guess at
    the same pair, and it also split any filename that happened to contain an arrow."""
    from hexmind.relay import dirty_paths

    root = _repo(tmp_path / "repo")
    (root / "old name.py").write_text("y = 1\n")
    subprocess.run(["git", "-C", str(root), "add", "-A"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(root), "-c", "user.email=a@b", "-c", "user.name=a", "commit", "-qm", "y"],
                   check=True, capture_output=True)
    subprocess.run(["git", "-C", str(root), "mv", "old name.py", "new name.py"], check=True, capture_output=True)

    assert dirty_paths(str(root)) == {"new name.py"}


# ---------- the check itself: one comparison per stage, attributed to that stage ----------

class LeakyStage(RelayFake):
    """A chain whose middle stage ignores its worktree and edits the main checkout.

    `timeline` records every stage as it starts and every message hexmind sends, so a test can tell
    *when* the breach was reported and not just that it was.
    """

    def __init__(self, root: Path, leak_in: str | None, timeline: list):
        super().__init__(str(root))
        self.root, self.leak_in, self.timeline = root, leak_in, timeline

    async def run(self, agent, prompt, cwd=None):
        if "Your task (" in prompt:
            tid = prompt.split("Your task (")[1].split(":")[0].strip()
            self.timeline.append(("run", tid))
            if tid == self.leak_in:  # the breach, made while this stage is the one running
                (self.root / "hexmind" / "x.py").write_text("x = 99\n")
        return await super().run(agent, prompt, cwd)


def _relay_in(root: Path, timeline: list, leak_in: str | None = "A2", workspace: str = "worktree") -> str:
    """Run the 3-stage chain RelayFake's lead designs, in real worktrees, and collect the messages.

    Real `git worktree add` rather than a stubbed folder, so the check sees the layout it would in
    life: the worktree under `.hexmind/`, invisible to the main folder's status, and the notes file
    beside it.
    """
    orch = Orchestrator(LeakyStage(root, leak_in, timeline), ["claude", "agy"], "claude",
                        emit=lambda k, d: timeline.append(("say", d.get("text", ""))) if k == "message" else None)
    return run(orch, f"/relay fix the parser --workspace {workspace} --end list")


def test_a_stage_that_writes_to_the_main_folder_is_reported_as_a_breach(tmp_path):
    """The prompt tells a stage which directory is its own, but a prompt is a soft control. This is
    the hard one: the chain must notice and say so, instead of reporting a clean run over changes
    that landed in the wrong place. It happened once, silently."""
    root = _repo(tmp_path / "repo")
    timeline: list = []
    final = _relay_in(root, timeline)
    said = "\n".join(text for kind, text in timeline if kind == "say")

    assert "wrote outside its own worktree" in said
    assert "hexmind/x.py" in said
    assert "isolation breach" in final  # the summary cannot present the run as clean either


def test_a_breach_names_the_stage_that_caused_it_and_lands_before_the_next_stage_runs(tmp_path):
    """The comparison used to run once, after the whole chain, so the only thing the report could
    name was the last stage — which is exactly the stage that did nothing wrong. And a breach the
    user hears about three stages later is a breach they have already reacted to."""
    root = _repo(tmp_path / "repo")
    timeline: list = []
    _relay_in(root, timeline, leak_in="A2")

    escalated = [i for i, (kind, text) in enumerate(timeline) if kind == "say" and "outside its own worktree" in text]
    assert len(escalated) == 1, timeline
    at = escalated[0]
    third_stage = next(i for i, (kind, what) in enumerate(timeline) if (kind, what) == ("run", "A3"))
    assert at < third_stage, "the breach was only reported after the chain had finished"
    assert "A2" in timeline[at][1], timeline[at][1]  # blamed on the stage that made it, not on A3

def test_shared_workspace_legitimate_edits_do_not_trigger_isolation_check(tmp_path, monkeypatch):
    """In --workspace shared, every chain's cwd IS the main folder, so legitimate edits by stages
    would falsely trigger the isolation check. The check must be gated on workspace == 'worktree'."""
    import subprocess as sp
    root = tmp_path / "repo"
    (root / "hexmind").mkdir(parents=True)
    (root / "hexmind" / "x.py").write_text("x = 1\n")
    for cmd in (["init", "-q"], ["add", "-A"], ["-c", "user.email=a@b", "-c", "user.name=a", "commit", "-qm", "x"]):
        sp.run(["git", "-C", str(root), *cmd], capture_output=True, check=True)

    said = []
    backend = RelayFake(str(root))
    orch = Orchestrator(backend, ["claude"], "claude",
                        emit=lambda k, d: said.append(d.get("text", "")) if k == "message" else None)
    orch.backend.cwd = str(root)
    monkeypatch.setattr("hexmind.relay.load_chain", lambda p: Chain("c", "d", [Stage("s", "do it", "claude")]))

    async def legit_edit(*a, **k):
        # a stage that legitimately edits the main folder (shared workspace)
        (root / "hexmind" / "x.py").write_text("x = 2\n")
        return ""

    monkeypatch.setattr(orch, "run_tasks", legit_edit)

    ns = argparse.Namespace(target=["c"], chains=1, assign="pinned", workspace="shared",
                            end="list", goal=None)
    asyncio.run(run_relay(orch, ns))

    joined = "\n".join(said)
    # The isolation check should NOT run in shared mode, so no breach message
    assert "wrote outside its own worktree" not in joined
    assert "isolation breach" not in joined
    # The run should complete normally
    assert "Relay finished" in joined


def test_a_run_where_git_could_not_tell_reports_the_check_as_unavailable(tmp_path, monkeypatch):
    """The check that cannot answer must not read as the check that passed. `None` from git used to
    be an empty set, so a broken or slow git made every worktree relay claim it had verified
    isolation when it had verified nothing."""
    root = _repo(tmp_path / "repo")
    monkeypatch.setattr("hexmind.relay.dirty_paths", lambda r: None)
    timeline: list = []
    final = _relay_in(root, timeline, leak_in=None)
    said = "\n".join(text for kind, text in timeline if kind == "say")

    assert "isolation check unavailable" in said
    assert "isolation check unavailable" in final  # the status block too, so the summary cannot hide it
    assert "isolation breach" not in final  # unverifiable is not a breach, and not a clean run either


def test_a_check_that_could_not_tell_never_reports_a_breach_it_invented(tmp_path, monkeypatch):
    """A folder can be dirty for reasons that have nothing to do with the run. If the baseline is
    missing, the first answer git does give is a baseline, not a diff — reporting it as fresh would
    blame the chain for the user's own uncommitted work."""
    from hexmind.relay import dirty_paths

    root = _repo(tmp_path / "repo")
    (root / "hexmind" / "x.py").write_text("x = 7\n")  # dirty before the relay starts
    calls = []
    monkeypatch.setattr("hexmind.relay.dirty_paths",
                        lambda r: calls.append(r) or (None if len(calls) == 1 else dirty_paths(r)))
    timeline: list = []
    final = _relay_in(root, timeline, leak_in=None)

    assert "isolation breach" not in final
    assert "isolation check unavailable" in final


def test_a_shared_workspace_run_is_not_reported_as_a_breach(tmp_path):
    """In shared mode the main folder is where the work is supposed to land, so the check stays off
    and a shared run must not claim it verified anything."""
    root = _repo(tmp_path / "repo")
    timeline: list = []
    _relay_in(root, timeline, leak_in="A2", workspace="shared")
    said = "\n".join(text for kind, text in timeline if kind == "say")

    assert "isolation" not in said.lower()


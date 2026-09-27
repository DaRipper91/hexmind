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


def test_no_goal_is_still_none():
    from hexmind.relay import _parse_relay

    assert _parse_relay(["opencode-team", "--assign", "pinned"]).goal is None


# ---------- worktree isolation: told where to work, and checked afterwards ----------

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


def test_dirty_paths_is_empty_outside_a_git_repo(tmp_path):
    """`--cwd` can be any folder, and a non-git folder has no isolation to check. Returning empty
    rather than raising keeps the check from breaking a shared-workspace relay."""
    from hexmind.relay import dirty_paths

    assert dirty_paths(str(tmp_path)) == set()


def test_a_stage_that_writes_to_the_main_folder_is_reported_as_a_breach(tmp_path, monkeypatch):
    """The prompt tells a stage which directory is its own, but a prompt is a soft control. This is
    the hard one: the chain must notice and say so, instead of reporting a clean run over changes
    that landed in the wrong place. It happened once, silently."""
    import subprocess as sp
    root = tmp_path / "repo"
    (root / "hexmind").mkdir(parents=True)
    (root / "hexmind" / "x.py").write_text("x = 1\n")
    for cmd in (["init", "-q"], ["add", "-A"], ["-c", "user.email=a@b", "-c", "user.name=a", "commit", "-qm", "x"]):
        sp.run(["git", "-C", str(root), *cmd], capture_output=True, check=True)
    chain = tmp_path / "c.toml"
    chain.write_text('name = "c"\ndescription = "d"\n[[stages]]\nname = "s"\n'
                     'instructions = "do it"\nagent = "claude"\n')

    said = []
    backend = RelayFake(str(root))
    orch = Orchestrator(backend, ["claude"], "claude",
                        emit=lambda k, d: said.append(d.get("text", "")) if k == "message" else None)
    orch.backend.cwd = str(root)
    monkeypatch.setattr("hexmind.relay.load_chain", lambda p: Chain("c", "d", [Stage("s", "do it", "claude")]))
    monkeypatch.setattr("hexmind.relay.make_workspaces",
                        lambda r, run, n, mode: ([str(root / "fake-wt")], [str(root / "n.md")]))

    async def leak(*a, **k):
        # a stage that ignores its worktree and edits the main checkout
        (root / "hexmind" / "x.py").write_text("x = 99\n")
        return ""

    monkeypatch.setattr(orch, "run_tasks", leak)

    ns = argparse.Namespace(target=["c"], chains=1, assign="pinned", workspace="worktree",
                            end="list", goal=None)
    asyncio.run(run_relay(orch, ns))

    joined = "\n".join(said)
    assert "wrote outside its own worktree" in joined
    assert "hexmind/x.py" in joined




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

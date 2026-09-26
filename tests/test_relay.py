import asyncio
import json
import subprocess
from pathlib import Path

from hexmind.core import Orchestrator
from hexmind.relay import Chain, Stage, assign, read_agent_file


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

# Hexmind GUI: Expansion Ideas (Feature Forge), 2026-09-28

> This is a brainstorm, not a backlog. Nothing here is prioritized against the fix-plan
> (`2026-09-28-hexmind-fixes.md`). Pick what excites you, ignore the rest, and treat each idea as a
> starting pitch, not a spec.

**Context:** `hexmind-gui` is a `QMainWindow` (`qt/app.py`) around `HexmindWidget` (`qt/widget.py`).
It drives the same `Orchestrator` as the TUI from a `_Room` QThread, and today it sees the team
through four signals: `message`, `taskChanged`, `teamChanged` and `turnState`
(`widget.py:118-121`). These ideas take one position. **The orchestrator already produces more
truth than the GUI can see, so the flagship move is to widen that pipe (new emit kinds, handles
kept on running work), not to add Qt logic.** Every idea below keeps the "one brain" rule
(`widget.py:8-11`, `AETHER-INTERFACE.md` hard rules). Where the logic doesn't exist yet it goes
into `core.py` / `relay.py` / `reaping.py` / `auditor.py` as a public function. Qt only renders it
and calls it.

The four features already being designed (model manager, 1:1 chat, CLI health, settings) are
treated as given. Several ideas below state what they build on or unlock.

**Hard constraints respected throughout:** nothing restyles the host (the stylesheet stays in
`app.py:200`), no new dependencies (QtWebSockets and QSystemTrayIcon ship with PySide6, and I
verified `import PySide6.QtWebSockets` on this machine), and the TUI is untouched.

---

## Weekend-scale

### Hand brake: stop the turn, kill one task, hand it to someone else
**Pitch:** A turn is running with four tasks and one of them is clearly lost (codex has been
rewriting the wrong file for nine minutes). Today your options are to wait up to 30 minutes
(`DirectBackend(timeout=1800)`, `backends.py:154`) or to quit the app. With the hand brake you
right-click that row on the task board and choose "Stop t3", or "Stop t3 and give it to claude".
The other three keep running, and the graph re-resolves its dependents. A red Stop button next to
Send cancels the whole turn cleanly.

**Why this project, specifically:** Most of the machinery is already there with nothing driving
it. `run_tasks` has a `finally` written for cancelled turns: it marks stranded tasks failed, writes
them to relay notes and fixes the busy set (`core.py:1066-1076`). `_terminate_group` kills a
CLI's whole process group (`backends.py:90`), but only the timeout path calls it
(`backends.py:189-190`), so a cancel today would orphan the agent process. `_Room.submit` throws away
the future from `run_coroutine_threadsafe` (`widget.py:174`), so the GUI has no handle to cancel
with. The per-task `running` dict is local to `run_tasks` (`core.py:1020`). Reassignment can
reuse the path the quota handoff already takes: rewrite the prompt, set `t.agent = spare`, emit
(`core.py:1135-1139`).

**What it'd take:**
- In `core.py`, keep `running` on the orchestrator and add `cancel_task(id, reassign_to=None)`.
- In `DirectBackend.run`, call `_terminate_group` on `CancelledError`.
- In `_Room`, keep the turn future and add a `cancel()` method.
- Add a context menu on the task table.
- Add a `POST /api/cancel` to `server.py` so remote clients get the same control.

### Come-back pings: tray presence plus the phone buzz `notify.py` was written for
**Pitch:** You send a relay and walk away. The window goes to the tray. When the turn ends, an
audit escalates, a draft plan is waiting for `/approve`, or a member runs out of quota, you get a
desktop notification and your phone buzzes through KDE Connect. Clicking the notification brings
the window back with the relevant task already selected.

**Why this project, specifically:** `hexmind/notify.py` exists, is tested (`tests/test_notify.py`)
and describes its own purpose: "Phone ping when the room needs you back (a run finished, an
ESCALATION)". Nothing in `hexmind/` calls it. Every trigger is already an emit with a stable
shape:
- `ESCALATION:` (`auditor.py:277`)
- the draft-plan note (`core.py:830`)
- the quota handoff (`core.py:1134`)
- `turnState(False)` (`widget.py:121`)

The embed rule decides where the code goes. The widget exposes one new optional signal,
`attentionNeeded(kind, text)`, in the same way it exposes `openFileRequested`
(`AETHER-INTERFACE.md`, "optional signal surface"). `app.py` owns the `QSystemTrayIcon` and calls
`notify()`. Aether can route the same signal into its own `SignalBus`.

**What it'd take:**
- A signal and a classifier in `widget.py`.
- A tray icon, notification preferences and an "only after N seconds of turn time" threshold in
  `app.py`.
- `notify()` called through `asyncio.to_thread`/`QThreadPool`, as its docstring asks.

---

## Subsystem-scale

### Live tap: watch every agent think, in real time
**Pitch:** Each running task gets a live pane. You see claude's tool calls tick past ("Read
core.py, Edit relay.py:980"), agy's stream-json events, and kimi's partial reply. The lead's
invisible phases ("planning…", "designing chain…", "summarizing…") show as a pulse on its roster
row. A turn stops being a spinner followed by a wall of text. You watch the room work, and you can
tell stuck apart from slow.

**Why this project, specifically:**
- `DirectBackend.run` buffers each CLI's whole stdout (`_read_capped`, `backends.py:61,184`) and
  only parses it after exit, even though agy and kimi are already invoked with
  `--output-format stream-json` (`backends.py:28-37`). A comment already plans the same for
  opencode ("`--format json` (plan WS-4) will replace the bare stdout read with a session-aware
  event stream", `backends.py:41`).
- The orchestrator already emits `status` events (`core.py:806,811,986,988`, `relay.py` "designing
  chain"), but `_Room._emit` drops them. It handles only message/task/team/plan
  (`widget.py:141-150`).
- `server.py` already broadcasts unknown kinds unchanged (`server.py:296-298`), so remote clients
  would get the stream for free.

**What it'd take:**
- An optional `on_event(agent, event)` callback in `backend.run`. It needs a line-by-line reader
  that keeps the final-result parsing it has today.
- Orchestrator re-emits it as `emit("chunk", {"task": id, ...})`.
- `_Room` gains a `chunk` signal and a `status` signal.
- A `LivePane` widget with a per-task ring buffer. It must be capped like the transcript's
  2000-block limit.
- An hcom backend can't stream the same way. For hcom the pane shows a "watch in terminal" action
  (`hcom term <name>`, the backend already suggests this at `backends.py:340`).

### Relay Runs desk: from "the chain finished" to "merge chain B"
**Pitch:** A Runs tab lists every relay run in `.hexmind/runs/`. Open one and you get the
chains-by-stages grid, each stage's report rendered from `chain-X.md`, and a real `git diff`
per chain worktree against main. Two chains can be compared side by side. Each worktree shows its
reaping verdict as a badge (safe / dirty / unmerged / active / missing). Two buttons close the
loop: **Adopt chain B**, which merges `hexmind/<run>-B`, and **Reap safe**. The launch side lives
here too. A relay form (chain, `-n`, assign mode, workspace, end mode, goal) shows a **dry-run
preview grid** before anything spawns.

**Why this project, specifically:**
- `run_relay` already produces everything this desk shows, but only as one markdown table in the
  transcript (`relay.py:998-1002`). It leaves real artifacts on disk: notes per chain, a worktree
  and branch per chain (`make_workspaces`, `relay.py:168-190`), and an `active` marker
  (`relay.py:994`).
- `reaping.classify` already assigns each worktree a verdict with a reason (`reaping.py:127`).
  `_relay_clean` flattens that to text (`relay.py:874`).
- The "compare" end mode asks the lead to compare chains in prose (`relay.py:216-220`). The desk
  puts the actual diffs next to that prose.
- `reaping` flags branches as *unmerged*, but no path merges them. Adopting a chain is the missing
  verb.
- The preview is free because `relay.assign` is pure (`relay.py:135`). The workspace default
  (`relay.py:980`) should become a small `relay.preview(ns, members)` so Qt doesn't
  re-derive it.
- This builds on the chains editor in the settings work. That work covers authoring chains; this
  covers running them and harvesting the results.

**What it'd take:**
- Make `_run_candidates`/`_active_runs` public in `relay.py`.
- Add `relay.preview()` and `reaping.adopt(root, candidate)`, which does a merge that refuses a
  dirty main.
- Add `qt/runs.py`: a run list, a stage report browser, a diff view in `QPlainTextEdit` with a
  small syntax highlighter, and a launch form that submits the exact `/relay` line through
  `_room.submit`.

### Draft plan workbench: edit the lead's plan before it runs
**Pitch:** Turn on draft plans. The lead's plan no longer arrives as a markdown list with
"`/approve` or `/discard`". It opens in the Graph tab as an editable draft:
- Swap t2 from opencode-ultra to claude. The combo is ranked by each member's audit record in that
  task's domain.
- Mark t4 as a gate.
- Delete t5.
- Tighten t1's instructions.

Then click Approve. What runs is the plan you signed off, and the chains the lead attached are
listed as checkboxes.

**Why this project, specifically:**
- `approve_plans` already parks a real object: `orch.pending = (request, tasks)` plus
  `pending_directives` (`core.py:824-826`).
- `server.py` already serialises it as `pending_plan` (`server.py:314-320`), so a remote client
  sees the same thing.
- Validation for "unknown agent / bad dependency" already lives in `parse_plan` (`core.py:313`),
  which the fix-plan's Task 4 is making louder. An edited draft goes back through that same
  validator, not a Qt copy of it.
- `TaskGraphView` (`qt/graph.py`) already lays out the dependency graph.
- `Stats.ranked(members, domain)` (`auditor.py:117`) provides the reassignment hint.
- The draft is where "one room, many opinions" pays off: you are the tie-breaker on the plan, not
  just on the result.

**What it'd take:**
- Add `Orchestrator.revise_pending(edits) -> list[str] findings` to `core.py`. It re-validates and
  refuses TEXT_ONLY members for file work, as `fallback` does (`core.py:1143`).
- Add an edit mode to `graph.py` (inspector dock: agent combo, gate, instructions, delete).
- The Approve/Discard buttons still submit `/approve` / `/discard`, so the command path stays the
  only execution path.

### Audit courtroom: every round of the argument, not just the verdict
**Pitch:** Click a task that went `fixed` or `disputed` and see the whole case as a thread:
1. The primary's first output.
2. The auditor's issues.
3. A real diff of the revision.
4. The second verdict, and so on to the end.

A disputed task becomes an actionable card rather than an `ESCALATION:` paragraph. It offers:
- **Accept anyway**
- **Re-audit with someone else**, who gets picked by the next-best ranking
- **Hand to another agent** (the Hand brake idea's reassign)

**Why this project, specifically:** `audited_run` holds every round's `audit_out`, `issues` and
revised `out` in local variables and then discards them (`auditor.py:202-275`). `Task` keeps only
the final `audit` and `auditor` fields (`core.py:118-119`). The Timeline panel's docstring says it
exists to answer "what did the auditor say about it?", and admits it can only read `Task.audit`
(`qt/timeline.py:1-30`). The courtroom gives it the data. The ledger rule is kept: `Stats` records
only the first verdict (`auditor.py:244-246`, restated in `qt/stats.py`), and a user overriding a
dispute is recorded separately, never folded into first-attempt reliability.

**What it'd take:**
- `emit("audit", {task, round, auditor, passed, issues, output})` inside the loop in
  `auditor.py`, plus a `rounds` list on `Task` so the snapshot carries it.
- A `qt/courtroom.py` thread view that uses `difflib` from the standard library.
- An override record in `Stats` under a separate key.

---

## Swing-for-the-fence

### The room is a protocol: local, remote and replayed rooms behind one widget
**Pitch:** `HexmindWidget` stops caring where its room lives.
- **Local** is today's `_Room`.
- **Remote** connects to `hexmind --serve` on another machine. The M2 laptop runs the agents and
  the worktrees. The GUI runs anywhere: a second desktop, or Aether on a different box. Several
  windows can watch one room.
- **Replay** opens a recorded session (`.hexmind/sessions/*.jsonl`) and scrubs through it with a
  slider. The transcript, task board, graph, timeline and audit courtroom all rewind together.

The same widget and panels serve all three. Only the signal source changes.

**Why this project, specifically:** The seam already exists, even though nobody has named it. The
widget talks to `_Room` only through four signals plus `submit`, `change_lead` and `snapshot`
(`widget.py:118-121,166-183,227`). Panels are duck-typed on a host exposing `snapshot()`
(`widget.py:303`).

`server.py`'s WebSocket already speaks nearly the same event vocabulary:
`init`/`message`/`task`/`plan`/`status`, with timestamps (`server.py:259-298,472-530`). It has
token auth over a subprotocol (`hexmind.token.<b64>`, `server.py:77-97`) and a loopback-only
default (`server.py:553`).

Replay covers a real gap. Tasks carry no timestamps (the Timeline docstring calls plan order "the
only time proxy there is"), and `Orchestrator.history` lives only in memory. A tee on `emit`
fixes both. It also gives the BUILD-PATH's untouched WS-11 journals (`docs/BUILD-PATH.md:32`)
their first data source.

The settings work already stores server host, port and token. This turns those fields into a
"Connect to room…" dialog.

**What it'd take:**
- Define a `RoomSource` shape: the four signals plus submit/change_lead/snapshot/cancel.
- Add `qt/remote.py` (`QWebSocket`, reconnect, token subprotocol).
- Add `qt/replay.py` (a JSONL reader and a scrubber).
- In `core.py` (or a small `hexmind/journal.py`), add an `emit` tee that writes JSONL.
- Close the gaps on the server side: `get_status_summary` lacks `known` and `busy` (compare
  `widget.py:227-240`), the WS has no lead change or cancel, and task dicts need to become `Task`
  again on the client.

### Mission control: many rooms, one fleet, one quota picture
**Pitch:** One window, one tab per repository, each a live room with its own lead, running at the
same time. A fleet strip across the top shows which CLI is working in which room right now
(claude in `hexmind`, codex in `agentdeck`, two opencode models in `Aether`). It also shows which
CLIs have hit quota in the last hour, and what the machine is carrying. When claude hits its usage
limit in one room, the other rooms know about it before they send claude work. When you queue
work in a room while its best member is busy elsewhere, it waits or routes around the busy member
without guessing.

**Why this project, specifically:**
- The process is already multi-room by construction. `_LIVE_ROOMS` is a WeakSet of every running
  room (`widget.py:100,138`), and each room has its own thread, loop and orchestrator.
- The widget takes `cwd` per instance (`widget.py:256`).
- The one piece of shared state is the stats ledger, and it is already shared across rooms because
  it is one file (`qt/stats.py:73`).

What's missing is the thing that makes several rooms smarter than several windows: shared
awareness of the CLIs. Today quota is discovered per task by regex after the fact (`QUOTA_RE`,
`core.py:39,1129`), and `fallback()` reads only its own room's members (`core.py:1141-1146`). The
agent CLI health view being designed now is the natural fleet strip, with live occupancy and quota
history added. This also fits Aether's direction as a multi-tool host, and it is the step that
makes the GUI clearly more than the TUI can ever be.

**What it'd take:**
- A new `hexmind/fleet.py` in core, not Qt. It is a process-wide registry of CLI occupancy and
  recent quota hits that `Orchestrator.fallback` and task launch can consult (opt-in, with no
  behaviour change for a single room).
- A `qt/mission.py` that holds N `HexmindWidget`s in tabs, plus a fleet strip fed by a `fleet`
  signal.
- Session restore of open rooms via `QSettings`, which the widget already uses for layout
  (`widget.py:443-455`).

---

## Ideas we deliberately left out

- **Jules desk.** `send_message` in `jules.py:190` has no caller, a session waiting for input
  currently fails the task with a link (`jules.py:380`), and `parse_activity` already produces a
  chat-shaped feed. So a reply-to-Jules panel is well grounded. It depends on an alpha API and a
  single optional member, so it ranked below the eight above. Revisit it if Jules becomes a regular
  teammate.
- **hcom terminal embedding** (embedding `hcom term` output into Qt). It was folded into Live tap
  as a "watch in terminal" action, because an embedded terminal emulator would be a new dependency
  for one backend.
- **Cut for being generic or already chosen:** themes, layout, icons (the visuals agent owns
  those), plus a standalone chain editor, a model browser and a settings dialog (already being
  designed).

# Variants Consolidation — one `main`, not three forks

Applies to: **Hexmind, agentdeck, Aether-Next** (same plan for each repo).
Written 2026-09-26. Copy this same file into every clone; don't edit per clone.

## The problem

Each project now exists as three diverging clones:

| Setup | Machine | What's different |
|---|---|---|
| **laptop** | Asahi (Fedora, aarch64) — daily driver | The original. Canonical `main`. |
| **mobile** | Small touch screens | Same logic, UI changed for touch. |
| **desktop** | CachyOS (x86_64) — home workhorse | More RAM, more/larger drives, multi-monitor. Deeper changes. |

Only `main` exists on GitHub. The mobile and desktop work lives **only in local
clones**, so if one of those disks dies, that work is gone. Permanent per-platform
branches also stop merging cleanly within months, and every fix has to be
applied three times.

## The target

One `main` per repo. The app picks its behavior **at runtime**; no fork
decides it.

```
core/          all logic — shared, platform-agnostic
ui/desktop/    default UI (laptop + CachyOS)
ui/mobile/     touch layout, bigger targets
```

- **UI choice:** auto-detect (screen size / touch) at startup; `--ui=mobile|desktop` overrides.
- **Hardware choice:** a host profile, detected with a file override:

```toml
# ~/.config/<app>/host.toml   (per machine, NOT committed)
profile    = "workhorse"          # laptop | workhorse | mobile
max_ram_gb = 64
monitors   = "auto"
storage    = ["/mnt/fast", "/mnt/bulk"]
```

Features that need big RAM, multiple drives, or multi-monitor switch on when the
profile or detection says the machine has them. Without a profile the app
falls back to lean laptop defaults.

- **Architecture differences** (aarch64 vs x86_64) are handled by a CI build
  matrix if needed, never by branches.
- **Booting from any drive** is bootloader config on CachyOS, not app
  code. Keep it out of these repos.
- **Host-profile code:** build it in ONE project first (Aether, the optional
  host). Pull it into a shared library only once a second project actually
  needs it.

## Step 1: get every clone's work onto GitHub (each setup does its own part)

Nothing gets merged yet. The goal is just that no work exists only on one disk.
**Do not push to or force-push `main` from the mobile or desktop clones.**

### If you are the **laptop** clone
1. `git status`: commit or stash anything uncommitted.
2. `git push origin main`. You are the base everything merges into.
3. Wait for mobile + desktop to finish Step 1, then do Step 2.

### If you are the **mobile** clone
1. `git status`: commit everything, including WIP (`wip:` prefix is fine).
2. `git switch -c variant/mobile` (or rename the current branch to it).
3. `git push -u origin variant/mobile`
4. Stop. Report the pushed commit hash back to the user.

### If you are the **desktop** (CachyOS) clone
1. `git status`: commit everything, including WIP.
2. `git switch -c variant/desktop`
3. `git push -u origin variant/desktop`
4. Also write down any machine-specific paths/values the code hardcodes
   (drive mounts, RAM limits, monitor names). These become `host.toml` keys.
5. Stop. Report the pushed commit hash back to the user.

Not sure which clone you are? Check `hostname` and `uname -m` (aarch64 means
the Asahi laptop, x86_64 means CachyOS). If it's still unclear, **ask the user
before doing anything**.

## Step 2: sort the changes (laptop clone, after all pushes)

For each variant branch:

```sh
git fetch origin
git diff $(git merge-base main origin/variant/mobile) origin/variant/mobile --stat
```

Put every change into one of these buckets:

| Bucket | Goes to |
|---|---|
| Bug fix / logic improvement, useful everywhere | straight into `core/` on `main` |
| Touch/small-screen UI | `ui/mobile/`, picked at runtime |
| Needs big RAM / drives / multi-monitor | `main`, gated on host profile |
| Hardcoded machine path/value | a `host.toml` key with a lean default |
| Obsolete / experiment | drop it (note it in the PR) |

Write the sorted list to `docs/CONSOLIDATION-<variant>.md` and **show it to
the user before merging**.

## Step 3: merge back

1. Mobile first (smaller, UI-only). Branch `merge/mobile` off `main`, apply the
   sorted changes, run tests, open a PR.
2. Desktop second, same way.
3. After both are merged: delete `variant/*` on GitHub, then on the mobile
   and desktop machines run `git fetch && git switch main && git reset --hard origin/main`.
   **The reset throws away local-only work. Confirm with the user first**
   and check that `git status` is clean and the variant branch was pushed.

## Rules from here on

- Keep branches short-lived: one feature, merged back within days.
- A platform difference goes behind a profile check or UI layer, never a new fork.
- Every machine pulls `main` before starting work and pushes when done.
- `host.toml` is per machine and never committed. Commit an example file
  (`host.example.toml`) instead.

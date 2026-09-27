# Example chains — templates, not bundled

These two chains are **not** shipped inside the `hexmind` package. They import agent
instructions with `from =`, and those agent files belong to a person, not to a package:

| chain | needs |
| :--- | :--- |
| `rip-it-apart.toml` | six `rip-it-apart-*.md` agents |
| `doc-chain.toml` | four `doc-chain-*.md` agents from a `doc-chain` checkout |

Bundling them meant every install showed a `/chains` listing that was two-thirds broken,
because the files they point at only exist on the machine where they were written.

Only **self-contained** chains ship in `hexmind/chains/`:

- `feature.toml` — inline instructions, nothing external
- `opencode-team.toml` — inline instructions, pinned free opencode models

## Use one

```sh
mkdir -p ~/.config/hexmind/chains
cp docs/examples/chains/rip-it-apart.toml ~/.config/hexmind/chains/
```

`~/.config/hexmind/chains/` wins over the bundled directory, and only one copy shadows a
bundled name — so copying `feature.toml` there is how you override it.

## `from =` takes a name or a path

A stage may name an agent instead of spelling out where it lives:

```toml
[[stages]]
name = "recon"
from = "rip-it-apart-recon-mapper.md"
```

Hexmind resolves a bare filename against, in order:

1. `~/.claude/agents/`
2. `~/.agents/agents/`
3. `./.claude/agents/` — the room's project
4. `./.agents/agents/`

`.md` and `.toml` are both tried, and the extension may be omitted. This is what makes the
feature usable: agents are per-user and per-project, so a package cannot know where they are.

A reference that **contains a path separator** is never searched for by name. If you wrote a
path and it is not there, that is reported as the error it is, rather than silently resolving
to some same-named file elsewhere.

Both forms work:

```toml
from = "~/.claude/agents/reviewer.md"    # explicit path — must exist as written
from = "reviewer.md"                     # searched in the standard agent dirs
```

`rip-it-apart.toml` here uses the explicit-path form, since its agents live in a specific
project checkout. Switch it to bare filenames if you keep them in `~/.claude/agents/`.

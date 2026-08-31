# SD AI Command Pack

[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Tests](https://img.shields.io/badge/tests-unittest-2E7D32)](#verify)
[![License: MIT](https://img.shields.io/github/license/platypeeps/sd-ai-command-pack)](LICENSE)
[![Source](https://img.shields.io/badge/source-GitHub-181717?logo=github)](https://github.com/platypeeps/sd-ai-command-pack)

## Overview

One repository, one prefix, one machine-scope install. The pack renders its
`sd-*` surfaces into the AI tools installed on a machine and gets out of the
way — eleven commands, the `sd-help` catalog, and the skills they draw on. It
does not install anything into the repositories you work in.

That last sentence is the design, not a summary of it. The previous version of
this pack copied roughly 56,000 lines of payload into every consuming
repository, kept those copies in sync through a release train, and needed a
plugin marketplace, a fleet registry, and a receipt protocol to do it. All of
that existed to solve a problem the pack had created for itself. The
replacement renders from `skills/` at install time, so there are no copies to
keep in sync, no versions to roll out, and nothing tracked in a repository that
the framework owns.

**What it writes on a machine:**

- `~/.claude/skills/sd-*/SKILL.md`
- `~/.codex/skills/sd-*/SKILL.md`
- `~/.config/opencode/commands/sd-*.md`
- `~/.claude/agents/sd-*.md`
- one `SessionStart` hook entry in `~/.claude/settings.json`, for
  `sd-handoff-restore`
- one line — `CLAUDE.local.md` — in the global git excludes

**What it writes in a repository:** nothing, ever. Work items live under
`docs/work/<date>-<slug>/` because you put them there; per-repo configuration
lives in `CLAUDE.local.md`, which is untracked by way of that one excludes line.
`bin/sd_install.py --repo` refuses outright if `CLAUDE.local.md` turns out to be
tracked, rather than edit a file under version control.

Agents render to Claude only. Codex keeps its agents as TOML with the
instructions embedded in a quoted string, and producing that would be a
translation layer — the one thing this renderer refuses to be, since a
translated file cannot be checked by comparing bytes. The limit is a test, not
a note: `tests/test_sd_agents.py` asserts nothing lands in `~/.codex/agents`.
The pack neither renders there nor removes what it finds there; what the test
guarantees is that the installer writes nothing, not that the directory is
absent. The three skills naming the agent trio all make the delegation optional,
so a Codex session runs those passes inline rather than losing them.

Antigravity is deliberately **not** rendered. Its skill format is byte-identical
to Claude's, but which of three candidate roots `agy` actually loads is
unresolved, and rendering into the wrong one would produce surfaces that appear
installed and never load — worse than absent, because nothing would report them
missing. Zero or all, never partial, is the rule; what the test asserts today
is the zero half of it — no `sd-*` under any of the three candidate roots —
because P1 has not passed and there is no all half to check yet.

## Install

```bash
git clone https://github.com/platypeeps/sd-ai-command-pack
cd sd-ai-command-pack
python3 bin/sd_install.py --user
```

The checkout you install from is the serving checkout: every rendered surface is
a copy of what is in it at that moment. Keep it on a clean `main` and update
with `--pull`, which fast-forwards and re-renders in one step and refuses to run
off `main` or over uncommitted changes.

| Command | What it does |
|---|---|
| `bin/sd_install.py --user` | Render every `sd-*` surface into this machine's platform homes |
| `bin/sd_install.py --status` | What is installed, what has drifted, what legacy residue remains |
| `bin/sd_install.py --pull` | Fast-forward the serving checkout (clean, on `main`) and re-render |
| `bin/sd_install.py --uninstall` | Remove exactly what the receipt records having written |
| `bin/sd_install.py --adopt-legacy` | Delete the pre-3e fleet installer's successor-less renders |
| `bin/sd_install.py --repo [PATH]` | Write the marked block into `PATH/CLAUDE.local.md` |

`--dry-run` prints what any of them would do and writes nothing. `--home DIR`
installs into a scratch directory instead of `$HOME`, which is how the tests
drive it.

### What it owns, and what it will not touch

The receipt at `~/.local/state/sd-ai-command-pack/installed.json` records every
path the installer wrote together with the digest of what it wrote. That single
fact is what makes the rest safe:

- A surface you rename or retire in `skills/` disappears from every platform on
  the next `--user`, because the receipt knows the old path was ours.
- A rendered file you have since edited by hand is **kept** and reported, never
  silently deleted.
- `--uninstall` removes those paths and nothing else. The global excludes line
  and any `CLAUDE.local.md` blocks are left alone; they are yours.
- If the receipt will not parse, it grants no delete authority at all — the
  installer converges forward and removes nothing it cannot account for.

## Commands

The twelve named surfaces — eleven commands plus `sd-help`, which the taxonomy
makes a skill because a catalog authorizes nothing — rendered identically to
every platform. Each is documented in its own `skills/sd-*/SKILL.md`, which is
the file that gets installed, so the documentation and the artifact are the
same object.

`skills/` also holds the skills these commands draw on — knowledge and
procedure with no standing side-effect authority, loaded when relevant rather
than invoked. They are not listed here: `sd-help` reads the installed tree at
runtime, which is the only inventory that cannot go stale. The one structural
difference is in the frontmatter, and it is what the taxonomy means: each of
the eleven commands sets `disable-model-invocation`, so invoking it is a
deliberate act; every other surface, `sd-help` included, does not.

| Command | Purpose |
|---|---|
| `sd-plan` | Interview into a work item under `docs/work/`, review it, open its branch |
| `sd-check` | Deterministic runner over the repo's own entrypoints |
| `sd-review` | Local review on the exact diff; findings dispositioned locally, never posted |
| `sd-ship` | Verify, commit enumerated paths, push, open the PR, settle, squash-merge |
| `sd-spec` | Update `docs/spec/**` on the PR branch |
| `sd-status` | Read-only: derived status, open PRs, branch-protection gaps |
| `sd-deps` | Batch-triage dependabot and renovate PRs |
| `sd-help` | Runtime catalog of installed `sd-*` surfaces |
| `sd-suggest` | File framework improvements to the configured tracker |
| `sd-skill-adopt` | Safety pre-screen, lint, and canonical transform for an incoming skill |
| `sd-map` | Supporting artifacts into an out-of-tree cache; never a gate, never scheduled |
| `sd-handoff` | Write the local session packet for this directory; `/clear` restores it |

## Maintaining

### Verify

```bash
make setup   # once
make check   # test + lint + audit
```

CI is four jobs, named here as branch protection sees them:

| Job | What it runs |
|---|---|
| `unittest` (matrix) | The suite on Ubuntu, Python 3.10 and 3.13, plus the installer coverage gate |
| `lint` | Ruff and mypy over `bin/` |
| `bash 3.2 syntax` | Every tracked shell script parsed by a bash 3.2 built from source |
| `security` | Bandit over `bin/`, zizmor over the workflows, ShellCheck |

The matrix means five reporting contexts and, with `strict: true`, six required
ones. `sd-status` reads the live protection object rather than any list written
here, so this table cannot silently disagree with what is enforced.

**Installer coverage is gated at 100% line and branch.** The gate enumerates its
subject from git rather than matching a glob, and declares a statement floor, so
neither adding an unmeasured module nor gutting the measured one can report
green. See `.github/scripts/check-installer-coverage.sh`, whose comments explain
why the floor moved from files to statements at step 3e.

```bash
PYTHON_BIN=python bash .github/scripts/check-installer-coverage.sh
```

The `bash 3.2 syntax` gate survives on a narrower rationale than it had. It
existed because the pack shipped shell that ran on whatever bash a consumer's
macOS provided, which is 3.2. Nothing is shipped now; what it still protects is
this repo's own three scripts under `.github/scripts/`, which `make check` runs
through `/bin/bash` on macOS.

**No macOS CI leg currently runs.** It was dropped to save runner cost, which
GitHub bills at ten times the Linux rate. macOS-specific behaviour is covered
only by the maintainer's local `make check` — one machine, not a gate. The leg
returns when the maintainer restores it by hand at the end of the
artifacts-as-product rollout. No date is set, so this paragraph stands until a
macOS CI job actually reports — that, not a promise, is what ends it.

### Where the work happens

This repository dogfoods its own artifacts. The rebuild is designed at
`docs/work/2026-08-29-artifacts-as-product/`, and every step of it lands as one
pull request that deletes what it replaces.

## License

MIT. See [LICENSE](LICENSE).

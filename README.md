# SD AI Command Pack

[![Python](https://img.shields.io/badge/Python-3.13%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Tests](https://img.shields.io/badge/tests-unittest-2E7D32)](#verify)
[![License: MIT](https://img.shields.io/github/license/platypeeps/sd-ai-command-pack)](LICENSE)
[![Source](https://img.shields.io/badge/source-GitHub-181717?logo=github)](https://github.com/platypeeps/sd-ai-command-pack)

## Overview

One repository, one prefix, one machine-scope install. The pack renders its
`sd-*` surfaces into the AI tools installed on a machine and gets out of the
way. `sd --help` and `sd-help` enumerate the installed commands and skills. It
does not install anything into the repositories you work in.

That last sentence is the design, not a summary of it. The previous version of
this pack copied roughly 56,000 lines of payload into every consuming
repository, kept those copies in sync through a release train, and needed a
plugin marketplace, a fleet registry, and a receipt protocol to do it. All of
that existed to solve a problem the pack had created for itself. The
replacement renders from `skills/` at install time, so there are no copies to
keep in sync, no versions to roll out, and nothing tracked in a repository that
the framework owns.

What renders is what a path names. `skills/paths.json` describes three
pipelines — **research**, sources to brief to handoff; **development**, plan to
build to ship; **act**, brief to draft to send — and the installer writes
exactly the skills those paths name. Every other skill lives in `contrib/`: in
this repository, versioned, documented, and not installed. `sd skill try
<name>` installs one for thirty days and writes down when it started; if
nothing used it by then, the next install run removes it and says so.

The split is not a ranking. Nothing decided it by usage, because no usage
counts existed — three ways of counting the same eight days of history gave
six skills, thirteen, and eighty-one. What a path can say is which skills are
steps in one sequence somebody actually runs, and that is what these three
say. A skill in `contrib/` is one command away, and use is what moves it.

**What it writes on a machine:**

- `~/.claude/skills/sd-*/SKILL.md`
- `~/.codex/skills/sd-*/SKILL.md`
- `~/.config/opencode/commands/sd-*.md`
- `~/.claude/agents/sd-*.md`
- three hook entries in `~/.claude/settings.json` — `SessionStart` for
  `sd-handoff-restore`, and `PreToolUse` and `UserPromptSubmit` for
  `sd-skill-use`. `bin/sd_install.py`'s `HOOK_SPECS` is the one list; this
  line describes it and does not govern it.
- one line — `CLAUDE.local.md` — in the global git excludes

**What it writes in a repository:** nothing, ever. Work items live under
`docs/work/<date>-<slug>/` because you put them there; per-repo configuration
lives in `CLAUDE.local.md`, which is untracked by way of that one excludes line.
`bin/sd_install.py --repo` refuses outright if `CLAUDE.local.md` turns out to be
tracked, rather than edit a file under version control.

That block's `mode:` line carries one of three values, and the workflow each
selects is stated in [WORKFLOW.md](WORKFLOW.md):

- `full` — planning artifacts live in `docs/work/` in the repository, and the
  whole path runs; an unattended merge additionally needs `merge: auto` on the
  item's row.
- `minimal` — no work items anywhere, and the small-change path only.
- `guest` — planning artifacts go to the fork's integration branch, the loop
  stops at pull-request-ready, and nothing is posted upstream.

Without a `mode:` line the mode is detected, and detection only ever lowers a
line you wrote.

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

## Standing operator authorization

The pack supports standing permission across consuming repositories. Installation grants neither permission for a new user.
After that operator explicitly grants permission, record it through the existing configuration commands:

```sh
sd config set sd.external_reviews configured
sd config set sd.merge_authorization controlled
```

These values live in `~/.config/sd-ai-command-pack/config.json`; `XDG_CONFIG_HOME` overrides the configuration root.
`sd config get`, `list`, and `unset` inspect or remove settings. No personal grant ships in this repository.

`configured` allows private code and scoped review context to the operator's eligible configured providers, including future entries.
A local `reviewers` list restricts recipients; an explicit empty value denies review.
Machine `sd.external_reviews deny` vetoes local consent. Missing machine policy requires explicit local consent.
The installer preserves restrictions and refuses malformed answers. It cannot recover historical empty answers whose keys were erased.

`controlled` permits the assistant to merge active, in-scope PR work in repositories the user controls.
An explicit instruction to wait overrides it. `ask`, or an absent setting, requires task-specific permission.
The setting is read by the assistant, not by `sd-ship`: `sd config` validates and stores it, and no tool in `bin/` consults it.
Ownership, review, CI, protection, and runner gates remain mandatory. This setting starts no background work.
See [the workflow policy](WORKFLOW.md#standing-authorization) for resolution and limits.

## Daily workflow

The dashboard and CLI use the same `sd_db` operations from `system/local-sd-db`.
Capture a task without a checkout or planning document:

```bash
sd task add "Investigate the delayed pipeline" --priority 1
sd today
sd task status 42 in_progress
sd task note 42 --body "Reproduced with the staging input"
sd task status 42 done
```

`sd store items --open` lists the backlog; `sd store item 42 --json` includes
history and a revision that edits can require with `--if-revision`. Notes,
priorities, due dates and task status save directly to the database. GitHub
issues are optional external references, with their last successful sync shown
separately from local progress.

Repository work uses `sd work register`, `sd work relink`, `sd work cancel`,
and `sd work deliver`. `sd work register docs/work/<item>/prd.md` makes the row
that owns a planning folder already on disk, reading its title and date from
the file's own frontmatter; it applies only where the repository's status
source is the database, and refuses a repository whose files still own status.
Delivery verifies a full commit and its delivery trailer against the default
branch before recording completion. Cancelling work requires a reason and
completes immediately in the database. Neither operation writes a status file
or creates a bookkeeping pull request.

From the writing checkout, `sd writing list`, `sd writing readiness --piece
YEAR/slug`, and `sd writing stage` share the dashboard's writing controls.
Import and cutover have separate preview and verification commands. Once the
repository uses rows, routine stage, parking and metadata changes leave content
files untouched. See the writing pack's `.claude/reference/database-workflow.md`
for review evidence and recovery commands.

`sd jobs list` and `sd assignments list` show operational state. Job retry and
cancellation require a recognized installed job and a fresh state check;
unsupported controls explain why they are unavailable. Cancelling a queued
assignment does not claim to terminate an independently running process.

The current dashboard and its installation instructions live in
`system/local-project-dashboard`. It binds to loopback; remote access requires
an explicitly configured private HTTPS front door and operator identity.

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

- A surface you rename or retire in `skills/` — or move to `contrib/` —
  disappears from every platform on the next `--user`, because the receipt
  knows the old path was ours.
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

`skills/` and `contrib/` also hold the skills these commands draw on —
knowledge and procedure with no standing side-effect authority, loaded when
relevant rather than invoked. They are not listed here: `sd-help` reads the
installed tree at runtime, and `sd skill list` reads both roots, which are the
only two inventories that cannot go stale.

Three of the twelve named surfaces — `sd-deps`, `sd-map` and `sd-skill-adopt` —
are in `contrib/` rather than on a path. They are still commands, and the table
below still describes them; they install with `sd skill try` rather than by
default. A command is a thing that authorizes side effects, which is a claim
about the frontmatter, not a claim that everyone needs it installed. The one structural
difference is in the frontmatter, and it is what the taxonomy means: each of
the eleven commands sets `disable-model-invocation`, so invoking it is a
deliberate act; every other surface, `sd-help` included, does not.

**Runs as** says whether there is something to execute. `bin/` is a shipped
entrypoint you can run; **prose** is a sequence an agent follows, with no
runner behind it — the skill is the implementation. Six of the twelve are
prose today, each saying so in its own "State of the tooling" section, and
`tests/test_skill_frontmatter.py` fails if one of them ever names a `bin/`
command without that sentence, or keeps the sentence after the command
arrives.

| Command | Runs as | Purpose |
|---|---|---|
| `sd-plan` | prose | Interview into a work item under `docs/work/`, review it, open its branch |
| `sd-check` | `bin/` | Deterministic runner over the repo's own entrypoints |
| `sd-review` | `bin/` | Local review on the exact diff; findings dispositioned locally, never posted |
| `sd-ship` | `bin/` | Review committed work, prepare its PR, verify merge authority, and reconcile delivery |
| `sd-spec` | prose | Update `docs/spec/**` on the PR branch |
| `sd-status` | `bin/` | Read-only: derived status, open PRs, branch-protection gaps and the states this repo accepts (`.github/sd-status.json`) |
| `sd-deps` | prose | Batch-triage dependabot and renovate PRs |
| `sd-help` | prose | Runtime catalog of installed `sd-*` surfaces |
| `sd-suggest` | prose | File framework improvements to the configured tracker |
| `sd-skill-adopt` | `bin/` | Safety pre-screen, lint, and canonical transform for an incoming skill |
| `sd-map` | prose | Supporting artifacts into an out-of-tree cache; never a gate, never scheduled |
| `sd-handoff` | `bin/` | Write the local session packet for this directory; `/clear` restores it |

## Maintaining

### Verify

```bash
make setup   # once
make check   # test + lint + audit
```

CI is four jobs, named here as branch protection sees them:

| Job | What it runs |
|---|---|
| `unittest` | The suite on Ubuntu, Python 3.13, plus the installer coverage gate |
| `lint` | Ruff and mypy over `bin/` |
| `bash 3.2 syntax` | Every tracked shell script parsed by a bash 3.2 built from source |
| `security` | Bandit over `bin/`, zizmor over the workflows, ShellCheck |

`sd-status` compares the live protection object with the contexts the
workflow files produce, not with this table, so a row here can go stale
without anything saying so; the workflow files are the inventory.

One protection state on `main` is accepted rather than open, and it is recorded
in tracked `.github/sd-status.json` rather than in prose: a pull request is
required and asks for **zero** approving reviews, because with `enforce_admins`
on and one maintainer, GitHub's refusal of self-approval makes requiring one
approval a lock and deleting the review object a loss of the pull-request
requirement. `sd-status` prints it every run as `ok  [reviews] accepted …` with
the condition that ends it, and stops accepting it the moment the live
protection state stops matching what the file pins.

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
`docs/work/archive/2026-09/2026-08-29-artifacts-as-product/`, and every step of it lands as one
pull request that deletes what it replaces.

## License

MIT. See [LICENSE](LICENSE).

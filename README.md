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

A repository can extend the framework from the other side. `sd plugin add`
registers a **domain pack** — its own manifest, its own `<prefix>-*` skills, its
own rows — and three exist today. What a manifest may declare, and what the
other halves are, is in [domain packs](docs/domain-packs.md).

**What it writes on a machine:**

- `~/.claude/skills/sd-*/SKILL.md`
- `~/.codex/skills/sd-*/SKILL.md`
- `~/.config/opencode/commands/sd-*.md`
- `~/.claude/agents/sd-*.md`
- `~/.local/bin/sd` and `~/.local/bin/sd-*` — one symlink per executable in
  `bin/`, so the commands resolve from any directory; `--bin-dir DIR` puts them
  elsewhere. The installer never edits `PATH`: `--user` warns when the link
  directory is not on it, and `--status` says how many commands resolve.
- three hook entries in `~/.claude/settings.json` — `SessionStart` for
  `sd-handoff-restore`, and `PreToolUse` and `UserPromptSubmit` for
  `sd-skill-use`. `bin/sd_install.py`'s `HOOK_SPECS` is the one list; this
  line describes it and does not govern it.
- one line — `CLAUDE.local.md` — in the global git excludes

**What it writes in a repository:** nothing at machine-scope install. Everything
below is written by something you invoke against that repository, and nothing
else is. Its executables write these paths, and no others:

- `CLAUDE.local.md` — per-repo configuration, from `python3 bin/sd_install.py --repo`.
  Untracked by way of that one excludes line, and that command refuses outright
  if `CLAUDE.local.md` turns out to be tracked, rather than edit a file under
  version control.
- `.github/workflows/sd-review-route.yml` — the routing lane, from `sd-review
  setup-github`, which runs only in a `full`-mode repository. **Tracked.** With
  `--remove-legacy` it also deletes the three files the old `sd-github-review`
  installer left.
- `docs/work/<item>/.citations.tsv` — the citation baseline, one per active work
  item, from `sd-docs-lint --update-citations`. **Tracked.**
- `build/` — HTML from `sd-research-kit render`, into the research repository you
  are standing in. Gitignored.
- `CLAUDE.md` — the research-repo standard in short form, from `sd-research-kit
  init-claude-md`, into a research repository that has none. **Tracked.** Written
  once: the verb refuses if a copy is already there, and there is no re-sync
  verb, because a repo may state parts of the template differently on purpose.
  From then on `sd-research-kit review` reports where the copy and
  `skills/sd-research-repo/templates/CLAUDE.md` disagree, and the repo's own
  `## Local overrides of the shared template` section records the disagreements
  that are deliberate.

Two skills add paths of their own, both tracked. Invoking either is the approval
to write, and neither writes anywhere else:

- `sd-plan` — `docs/work/<YYYY-MM-DD>-<slug>/`: `prd.md`, plus `README.md` when
  the directory is new, plus `design.md` and `implement.md` only when you ask
  for them. `--work-dir` selects a root other than `docs/work`; `--decision`
  writes `docs/decisions/<YYYY-MM-DD>-<slug>.md` instead of a work item.
- `sd-spec` — `docs/spec/**`, rewritten in place on the branch so the
  correction lands with the change, plus the learnings page under `--retro`.

Every other skill either edits documents that are already yours or reads only.

`sd attribute` adds one empty commit to `HEAD` and writes no file. Everything
else the pack writes lands outside the repository entirely.

That `CLAUDE.local.md` block carries a `mode:` line with one of three values,
and the workflow each selects is stated in [WORKFLOW.md](WORKFLOW.md):

- `full` — planning artifacts live in `docs/work/` in the repository, and the
  whole path runs; an unattended merge additionally needs `runner_merge: auto`
  on the repository row, set with `sd-db.sh repo runner-merge <path> auto`.
- `minimal` — no work items anywhere, and the small-change path only.
- `guest` — planning artifacts go to the fork's integration branch, the loop
  stops at pull-request-ready, and nothing is posted upstream.

Without a `mode:` line the mode is detected, and detection only ever lowers a
line you wrote.

Agents render to Claude only. Codex agent TOML translation remains outside this installer's scope.
The Codex skill metadata adapter does not change that boundary.
The limit is a test, not
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
sd config set sd.assistant_merge controlled
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

`sd.copilot_review` says when `sd-ship` requests a GitHub Copilot review by itself: `deep` on deep-tier changes only, `always` on every reviewing tier, `never` on none.
Unset reads `deep`, so every repository gets Copilot on deep changes without a per-repository file.
A repository's `.github/sd-review.json` `copilot_review.automatic_deep` overrides it when the file names the key; a file that does not name it inherits.
`sd-review --explain` reports the effective policy and its source (`repository`, `machine config`, `machine default`) under `remote_reviews.copilot`.
`sd-ship` applies the setting as it stands at dispatch to the tiers the retained passes recorded, so a change takes effect without another review.
`sd-ship --copilot-review request|skip` still overrides both for one prepare.
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

A task a commit delivered closes with that commit named:
`sd task status 42 done --delivered-by <full-sha>`. The SHA is verified the
way `sd work deliver` verifies one — reachable from the checkout's default
branch and carrying a `Delivers: sd:42` trailer in the block
`git interpret-trailers` reads — and is recorded on the transition, so the
history answers "what delivered this" for a task and for a work item alike.
A commit that states the trailer outside that block is refused by name rather
than reported as carrying none. An item that belongs to no checkout has no
default branch to verify a commit against, so `--delivered-by` on a
`personal` item, or on a `followup` filed off every checkout, is refused for
that reason and the item closes without it. A `followup` filed in a
registered checkout carries that checkout since sd:809, but only a task's
move to done records a delivering commit, so the flag is refused there too,
on that second reason, and the item closes without it just the same.

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
The row's branch is the branch the work happens on — the checkout's own local
branch when that is not the default, and otherwise nothing at all, never a
remote-tracking name.
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
| `python3 bin/sd_install.py --user` | Render skills and link commands into `~/.local/bin`; use `--bin-dir DIR` for another directory |
| `python3 bin/sd_install.py --status` | Report installed source, drift, and legacy residue without failing on drift |
| `python3 bin/sd_install.py --verify --json` | Read-only: fail on receipt, source, rendered-file, command-resolution, or bounded help-probe errors |
| `python3 bin/sd_install.py --pull` | Fast-forward the clean serving checkout on `main`, then render |
| `python3 bin/sd_install.py --uninstall` | Remove receipt-owned renders, hooks, and command links; preserve modified files and retargeted links |
| `python3 bin/sd_install.py --adopt-legacy` | Delete the pre-3e fleet installer's successor-less renders |
| `python3 bin/sd_install.py --repo [PATH]` | Write the marked block into `PATH/CLAUDE.local.md` |

`--verify` runs no provider, meter, database migration, or installation operation.
It resolves every executable through the current `PATH` and rejects commands from another checkout.
Relative or empty `PATH` entries fail verification before help probes run.
It runs only `sd --help`, `sd-review --help`, and `sd-ship --help`, with five-second limits.
Other commands receive interpreter and resolution checks, but remain explicitly unsmoked.
Verification requires the receipt's clean source commit; staged source changes are not an installed verification pass.

### Codex invocation metadata

Use `$sd-review`, `$sd-ship`, or another installed skill name in Codex.
Codex CLI also provides `/skills`; installed skills are not individual `/sd-*` commands.
Restart Codex if updated skills do not appear.
See [OpenAI skill documentation](https://developers.openai.com/es-419/docs/build-skills).

The installer preserves canonical Claude command markers.
For Codex skills, it translates `disable-model-invocation: true` into `policy.allow_implicit_invocation: false` in `agents/openai.yaml`.
An explicit `false` marker becomes `true`; absent markers add no policy.
The Markdown body and other source metadata remain unchanged.
Generated policy files belong to the installation receipt and retain drift protection during removal.
Failed installations restore unchanged generated policies to their prior state; concurrent changes remain untouched.
Conflicting or unsupported invocation metadata refuses installation before rendering.
The adapter accepts plain block-mapping keys and lowercase booleans; other metadata sections remain opaque.
Invocation booleans cannot have indented continuation lines.
Claude agents and OpenCode rendering remain unchanged.

`--dry-run` prints what any of them would do and writes nothing. `--home DIR`
installs into a scratch directory instead of `$HOME`, which is how the tests
drive it. `--bin-dir DIR` links the commands somewhere other than
`~/.local/bin`, and the receipt remembers the directory, so a later `--user`
or `--pull` without the flag links there again; a link already pointing into
this checkout is kept as it is, and anything at a link's path that is not such
a link makes `--user` refuse by name and write nothing.

If you commit to this checkout, `make hooks` arms the pre-commit tier: it
links `.git/hooks/pre-commit` to the tracked `hooks/pre-commit`, which runs
Ruff over the staged Python and the two whole-tree test passes
(`tests.test_code_health`, `tests.test_doc_citations`) in about five seconds
and prints its own wall time against the budget its header states.
`SD_SKIP_HOOKS=1 git commit` skips it with a notice. The hook is one per
clone: the link sits in the clone's common `.git/hooks`, its target is the
relative `../../hooks/pre-commit`, so it reads the main checkout's tracked
file and every linked worktree shares it, whichever worktree ran `make
hooks`; the target refuses to replace anything else already at that path; it never
sets `core.hooksPath` and refuses to run while one is set, since git would
then place the link under that directory, and the directory is not
`.githooks/`, because `sd-status` reports both of those as the retired gate
stack's residue. This is
a setting of the clone, not a render, so `--user` does not make it and
`--uninstall` does not remove it; `bin/sd_install.py` is unchanged, and folding
the hook into `--user` is the owner's call.

### What it owns, and what it will not touch

The receipt at `~/.local/state/sd-ai-command-pack/installed.json` records every
path the installer owns: written by it, or an existing link to this checkout it
adopted. A render row carries the digest of what it wrote, and a link row the
target the link points at. That single fact is what makes the
rest safe:

- A surface you rename or retire in `skills/` — or move to `contrib/` —
  disappears from every platform on the next `--user`, because the receipt
  knows the old path was ours.
- A rendered file you have since edited by hand is **kept** and reported, never
  silently deleted.
- `--uninstall` removes those paths and nothing else. A recorded link that no
  longer points into this checkout is left and reported, a link the receipt
  never named is never touched, and the link directory stays. The global
  excludes line and any `CLAUDE.local.md` blocks are left alone; they are yours.
- If the receipt will not parse, it grants no delete authority at all — the
  installer converges forward and removes nothing it cannot account for.

## Commands

There are ten named surfaces: nine commands plus `sd-help`.
The taxonomy makes `sd-help` a skill because a catalog authorizes nothing.
All platforms preserve Markdown bodies.
Codex invocation metadata uses the [adapter](#codex-invocation-metadata).
Each surface has one `skills/sd-*/SKILL.md` file.
That file is both the installed artifact and its documentation.

`skills/` and `contrib/` also hold the skills these commands draw on —
knowledge and procedure with no standing side-effect authority, loaded when
relevant rather than invoked. They are not listed here: `sd-help` reads the
installed tree at runtime, and `sd skill list` reads both roots, which are the
only two inventories that cannot go stale.

`sd-skill-adopt` is the only named surface in `contrib/`.
It installs with `sd skill try` instead of the default installer.
It remains a command because it authorizes side effects.
Each of the nine commands sets `disable-model-invocation`.
Every other surface, including `sd-help`, omits that marker.

**Runs as** identifies the execution form.
`bin/` means the pack ships an executable entry point.
**prose** means an agent follows the skill without a runner.
For prose surfaces, the skill is the implementation.
Four of the ten are prose.
Each prose skill has a "State of the tooling" section.
`tests/test_skill_frontmatter.py` checks each claim against the filesystem.

| Command | Runs as | Purpose |
|---|---|---|
| `sd-plan` | prose | Interview into a work item under `docs/work/`, review it, open its branch |
| `sd-check` | `bin/` | Deterministic runner over the repo's own entrypoints |
| `sd-review` | `bin/` | Local review on the exact diff; findings dispositioned locally, never posted |
| `sd-ship` | `bin/` | Review committed work, prepare its PR, verify merge authority, and reconcile delivery |
| `sd-spec` | prose | Update `docs/spec/**` on the PR branch |
| `sd-status` | `bin/` | Read-only: derived status, open PRs, branch-protection gaps and the states this repo accepts (`.github/sd-status.json`) |
| `sd-help` | prose | Runtime catalog of installed `sd-*` surfaces |
| `sd-suggest` | prose | Record framework friction as a local proposal; publish only when asked |
| `sd-skill-adopt` | `bin/` | Safety pre-screen, lint, and canonical transform for an incoming skill |
| `sd-handoff` | `bin/` | Write the local session packet for this directory; `/clear` restores it |

## Maintaining

### Verify

```bash
make setup   # once
make check   # test + lint + audit + docs-lint
```

CI is two gating jobs in `tests.yml`, named here by the status context GitHub
emits for each (the matrix job's context carries its matrix values), plus the
advisory `route` job in `sd-review-route.yml`:

| Context | What it runs |
|---|---|
| `unittest (ubuntu-latest, 3.13)` | The suite on Ubuntu, Python 3.13, plus the installer coverage gate |
| `lint` | Ruff over `bin/` and `tests/` and mypy over `bin/` (the path lists are `LINT_RUFF_PATHS` and `LINT_MYPY_PATHS` in the `Makefile`, read rather than restated), `sd-docs-lint` over this checkout's `docs/`, then Bandit over `bin/`, zizmor over the workflows, and ShellCheck over the tracked shell |

`sd-status` compares the live protection object with the contexts the
workflow files produce, not with this table, so a row here can go stale
without anything saying so; the workflow files are the inventory.

`main` is currently unprotected, and that is an accepted gap rather than an
open one, recorded in tracked `.github/sd-status.json` under the id
`unprotected` with the reason and the condition that ends it (a second
account with push or merge rights). `sd-status` reports it every run as
accepted and stops accepting it the moment the live state stops matching what
the file pins. While protection is gone there are no required contexts, and
`sd-ship merge` refuses to run: it reads the protection object before it
reads the pull request's checks and refuses a missing one
(`bin/sd_ship_remote.py`, `protection()`). Merges land by hand with
`gh pr merge` after the maintainer reads the checks.

**Installer coverage is gated at 100% line and branch.** The gate enumerates its
subject from git rather than matching a glob, and declares a statement floor, so
neither adding an unmeasured module nor gutting the measured one can report
green. See `.github/scripts/check-installer-coverage.sh`, whose comments explain
why the floor moved from files to statements at step 3e.

```bash
PYTHON_BIN=python bash .github/scripts/check-installer-coverage.sh
```

The bash 3.2 syntax gate runs in `make lint` and in no CI job. It existed
because the pack shipped shell that ran on whatever bash a consumer's macOS
provided, which is 3.2. Nothing is shipped now; what it still protects is this
repo's own three scripts under `.github/scripts/`, which `make check` runs
through `/bin/bash` on macOS. The CI job that built bash 3.2 from source to
run the same gate on Linux was cut for that reason (sd:10, criterion 17).

**No macOS CI leg currently runs.** It was dropped to save runner cost, which
GitHub bills at ten times the Linux rate. macOS-specific behaviour is covered
only by the maintainer's local `make check` — one machine, not a gate. The leg
returns when the maintainer restores it by hand at the end of the
artifacts-as-product rollout. No date is set, so this paragraph stands until a
macOS CI job actually reports — that, not a promise, is what ends it.

### Where the work happens

This repository dogfoods its own artifacts.
The [current architecture](docs/current-architecture.md) describes the resulting design.

## License

MIT. See [LICENSE](LICENSE).

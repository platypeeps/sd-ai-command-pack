# SD AI Command Pack

[![Trellis](https://img.shields.io/badge/Trellis-trytrellis.app-255E63)](https://trytrellis.app/)
[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Tests](https://img.shields.io/badge/tests-unittest-2E7D32)](#verify)
[![License: MIT](https://img.shields.io/github/license/platypeeps/sd-ai-command-pack)](LICENSE)
[![Source](https://img.shields.io/badge/source-GitHub-181717?logo=github)](https://github.com/platypeeps/sd-ai-command-pack)

## Overview

Install reusable AI workflow helpers into
[Trellis-managed repositories](https://trytrellis.app/). The current pack is
focused on Trellis enrichment: start, continue, finish-work, local review, PR
creation/review, full-codebase local review, review learnings, full-check,
post-merge housekeeping, and update-spec workflows. The repository and `sd`
command namespace are intentionally
broader than that initial scope, so future skills, commands, scripts, docs, or
rules may cover adjacent AI workflow support that is not strictly
Trellis-specific.

This pack only works in a repo that already has Trellis installed and
initialized. If `trellis` is not available yet, follow the official
[Trellis install and first-task instructions](https://docs.trytrellis.app/start/install-and-first-task)
first; they cover installing the CLI with
`npm install -g @mindfoldhq/trellis@latest` and running `trellis init` so the
target repo has `.trellis/config.yaml`.

The current Trellis-focused pack installs:

- shared `sd-*` skills under `.agents/skills/`
- helper scripts under `scripts/`
- the installed usage guide at `docs/SD_AI_COMMAND_PACK.md`
- Prism defaults under `.prism/`
- Gito defaults under `.gito/`
- platform command, prompt, workflow, or native-skill adapters for Trellis'
  supported AI-tool platforms when the matching active Trellis platform is
  present
- a managed `sd-ai-command-pack` guidance block in
  `.github/copilot-instructions.md` for GitHub Copilot installs

The exact installed file set is defined by `manifest.json` and validated in
target repos by `scripts/sd-ai-command-pack-install-audit.py`.

The shared skills own the workflows. Platform command and prompt files are thin
entry points that tell the agent to load the appropriate shared skill.
Codex exposes pack entry points as enabled skills named `sd-start`, `sd-continue`,
`sd-finish-work`, `sd-create-pr`, `sd-work-backlog`, `sd-work-designs`,
`sd-full-check`, `sd-housekeeping`, `sd-review-pr`, `sd-review-local`,
`sd-review-local-all`, `sd-review-learnings`, and `sd-update-spec`; type
`/sd` in Codex command completion or invoke them explicitly with
`$sd-review-pr`-style skill mentions.
User-facing command adapters live under the `sd` namespace so pack-owned
wrappers do not collide with Trellis-owned generated `/trellis:*` commands on
future `trellis update` runs. Command-capable adapters expose either
namespaced `sd/<command>` files or flat `sd-<command>` files, matching the
platform convention Trellis uses for that tool. Skill-only adapters install the
same `sd-*` skills into the platform's native skill root.
The update-spec workflow runs the Trellis-provided `trellis-update-spec` skill
as-is, refreshes repo-owned repospec artifacts through existing maintenance
infrastructure when available, then adds an explicit architectural-overview
check and rebuilds a repo-local `.obsidian-kb` folder of copied
repository-knowledge files.
The start, continue, and finish-work wrappers similarly delegate to
Trellis-provided `trellis-start`, `trellis-continue`, and
`trellis-finish-work` skills without changing their behavior.
On Claude Code — where Trellis ships a SessionStart hook instead of a
`trellis-start` skill — the start wrapper derives the same session context
from `.trellis/scripts/get_context.py` directly, and the continue and
finish-work wrappers accept the installed `trellis:continue` and
`trellis:finish-work` command names as valid resolutions.
The installed `docs/SD_AI_COMMAND_PACK.md` file gives humans and agents a
repo-local usage guide for the commands, script, environment variables, local
review-provider behavior when available, and troubleshooting steps.

Quick links:

- [Overview](#overview)
- [Commands](#commands)
- [Configuration Quick Reference](#configuration-quick-reference)
- [Install](#install)
- [Verify](#verify)
- [Releasing](#releasing)
- [Fleet Rollout](#fleet-rollout)
- [Direct-to-main Chore Commits](#direct-to-main-chore-commits)
- [Supported Adapters](#supported-adapters)
- [License](#license)
- [Upstream Path](#upstream-path)

## Commands

The installed guide has the full command behavior, environment variables,
managed-block examples, local-review exclusions, and troubleshooting details:
[docs/SD_AI_COMMAND_PACK.md](docs/SD_AI_COMMAND_PACK.md#commands).

### Command Names And Adapters

Claude and Gemini expose wrappers as namespaced commands such as
`/sd:review-pr`; other command-capable platforms use flat `sd-<command>` or
`sd/<command>` entries according to their native convention. Skill-only
platforms expose native `sd-*` skills. See [Supported Adapters](#supported-adapters)
for the platform matrix and command shapes.

### sd-start

Initializes Trellis session context through the existing `trellis-start`
behavior. Claude Code derives equivalent context from
`.trellis/scripts/get_context.py` because Claude's Trellis install does not ship
a `trellis-start` skill.

### sd-continue

Resumes the current Trellis task through the target repo's existing
`trellis-continue` behavior or installed `trellis:continue` command.

### sd-finish-work

Wraps Trellis finish-work and records complete journal entries through
`scripts/sd-ai-command-pack-record-session.py` so placeholders are not committed.

### sd-create-pr

Runs `sd-update-spec`, stages only intended files, commits and pushes the current
feature branch, creates or reuses the branch PR, and hands off to `sd-review-pr`.
It detects the default branch instead of assuming `origin/main`.

### sd-work-backlog

Processes Trellis backlog tasks sequentially: pick one implementation-ready
task, implement it, publish through `sd-create-pr`, merge and clean up through
`sd-housekeeping`, then address or record follow-ups before selecting another
task.

### sd-work-designs

Reviews existing Trellis tasks that have real PRDs but still need `design.md`
and/or `implement.md`, writes implementation proposals and execution guidance
into those task artifacts, parks tasks that need user input, and reports links
to every planning document it created or updated.

### sd-full-check

Runs the deterministic local verification gate before PR readiness. Prism can
run automatically when available; Gito is opt-in through
`SD_AI_COMMAND_PACK_FULL_CHECK_GITO=1` because it may need network access,
local caches, and LLM credentials.

### sd-review-pr

Runs the deterministic local PR gate with Prism and Gito disabled, requests the
configured remote reviewer, addresses review comments or CI failures, and
re-requests review after each pushed fix up to the configured round limit.

### sd-review-local

Runs configured local review providers against local changes, or against the
current branch when no local changes exist, then enters a user-selected fix loop.

### sd-review-local-all

Uses the same local-review fix loop against the full checked-out repository. The
complete Prism/Gito exclusion and retry behavior lives in the installed guide's
[Local Review](docs/SD_AI_COMMAND_PACK.md#local-review) section.

### sd-review-learnings

Scans local diffs and optional recent GitHub review comments for repeated review
patterns, then updates a managed learning block when requested.

### sd-update-spec

Runs the existing Trellis `trellis-update-spec` skill, refreshes repo-owned
repospec or repository-map artifacts when maintained by the target repo, updates
an existing architecture overview only when warranted, and refreshes the
repo-local `.obsidian-kb/` copy folder.

### sd-housekeeping

Ends a development stream by running finish-work before merge, merging only when
the PR is clean and comment-free, then switching to the default branch,
fast-forwarding, deleting merged refs, and reporting the final clean state.

## Configuration Quick Reference

| Variable | Purpose | Default |
| --- | --- | --- |
| `SD_AI_COMMAND_PACK_FULL_CHECK_REVIEW_PREFLIGHT_COMMAND` | Extra repo-local preflight command for full-check. | unset |
| `SD_AI_COMMAND_PACK_FULL_CHECK_PACKAGE_SCRIPTS` | Package scripts to run when a compatible package runner is available. | `typecheck lint test:unit test:integration build test:e2e` |
| `SD_AI_COMMAND_PACK_FULL_CHECK_SKIP_PACKAGE_SCRIPTS` | Boolean flag to skip all package-script checks. | unset |
| `SD_AI_COMMAND_PACK_FULL_CHECK_PRISM` | Prism mode for full-check; use `0` to skip or `required` to fail when unavailable. | `auto` |
| `SD_AI_COMMAND_PACK_FULL_CHECK_GITO` | Enables Gito during full-check. | `0` |
| `SD_AI_COMMAND_PACK_FULL_CHECK_GITO_OUT_DIR` | Gito report directory for full-check. | `.build/review/gito` |
| `SD_AI_COMMAND_PACK_INSTALL_AUDIT` | Controls structural post-install audit; unset warns and continues, `0` skips, and `required` fails when unavailable. | unset |
| `SD_AI_COMMAND_PACK_FULL_CHECK_KB` | Obsidian KB freshness check in full-check; `auto` checks only when `.obsidian-kb/` exists, `0` skips, `required` fails when unavailable or stale. | `auto` |
| `SD_AI_COMMAND_PACK_FULL_CHECK_RELEASE_BASE_REF` | Base ref used by pack-source full-check to confirm shipped payload changes include a manifest version bump. | full-check base ref |
| `SD_AI_COMMAND_PACK_CREATE_PR_BASE` | Base branch override for `sd-create-pr`; unset detects the GitHub default branch. | unset |
| `SD_AI_COMMAND_PACK_CREATE_PR_BRANCH` | Feature branch name for `sd-create-pr` when it starts on the repository default branch. | auto-derived `codex/<slug>` |
| `SD_AI_COMMAND_PACK_CREATE_PR_BRANCH_SLUG` | Slug source used to derive `codex/<slug>` when `SD_AI_COMMAND_PACK_CREATE_PR_BRANCH` is unset. | unset |
| `SD_AI_COMMAND_PACK_CREATE_PR_COMMIT_MESSAGE` | Commit message used by `sd-create-pr` when it creates a commit and the user did not provide a message. | `chore: prepare pull request` |
| `SD_AI_COMMAND_PACK_CREATE_PR_DRAFT` | Create the PR as draft when set to `1`, unless the user explicitly asks for ready. | unset |
| `SD_AI_COMMAND_PACK_REVIEW_LOCAL_TOOLS` | Local review tool set for `sd-review-local` or `sd-review-local-all`; unset uses the runner default. | unset |
| `SD_AI_COMMAND_PACK_REVIEW_LOCAL_<TOOL>_COMMAND` | Custom command for a named local review provider. | unset |
| `SD_AI_COMMAND_PACK_REVIEW_LOCAL_ALL_<TOOL>_COMMAND` | Full-codebase custom command for a named provider; unset falls back to the non-`ALL` command. | unset |
| `SD_AI_COMMAND_PACK_REVIEW_LOCAL_SEMGREP_COMMAND` | Example Semgrep custom-provider command for `sd-review-local`; follows the generic `<TOOL>` command naming pattern. | unset |
| `SD_AI_COMMAND_PACK_REVIEW_LOCAL_ALL_SEMGREP_COMMAND` | Example Semgrep custom-provider command for `sd-review-local-all`; falls back to the non-`ALL` Semgrep command when unset. | unset |
| `SD_AI_COMMAND_PACK_REVIEW_LOCAL_GITO_MAX_ATTEMPTS` | Max Gito attempts for HTTP 429 provider rate limits. | `2` |
| `SD_AI_COMMAND_PACK_REVIEW_LOCAL_GITO_RETRY_DELAY_SECONDS` | Initial Gito retry delay. | `30` |
| `SD_AI_COMMAND_PACK_REVIEW_LOCAL_GITO_RETRY_MAX_DELAY_SECONDS` | Maximum Gito retry delay after backoff. | `120` |
| `MAX_CONCURRENT_TASKS` | Gito LLM concurrency cap. Loaded from `.gito/sd-ai-command-pack.env` by pack runners when unset. | `4` |
| `SD_AI_COMMAND_PACK_REVIEW_LOCAL_PRISM_CODEBASE_FALLBACK` | Enables Prism full-codebase batch/path fallback after empty chunk responses. | `1` |
| `SD_AI_COMMAND_PACK_SCOPE_PR_BODY` | General PR body override for review-scope and fallback PR-body scope checks. | unset |
| `SD_AI_COMMAND_PACK_PR_BODY_SCOPE_PR_BODY` | PR body override consumed specifically by `sd-ai-command-pack-pr-body-scope.py`; unset falls back to `SD_AI_COMMAND_PACK_SCOPE_PR_BODY`. | unset |
| `SD_AI_COMMAND_PACK_PR_BODY_SCOPE_ACTOR` | PR author login (or `--actor`) for `sd-ai-command-pack-pr-body-scope.py`; a `[bot]`-suffixed login (e.g. `dependabot[bot]`) is exempt from strict validation so automated PRs are not blocked. | unset |
| `SD_AI_COMMAND_PACK_REVIEW_PR_SELECTOR` | PR number or URL for `sd-review-pr` when it cannot resolve the pull request from the current branch. | unset |
| `SD_AI_COMMAND_PACK_REVIEW_PR_REMOTE_REVIEWER` | Remote reviewer login/slug for `sd-review-pr`. | `copilot-pull-request-reviewer` |
| `SD_AI_COMMAND_PACK_REVIEW_PR_REMOTE_REQUEST_COMMAND` | Custom command for requesting a remote review. | unset |
| `SD_AI_COMMAND_PACK_REVIEW_PR_REMOTE_ROUND_LIMIT` | Max remote review request/fix rounds before asking whether to continue. | `5` |

The deprecated `REVIEW_PREFLIGHT_PR_BODY` fallback remains honored and is
documented in the installed guide for older target repos.

## Install

Prerequisite: install Trellis and run `trellis init` in the target repository
before installing this pack. The official setup guide is
[Install And First Task](https://docs.trytrellis.app/start/install-and-first-task).

From this repository:

```bash
python3 install.py /path/to/trellis/repo
```

The installer requires `.trellis/config.yaml` in the target repo and will fail
with the Trellis install link if that marker is missing. It always installs the
shared `.agents` skills, full-check, the shared shell helper, housekeeping,
record-session, review-scope, review-local command assets, review-preflight,
install-audit, review-learnings, PR-body scope, and update-spec KB scripts,
Prism/Gito defaults, usage guide, and the
generated `.sd-ai-command-pack/installed-targets.txt` snapshot used by the scope
checks. Normal shared installs should commit that snapshot with the other
pack-owned files so audit and review-scope helpers can compare the intended
installed footprint. For normal shared installs, it also maintains a managed
`sd-ai-command-pack trellis-gitignore` block in the repo root `.gitignore` that
ignores Trellis local/runtime files such as `.trellis/.developer`,
`.trellis/.runtime/`, `.trellis/.cache/`, `.trellis/.backup-*`,
`.trellis/worktrees/`, and `.trellis/.template-hashes.json` without
blanket-ignoring shareable `.trellis` workflow, spec, task, and script files.
It also keeps shared Claude SD commands trackable while ignoring the rest of
`.claude/` as local Claude Code state. Other AI-tool local state such as tool
caches, logs, sessions, tmp folders, Gito report/temp artifacts,
`.opencode/node_modules/`, and root `node_modules/` are ignored without
blanket-ignoring shareable `.codex/`, `.gemini/`, `.gito/`, or `.opencode/`
platform adapter directories.
It installs platform adapters only when the target repo has the corresponding
platform directory and a Trellis-owned marker for that platform, such as a
Trellis command, hook, skill, or Copilot hook file. A plain `.github` directory
for Actions is not enough.

Useful options:

```bash
python3 install.py --help
python3 install.py --version
python3 install.py /path/to/repo --dry-run
python3 install.py /path/to/repo --local-only
python3 install.py /path/to/repo --all
python3 install.py /path/to/repo --platform cursor --platform gemini
python3 install.py /path/to/repo --force
python3 install.py /path/to/repo --force --backup
python3 install.py /path/to/repo --remove
```

After installing or refreshing a target repo, a quick smoke test is:

```bash
cd /path/to/repo
SANDBOX_TMP="${SANDBOX_TMP:-${TMPDIR:-/tmp}}"
export PYTHONPYCACHEPREFIX="${PYTHONPYCACHEPREFIX:-$SANDBOX_TMP/sd-ai-command-pack-pycache}"
export UV_CACHE_DIR="${UV_CACHE_DIR:-$SANDBOX_TMP/sd-ai-command-pack-uv-cache}"
export UV_TOOL_DIR="${UV_TOOL_DIR:-$SANDBOX_TMP/sd-ai-command-pack-uv-tools}"
export RUFF_CACHE_DIR="${RUFF_CACHE_DIR:-$SANDBOX_TMP/sd-ai-command-pack-ruff-cache}"
python3 scripts/sd-ai-command-pack-install-audit.py
# For fleet or scripted refreshes, pass the repo's explicit platforms too:
python3 scripts/sd-ai-command-pack-install-audit.py \
  --expected-platform claude --expected-platform gemini \
  --expected-platform github --expected-platform opencode
bash -n scripts/sd-ai-command-pack-full-check.sh
bash -n scripts/sd-ai-command-pack-shell-lib.sh
bash -n scripts/sd-ai-command-pack-review-local.sh
bash -n scripts/sd-ai-command-pack-review-scope.sh
python3 scripts/sd-ai-command-pack-update-spec-kb.py --dry-run
```

Use `--local-only` when you want Trellis and this pack available in one clone
without adding generated framework files to the shared GitHub repository. In
that mode the installer requires the target to be the Git repo root, runs
`trellis init --yes --skip-existing --codex` when `.trellis/config.yaml` is
missing, adds any requested platform flags such as `--cursor` or `--gemini`,
then writes a managed local block to `.git/info/exclude` for Trellis and
sd-ai-command-pack paths. It also writes `.sd-ai-command-pack/local-only.txt`
and keeps `.sd-ai-command-pack/installed-targets.txt` in the clone-local
exclude list so pack helpers know this checkout should use local state,
including for `.obsidian-kb/`, instead of modifying tracked `.gitignore`.

Local-only mode intentionally refuses to manage paths that are already tracked
by Git, because `.git/info/exclude` cannot hide changes to tracked files. Remove
existing Trellis or pack-generated files from Git tracking first, or use the
normal tracked install when the repository should share one setup.

By default, existing files with different content are reported as conflicts and
left untouched. Use `--force` to overwrite them. The exceptions are an existing
`.prism/rules.json`, `.gito/config.toml`, and `.github/PULL_REQUEST_TEMPLATE.md`:
once one differs from the pack template, it is reported as `preserved` and is
never overwritten or reported as a conflict. Add `--backup` with `--force` to save a `.bak` copy of every
overwritten file next to the original before it is changed. The pack-owned
`.gito/sd-ai-command-pack.env` file is updateable like scripts and docs so the
standard Gito concurrency cap can be refreshed.

Use `--remove` to uninstall the pack from a target checkout. Removal deletes
pack-vouched files, files that still match the bundled template, generated pack
state under `.sd-ai-command-pack/`, and the pack-managed blocks in `.gitignore`,
`.git/info/exclude`, and `.github/copilot-instructions.md`. Drifted files,
symlinks, directories, and user-owned policy files are preserved by default;
add `--force` to delete drifted regular pack files too, and add `--backup` to
keep `.bak` copies of deleted files.
Removal only deletes manifest-recognized pack artifacts and generated pack
state; corrupted receipt or provenance entries for `.git/*` or arbitrary repo
files are reported as `ignored`, even with `--force`.

Platform filters always include the shared skills, full-check, the shared shell
helper, housekeeping, review-scope, review-preflight, review-local command
assets, install-audit, review-learnings, PR-body scope, and
update-spec KB scripts, Prism/Gito defaults, usage guide, and installed-targets
snapshot, because the review,
full-check, housekeeping, and update-spec adapters delegate to those shared
assets.
`--platform` and `--all`
are explicit overrides for repairing or bootstrapping adapters when the active
Trellis platform markers are missing. The update-spec adapter delegates to
the Trellis-provided `trellis-update-spec` skill in the target repo.

When the GitHub platform is installed, the installer also seeds
`.github/PULL_REQUEST_TEMPLATE.md` with Summary/Test plan/Pre-PR checklist
sections that prompt for the explicit scope sections the PR-body checks look
for; an existing customized template is always preserved. The installer also
creates or updates a
managed `sd-ai-command-pack` block in `.github/copilot-instructions.md`. It
preserves existing repo-specific Copilot instructions, replaces only the marked
pack block on future installs, and adopts any earlier unmarked pack guidance
into the managed block so later installs can keep it refreshed. The block also
steers mixed PR reviews toward app behavior, data contracts, specs, tests,
operator docs, and repo-owned scripts instead of copied pack or Trellis payloads
unless those files have obvious syntax, secret, or integration-goal issues. It
also tells Copilot not to leave line comments on wording, spelling, links,
formatting, examples, or implementation details inside copied Trellis or copied
SD command-pack files. Original Trellis-owned runtime/template copies are also
out of scope for local edits and line-by-line review in target repos or this
pack; when a change appears needed, the guidance asks for one handoff comment
that sends the finding back to the sd-ai-command-pack source session. It asks
Copilot to group duplicate root causes and point to deterministic local checks
when they already cover a repeated issue class, or request a focused local
fixture when a repeated issue needs a stronger preflight.

Managed block examples, audit/provenance details, review-scope and PR-body
scope configuration, local-review exclusions, and classifier behavior live in
the installed guide to avoid duplicate README drift:
[docs/SD_AI_COMMAND_PACK.md](docs/SD_AI_COMMAND_PACK.md#updating-the-pack).

## Verify

The installer runs `git diff --check` on installed pack paths unless
`--skip-diff-check` is passed.

For the complete maintainer workflow, run `make setup` once and then
`make check`; see [CONTRIBUTING.md](CONTRIBUTING.md) for the target-by-target
breakdown and release rules. The explicit commands below mirror the main test
lane for environments without `make`.

Run the pack tests with the explicit dev dependencies from
`requirements-dev.txt`, including `coverage.py` via the `coverage` package.
On macOS, use Homebrew Python for the local virtualenv instead of Apple/Xcode
Python; the system Python often lacks the dev dependencies and can try to write
bytecode caches under protected `~/Library/Caches` paths.

```bash
BREW_PYTHON="${BREW_PYTHON:-/opt/homebrew/bin/python3}"  # Apple Silicon Homebrew
test -x "$BREW_PYTHON" || BREW_PYTHON=/usr/local/bin/python3  # Intel Homebrew
"$BREW_PYTHON" -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m ruff check install.py installer scripts templates/scripts tests
if command -v node >/dev/null 2>&1; then
  node --check scripts/sd-ai-command-pack-review-preflight.mjs
  node --check templates/scripts/sd-ai-command-pack-review-preflight.mjs
else
  printf '%s\n' "warning: node not found; skipping review-preflight JavaScript syntax checks."
fi
COVERAGE_PROCESS_START="$(pwd)/.coveragerc" COVERAGE_FILE="$(pwd)/.coverage" \
  PYTHONPATH="$(pwd)/tests/coverage_sitecustomize${PYTHONPATH:+:$PYTHONPATH}" \
  python -m coverage run --parallel-mode -m unittest discover -s tests
python -m coverage combine
python -m coverage report --include="install.py,installer/*" --fail-under=100
python -m coverage report --include="scripts/sd-ai-command-pack-*" --fail-under=76
```

Two coverage gates run: the `--fail-under=100` gate measures the installer
(`install.py` plus the `installer/` package, lines and branches; this is also
the default scope of a bare `coverage report`), and a second gate measures the
shipped Python helpers under `scripts/` with a provisional 76% floor that
ratchets up as helper tests grow. CI fails when `unittest` reports any skipped
tests, runs the test suite on Ubuntu and macOS, and runs Ruff over pack Python
plus `node --check` over the review-preflight JavaScript twins when Node is
available locally. The shipped shell scripts are exercised by behavioral tests
rather than a coverage number; CI also runs `shellcheck -S warning` over every
tracked shell script and the git hooks — consumers exempt the vendored pack
shell from line review ("reviewed upstream"), so upstream lint rigor is the
compensating control.

## Releasing

Start every release from a clean, up-to-date `main`, then create a release
branch. Bump `manifest.json` whenever the shipped payload changes: `templates/**`,
`docs/SD_AI_COMMAND_PACK.md`, or the manifest itself. The full-check pack-source
drift gate fails when those files change without a manifest version bump.

For docs, spec, README, or PRD edits, refresh the local KB before full-check:

```bash
python3 scripts/sd-ai-command-pack-update-spec-kb.py
```

Run the local release gate with local AI reviewers disabled unless the release
is explicitly about Prism or Gito behavior:

```bash
SD_AI_COMMAND_PACK_FULL_CHECK_PRISM=0 SD_AI_COMMAND_PACK_FULL_CHECK_GITO=0 \
  bash scripts/sd-ai-command-pack-full-check.sh
```

Use a conventional release commit such as
`chore: release sd-ai-command-pack <version>`, merge the PR, fast-forward `main`,
then tag the merge/release commit:

```bash
git tag v<version>
git push origin v<version>
```

After the tag is pushed, use the fleet preflight below before opening consumer
refresh PRs.

## Fleet Rollout

The checked-in fleet manifest lives at `docs/fleet/consumers.json`. It lists
the real consumer repositories, GitHub slugs, local path hints, and explicit
platform sets. Run the source-owned preflight from this checkout:

```bash
python3 scripts/sd-ai-command-pack-fleet-preflight.py
```

Repos reported as `at-target` should be skipped, which prevents duplicate
empty refresh PRs. For repos that need a refresh, the preflight prints the
exact `install.py --force --platform ...` and install-audit commands. The audit
command passes each explicit platform through `--expected-platform`, so missing
selected-platform files are caught even if a faulty install also omitted them
from receipts and provenance. See [docs/FLEET_ROLLOUT.md](docs/FLEET_ROLLOUT.md)
for the compact rollout runbook.

## Direct-to-main Chore Commits

Branch protection on `main` requires pull requests with the `CI Result`
check, with `enforce_admins` left off deliberately: the Trellis wrap-up flow
(task archive, journal, and task-file commits under `.trellis/tasks/**` and
`.trellis/workspace/**`) pushes those chore commits directly to `main` under
the maintainer bypass. Everything else goes through a pull request.

The tracked `.githooks/pre-push` hook keeps that bypass honest by rejecting
any direct push to `main` that touches paths outside the two chore
directories. Install it once per clone:

```bash
git config core.hooksPath .githooks
```

`make setup` also arms the hook. The full-check script warns in this source
checkout when `.githooks` is not configured, because direct-to-main chore
commits rely on that local guard when maintainer bypass is available.

For a deliberate one-shot exception, bypass the hook with
`SD_AI_COMMAND_PACK_CHORE_SCOPE_BYPASS=1 git push ...` — GitHub's own rules
still apply on the remote.

## Supported Adapters

| Platform | Installed When |
| --- | --- |
| Shared skills, scripts, Prism/Gito defaults, usage guide | Always |
| Codex skill completion | `.agents/skills/sd-*` installed as shared skills |
| Antigravity | `.agent/` exists with Trellis workflow or skill markers; or `--all` / `--platform antigravity` |
| Claude Code | `.claude/` exists with Trellis command, hook, or skill markers; or `--all` / `--platform claude` |
| CodeBuddy | `.codebuddy/` exists with Trellis command, hook, agent, settings, or skill markers; or `--all` / `--platform codebuddy` |
| Cursor | `.cursor/` exists with Trellis command, hook, or skill markers; or `--all` / `--platform cursor` |
| Devin | `.devin/` exists with Trellis workflow or skill markers; or `--all` / `--platform devin` |
| Factory Droid | `.factory/` exists with Trellis command, hook, droid, settings, or skill markers; or `--all` / `--platform droid` |
| Gemini CLI | `.gemini/` exists with Trellis command, hook, or agent markers; or `--all` / `--platform gemini` |
| GitHub Copilot | `.github/` exists with Trellis hook, Copilot hook, or skill markers; or `--all` / `--platform github` |
| Kilo | `.kilocode/` exists with Trellis workflow or skill markers; or `--all` / `--platform kilo` |
| Kiro | `.kiro/` exists with Trellis skill, hook, or agent markers; or `--all` / `--platform kiro` |
| OpenCode | `.opencode/` exists with Trellis command, library, or skill markers; or `--all` / `--platform opencode` |
| Pi | `.pi/` exists with Trellis prompt, extension, setting, agent, or skill markers; or `--all` / `--platform pi` |
| Qoder | `.qoder/` exists with Trellis command, hook, settings, agent, or skill markers; or `--all` / `--platform qoder` |
| Reasonix | `.reasonix/` exists with Trellis skill markers; or `--all` / `--platform reasonix` |
| Trae | `.trae/` exists with Trellis command, hook, settings, agent, or skill markers; or `--all` / `--platform trae` |
| ZCode | `.zcode/` exists with Trellis command or `.zcode/agents/` markers; or `--all` / `--platform zcode` |

ZCode Trellis agents now live under `.zcode/agents/`; the installer still
treats the legacy `.zcode/cli/agents/` path as copied Trellis surface for
local-only excludes and review-scope classification during the transition.

## License

This repository is licensed under the [MIT License](LICENSE).

## Upstream Path

This pack is intentionally shaped so pieces could move upstream later, while
the local command namespace stays pack-owned:

- Do not patch original Trellis-owned runtime/template copies in this repo or
  target repos. If `.trellis/scripts/**`, `.trellis/agents/**`, or platform
  `trellis-*` payload behavior needs to change, use a pack-owned wrapper,
  guard, or template change when the behavior belongs here; otherwise hand the
  issue to the Trellis source owner.
- Move the shared skill to
  `packages/cli/src/templates/common/bundled-skills/sd-review-pr/SKILL.md`.
- Move the full-check skill and script to the equivalent shared template
  locations.
- Move the housekeeping skill and script to the equivalent shared template
  locations.
- Move command behavior into Trellis' common or platform-specific command
  templates only if Trellis intentionally adopts those workflows; otherwise
  keep local wrappers under the pack-owned `sd` namespace.
- Add template distribution tests and package verification in the Trellis CLI
  repo.

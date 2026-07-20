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
read-only repository/fleet status, post-merge housekeeping, update-spec,
backlog implementation, and backlog design workflows. The repository and `sd`
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

The shared skills own the workflows; the platform command and prompt files are
thin entry points that load the matching shared skill. Wrappers live under the
`sd` namespace (not `trellis`) so they never collide with Trellis' generated
`/trellis:*` commands, and they delegate to Trellis' own start, continue,
finish-work, and update-spec skills without changing behavior — including on
Claude Code, where the start wrapper reads SessionStart context from
`.trellis/scripts/get_context.py`. Codex exposes them as `sd-*` skills. See the
installed guide's [What is installed](docs/SD_AI_COMMAND_PACK.md#what-is-installed)
for the full Codex skill list, per-platform command shapes, and adapter details.

Quick links:

- [Overview](#overview)
- [Commands](#commands)
- [Configuration Quick Reference](#configuration-quick-reference)
- [Install](#install)
- [Supported Adapters](#supported-adapters)
- [Verify](#verify)
- [Releasing](#releasing)
- [Fleet Rollout](#fleet-rollout)
- [Direct-to-main Chore Commits](#direct-to-main-chore-commits)
- [Upstream Path](#upstream-path)
- [License](#license)

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

### sd-help

Provides read-only discovery for the installed SD command surface. It can list
commands by family, explain or compare commands, recommend the smallest-fit
workflow for a goal, show examples, or give a compact lifecycle tour. It
reports the bundled and installed pack versions plus current-session
availability when those values can be observed, and it never runs the command
it recommends.

Examples:

```text
/sd:help
/sd:help review-pr
/sd:help "compare sd-create-pr and sd-ship"
/sd:help "I need to fix failing CI"
/sd:help all
```

Use the native form exposed by the current platform, such as `/sd:help`,
`/sd-help`, `sd/help`, or `$sd-help`. Run the recommended command only in a
separate explicit request.

### sd-status

Reports repository delivery state without changing it: branch and working-tree
counts, cached upstream divergence, pack/Trellis versions, GitHub PR and issue
inventory, current/open Trellis work, user-local autonomous loop progress,
completed tasks stranded outside the Trellis archive, anomalies, and numbered
next steps. Loop status includes its run ID, selector
and focus, iteration, phase, task/PR, counters, heartbeat, context health, and
checkpoint without mutating the ledger or lock. Dynamically loaded helper
snapshots are reduced to a bounded, sanitized pack-owned contract; malformed
snapshots are reported as `invalid` anomalies instead of rendering raw data.
The shared preflight fails when a completed task remains directly under
`.trellis/tasks/` and reports the `task.py archive` remediation; `sd-status`
surfaces the same condition without mutating it.

Autonomous work loops keep lifecycle phases separate from mutable Git/PR facts.
The shipped work-loop helper's `evidence` subcommand records verified commit,
PR, review-fix, finish-work, and merge facts atomically without an artificial
checkpoint transition. Stable task/base identity and Git ancestry checks keep
real contradictions fail-closed, while successful recovery clears obsolete
ready or blocked checkpoints.
Use `fleet` from any installed
checkout to collect a rollout-priority summary for every configured consumer
after creating the machine-local fleet profile.

```text
/sd:status
/sd:status --no-network
/sd:status /path/to/another/repo
/sd:status fleet
/sd:status fleet --json
```

Configure that profile once from the canonical pack checkout (or repeat after
moving it):

```bash
python3 install.py /path/to/a/consumer --configure-fleet
```

Fleet topology and rollout policy remain versioned in
`docs/fleet/consumers.json`; the user profile only locates that source and may
override local checkout paths.

Ordinary status does not fetch, so it labels refs `cached`. Housekeeping passes
the `refreshed` label after its fetch/prune and delegates its final verification
to the same collector. The command's `--json` output uses schema version 1.

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
It detects the default branch instead of assuming `origin/main`, and sends
custom Markdown PR bodies through a literal temporary file plus `--body-file`
so shell expansion cannot execute content or inflate the submitted body.
Standalone use still enters `sd-review-pr`; when `sd-ship` delegates its first
stage, an internal composite-only context returns after PR publication so the
ship workflow can own review exactly once in Stage 2.

### sd-work-backlog

Runs a resumable autonomous loop over Trellis tasks. It plans missing artifacts,
implements and validates one task at a time, delegates the complete PR lifecycle
to `sd-ship until=merge`, processes follow-ups, verifies clean state, then
re-inventories until a documented stop condition. A user-local atomic ledger
and lock make it safe to resume after interruption or context compaction.
Repositories that already maintain `.obsidian-kb` are refreshed after task
archival and again after any follow-up task creation; repositories without that
folder remain unchanged.

```text
/sd:work-backlog
/sd:work-backlog CI pipeline
/sd:work-backlog focus="CI pipeline" focus="release automation"
/sd:work-backlog focus-only="priority:P1"
```

### sd-work-designs

Uses the same autonomous controller with a `needs-design` selector. It starts
with tasks whose real PRDs still need `design.md` or `implement.md`, then carries
them through implementation and green merge by default. Use `until=design` to
stop after creating and validating planning artifacts.

```text
/sd:work-designs CI pipeline
/sd:work-designs until=design focus-only="scope:ci"
```

### sd-full-check

Runs the deterministic local verification gate before PR readiness. Prism can
run automatically when available; Gito is opt-in through
`SD_AI_COMMAND_PACK_FULL_CHECK_GITO=1` because it may need network access,
local caches, and LLM credentials.

### sd-review-pr

Runs the deterministic local PR gate with Prism and Gito disabled, requests the
configured remote reviewer, addresses review comments or CI failures, and
re-requests review after each pushed fix up to the configured round limit.
Before remote review it dispositions deterministic boundary-risk and scope
advisories; after the overall loop is clean it runs one read-only, PR-scoped
review-learning pass.

### sd-review-local

Runs configured local review providers against local changes, or against the
current branch when no local changes exist, then enters a user-selected fix
loop. With the `all` argument it reviews the full checked-out repository (the
former `sd-review-local-all` command, folded in as of 0.13.0); exclusion and
retry behavior lives in the installed guide's
[Local Review](docs/SD_AI_COMMAND_PACK.md#local-review) section.

### sd-review-learnings

Scans local diffs and optional recent GitHub review comments for repeated review
patterns, then updates a managed learning block when requested. Time-window
scans cover the complete window by default, while `--github-pr` supports a
bounded single-PR analysis. Historical review paths remain readable remote
provenance and are not treated as current checkout paths by the local preflight.

### sd-audit-repo

Runs the formal multi-dimension repository audit: one read-only reviewer per
charter dimension, adversarial verification of findings, Trellis backlog
reconciliation, and a canonical report backed by the committed findings ledger
at `.trellis/audit/ledger.md`. Bare exact charter names such as `security
testing` select dimensions; `dimensions=`, `depth=`, and `follow-up` remain
available explicitly. Details live in the installed guide's
[Commands](docs/SD_AI_COMMAND_PACK.md#commands) section.

### sd-watch-pr

Watches the current branch's open PR inside a bounded polling loop until
checks, the requested reviewer, and review threads settle, then hands off to
the `sd-housekeeping` gate (or reports blockers with `no-merge`). Never merges
outside that gate.

### sd-fix-ci

Triages a red CI run: classifies each failing job as real-code, flake, infra,
or stale-baseline; fixes real failures through the gated flow (main fixes via
a PR, never a direct push); reruns flakes boundedly; never weakens tests to
get green.

### sd-update-deps

Batch-triages dependency-bot PRs: merges the safe class (patch/minor dev
deps, Actions pin bumps, security patches) sequentially under the
housekeeping gate criteria, keeps majors manual, and parks the rest with
recommendations. `dry-run` reports classifications only.

### sd-fleet-refresh

Source-checkout-only operator command; it is not installed into consumer
repositories because it depends on this repository's installer, fleet
registry, and rollout procedure. It rolls the pack release across consumer
repos per `docs/FLEET_ROLLOUT.md`:
fleet preflight, then one consumer at a time — clean-tree check, install,
consumer full-check, PR, watch, gated merge — ending with a per-consumer
status table. Bare consumer names select a subset, for example
`/sd:fleet-refresh loadsmith rwbp-website`; `consumer=`, `dry-run`, and
`no-merge` remain available explicitly.

### sd-test-gaps

Ranks shipped files by per-file coverage, authors targeted tests for the
worst `max-gaps=` files through the normal implement/check flow, and reports
before/after numbers. A bare path such as `/sd:test-gaps scripts/example.py`
targets one file, equivalent to `file=scripts/example.py`. Writes test files
and fixtures only.

### sd-ship

Sequences the publish-to-merge endgame — create-pr, review-pr, watch-pr, then
the housekeeping merge gate — with `until=pr|review|merge` stop-points. Adds
no gate logic of its own; every stage's gates remain authoritative. A review
stop finishes Trellis work in the review stage, while the merge-through path
keeps the task active during the watch and lets housekeeping finish, merge,
and clean up exactly once. Stage 1 always publishes without review; Stage 2 is
the sole review owner and does not run for `until=pr`.

### sd-retro

Captures a structured debug retrospective (what broke, root cause, why gates
missed it) as a journal entry via the session recorder, and proposes
consent-gated prevention tasks. Bare text supplies the topic, for example
`/sd:retro deployment timeout`; `topic=` remains available explicitly. Makes
no code changes.

### sd-update-spec

Runs the existing Trellis `trellis-update-spec` skill, refreshes repo-owned
repospec or repository-map artifacts when maintained by the target repo, updates
an existing architecture overview only when warranted, and refreshes the
repo-local `.obsidian-kb/` copy folder.

### sd-housekeeping

Ends a development stream by running finish-work before merge, merging only when
the PR is clean and comment-free, then switching to the default branch,
fast-forwarding, deleting merged refs, and reporting the final clean state.
The cleanup script delegates final Git/GitHub/Trellis inventory, anomaly
classification, and next steps to `sd-status` in strict mode.

## Configuration Quick Reference

| Variable | Purpose | Default |
| --- | --- | --- |
| `SD_AI_COMMAND_PACK_PYTHON` | Authoritative Python executable used by the toolchain preflight. | repo `.venv`, active virtualenv, Homebrew Python 3.13, then supported `python3` |
| `SD_AI_COMMAND_PACK_PROJECT_CHECK_COMMAND` | Explicit trusted project-check command; discovered candidates are never auto-selected. | unset |
| `SD_AI_COMMAND_PACK_TOOLCHAIN_PLATFORM` | Advanced/test override for toolchain platform detection. | `uname -s` |
| `SD_AI_COMMAND_PACK_TOOLCHAIN_HOMEBREW_PREFIXES` | Advanced/test override for colon-separated Homebrew Python prefixes. | `/opt/homebrew:/usr/local` |
| `SD_AI_COMMAND_PACK_REPO_ROOT` | Advanced/test override for the repository root inspected by the toolchain helper. | Git top-level directory |
| `SD_AI_COMMAND_PACK_STATE_HOME` | Absolute user-local root for resumable autonomous work-loop ledgers and locks. | XDG state, Windows local app data, or `~/.local/state/sd-ai-command-pack` |
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
| `SD_AI_COMMAND_PACK_REVIEW_LOCAL_TOOLS` | Local review tool set for `sd-review-local` (any scope); unset uses the runner default. | unset |
| `SD_AI_COMMAND_PACK_REVIEW_LOCAL_<TOOL>_COMMAND` | Custom command for a named local review provider. | unset |
| `SD_AI_COMMAND_PACK_REVIEW_LOCAL_ALL_<TOOL>_COMMAND` | Full-codebase custom command for a named provider; unset falls back to the non-`ALL` command. | unset |
| `SD_AI_COMMAND_PACK_REVIEW_LOCAL_SEMGREP_COMMAND` | Example Semgrep custom-provider command for `sd-review-local`; follows the generic `<TOOL>` command naming pattern. | unset |
| `SD_AI_COMMAND_PACK_REVIEW_LOCAL_GITO_MAX_ATTEMPTS` | Max Gito attempts for HTTP 429 provider rate limits. | `2` |
| `SD_AI_COMMAND_PACK_REVIEW_LOCAL_GITO_RETRY_DELAY_SECONDS` | Initial Gito retry delay. | `30` |
| `SD_AI_COMMAND_PACK_REVIEW_LOCAL_GITO_RETRY_MAX_DELAY_SECONDS` | Maximum Gito retry delay after backoff. | `120` |
| `MAX_CONCURRENT_TASKS` | Gito LLM concurrency cap. Loaded from `.gito/sd-ai-command-pack.env` by pack runners when unset. | `4` |
| `SD_AI_COMMAND_PACK_REVIEW_LOCAL_PRISM_CODEBASE_FALLBACK` | Enables Prism full-codebase batch/path fallback after empty chunk responses. | `1` |
| `SD_AI_COMMAND_PACK_SCOPE_PR_BODY` | General PR body override for review-scope and fallback PR-body scope checks. | unset |
| `SD_AI_COMMAND_PACK_PR_BODY_SCOPE_PR_BODY` | PR body override consumed specifically by `sd-ai-command-pack-pr-body-scope.py`; unset falls back to `SD_AI_COMMAND_PACK_SCOPE_PR_BODY`. | unset |
| `SD_AI_COMMAND_PACK_PR_BODY_SCOPE_ACTOR` | PR author login (or `--actor`) for `sd-ai-command-pack-pr-body-scope.py`; a `[bot]`-suffixed login (e.g. `dependabot[bot]`) is exempt from strict validation so automated PRs are not blocked. | unset |
| `SD_AI_COMMAND_PACK_REVIEW_PR_SELECTOR` | PR number or URL for `sd-review-pr` when it cannot resolve the pull request from the current branch. | unset |
| `SD_AI_COMMAND_PACK_REVIEW_PR_REMOTE_REVIEWER` | Remote reviewer request identity for `sd-review-pr`. | `@copilot` |
| `SD_AI_COMMAND_PACK_REVIEW_PR_REMOTE_REVIEWER_LABEL` | Human-readable remote reviewer name used in `sd-review-pr` status output and reports. | `GitHub Copilot` |
| `SD_AI_COMMAND_PACK_REVIEW_PR_REMOTE_AUTHOR_MATCH` | Review/comment author matched after a remote request; defaults to the configured reviewer except for Copilot. | `copilot-pull-request-reviewer[bot]` |
| `SD_AI_COMMAND_PACK_REVIEW_PR_REMOTE_REQUEST_COMMAND` | Custom command for requesting a remote review. | unset |
| `SD_AI_COMMAND_PACK_REVIEW_PR_REMOTE_ROUND_LIMIT` | Max remote review request/fix rounds before asking whether to continue. | `5` |
| `SD_AI_COMMAND_PACK_REVIEW_PR_REMOTE_SETTLE_POLLS` | Maximum 30-second polls before an accepted request without author-matched activity stops as ambiguous. | `40` |

Use `SD_AI_COMMAND_PACK_SCOPE_PR_BODY` for explicit review-scope PR body text.

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
ignores Trellis and AI-tool local/runtime state (caches, logs, sessions, tmp,
Gito artifacts, `node_modules/`) while keeping shareable `.trellis` and platform
adapter files — plus tracked Claude SD commands — committed.
It installs platform adapters only when the target repo has the corresponding
platform directory and a Trellis-owned marker for that platform, such as a
Trellis command, hook, skill, or Copilot hook file. A plain `.github` directory
for Actions is not enough.

Useful options:

```bash
python3 install.py --help
python3 install.py --version
python3 install.py /path/to/repo --status
python3 install.py /path/to/repo --status --audit
python3 install.py /path/to/repo --check
python3 install.py /path/to/repo --check --json
python3 install.py /path/to/repo --dry-run
python3 install.py /path/to/repo --local-only
python3 install.py /path/to/repo --all
python3 install.py /path/to/repo --platform cursor --platform gemini
python3 install.py /path/to/repo --force
python3 install.py /path/to/repo --force --backup
python3 install.py /path/to/repo --remove
```

`--status` is a read-only informational comparison against the current pack
checkout. Add `--audit` for the structural installed-footprint audit. `--check`
always runs that audit and is intended for automation: it exits `0` when the
install is current, `3` when a valid install is absent or needs a refresh, and
`1` for invalid receipts, integrity failures, or audit errors. Add `--json` to
either mode for schema-versioned machine output. Inspection modes cannot be
combined with install, removal, selection, or dry-run options.

| Exit | Inspection meaning |
| --- | --- |
| `0` | Status completed; for `--check`, the install is current and audit-clean. |
| `1` | Installed state is invalid, audit failed, or inspection could not run. |
| `2` | Command-line usage is invalid. |
| `3` | `--check` found a valid missing or stale installation that needs action. |

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
bash -n scripts/sd-ai-command-pack-toolchain.sh
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

By default, conflicting files are left untouched and the tracked refresh exits
before writing anything; add `--force` to overwrite and `--backup` (with
`--force`) to keep a `.bak` of each overwritten file. Customized
`.prism/rules.json`, `.gito/config.toml`, and `.github/PULL_REQUEST_TEMPLATE.md`
are reported as `preserved` and never overwritten.

Use `--remove` to uninstall the pack. It deletes only manifest-recognized
pack-vouched or template-matching files, generated `.sd-ai-command-pack/` state,
and the pack-managed `.gitignore`, `.git/info/exclude`, and
`.github/copilot-instructions.md` blocks; drifted, symlinked, or user-owned
files are kept unless you add `--force`.

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

## Maintaining

### Verify

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
BREW_PYTHON="${BREW_PYTHON:-/opt/homebrew/bin/python3.13}"  # Apple Silicon Homebrew
test -x "$BREW_PYTHON" || BREW_PYTHON=/usr/local/bin/python3.13  # Intel Homebrew
"$BREW_PYTHON" -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m ruff check install.py installer scripts templates/scripts tests
if command -v node >/dev/null 2>&1; then
  node --check scripts/sd-ai-command-pack-review-preflight.mjs
  node --check templates/scripts/sd-ai-command-pack-review-preflight.mjs
  bash .github/scripts/check-opencode-js.sh
else
  printf '%s\n' "warning: node not found; skipping JavaScript syntax checks."
fi
bash .github/scripts/run-tests.sh
python -m coverage combine
python -m coverage report --include="install.py,installer/*" --fail-under=100
PYTHON_BIN=python bash .github/scripts/check-shipped-script-coverage.sh
```

Two coverage gates run: the `--fail-under=100` gate measures the installer
(`install.py` plus the `installer/` package, lines and branches; this is also
the default scope of a bare `coverage report`), and a second gate measures the
shipped Python helpers under `scripts/`: an aggregate 76% floor plus a
per-file floor listed in `.github/scripts/check-shipped-script-coverage.sh`.
Set each per-file floor at or just below the current measured helper coverage
and ratchet it upward when focused tests improve a script. CI fails when
`unittest` reports any skipped tests, runs the test suite on Ubuntu and macOS,
and runs Ruff over pack Python plus `node --check` over the review-preflight
JavaScript twins when Node is available locally. The shipped shell scripts,
GitHub workflow YAML, and `.github/scripts/*` automation are exercised by
behavioral tests and syntax/lint gates rather than a coverage.py number; CI
also runs `shellcheck -S warning` over every tracked shell script and the git
hooks. Consumers exempt the vendored pack shell from line review ("reviewed
upstream"), so upstream lint rigor and focused subprocess tests are the
compensating controls.

### Releasing

Start every release from a clean, up-to-date `main`, then create a release
branch. Bump `manifest.json` whenever the shipped payload changes: `templates/**`,
`docs/SD_AI_COMMAND_PACK.md`, or the manifest itself. The full-check pack-source
drift gate fails when those files change without a manifest version bump. Every
version bump must also add the matching top `CHANGELOG.md` heading in the form
`## <version> - YYYY-MM-DD`; the same gate rejects missing or stale headings.
Pull request CI runs the same release payload gate as a small standalone job
against the PR base and feeds that result into `CI Result`, so payload drift is
blocked remotely even when the local full-check was missed.

Before merging a release payload change, validate the working candidate against
disposable clones of every fleet consumer:

```bash
bash scripts/sd-ai-command-pack-toolchain.sh run-python -- \
  scripts/sd-ai-command-pack-fleet-candidate-check.py
```

The all-pass run updates `docs/fleet/candidate-validation.json`. The local/CI
release gate and automatic tag creator verify that ledger against the exact
pack payload and fleet manifest, so stale or partial evidence cannot release.
The validator never modifies active consumer worktrees. See the fleet runbook
for diagnostic filters and failure policy.

For docs, spec, README, or PRD edits, refresh the local KB before full-check:

```bash
python3 scripts/sd-ai-command-pack-update-spec-kb.py
```

Lifecycle owners use `--if-present` when they must refresh generated knowledge
without creating a KB in repositories that have not opted into one. Missing
KBs return success with a visible skip reason; existing invalid or conflicting
KB paths still fail.

Run the local release gate with local AI reviewers disabled unless the release
is explicitly about Prism or Gito behavior:

```bash
SD_AI_COMMAND_PACK_FULL_CHECK_PRISM=0 SD_AI_COMMAND_PACK_FULL_CHECK_GITO=0 \
  bash scripts/sd-ai-command-pack-full-check.sh
```

Use a conventional release commit such as
`chore: release sd-ai-command-pack <version>` and merge the PR. After the
required test lanes pass on `main`, the `Auto-tag release` CI job creates the
lightweight `v<version>` tag at the merged commit. The job is idempotent and
fails instead of moving an existing tag. Verify the same plan locally without
writing a tag:

```bash
python3 .github/scripts/create-release-tag.py --base HEAD^ --head HEAD --dry-run
```

If the post-merge tag job fails, rerun the failed workflow after correcting the
reported ledger or permissions problem; do not move or overwrite a published
version tag. After the tag exists, use the fleet preflight below before opening
consumer refresh PRs.

### Fleet Rollout

The checked-in fleet manifest lives at `docs/fleet/consumers.json`. It lists
the real consumer repositories, GitHub slugs, local path hints, explicit
platform sets, lightweight candidate checks, and rollout priorities. Run the
source-owned preflight from this checkout:

```bash
python3 scripts/sd-ai-command-pack-fleet-preflight.py
```

Repos reported as `at-target` should be skipped, which prevents duplicate
empty refresh PRs. For repos that need a refresh, the preflight prints the
exact `install.py --force --platform ...` and install-audit commands. The audit
command passes each explicit platform through `--expected-platform`, so missing
selected-platform files are caught even if a faulty install also omitted them
from receipts and provenance. See [docs/FLEET_ROLLOUT.md](docs/FLEET_ROLLOUT.md)
for the fast-canary order, interruption threshold, review ownership, and
compact rollout runbook.

### Direct-to-main Chore Commits

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

The `Main push scope` CI job applies the same path policy to every push on
`main` and feeds the result into `CI Result`. It is a server-side detective
backstop for an unarmed or bypassed local hook: an accidental non-chore push is
reported with its offending paths, but the pushed commit still needs an
explicit revert because CI cannot retract an accepted push.

For a deliberate one-shot exception, bypass the hook with
`SD_AI_COMMAND_PACK_CHORE_SCOPE_BYPASS=1 git push ...`. The server-side scope
job still evaluates that push; use a pull request for non-chore changes.

### Upstream Path

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

## License

This repository is licensed under the [MIT License](LICENSE).

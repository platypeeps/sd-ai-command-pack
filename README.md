# SD AI Command Pack

[![Trellis](https://img.shields.io/badge/Trellis-trytrellis.app-255E63)](https://trytrellis.app/)
[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Tests](https://img.shields.io/badge/tests-unittest-2E7D32)](#verify)
[![License: MIT](https://img.shields.io/github/license/platypeeps/sd-ai-command-pack)](LICENSE)
[![Source](https://img.shields.io/badge/source-GitHub-181717?logo=github)](https://github.com/platypeeps/sd-ai-command-pack)

Install reusable AI workflow helpers into
[Trellis-managed repositories](https://trytrellis.app/). The current pack is
focused on Trellis enrichment: start, continue, finish-work, local review, PR
review, full-codebase local review, review learnings, full-check, post-merge
housekeeping, and update-spec workflows. The repository and `sd`
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
- platform command or prompt adapters for Claude, Cursor, Gemini, GitHub
  Copilot, and OpenCode when the matching active Trellis platform is present
- a managed `sd-ai-command-pack` guidance block in
  `.github/copilot-instructions.md` for GitHub Copilot installs

The exact installed file set is defined by `manifest.json` and validated in
target repos by `scripts/sd-ai-command-pack-install-audit.py`.

The shared skills own the workflows. Platform command and prompt files are thin
entry points that tell the agent to load the appropriate shared skill.
Codex exposes pack entry points as enabled skills named `sd-start`, `sd-continue`,
`sd-finish-work`, `sd-full-check`, `sd-housekeeping`, `sd-review-pr`,
`sd-review-local`, `sd-review-local-all`, `sd-review-learnings`, and
`sd-update-spec`; type `/sd` in Codex command completion or invoke them
explicitly with `$sd-review-pr`-style skill mentions.
User-facing command adapters live under the `sd` namespace so pack-owned
wrappers do not collide with Trellis-owned generated `/trellis:*` commands on
future `trellis update` runs. Cursor command files, GitHub Copilot prompt
files, and OpenCode command files use flat `sd-<command>` filenames so their
slash-command completion lists can surface them when you type `/sd`.
The update-spec workflow runs the Trellis-provided `trellis-update-spec` skill
as-is, refreshes repo-owned repospec artifacts through existing maintenance
infrastructure when available, then adds an explicit architectural-overview
check and rebuilds a repo-local `.obsidian-kb` folder of copied
repository-knowledge files.
The start, continue, and finish-work wrappers similarly delegate to
Trellis-provided `trellis-start`, `trellis-continue`, and
`trellis-finish-work` skills without changing their behavior.
The installed `docs/SD_AI_COMMAND_PACK.md` file gives humans and agents a
repo-local usage guide for the commands, script, environment variables, local
review-provider behavior when available, and troubleshooting steps.

Quick links:

- [Install](#install)
- [Verify](#verify)
- [Supported Adapters](#supported-adapters)
- [License](#license)

Claude and Gemini expose the wrappers as namespaced commands such as
`/sd:review-pr`. Cursor command files, GitHub Copilot prompt files, OpenCode
command files, and Codex skills expose the same entries as flat `sd-<command>`
names, such as `sd-review-pr`.
For Gemini CLI specifically, the `sd` directory under `.gemini/commands/` is
intentional: Gemini maps `.gemini/commands/sd/review-pr.toml` to
`/sd:review-pr`, and displays each TOML file's `description` in `/help`. If the
CLI was already running when the files were installed, run `/commands reload`;
run `/commands list` to confirm the project command files Gemini loaded.

The full-check command (`/sd:full-check` in Claude/Gemini; `sd-full-check` in
Cursor, GitHub Copilot, OpenCode, and Codex) is optional but strongly
recommended before PR readiness.
It runs deterministic checks, the generic
`scripts/sd-ai-command-pack-review-preflight.mjs`, any configured
`SD_AI_COMMAND_PACK_FULL_CHECK_REVIEW_PREFLIGHT_COMMAND`, the legacy repo-local
`scripts/check-review-preflight.mjs` when present, optional package-script
checks when a `package.json`, Node.js, and the selected package runner are
available, and a current-diff CI classification report when a target repo provides
`scripts/classify-ci-changes.sh`. During migration it also tolerates the legacy
`scripts/classify_ci_changes.sh` name by passing a temporary changed-files list,
but target classifiers should support
`bash scripts/classify-ci-changes.sh -- changed-file ...` so paths beginning
with `-` are handled as data. The command then runs local Prism review when
`prism` is available and configured. Gito stays
opt-in through `SD_AI_COMMAND_PACK_FULL_CHECK_GITO=1` because it may invoke `uvx`,
local cache access, network access, and configured LLM credentials. When
enabled, Gito writes reports to `.build/review/gito` by default; override with
`SD_AI_COMMAND_PACK_FULL_CHECK_GITO_OUT_DIR` when needed.

The review-local command (`/sd:review-local` in Claude/Gemini;
`sd-review-local` in Cursor, GitHub Copilot, OpenCode, and Codex) runs local
review providers against local changed files, or against the current branch
diff when there are no local changed files, and enters a user-selected fix loop.
By default it runs Prism and Gito through
`scripts/sd-ai-command-pack-review-local.sh`, presents grouped findings, asks
which findings to fix, fixes only selected items, and repeats the same local
review stack until no items are selected or no actionable findings remain. Use
`SD_AI_COMMAND_PACK_REVIEW_LOCAL_TOOLS` or pass tool names to the script to run
a specific stack, and configure third-party tools with
`SD_AI_COMMAND_PACK_REVIEW_LOCAL_<TOOL>_COMMAND`.

The review-local-all command (`/sd:review-local-all` in Claude/Gemini;
`sd-review-local-all` in Cursor, GitHub Copilot, OpenCode, and Codex) uses the
same fix-loop behavior but reviews the entire checked-out repository. It runs
`bash scripts/sd-ai-command-pack-review-local.sh --full-codebase`, which calls
`prism review codebase` for Prism and normally calls
`gito review --all --path <absolute-repo-root>` for Gito with an include filter
built from existing tracked files, so branch-diff deletions are not reviewed as
deleted diff paths. Prism and Gito scans use the pack's managed standard
exclusions for top-level AI/tooling/cache directories:

```text
.github/
.claude/
.codex/
.gemini/
.opencode/
.agents/
.build/
.git/
.pytest_cache/
.obsidian-kb/
.trellis/
.ruff_cache/
.venv/
.sd-ai-command-pack/
node_modules/
```

Gito
full-codebase reports go to `.build/review/gito-all` by default; override with
`SD_AI_COMMAND_PACK_REVIEW_LOCAL_ALL_GITO_OUT_DIR` when needed.
For `uvx`-based Gito wrappers, the runner sets `UV_CACHE_DIR` and `UV_TOOL_DIR`
to writable temp directories when they are unset. The installed
`.gito/sd-ai-command-pack.env` file sets `MAX_CONCURRENT_TASKS=4` for pack
review runners when the caller has not already provided a value. When Gito
reports provider rate limiting through an explicit HTTP 429 status such as
`ClientError: 429` or a 429 slow-down response, the runner retries with bounded
exponential backoff; tune that with
`SD_AI_COMMAND_PACK_REVIEW_LOCAL_GITO_MAX_ATTEMPTS`,
`SD_AI_COMMAND_PACK_REVIEW_LOCAL_GITO_RETRY_DELAY_SECONDS`, and
`SD_AI_COMMAND_PACK_REVIEW_LOCAL_GITO_RETRY_MAX_DELAY_SECONDS`. If Prism
full-codebase review returns an empty chunk response, the runner retries in
tracked-file batches; set
`SD_AI_COMMAND_PACK_REVIEW_LOCAL_PRISM_CODEBASE_FALLBACK=0` to disable that.
For third-party tools that need different full-scan arguments, configure
`SD_AI_COMMAND_PACK_REVIEW_LOCAL_ALL_<TOOL>_COMMAND`.

The start, continue, and finish-work commands are local namespace aliases for
the Trellis-provided `trellis-start`, `trellis-continue`, and
`trellis-finish-work` skills. They exist so day-to-day Trellis entry points can
be invoked through the same `sd` command namespace as the pack workflows.

The housekeeping command is for ending a single active development stream. If
the current feature branch has an open PR, the command runs `sd-finish-work`
first and pushes any archive or journal commits it creates. It then runs the
housekeeping script, which merges only when the PR is clean, green,
comment-clean, and exactly matches the local and remote branch heads. If that
gate is not satisfied, it behaves as a post-merge cleanup command:
fetch/prune, confirm the current feature branch's PR is merged and the local
branch head matches that PR before deleting anything, switch to the default
branch, fast-forward it, remove the merged local and remote branch, and finish
with a condensed "expected clean state" plus anomalies report.

The review-pr command runs a deterministic local PR gate before requesting the
configured remote reviewer. Its command-owned full-check invocation disables
Prism and Gito with `SD_AI_COMMAND_PACK_FULL_CHECK_PRISM=0` and
`SD_AI_COMMAND_PACK_FULL_CHECK_GITO=0`; run `sd-full-check`,
`sd-review-local`, or `sd-review-local-all` explicitly when you want those
local review tools. Unless the user explicitly asks for local-only review, it
requests remote review after a clean local pass and re-requests it after every
pushed review-fix commit made during the loop, up to the configured round
limit. The default remote reviewer is GitHub Copilot's
`copilot-pull-request-reviewer`; target repos can override it with
`SD_AI_COMMAND_PACK_REVIEW_PR_REMOTE_REVIEWER`,
`SD_AI_COMMAND_PACK_REVIEW_PR_REMOTE_REVIEWER_LABEL`,
`SD_AI_COMMAND_PACK_REVIEW_PR_REMOTE_AUTHOR_MATCH`,
`SD_AI_COMMAND_PACK_REVIEW_PR_REMOTE_REQUEST_COMMAND`, and
`SD_AI_COMMAND_PACK_REVIEW_PR_REMOTE_ROUND_LIMIT`.
If a running review-pr command observes that the PR is `MERGED`, it stops the
review loop and runs the post-merge housekeeping command. This is command-time
automation, not a background webhook; it cannot wake an inactive tool session.

The review-learnings command scans local diffs for repeat mechanical
review-cycle patterns, can include recent Copilot review comments via
`--github-days`, and updates a managed block in `docs/review-learnings.md` or a
`--target` file when `--update` is passed. Use it to turn repeated review
feedback into repo-specific instructions, checklists, tests, or preflight gates;
keep repo-specific invariants in the target repo and reusable signatures in the
pack.

The update-spec command runs the existing Trellis `trellis-update-spec` skill
without modifying or replacing it. After the update-spec pass, it checks whether
the repo has checked-in infrastructure for maintaining a repospec artifact. It
looks for exact Makefile targets or package scripts named `repospec`,
`update-repospec`, `refresh-repospec`, `repomix`, `update-repomix`, or
`refresh-repomix`; executable `scripts/` entries with those names or
`repo-map`, `update-repo-map`, or `refresh-repo-map` and an optional `.sh`,
`.py`, `.js`, `.mjs`, or `.ts` extension; then a documented command under a
`Repospec`, `Repomix`, or `Repository map` heading in `AGENTS.md` or
`README.md`. It does not infer commands from incidental prose. When that
infrastructure exists, the command uses it to refresh the repospec artifact
instead of hand-editing generated output. If that refresh uses Repomix or
another repository-map tool, follow the target repo's documented output path;
if no path is documented, prefer `docs/repomix-map.md` and report the chosen
path. It then checks whether the repo already has an architectural overview such as
`ARCHITECTURE.md`, `docs/ARCHITECTURE.md`, or a
`.trellis/spec/**/architecture*.md` document. It updates that overview only
when the completed work changes high-level architecture; otherwise it reports
`not present` or `not warranted` without creating a new overview.

The command also runs `scripts/sd-ai-command-pack-update-spec-kb.py` to maintain
`.obsidian-kb/` in the repo root and ensure that folder is listed in
`.gitignore` inside a managed `sd-ai-command-pack obsidian-kb` marker block.
For local-only installs, the same managed block is written to `.git/info/exclude`
instead. The folder contains copies of repo files that are useful as portable
knowledge-base context, such as README files, agent instructions, architecture
and decision docs, `.trellis/spec/**/*.md`, `.trellis/workflow.md`,
`.trellis/config.yaml`, repo-owned repospec or Repomix outputs such as
`docs/repomix-map.md`, and project manifests that explain the repository shape
when present. The helper writes those copies into visible semantic category
folders rather than mirroring hidden source paths, so generated KB file and
folder names do not start with `.` or use Trellis-specific naming. It should
avoid secrets, caches, build output, dependency/vendor directories, `.git/`,
`.trellis/workspace/`, and broad source trees unless a specific source
entrypoint is intentionally maintained as repo documentation. If an existing
`.obsidian-kb` folder was created by an older symlink-based helper, the refresh
replaces pack-owned relative symlinks with real copies in the category layout
and prunes the old mirrored generated paths.
The helper also creates and refreshes `.obsidian-kb/Dashboard - <repo>.md`,
a generated Markdown landing page that groups and links to the current KB
copies, adds a brief one-line description for each linked document, points to
`.obsidian-kb/LLM-KB - <repo>.md`, and includes a GitHub repository link when
`origin` is a GitHub remote. Dashboard and overview links are grouped by
semantic categories such as repository overview, agent guidance, specs, repo
maps, and project manifests rather than by source folder name.
`LLM-KB - <repo>.md` is a generated, self-contained overview for LLM and
Obsidian indexing. If a
user-owned file already exists at either generated path, the helper leaves it
untouched and reports a conflict. Use
`python3 scripts/sd-ai-command-pack-update-spec-kb.py --dry-run` to preview the
refresh, `--check` to verify the folder is current without writing files, and
`--help` for the safe CLI summary.

To use that generated folder inside an Obsidian vault, copy the repo's
`.obsidian-kb` folder into the vault. Recopy it after future `sd-update-spec`
runs when the repository knowledge changes. For macOS/Linux:

```bash
cp -R "$(pwd)/.obsidian-kb/." "/path/to/your/vault/Repo-KB"
```

For Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force -Path "C:\path\to\vault\Repo-KB" | Out-Null
Copy-Item -Recurse -Force -Path "C:\path\to\repo\.obsidian-kb\*" -Destination "C:\path\to\vault\Repo-KB"
```

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
| `SD_AI_COMMAND_PACK_REVIEW_LOCAL_TOOLS` | Local review tool set for `sd-review-local` or `sd-review-local-all`; unset uses the runner default. | unset |
| `SD_AI_COMMAND_PACK_REVIEW_LOCAL_<TOOL>_COMMAND` | Custom command for a named local review provider. | unset |
| `SD_AI_COMMAND_PACK_REVIEW_LOCAL_ALL_<TOOL>_COMMAND` | Full-codebase custom command for a named provider; unset falls back to the non-`ALL` command. | unset |
| `SD_AI_COMMAND_PACK_REVIEW_LOCAL_GITO_MAX_ATTEMPTS` | Max Gito attempts for HTTP 429 provider rate limits. | `2` |
| `SD_AI_COMMAND_PACK_REVIEW_LOCAL_GITO_RETRY_DELAY_SECONDS` | Initial Gito retry delay. | `30` |
| `SD_AI_COMMAND_PACK_REVIEW_LOCAL_GITO_RETRY_MAX_DELAY_SECONDS` | Maximum Gito retry delay after backoff. | `120` |
| `MAX_CONCURRENT_TASKS` | Gito LLM concurrency cap. Loaded from `.gito/sd-ai-command-pack.env` by pack runners when unset. | `4` |
| `SD_AI_COMMAND_PACK_REVIEW_LOCAL_PRISM_CODEBASE_FALLBACK` | Enables Prism full-codebase batch/path fallback after empty chunk responses. | `1` |
| `SD_AI_COMMAND_PACK_SCOPE_PR_BODY` | General PR body override for review-scope and fallback PR-body scope checks. | unset |
| `SD_AI_COMMAND_PACK_PR_BODY_SCOPE_PR_BODY` | PR body override consumed specifically by `sd-ai-command-pack-pr-body-scope.py`; unset falls back to `SD_AI_COMMAND_PACK_SCOPE_PR_BODY`. | unset |
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
shared `.agents` skills, full-check, housekeeping, review-scope, review-local
command assets, review-preflight, install-audit, review-learnings, PR-body
scope, and update-spec KB scripts,
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
It also ignores local AI-tool state such as `.claude/settings.local.json`,
tool caches, logs, sessions, tmp folders, Gito report/temp artifacts,
`.opencode/node_modules/`, and root `node_modules/` without blanket-ignoring
`.claude/`, `.codex/`, `.gemini/`, `.gito/`, or `.opencode/`.
It installs platform adapters only when the target repo has the corresponding
platform directory and a Trellis-owned marker for that platform, such as a
Trellis command, hook, skill, or Copilot hook file. A plain `.github` directory
for Actions is not enough.

Useful options:

```bash
python3 install.py /path/to/repo --dry-run
python3 install.py /path/to/repo --local-only
python3 install.py /path/to/repo --all
python3 install.py /path/to/repo --platform cursor --platform gemini
python3 install.py /path/to/repo --force
python3 install.py /path/to/repo --force --backup
```

After installing or refreshing a target repo, a quick smoke test is:

```bash
cd /path/to/repo
python3 scripts/sd-ai-command-pack-install-audit.py
bash -n scripts/sd-ai-command-pack-full-check.sh
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
left untouched. Use `--force` to overwrite them. The exception is an existing
`.prism/rules.json` and `.gito/config.toml`: once either differs from the pack
template, it is reported as `preserved` and is never overwritten or reported as
a conflict. Add `--backup` with `--force` to save a `.bak` copy of every
overwritten file next to the original before it is changed. The pack-owned
`.gito/sd-ai-command-pack.env` file is updateable like scripts and docs so the
standard Gito concurrency cap can be refreshed.

Platform filters always include the shared skills, full-check, housekeeping,
review-scope, review-preflight, review-local command assets, install-audit,
review-learnings, PR-body scope, and
update-spec KB scripts, Prism/Gito defaults, usage guide, and installed-targets
snapshot, because the review,
full-check, housekeeping, and update-spec adapters delegate to those shared
assets.
`--platform` and `--all`
are explicit overrides for repairing or bootstrapping adapters when the active
Trellis platform markers are missing. The update-spec adapter delegates to
the Trellis-provided `trellis-update-spec` skill in the target repo.

When the GitHub platform is installed, the installer also creates or updates a
managed `sd-ai-command-pack` block in `.github/copilot-instructions.md`. It
preserves existing repo-specific Copilot instructions, replaces only the marked
pack block on future installs, and adopts any earlier unmarked pack guidance
into the managed block so later installs can keep it refreshed. The block also
steers mixed PR reviews toward app behavior, data contracts, specs, tests,
operator docs, and repo-owned scripts instead of copied pack or Trellis payloads
unless those files have obvious syntax, secret, or integration-goal issues. It
also tells Copilot not to leave line comments on wording, spelling, links,
formatting, examples, or implementation details inside copied Trellis or copied
SD command-pack files. It asks Copilot to group duplicate root causes and point
to deterministic local checks when they already cover a repeated issue class,
or request a focused local fixture when a repeated issue needs a stronger
preflight.

Managed blocks are intentionally replaceable on future pack updates. They look
like this:

```gitignore
# sd-ai-command-pack trellis-gitignore start
# Generated by `python3 install.py`. DO NOT EDIT MANUALLY.
# Ignore local/runtime files without hiding shared Trellis or AI-tool adapters.
# Common local secrets and environment files.
.env
.env.*
!.env.example
!.env.ci
!.env.test

# Trellis local/runtime state.
.trellis/.runtime/
.trellis/.cache/

# Review/build artifacts.
.build/
code-review-report.json
code-review-report.md
sd-ai-command-pack-gito.*
sd-ai-command-pack-review-paths.*
sd-ai-command-pack-review-filters.*
sd-ai-command-pack-prism-codebase.*
sd-ai-command-pack-ci-paths.*
sd-ai-command-pack-uv-cache/
sd-ai-command-pack-uv-tools/

# AI-tool local state; keep shared platform adapters tracked.
.gito/**/*.local.*
.gito/**/.cache/
.gito/**/cache/
.gito/**/logs/
.gito/**/tmp/
.gito/**/*.log
node_modules/

# Project-local personal ignores can be added below this managed block.
# sd-ai-command-pack trellis-gitignore end
```

```markdown
<!-- SD-AI-COMMAND-PACK:COPILOT-GUIDANCE:START -->
Pack-owned review guidance lives here.
<!-- SD-AI-COMMAND-PACK:COPILOT-GUIDANCE:END -->
```

The full-check script also runs `scripts/sd-ai-command-pack-review-preflight.mjs`.
It is a generic dependency-free preflight for copied/generated disclosure,
documentation path hygiene, Trellis journal consistency, npm override drift,
and large diff warnings. Target repos can tune it with
`.sd-ai-command-pack/review-preflight.json`, including intentional Linux
service users through `allowedLinuxHomeUsers`.

The full-check script also runs `scripts/sd-ai-command-pack-install-audit.py`.
That helper checks `.sd-ai-command-pack/installed-targets.txt` for missing
installed targets and reports pack-like files that are not listed in the
installed-targets snapshot. Set `SD_AI_COMMAND_PACK_INSTALL_AUDIT=0` to skip it.

The full-check script also runs `scripts/sd-ai-command-pack-review-scope.sh`.
That helper reads `.sd-ai-command-pack/installed-targets.txt`, reports changed
pack/Trellis runtime files, known repository-map files when present, and
Trellis workspace journal/index files as integration-only review surface. When
the GitHub CLI can resolve a current PR, it can also ensure mixed PRs include a
`Tooling/generated scope:` section in the PR body. In CI or local preflights
where `gh pr view` should not run, pass the PR body through
`SD_AI_COMMAND_PACK_SCOPE_PR_BODY`.

Base-ref precedence for branch-diff helpers is explicit env override first,
then the discovered remote default ref, then the current branch upstream, then
the first available remote ref. Tool-specific variables such as
`SD_AI_COMMAND_PACK_REVIEW_LOCAL_GITO_BASE_REF` take precedence over broader
full-check variables.

The full-check script also runs `scripts/sd-ai-command-pack-pr-body-scope.py`.
That pack-provided checker is generic and config-driven: by default it checks
pack/Trellis generated files, housekeeping automation files, and CI/review
tooling files for matching PR-body sections when a PR body is provided. Target
repos can add runtime, docs, or other categories by committing
`.sd-ai-command-pack/pr-body-scope.json` with a `rules` list of `label`,
`headings`, and `patterns`. Set `include_installed_targets: true` on a rule
when the generated `.sd-ai-command-pack/installed-targets.txt` paths should be
classified under that rule. Use `SD_AI_COMMAND_PACK_PR_BODY_SCOPE_PR_BODY`,
`SD_AI_COMMAND_PACK_SCOPE_PR_BODY`, or deprecated `REVIEW_PREFLIGHT_PR_BODY` to
provide the body without calling `gh`.

For mixed command-pack or generated-map updates that also touch CI/review
automation, include both sections:

```markdown
Tooling/generated scope:
- Copied SD command-pack files or generated repository maps were refreshed.
- Review focus should be integration wiring, provenance, secrets, and docs
  accuracy.

CI/review scope:
- CI, review preflight, or command-pack adapter changes were made intentionally.
- Review focus should be command invocation, env propagation, and whether local
  checks still exercise the expected paths.
```

When a target repo provides `scripts/classify-ci-changes.sh`, the full-check
script prints a current-diff CI classification section before optional
repo-specific checks run. The canonical classifier accepts explicit paths after
`--`; when only the legacy `scripts/classify_ci_changes.sh` is present, the pack
passes a temp changed-files list directly. That gives agents and reviewers a local
`docs_only`, `app_required`, and `expensive_required` signal before spending
remote CI budget.

## Verify

The installer runs `git diff --check` on installed pack paths unless
`--skip-diff-check` is passed.

Run the pack tests with the explicit dev dependencies from
`requirements-dev.txt`, including `coverage.py` via the `coverage` package:

```bash
python3 -m pip install -r requirements-dev.txt
COVERAGE_PROCESS_START=.coveragerc python3 -m coverage run --parallel-mode -m unittest discover -s tests
python3 -m coverage combine
python3 -m coverage report --fail-under=100
```

The `--fail-under=100` gate measures `install.py` (the installer logic) only;
`.coveragerc` scopes coverage to that file. The shipped shell and Python helper
scripts under `scripts/` are exercised by their own runtime behavior, not by
this coverage number.

## Supported Adapters

| Platform | Installed When |
| --- | --- |
| Shared skills, scripts, Prism/Gito defaults, usage guide | Always |
| Codex skill completion | `.agents/skills/sd-*` installed as shared skills |
| Claude Code | `.claude/` exists with Trellis command, hook, or skill markers; or `--all` / `--platform claude` |
| Cursor | `.cursor/` exists with Trellis command, hook, or skill markers; or `--all` / `--platform cursor` |
| Gemini CLI | `.gemini/` exists with Trellis command, hook, or agent markers; or `--all` / `--platform gemini` |
| GitHub Copilot | `.github/` exists with Trellis hook, Copilot hook, or skill markers; or `--all` / `--platform github` |
| OpenCode | `.opencode/` exists with Trellis command, library, or skill markers; or `--all` / `--platform opencode` |

## License

This repository is licensed under the [MIT License](LICENSE).

## Upstream Path

This pack is intentionally shaped so pieces could move upstream later, while
the local command namespace stays pack-owned:

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

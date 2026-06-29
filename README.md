# SD AI Command Pack

[![Trellis](https://img.shields.io/badge/Trellis-trytrellis.app-255E63)](https://trytrellis.app/)
[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Tests](https://img.shields.io/badge/tests-unittest-2E7D32)](#verify)
[![License: MIT](https://img.shields.io/github/license/platypeeps/sd-ai-command-pack)](LICENSE)
[![Source](https://img.shields.io/badge/source-GitHub-181717?logo=github)](https://github.com/platypeeps/sd-ai-command-pack)

Install reusable AI workflow helpers into
[Trellis-managed repositories](https://trytrellis.app/). The current pack is
focused on Trellis enrichment: start, continue, finish-work, PR review,
full-check, post-merge housekeeping, and update-spec wrapper workflows. The
repository and `sd` command namespace are intentionally broader than that
initial scope, so future skills, commands, scripts, docs, or rules may cover
adjacent AI workflow support that is not strictly Trellis-specific.

This pack only works in a repo that already has Trellis installed and
initialized. If `trellis` is not available yet, follow the official
[Trellis install and first-task instructions](https://docs.trytrellis.app/start/install-and-first-task)
first; they cover installing the CLI with
`npm install -g @mindfoldhq/trellis@latest` and running `trellis init` so the
target repo has `.trellis/config.yaml`.

The current Trellis-focused pack includes:

- `.agents/skills/sd-start/SKILL.md`
- `.agents/skills/sd-continue/SKILL.md`
- `.agents/skills/sd-finish-work/SKILL.md`
- `.agents/skills/sd-full-check/SKILL.md`
- `.agents/skills/sd-housekeeping/SKILL.md`
- `.agents/skills/sd-update-spec/SKILL.md`
- `.agents/skills/sd-review-pr/SKILL.md`
- `scripts/sd-ai-command-pack-full-check.sh`
- `scripts/sd-ai-command-pack-housekeeping.sh`
- `scripts/sd-ai-command-pack-review-scope.sh`
- `scripts/sd-ai-command-pack-install-audit.py`
- `scripts/sd-ai-command-pack-pr-body-scope.py`
- `scripts/sd-ai-command-pack-update-spec-kb.py`
- `.prism/rules.json`
- `docs/SD_AI_COMMAND_PACK.md`
- `.claude/commands/sd/start.md`
- `.claude/commands/sd/continue.md`
- `.claude/commands/sd/finish-work.md`
- `.claude/commands/sd/full-check.md`
- `.claude/commands/sd/housekeeping.md`
- `.claude/commands/sd/update-spec.md`
- `.claude/commands/sd/review-pr.md`
- `.cursor/commands/sd-start.md`
- `.cursor/commands/sd-continue.md`
- `.cursor/commands/sd-finish-work.md`
- `.cursor/commands/sd-review-pr.md`
- `.cursor/commands/sd-full-check.md`
- `.cursor/commands/sd-housekeeping.md`
- `.cursor/commands/sd-update-spec.md`
- `.gemini/commands/sd/start.toml`
- `.gemini/commands/sd/continue.toml`
- `.gemini/commands/sd/finish-work.toml`
- `.gemini/commands/sd/review-pr.toml`
- `.gemini/commands/sd/full-check.toml`
- `.gemini/commands/sd/housekeeping.toml`
- `.gemini/commands/sd/update-spec.toml`
- `.github/prompts/sd-start.prompt.md`
- `.github/prompts/sd-continue.prompt.md`
- `.github/prompts/sd-finish-work.prompt.md`
- `.github/prompts/sd-review-pr.prompt.md`
- `.github/prompts/sd-full-check.prompt.md`
- `.github/prompts/sd-housekeeping.prompt.md`
- `.github/prompts/sd-update-spec.prompt.md`
- a managed `sd-ai-command-pack` guidance block in
  `.github/copilot-instructions.md`
- `.opencode/commands/sd-start.md`
- `.opencode/commands/sd-continue.md`
- `.opencode/commands/sd-finish-work.md`
- `.opencode/commands/sd-review-pr.md`
- `.opencode/commands/sd-full-check.md`
- `.opencode/commands/sd-housekeeping.md`
- `.opencode/commands/sd-update-spec.md`

The shared skills own the workflows. Platform command and prompt files are thin
entry points that tell the agent to load the appropriate shared skill.
Codex exposes pack entry points as enabled skills named `sd-start`, `sd-continue`,
`sd-finish-work`, `sd-full-check`, `sd-housekeeping`, `sd-review-pr`, and
`sd-update-spec`; type `/sd` in Codex command completion or invoke them
explicitly with `$sd-review-pr`-style skill mentions.
User-facing command adapters live under the `sd` namespace so pack-owned
wrappers do not collide with Trellis-owned generated `/trellis:*` commands on
future `trellis update` runs. Cursor command files, GitHub Copilot prompt
files, and OpenCode command files use flat `sd-<command>` filenames so their
slash-command completion lists can surface them when you type `/sd`.
The update-spec wrapper runs the Trellis-provided `trellis-update-spec` skill
as-is, refreshes repo-owned repospec artifacts through existing maintenance
infrastructure when available, then adds an explicit architectural-overview
check and rebuilds a repo-local `.obsidian-kb` folder of symlinks to
repository-knowledge files.
The start, continue, and finish-work wrappers similarly delegate to
Trellis-provided `trellis-start`, `trellis-continue`, and
`trellis-finish-work` skills without changing their behavior.
The installed `docs/SD_AI_COMMAND_PACK.md` file gives humans and agents a
repo-local usage guide for the commands, script, environment variables, local
review-provider behavior when available, and troubleshooting steps.

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
It runs deterministic checks, an optional repo-local review preflight when
`SD_AI_COMMAND_PACK_FULL_CHECK_REVIEW_PREFLIGHT_COMMAND` is configured or
`scripts/check-review-preflight.mjs` exists, optional package-script checks
when a `package.json`, Node.js, and the selected package runner are available,
then local Prism review when `prism` is available and configured. Gito stays
opt-in through `SD_AI_COMMAND_PACK_FULL_CHECK_GITO=1` because it may invoke `uvx`,
local cache access, network access, and configured LLM credentials. When
enabled, Gito writes reports to `.build/review/gito` by default; override with
`SD_AI_COMMAND_PACK_FULL_CHECK_GITO_OUT_DIR` when needed.

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

The review-pr command is local-review-first. It runs the full-check path and
any available local review providers before requesting the configured remote
reviewer, and treats remote review as an explicit final pass rather than the
default convergence mechanism. The default remote reviewer is GitHub Copilot's
`copilot-pull-request-reviewer`; target repos can override it with
`SD_AI_COMMAND_PACK_REVIEW_PR_REMOTE_REVIEWER`,
`SD_AI_COMMAND_PACK_REVIEW_PR_REMOTE_REVIEWER_LABEL`,
`SD_AI_COMMAND_PACK_REVIEW_PR_REMOTE_AUTHOR_MATCH`,
`SD_AI_COMMAND_PACK_REVIEW_PR_REMOTE_REQUEST_COMMAND`, and
`SD_AI_COMMAND_PACK_REVIEW_PR_REMOTE_ROUND_LIMIT`.
If an active review-pr session observes that the PR is `MERGED`, it stops the
review loop and runs the housekeeping command automatically. This is session
automation, not a background webhook; it cannot wake an inactive tool session.

The update-spec command runs the existing Trellis `trellis-update-spec` skill
without modifying or replacing it. After the update-spec pass, it checks whether
the repo has checked-in infrastructure for maintaining a repospec artifact, such
as repo docs, scripts, package tasks, or make targets. When that infrastructure
exists, the command uses it to refresh the repospec artifact instead of
hand-editing generated output. If that refresh uses Repomix or another
repository-map tool, follow the target repo's documented output path; if no
path is documented, prefer `docs/repomix-map.md` and report the chosen path. It
then checks whether the repo already has an
architectural overview such as
`ARCHITECTURE.md`, `docs/ARCHITECTURE.md`, or a
`.trellis/spec/**/architecture*.md` document. It updates that overview only
when the completed work changes high-level architecture; otherwise it reports
`not present` or `not warranted` without creating a new overview.

The command also runs `scripts/sd-ai-command-pack-update-spec-kb.py` to maintain
`.obsidian-kb/` in the repo root and ensure that folder is listed in
`.gitignore`. The folder contains symlinks to repo files that are useful as
knowledge-base context, such as README files, agent instructions, architecture
and decision docs, `.trellis/spec/**/*.md`, `.trellis/workflow.md`,
`.trellis/config.yaml`, repo-owned repospec or Repomix outputs such as
`docs/repomix-map.md`, and project manifests that explain the repository shape
when present. It should avoid secrets, caches, build output, dependency/vendor
directories, `.git/`, `.trellis/workspace/`, and broad source trees unless a
specific source entrypoint is intentionally maintained as repo documentation.

To expose that generated folder inside an Obsidian vault, create a symlink from
the vault to the repo's `.obsidian-kb` folder. For macOS/Linux:

```bash
ln -s /absolute/path/to/repo/.obsidian-kb /absolute/path/to/vault/Repo-KB
```

For Windows PowerShell:

```powershell
New-Item -ItemType SymbolicLink -Path "C:\path\to\vault\Repo-KB" -Target "C:\path\to\repo\.obsidian-kb"
```

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
shared `.agents` skills, full-check, housekeeping, review-scope, PR-body scope,
and update-spec KB scripts, Prism rules, usage guide, and the generated
`.sd-ai-command-pack/installed-targets.txt` snapshot used by the scope checks.
It installs platform adapters only when the target repo has the corresponding
platform directory and a Trellis-owned marker for that platform, such as a
Trellis command, hook, skill, or Copilot hook file. A plain `.github` directory
for Actions is not enough.

Useful options:

```bash
python3 install.py /path/to/repo --dry-run
python3 install.py /path/to/repo --all
python3 install.py /path/to/repo --platform cursor --platform gemini
python3 install.py /path/to/repo --force
python3 install.py /path/to/repo --force --backup
```

By default, existing files with different content are reported as conflicts and
left untouched. Use `--force` to overwrite them. The exception is an existing
`.prism/rules.json`: once it differs from the pack template, it is reported as
`preserved` and is never overwritten or reported as a conflict. Add `--backup`
with `--force` to save a `.bak` copy of every overwritten or deleted file next
to the original before it is changed.
When installing the `sd` adapters, the installer also removes old
pack-generated `/trellis:*` adapter files when their content still matches the
pack templates. Legacy or obsolete adapter files with other content are
reported as conflicts and left in place unless `--force` is supplied; with
`--force` they are deleted (add `--backup` to keep a `.bak` copy of each removed
file first) while the `sd` replacement is installed.

Platform filters always include the shared skills, full-check, housekeeping,
review-scope, PR-body scope, and update-spec KB scripts, Prism rules, usage
guide, and installed-targets snapshot, because the review, full-check,
housekeeping, and update-spec adapters delegate to those shared assets.
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
to deterministic local checks when they already cover a repeated issue class.

The full-check script also runs `scripts/sd-ai-command-pack-install-audit.py`.
That helper checks `.sd-ai-command-pack/installed-targets.txt` for missing
installed targets, fails on obsolete pack artifacts such as old `trellis-*`
full-check/housekeeping files or `sd-refresh-specs` adapters, and warns when
known generated repository maps still mention obsolete pack names. Set
`SD_AI_COMMAND_PACK_INSTALL_AUDIT=0` to skip it or
`SD_AI_COMMAND_PACK_INSTALL_AUDIT_STRICT_REFS=1` to make stale repository-map
references fail.

The full-check script also runs `scripts/sd-ai-command-pack-review-scope.sh`.
That helper reads `.sd-ai-command-pack/installed-targets.txt`, reports changed
pack/Trellis runtime files, known repository-map files when present, and
Trellis workspace journal/index files as integration-only review surface. When
the GitHub CLI can resolve a current PR, it can also ensure mixed PRs include a
`Tooling/generated scope:` section in the PR body. In CI or local preflights
where `gh pr view` should not run, pass the PR body through
`SD_AI_COMMAND_PACK_SCOPE_PR_BODY` or the compatibility fallback
`REVIEW_PREFLIGHT_PR_BODY`.

The full-check script also runs `scripts/sd-ai-command-pack-pr-body-scope.py`.
That pack-provided checker is generic and config-driven: by default it checks
pack/Trellis generated files, housekeeping automation files, and CI/review
tooling files for matching PR-body sections when a PR body is provided. Target
repos can add runtime, docs, or other categories by committing
`.sd-ai-command-pack/pr-body-scope.json` with a `rules` list of `label`,
`headings`, and `patterns`. Use `SD_AI_COMMAND_PACK_PR_BODY_SCOPE_PR_BODY`,
`SD_AI_COMMAND_PACK_SCOPE_PR_BODY`, or `REVIEW_PREFLIGHT_PR_BODY` to provide the
body without calling `gh`.

When a target repo provides `scripts/classify_ci_changes.sh`, the full-check
script prints a current-diff CI classification section before optional
repo-specific checks run. That gives agents and reviewers a local `docs_only`,
`app_required`, and `expensive_required` signal before spending remote CI
budget.

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
| Shared skills, scripts, Prism rules, usage guide | Always |
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

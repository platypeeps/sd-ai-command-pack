# SD AI command pack

This repo has the reusable SD AI command setup installed from
`platypeeps/sd-ai-command-pack`.

This pack assumes the repo is already initialized with Trellis. If another repo
is missing `trellis` or `.trellis/config.yaml`, follow the official
[Trellis install and first-task instructions](https://docs.trytrellis.app/start/install-and-first-task)
first; they cover `npm install -g @mindfoldhq/trellis@latest` and
`trellis init`.

Quick links:

- [What is installed](#what-is-installed)
- [Recommended review loop](#recommended-review-loop)
- [Local commands](#local-commands)
- [Configuration](#configuration)
- [Install or refresh this pack](#install-or-refresh-this-pack)
- [Troubleshooting](#troubleshooting)

## What is installed

- `.agents/skills/sd-review-pr/SKILL.md`: local-review-first PR workflow.
- `.agents/skills/sd-review-local/SKILL.md`: local review provider fix loop.
- `.agents/skills/sd-review-local-all/SKILL.md`: full-codebase local review
  provider fix loop.
- `.agents/skills/sd-review-learnings/SKILL.md`: review feedback learning
  capture workflow.
- `.agents/skills/sd-full-check/SKILL.md`: full local verification workflow.
- `.agents/skills/sd-housekeeping/SKILL.md`: post-merge cleanup workflow.
- `.agents/skills/sd-*/SKILL.md`: Codex-visible `sd` entry points, including
  the full `sd-review-pr`, `sd-review-local`, `sd-review-local-all`,
  `sd-full-check`, and `sd-housekeeping` workflows plus adapter-only aliases.
- `scripts/sd-ai-command-pack-full-check.sh`: canonical full-check script.
- `scripts/sd-ai-command-pack-housekeeping.sh`: canonical post-merge housekeeping script.
- `scripts/sd-ai-command-pack-review-scope.sh`: copied/generated file scope
  preflight for mixed PRs.
- `scripts/sd-ai-command-pack-review-preflight.mjs`: generic dependency-free
  review preflight for copied/generated disclosure, documentation path hygiene,
  Trellis journal consistency, npm override drift, and large diff warnings.
- `scripts/sd-ai-command-pack-review-local.sh`: local Prism/Gito and configured
  review-tool runner for the review-local and review-local-all loops.
- `scripts/sd-ai-command-pack-review-learnings.py`: local review feedback
  pattern scanner and managed learning-block updater.
- `scripts/sd-ai-command-pack-install-audit.py`: structural post-install audit
  for missing installed targets and unlisted pack-like files.
- `scripts/sd-ai-command-pack-pr-body-scope.py`: configurable PR-body scope
  preflight for broad behavior-changing diffs.
- `scripts/sd-ai-command-pack-update-spec-kb.py`: Obsidian KB symlink-folder
  refresh helper for the update-spec wrapper.
- `.sd-ai-command-pack/installed-targets.txt`: generated list of pack targets
  installed in this repo, used by the review-scope preflight. Normal shared
  installs should commit this file with the other pack-owned files; `--local-only`
  installs keep it in the clone-local exclude list instead.
- `.prism/rules.json`: default Prism review rules for repo-specific checks.
- Platform adapters under `.claude/`, `.cursor/`, `.gemini/`,
  `.github/prompts/`, and `.opencode/` only when those platform folders include
  active Trellis command, hook, skill, agent, or platform-library markers. A
  plain `.github` directory for Actions is not enough unless the installer is
  run with `--platform github` or `--all`.

The command and prompt files are entry points only. The workflow behavior lives
in the shared skills and scripts. The update-spec wrapper runs the
Trellis-provided `trellis-update-spec` skill as-is, refreshes repo-owned
repospec artifacts through existing maintenance infrastructure when available,
and then performs the architecture-overview check.
Codex exposes the pack entry points as skills named `sd-start`, `sd-continue`,
`sd-finish-work`, `sd-full-check`, `sd-housekeeping`, `sd-review-pr`,
`sd-review-local`, `sd-review-local-all`, `sd-review-learnings`, and
`sd-update-spec`; type `/sd` in Codex command completion or invoke them with
`$sd-review-pr`-style skill mentions.
The start, continue, and finish-work wrappers run Trellis' existing
`trellis-start`, `trellis-continue`, and `trellis-finish-work` skills as-is.
The slash command namespace is `sd`, not `trellis`, so these pack-owned wrappers
do not collide with generated Trellis commands during future `trellis update`
runs. Cursor command files, GitHub Copilot prompt files, and OpenCode command
files use flat `sd-<command>` filenames so completion lists can surface them
when you type `/sd`.
For Gemini CLI, the project command files intentionally live under
`.gemini/commands/sd/`; Gemini maps a file such as
`.gemini/commands/sd/review-pr.toml` to `/sd:review-pr` and shows the TOML
`description` in `/help`. If the commands were installed while Gemini CLI was
already running, use `/commands reload`, then `/commands list` to confirm the
loaded project command files.

## Recommended review loop

1. Iterate with the narrowest deterministic checks for the files you touched.
2. Use the continue command when resuming an in-progress Trellis task.
3. Run the full-check command or `bash scripts/sd-ai-command-pack-full-check.sh`
   before PR readiness, before asking for remote review, and after substantial
   review fixes.
4. Fix deterministic failures first, then verify findings from any available
   local review provider against the actual code before changing behavior.
5. Use the review-local command when you want a current-diff local Prism/Gito
   or configured review-tool loop before involving a remote reviewer. It asks
   which findings to fix and repeats until no items are selected.
6. Use the review-local-all command when you want the same local fix loop run
   against the entire checked-out repository rather than just recent diffs.
7. Use the review-pr command for the PR loop. It should run the local
   full-check path, including any configured local review providers, before
   requesting remote review.
8. Request the configured remote reviewer, defaulting to GitHub Copilot, only
   when explicitly wanted or as a final remote pass.
9. Let the review-pr command reply to and resolve review threads as part of the
   normal loop once findings are fixed, rebutted with evidence, or confirmed
   already addressed.
10. Use the review-learnings command when review comments repeat across PRs and
   you want to capture repo-specific preventive guidance.
11. Run the update-spec command when the work taught you a durable
   implementation contract or convention. It runs the existing update-spec skill
   and also checks whether an existing architectural overview needs to be
   updated.
12. Run the finish-work command when the coding session is complete and you need
   the Trellis finish-work skill's quality gate, archive, journal, and commit
   reminder behavior.
13. After the PR merges, run the housekeeping command to get back to the default
   branch, prune/delete the merged development stream, and see the condensed
   clean-state/anomaly report.
14. If the review-pr command sees the PR is already merged or becomes merged
   during the active session, it auto-dispatches housekeeping before the final
   report. This does not wake inactive sessions; it only runs when the active
   agent observes the merge.

The default remote reviewer for review-pr is GitHub Copilot's
`copilot-pull-request-reviewer`. Target repos can override it with
`SD_AI_COMMAND_PACK_REVIEW_PR_REMOTE_REVIEWER`,
`SD_AI_COMMAND_PACK_REVIEW_PR_REMOTE_REVIEWER_LABEL`,
`SD_AI_COMMAND_PACK_REVIEW_PR_REMOTE_AUTHOR_MATCH`,
`SD_AI_COMMAND_PACK_REVIEW_PR_REMOTE_REQUEST_COMMAND`, and
`SD_AI_COMMAND_PACK_REVIEW_PR_REMOTE_ROUND_LIMIT`.

## Commands

Use the platform-native command when available.

Claude Code and Gemini CLI:

```bash
/sd:start
/sd:continue
/sd:finish-work
/sd:full-check
/sd:housekeeping
/sd:review-pr
/sd:review-local
/sd:review-local-all
/sd:review-learnings
/sd:update-spec
```

Cursor command files, GitHub Copilot prompt files, OpenCode command files, and
Codex skills:

```bash
/sd-start
/sd-continue
/sd-finish-work
/sd-full-check
/sd-housekeeping
/sd-review-pr
/sd-review-local
/sd-review-local-all
/sd-review-learnings
/sd-update-spec
```

In Codex, you can also invoke the enabled skills explicitly with
`$sd-review-pr`-style skill mentions.

For GitHub Copilot, the installer also creates or updates a managed
`sd-ai-command-pack` block in `.github/copilot-instructions.md`. Existing
repo-specific Copilot instructions are preserved; only the marked pack block is
replaced on future installs. The block tells Copilot to ignore copied-in
Trellis runtime files and copied-in `sd-ai-command-pack` files unless a PR is
explicitly about those integrations. For mixed PRs, it tells Copilot to spend
review budget on app behavior, data contracts, specs, tests, operator docs, and
repo-owned scripts, and to comment on copied Trellis/SD-pack files only for
obvious syntax breakage, secret leakage, or a direct mismatch with the PR's
stated tooling goal. It explicitly tells Copilot not to leave line comments on
wording, spelling, links, formatting, examples, or implementation details inside
copied Trellis skills/agents/commands or copied SD command-pack
skills/prompts/scripts/docs/rules. It also asks Copilot to group duplicate root
causes and point to deterministic local checks when they already cover a
repeated issue class.

Use the script directly from any shell:

```bash
bash scripts/sd-ai-command-pack-full-check.sh
bash scripts/sd-ai-command-pack-review-local.sh
bash scripts/sd-ai-command-pack-review-local.sh --all
bash scripts/sd-ai-command-pack-housekeeping.sh
python3 scripts/sd-ai-command-pack-review-learnings.py --include-working-tree
```

The full-check script runs `git diff --check`, `git diff --cached --check`,
review preflight through `scripts/sd-ai-command-pack-review-preflight.mjs`, any
configured `SD_AI_COMMAND_PACK_FULL_CHECK_REVIEW_PREFLIGHT_COMMAND`, and the
legacy repo-local `scripts/check-review-preflight.mjs` when present. It then
runs the post-install audit, the tooling/generated file scope preflight, the
PR-body scope preflight, current-diff CI classification when
`scripts/classify-ci-changes.sh` exists, optional package-script checks when a
`package.json`, Node.js, and the selected package runner are available, and
local Prism review when `prism` is available and configured. For target repos
that provide a CI classifier, prefer `scripts/classify-ci-changes.sh` with
support for `-- changed-file ...`; the full-check script also tolerates legacy
`scripts/classify_ci_changes.sh` by passing a temp changed-files list directly.
The install audit checks
`.sd-ai-command-pack/installed-targets.txt` for missing targets, reports
pack-like files that are not listed in the installed-targets snapshot, and warns
when legacy pack names such as `trellis-full-check`, `trellis-housekeeping`,
`trellis-review-pr`, or `sd-refresh-specs` still appear in target files.
The copied/generated scope preflight reads
`.sd-ai-command-pack/installed-targets.txt`, reports changed pack/Trellis
runtime files, known repository-map files when present, and Trellis workspace
journal/index files as integration-only review surface. When the GitHub CLI can
resolve a current PR, it checks that the PR body includes a
`Tooling/generated scope:` section before review cycles spend attention on
copied or generated surfaces. In CI or local preflights where `gh pr view`
should not run, pass the PR body through `SD_AI_COMMAND_PACK_SCOPE_PR_BODY`.

The review preflight is intentionally generic and safe to run without project
dependencies. It checks for duplicate npm override sources of truth, changed
copied Trellis or SD command-pack surfaces without companion repo-owned
integration context, personal absolute paths in docs/prompts/specs, missing
repo path references in docs/prompts/specs, completed Trellis journal
placeholder or journal/index commit drift, and large diffs that are likely to
skip remote AI review. Target repos can tune roots, path-reference prefixes,
integration paths, optional paths, copied-template paths, and warning thresholds
with `.sd-ai-command-pack/review-preflight.json`. Repos that intentionally
document service-user paths under `/home/<user>/` can add those service users to
`allowedLinuxHomeUsers` in that config.

The review-local script defaults to Prism plus Gito and is intentionally
tool-stack aware. Its default scope is local-files-first: it reviews unstaged,
staged, and untracked local files when present; if there are no local changed
files, it reviews the current branch diff from the configured base. Pass tool
names as arguments, set
`SD_AI_COMMAND_PACK_REVIEW_LOCAL_TOOLS`, or configure a third-party tool with
`SD_AI_COMMAND_PACK_REVIEW_LOCAL_<TOOL>_COMMAND`. The review-local command uses
that script output to ask which findings to fix, applies only selected fixes,
and repeats the same tool stack until the user selects no more items.

Use `bash scripts/sd-ai-command-pack-review-local.sh --all` or the
review-local-all command when you want a full checked-out repository review.
In that mode, Prism runs `prism review codebase`; Gito normally runs
`gito review --all --path <repo-root>` and writes to `.build/review/gito-all`
by default. If tracked deletions are present in the working tree or deleted
files exist in the current branch diff, the runner omits `--all` and reviews
the explicit existing-file filter so deleted paths do not break Gito.
Prism and Gito scans use the pack's managed standard exclusions for
top-level AI/tooling/cache directories: `.github/`, `.claude/`, `.codex/`,
`.gemini/`, `.opencode/`, `.agents/`, `.build/`, `.git/`, `.pytest_cache/`,
`.obsidian-kb/`, `.trellis/`, `.ruff_cache/`, `.venv/`,
`.sd-ai-command-pack/`, and `node_modules/`. For `uvx`-based Gito wrappers, the
runner sets `UV_CACHE_DIR` and `UV_TOOL_DIR` to writable temp directories when
they are unset. When Gito reports provider rate limiting such as
`ClientError: 429` or `Slow down`, the runner retries with bounded exponential
backoff. Tune attempts and delays with
`SD_AI_COMMAND_PACK_REVIEW_LOCAL_GITO_MAX_ATTEMPTS`,
`SD_AI_COMMAND_PACK_REVIEW_LOCAL_GITO_RETRY_DELAY_SECONDS`, and
`SD_AI_COMMAND_PACK_REVIEW_LOCAL_GITO_RETRY_MAX_DELAY_SECONDS`. If Prism
full-codebase review returns an empty chunk response, the runner retries in
tracked-file batches and splits a failed batch down to individual paths when
needed. Configure third-party full-codebase scans with
`SD_AI_COMMAND_PACK_REVIEW_LOCAL_ALL_<TOOL>_COMMAND`; if that is not set, the
runner falls back to `SD_AI_COMMAND_PACK_REVIEW_LOCAL_<TOOL>_COMMAND`.

The PR-body scope preflight is generic and config-driven. By default it checks
pack/Trellis generated files, housekeeping automation files, and CI/review
tooling files for matching `Tooling/generated scope:`, `Automation scope:`, or
`CI/review scope:` sections when a PR body is provided. Target repos can add
runtime, docs, or other categories by committing
`.sd-ai-command-pack/pr-body-scope.json`:

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

```json
{
  "rules": [
    {
      "label": "Runtime/server scope",
      "headings": ["Runtime/server scope:", "Runtime scope:"],
      "patterns": ["src/**", "apps/**"]
    }
  ]
}
```

The start, continue, and finish-work wrappers each read the matching
Trellis-provided skill — `.agents/skills/trellis-start/`,
`.agents/skills/trellis-continue/`, or `.agents/skills/trellis-finish-work/`
respectively — and follow it without changing its behavior.

The update-spec wrapper reads the existing Trellis `trellis-update-spec` skill
from the target repo, follows it as-is to update `.trellis/spec/`, and then
checks whether the repo has checked-in infrastructure for maintaining a repospec
artifact. When repo docs, scripts, package tasks, make targets, or similar
commands describe how to generate or refresh the repospec, the wrapper uses that
infrastructure instead of hand-editing generated output. If that refresh uses
Repomix or another repository-map tool, follow the target repo's documented
output path; if no path is documented, prefer `docs/repomix-map.md` and report
the chosen path. It then checks for an
existing architectural overview. Candidate overview paths include
`ARCHITECTURE.md`, `ARCHITECTURE_OVERVIEW.md`, `docs/ARCHITECTURE.md`,
`docs/ARCHITECTURE_OVERVIEW.md`, and `.trellis/spec/**/architecture*.md`. If an
overview exists and the work changes high-level architecture such as packages,
command surfaces, data flow, persistence, external integrations, config/env, or
runtime/deployment topology, the wrapper updates it. Otherwise it leaves the
overview untouched and reports `not present` or `not warranted`.

The update-spec wrapper also runs
`scripts/sd-ai-command-pack-update-spec-kb.py` to maintain `.obsidian-kb/` in the
repo root and ensure that folder is listed in `.gitignore` inside a managed
`sd-ai-command-pack obsidian-kb` marker block. For local-only installs, the same
managed block is written to `.git/info/exclude` instead. The folder contains
symlinks to repository-knowledge files such as README files, agent instructions,
architecture and decision docs, `.trellis/spec/**/*.md`, `.trellis/workflow.md`,
`.trellis/config.yaml`, repo-owned repospec or Repomix outputs such as
`docs/repomix-map.md`, and project manifests that explain the repository shape
when present. It should avoid secrets, caches, build output, dependency/vendor
directories, `.git/`, `.trellis/workspace/`, and broad source trees unless a
specific source entrypoint is intentionally maintained as repo documentation.
The helper also creates and refreshes `.obsidian-kb/Dashboard.md`, a generated
Markdown landing page that groups and links to the current KB symlinks. If a
user-owned file already exists at that path, the helper leaves it untouched and
reports a conflict. Run
`python3 scripts/sd-ai-command-pack-update-spec-kb.py --dry-run` to preview the
refresh without writes, `--check` to verify the generated folder and ignore
entry are current, or `--help` for the safe CLI summary.

To expose the generated knowledge folder inside an Obsidian vault, create a
symlink from the vault to the repo's `.obsidian-kb` folder.

macOS/Linux:

```bash
ln -s /absolute/path/to/repo/.obsidian-kb /absolute/path/to/vault/Repo-KB
```

Windows PowerShell:

```powershell
New-Item -ItemType SymbolicLink -Path "C:\path\to\vault\Repo-KB" -Target "C:\path\to\repo\.obsidian-kb"
```

Windows symlink creation may require PowerShell running as Administrator or
Developer Mode enabled.

The housekeeping command ends a single active development stream. On an open
PR, it runs the SD finish-work flow before actual cleanup and pushes any
archive or journal commits that finish-work creates. It then runs the
housekeeping script, which checks a strict auto-merge gate: the working tree is
clean, the local branch head, remote branch head, and PR head all match, the PR
is open and not draft, the base is the default branch, merge state is clean,
reported checks are green, and there are no unresolved review threads. When
that is true, it merges the PR and then performs normal cleanup. If that gate is
not satisfied, it behaves as a post-merge cleanup command: fetch/prune
`origin`, confirm the current feature branch's PR is merged and the local branch
head matches that PR before deleting it, switch to the default branch,
fast-forward from `origin`, delete the merged local and remote branch, and then
report the expected clean state plus anomalies.

A clean housekeeping run should end with:

```text
==> Expected clean state
- branch: <default>
- working tree: clean
- <default> matches origin/<default>
- local branches: only <default>
- remote branches: only origin/HEAD and origin/<default>
- open PRs: none
- open issues: none
- Trellis active tasks: none

==> Anomalies
none
```

## Configuration

Common environment variables:

- `SD_AI_COMMAND_PACK_FULL_CHECK_BASE_REF`: explicit base ref for branch review.
  When unset, branch-diff helpers use the discovered remote default ref, then
  the current branch upstream, then the first available remote ref.
- `SD_AI_COMMAND_PACK_REVIEW_PREFLIGHT_BASE_REF`: explicit base ref for the
  JavaScript review-preflight branch-diff probes. Defaults to
  `SD_AI_COMMAND_PACK_FULL_CHECK_BASE_REF`, then the discovered branch-diff
  sequence above.
- `SD_AI_COMMAND_PACK_FULL_CHECK_REVIEW_PREFLIGHT=0`: skip
  repo-local review preflight.
- `SD_AI_COMMAND_PACK_FULL_CHECK_REVIEW_PREFLIGHT=required`: fail if no configured
  review preflight command can run and the shared or legacy review preflight is
  unavailable.
- `SD_AI_COMMAND_PACK_FULL_CHECK_REVIEW_PREFLIGHT_COMMAND`: repo-specific review
  preflight command to run with `bash -lc`.
- `SD_AI_COMMAND_PACK_FULL_CHECK_REVIEW_PREFLIGHT_SCRIPT`: custom JavaScript
  review preflight script to run before the legacy repo-local
  `scripts/check-review-preflight.mjs` fallback.
- `SD_AI_COMMAND_PACK_INSTALL_AUDIT=0`: skip the structural post-install audit.
- `SD_AI_COMMAND_PACK_INSTALL_AUDIT=required`: fail if the full-check cannot run
  the audit script.
- `SD_AI_COMMAND_PACK_FULL_CHECK_PACKAGE_SCRIPTS`: space-separated package scripts
  to run when `package.json` and the selected package runner are available.
- `SD_AI_COMMAND_PACK_FULL_CHECK_PACKAGE_RUNNER`: package runner. Defaults to
  `npm` when package-script checks apply.
- `SD_AI_COMMAND_PACK_FULL_CHECK_SKIP_PACKAGE_SCRIPTS=1`: skip package-script
  checks.
- `SD_AI_COMMAND_PACK_FULL_CHECK_PRISM=0`: skip Prism review.
- `SD_AI_COMMAND_PACK_FULL_CHECK_PRISM=required`: fail if Prism is missing,
  unauthenticated, or has provider/model configuration failures.
- `SD_AI_COMMAND_PACK_FULL_CHECK_PRISM_RULES`: explicit Prism rules file. Defaults to
  `.prism/rules.json` when present.
- `SD_AI_COMMAND_PACK_FULL_CHECK_PRISM_FAIL_ON`: severity that fails the Prism
  review (passed to `prism --fail-on`). Defaults to `high`.
- `SD_AI_COMMAND_PACK_FULL_CHECK_PRISM_MAX_FINDINGS`: cap on reported Prism
  findings (passed to `prism --max-findings`). Unset by default (no cap).
- `SD_AI_COMMAND_PACK_FULL_CHECK_GITO=1`: opt into Gito review.
- `SD_AI_COMMAND_PACK_FULL_CHECK_GITO_BASE_REF`: base ref for Gito review. Defaults to
  `SD_AI_COMMAND_PACK_FULL_CHECK_BASE_REF`, then the discovered branch-diff
  sequence above.
- `SD_AI_COMMAND_PACK_FULL_CHECK_GITO_OUT_DIR`: output folder for Gito reports. Defaults
  to `.build/review/gito`.
- `SD_AI_COMMAND_PACK_FULL_CHECK_GITO_MAX_ATTEMPTS`: max Gito attempts when the
  provider reports HTTP 429 or slow-down rate limiting. Defaults to the
  review-local Gito value, then `2`.
- `SD_AI_COMMAND_PACK_FULL_CHECK_GITO_RETRY_DELAY_SECONDS`: initial Gito retry
  delay for rate limits. Defaults to the review-local Gito value, then `30`.
- `SD_AI_COMMAND_PACK_FULL_CHECK_GITO_RETRY_MAX_DELAY_SECONDS`: maximum Gito
  retry delay after exponential backoff. Defaults to the review-local Gito
  value, then `120`.
- `SD_AI_COMMAND_PACK_REVIEW_LOCAL_TOOLS`: local review tool list for
  `sd-review-local`. Defaults to `prism gito`; accepts spaces or commas.
- `SD_AI_COMMAND_PACK_REVIEW_LOCAL_SCOPE=all`: run the local review runner
  against the full checked-out repository. Defaults to current-diff scope. The
  `sd-review-local-all` command passes this by invoking the runner with `--all`.
- `SD_AI_COMMAND_PACK_REVIEW_LOCAL_PRISM_MODE=0`: skip Prism in the local review
  runner. Defaults to required when Prism is selected.
- `SD_AI_COMMAND_PACK_REVIEW_LOCAL_PRISM_CODEBASE_FALLBACK=0`: disable the
  tracked-file batch fallback used when Prism full-codebase review reports an
  empty chunk response.
- `SD_AI_COMMAND_PACK_REVIEW_LOCAL_PRISM_CODEBASE_BATCH_SIZE`: tracked file
  batch size for that fallback before adaptive splitting. Defaults to `25`.
- `SD_AI_COMMAND_PACK_REVIEW_LOCAL_GITO_MODE=0`: skip Gito in the local review
  runner. Defaults to required when Gito is selected.
- `SD_AI_COMMAND_PACK_REVIEW_LOCAL_GITO_MAX_ATTEMPTS`: max Gito attempts when
  the provider reports HTTP 429 or slow-down rate limiting. Defaults to `2`.
- `SD_AI_COMMAND_PACK_REVIEW_LOCAL_GITO_RETRY_DELAY_SECONDS`: initial Gito retry
  delay for rate limits. Defaults to `30`.
- `SD_AI_COMMAND_PACK_REVIEW_LOCAL_GITO_RETRY_MAX_DELAY_SECONDS`: maximum Gito
  retry delay after exponential backoff. Defaults to `120`.
- `SD_AI_COMMAND_PACK_REVIEW_LOCAL_UV_CACHE_DIR`: fallback `UV_CACHE_DIR` for
  Gito when `UV_CACHE_DIR` is unset. Defaults to a temp
  `sd-ai-command-pack-uv-cache` directory.
- `SD_AI_COMMAND_PACK_REVIEW_LOCAL_UV_TOOL_DIR`: fallback `UV_TOOL_DIR` for
  Gito when `UV_TOOL_DIR` is unset. Defaults to a temp
  `sd-ai-command-pack-uv-tools` directory.
- `SD_AI_COMMAND_PACK_REVIEW_LOCAL_<TOOL>_COMMAND`: command for a repo-specific
  or third-party local review tool, run with `bash -lc`.
- `SD_AI_COMMAND_PACK_REVIEW_LOCAL_ALL_<TOOL>_COMMAND`: full-codebase command
  for a repo-specific or third-party local review tool. Takes precedence over
  `SD_AI_COMMAND_PACK_REVIEW_LOCAL_<TOOL>_COMMAND` when scope is `all`.
- `SD_AI_COMMAND_PACK_REVIEW_LOCAL_GITO_BASE_REF`: base ref for review-local Gito
  review. Defaults to `SD_AI_COMMAND_PACK_FULL_CHECK_GITO_BASE_REF`, then
  `SD_AI_COMMAND_PACK_FULL_CHECK_BASE_REF`, then the discovered branch-diff
  sequence above.
- `SD_AI_COMMAND_PACK_REVIEW_LOCAL_GITO_OUT_DIR`: output folder for review-local
  Gito reports. Defaults to `SD_AI_COMMAND_PACK_FULL_CHECK_GITO_OUT_DIR`, then
  `.build/review/gito`.
- `SD_AI_COMMAND_PACK_REVIEW_LOCAL_ALL_GITO_OUT_DIR`: output folder for
  review-local-all Gito reports. Defaults to
  `SD_AI_COMMAND_PACK_REVIEW_LOCAL_GITO_OUT_DIR`, then
  `SD_AI_COMMAND_PACK_FULL_CHECK_GITO_OUT_DIR`, then `.build/review/gito-all`.
- `SD_AI_COMMAND_PACK_SCOPE_CHECK=0`: skip tooling/generated file scope checks.
- `SD_AI_COMMAND_PACK_SCOPE_CHECK_GH=required`: fail when `gh` cannot resolve the
  current PR for the tooling/generated scope body check. Defaults to optional.
- `SD_AI_COMMAND_PACK_SCOPE_BASE_REF`: base ref for tooling/generated scope checks.
  Defaults to `SD_AI_COMMAND_PACK_FULL_CHECK_BASE_REF`, then the discovered
  branch-diff sequence above.
- `SD_AI_COMMAND_PACK_SCOPE_PR_BODY`: explicit PR body text for tooling/generated
  scope checks when `gh pr view` should not be used. Deprecated fallback:
  `REVIEW_PREFLIGHT_PR_BODY`.
- `SD_AI_COMMAND_PACK_PR_BODY_SCOPE_CHECK=0`: skip configurable PR-body scope
  checks.
- `SD_AI_COMMAND_PACK_PR_BODY_SCOPE_CHECK=required`: fail if the pack-provided
  PR-body scope checker cannot run, including when `python3` is missing.
- `SD_AI_COMMAND_PACK_PR_BODY_SCOPE_CONFIG`: explicit JSON config path for
  additional PR-body scope rules. Defaults to
  `.sd-ai-command-pack/pr-body-scope.json` when present.
- `SD_AI_COMMAND_PACK_PR_BODY_SCOPE_PR_BODY`: explicit PR body text for
  configurable PR-body scope checks. Falls back to
  `SD_AI_COMMAND_PACK_SCOPE_PR_BODY`, then the deprecated
  `REVIEW_PREFLIGHT_PR_BODY`.
- `SD_AI_COMMAND_PACK_PR_BODY_SCOPE_CHANGED_FILES`: explicit newline- or
  NUL-delimited changed path list for configurable PR-body scope checks.
- `SD_AI_COMMAND_PACK_HOUSEKEEPING_GITHUB_REPO`: explicit `owner/repo` slug when the
  selected remote URL cannot be parsed as a GitHub repository.
- `SD_AI_COMMAND_PACK_HOUSEKEEPING_MERGE_STRATEGY`: auto-merge strategy: `merge`,
  `squash`, or `rebase`. Defaults to `merge`.

Prism is enabled by default when the executable is present. If Prism is missing
or credentials/config are unavailable, the script reports the skip and continues
unless `SD_AI_COMMAND_PACK_FULL_CHECK_PRISM=required` is set.

Gito is opt-in because it can require `uvx`, cache access outside the repo,
network access, and configured LLM credentials. When enabled, Gito writes
reports to `.build/review/gito` by default so generated review artifacts do not
land at the repository root. If Gito reports provider rate limiting such as
`ClientError: 429` or `Slow down`, full-check retries with the same bounded
backoff behavior as review-local.

## CI cadence

Run the full-check locally before deliberately triggering expensive remote CI
or remote AI review. Repos can still use labels such as `full-ci`, manual
workflow dispatch, or ready-for-review transitions for provider-side expensive
checks.

## Housekeeping cadence

Run housekeeping after a PR is merged and any finish-work journal commit has
landed. If the command reports anomalies, treat them as the next manual action:
dirty files, an unmerged PR, extra branches, open PRs/issues, or remaining
Trellis tasks mean the repo is not yet in the expected clean state.

## Updating the pack

To refresh installed assets from the pack checkout:

```bash
python3 /path/to/sd-ai-command-pack/install.py /path/to/target/repo --force
```

Normal shared installs maintain a managed `sd-ai-command-pack
trellis-gitignore` block in the repo root `.gitignore`. The block ignores
Trellis local/runtime files such as `.trellis/.developer`,
`.trellis/.runtime/`, `.trellis/.cache/`, and `.trellis/.backup-*` without
blanket-ignoring shareable `.trellis` workflow, spec, task, and script files.
It also ignores local AI-tool state such as `.claude/settings.local.json`,
tool caches, logs, sessions, tmp folders, and `.opencode/node_modules/` without
blanket-ignoring `.claude/`, `.codex/`, `.gemini/`, or `.opencode/`.
The installer replaces exact unmarked `.trellis/` ignore entries with that
specific-pattern block.

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

# Trellis local/runtime state.
.trellis/.runtime/
.trellis/.cache/
# sd-ai-command-pack trellis-gitignore end
```

```markdown
<!-- SD-AI-COMMAND-PACK:COPILOT-GUIDANCE:START -->
Pack-owned review guidance lives here.
<!-- SD-AI-COMMAND-PACK:COPILOT-GUIDANCE:END -->
```

For a personal setup that should not add generated framework files to the
shared GitHub repository, install with:

```bash
python3 /path/to/sd-ai-command-pack/install.py /path/to/target/repo --local-only
```

Local-only mode runs `trellis init --yes --skip-existing --codex` when Trellis
is not initialized yet, passes through requested installer platforms such as
`--platform cursor`, and writes Trellis plus sd-ai-command-pack generated paths
to `.git/info/exclude`. It also creates `.sd-ai-command-pack/local-only.txt` so
pack helpers keep generated local state, including `.obsidian-kb/`, out of
tracked `.gitignore`. It also keeps `.sd-ai-command-pack/installed-targets.txt`
clone-local in this mode. If a generated framework file is already tracked by
Git, the installer stops because clone-local excludes cannot hide tracked files.

Use `--dry-run` first when you want to inspect which files would change.
Use `--backup` with `--force` if the target repo may have local edits that need
to be preserved next to the overwritten files. An existing `.prism/rules.json`
that differs from the pack template is reported as `preserved` and is never
overwritten or reported as a conflict, so repo-specific Prism rules are not
replaced during a pack refresh.

After installing or refreshing a target repo, a quick smoke test is:

```bash
cd /path/to/repo
python3 scripts/sd-ai-command-pack-install-audit.py
bash -n scripts/sd-ai-command-pack-full-check.sh scripts/sd-ai-command-pack-review-local.sh scripts/sd-ai-command-pack-review-scope.sh
python3 scripts/sd-ai-command-pack-update-spec-kb.py --dry-run
```

## Troubleshooting

- Missing an `sd-*` command: reinstall the pack and include the platform
  adapter for the tool you are using. Claude and Gemini expose these as
  `/sd:<command>`; GitHub Copilot, OpenCode, and Codex expose flat
  `/sd-<command>` entries.
- In Gemini CLI, after reinstalling run `/commands reload` and then
  `/commands list`; the loaded project files should include
  `.gemini/commands/sd/<command>.toml`.
- The update-spec command reports a missing `trellis-update-spec` skill: run
  `trellis update` in the target repo so the Trellis-provided skill files are
  present, then retry the wrapper command.
- `scripts/sd-ai-command-pack-update-spec-kb.py` is missing: reinstall the pack;
  update-spec uses it to rebuild `.obsidian-kb/`.
- Install audit warns about legacy `trellis-*` or `sd-refresh-specs` names:
  migrate those references to the current `sd-*` command names and
  `sd-ai-command-pack-*` scripts, then rerun the audit.
- `scripts/sd-ai-command-pack-full-check.sh` is missing: reinstall the pack; every target
  repo should receive the shared script.
- `scripts/sd-ai-command-pack-housekeeping.sh` is missing: reinstall the pack; every
  target repo should receive the shared script.
- Prism authentication/config failure: configure Prism locally, set
  `SD_AI_COMMAND_PACK_FULL_CHECK_PRISM=0` to skip it, or set
  `SD_AI_COMMAND_PACK_FULL_CHECK_PRISM=required` when review must be mandatory.
- Gito fails due to cache, network sandboxing, or provider rate limiting:
  `sd-review-local` and `sd-review-local-all` set writable `UV_CACHE_DIR` and
  `UV_TOOL_DIR` defaults and retry HTTP 429 / slow-down responses with bounded
  backoff. If the failure is network or credential related, run from an
  environment with the needed access. For `sd-full-check`, leave
  `SD_AI_COMMAND_PACK_FULL_CHECK_GITO` unset unless Gito is configured locally.
- Root-level `code-review-report.*` files appear after manual Gito runs: move
  or delete them, then rerun through `SD_AI_COMMAND_PACK_FULL_CHECK_GITO=1
  bash scripts/sd-ai-command-pack-full-check.sh` so reports go under `.build/review/gito`.
- Stale generated cache causes type or build failures: clear the repo-specific
  generated cache and rerun the deterministic check that failed.

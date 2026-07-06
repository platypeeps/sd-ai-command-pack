# Adapter Guidelines

> How shared workflow instructions and platform entry points are written.

---

## Overview

The shared skill is the product. Platform adapters are thin entry points that
load the shared skill and summarize the required behavior.

Reference files:

- `templates/.agents/skills/sd-review-pr/SKILL.md`
- `templates/.agents/skills/sd-review-local/SKILL.md`
- `templates/.agents/skills/sd-review-local-all/SKILL.md`
- `templates/.agents/skills/sd-full-check/SKILL.md`
- `templates/.agents/skills/sd-housekeeping/SKILL.md`
- `templates/.agents/skills/sd-continue/SKILL.md`
- `templates/.agents/skills/sd-finish-work/SKILL.md`
- `templates/.agents/skills/sd-update-spec/SKILL.md`
- `templates/scripts/sd-ai-command-pack-review-local.sh`
- `templates/.claude/commands/sd/continue.md`
- `templates/.claude/commands/sd/finish-work.md`
- `templates/.claude/commands/sd/review-pr.md`
- `templates/.claude/commands/sd/review-local.md`
- `templates/.claude/commands/sd/review-local-all.md`
- `templates/.cursor/commands/sd-review-local.md`
- `templates/.cursor/commands/sd-review-local-all.md`
- `templates/.cursor/commands/sd-review-pr.md`
- `templates/.gemini/commands/sd/review-pr.toml`
- `templates/.github/prompts/sd-review-pr.prompt.md`
- `templates/.opencode/commands/sd-review-pr.md`

## Shared Skill Pattern

Keep detailed workflow rules in the matching shared skill under
`templates/.agents/skills/<command>/SKILL.md`.

The `sd-review-pr` shared skill should continue to define:

- required local checks before starting, including `gh --version`,
  `gh auth status`, and PR resolution from the current branch
- a deterministic local full-check gate that disables Prism and Gito for the
  command-owned PR cycle; those local review tools should run only through an
  explicit `sd-full-check`, `sd-review-local`, or `sd-review-local-all`
  invocation
- a local `HEAD` versus PR `headRefOid` check before marking a PR ready or
  requesting review, so the remote reviewer sees the pushed code the user
  intends
- dirty working-tree classification before staging or committing
- the configured remote reviewer request path and fallback, with GitHub Copilot
  as the default reviewer
- polling behavior that avoids fetching full comment bodies on every interval
- thread-aware review inspection through GraphQL when using `gh`
- CI check inspection and failed-log routing
- standing permission to reply to review comments and resolve addressed review
  threads without asking for separate approval
- reply, resolve, fix, commit, and push behavior
- the five-round limit before asking the user to continue
- automatic Trellis finish-work after a clean final review
- the final report fields

The `sd-full-check` shared skill should continue to define the canonical
local verification script, deterministic checks, optional local review-provider
behavior, skipped-check reporting, and no-edit safety rules.

The `sd-create-pr` shared skill should never stop only because the current
checkout is on the repository default branch. It should create a feature
branch before committing or opening a PR, preferring
`SD_AI_COMMAND_PACK_CREATE_PR_BRANCH`, then a derived `codex/<slug>` from
`SD_AI_COMMAND_PACK_CREATE_PR_BRANCH_SLUG` or the commit message, with a
timestamped fallback for empty or colliding names.

The `sd-review-local` and `sd-review-local-all` shared skills should continue
to define the interactive local review/fix loop while delegating provider
execution to `scripts/sd-ai-command-pack-review-local.sh`. Keep their behavior
parallel except for review scope:

- `sd-review-local` reviews local changes first; when no local changes exist,
  it reviews the current branch diff against the configured base ref.
- `sd-review-local-all` reviews the full checked-out repository and should not
  infer scope from dirty-state or branch diffs.
- Both commands should default to the configured local providers, currently
  Prism and Gito, and remain open to repo-local custom providers named through
  `SD_AI_COMMAND_PACK_REVIEW_LOCAL_TOOLS`.
- Custom provider commands are shell snippets supplied by the target repo or
  user configuration; run them with `bash -c` from the repo root so profile
  startup files do not unexpectedly change review behavior.
- Standard review exclusions must stay aligned across providers. Prism receives
  exclusions from the runner through `--exclude`; Gito receives distributed
  defaults through `.gito/config.toml`, with the runner also filtering full
  codebase path lists to tracked, existing files outside excluded top-level
  directories.
- Gito HTTP 429 handling should retry only when recent output contains an
  explicit error-like 429 or slow-down response. Do not retry because prose,
  docs, or source examples mention `429`.
- The runner must register temporary files as they are created and remove them
  through its cleanup trap, including paths created by Prism chunking, Gito
  output capture, and review path/filter generation.

The `sd-housekeeping` shared skill should continue to define the
post-merge task list, the expected clean-state report, anomaly reporting, and
safety rules that prevent deleting branches unless GitHub confirms the PR is
merged and the local branch head matches that PR.

Codex does not read the platform command adapter directories for slash-command
completion. It exposes enabled skills in the slash list, so this pack also
installs `sd-*` skills under `.agents/skills/`. Keep the shared skills parallel
with the platform `sd` adapters, and keep each command's detailed behavior in
its matching shared skill.

GitHub Copilot prompt adapters use `.github/prompts/sd-<command>.prompt.md`
with YAML frontmatter descriptions and `mode: agent`, so prompt completion has
explicit metadata and runs in agent mode. Cursor and OpenCode command adapters
use flat `.cursor/commands/sd-<command>.md` and
`.opencode/commands/sd-<command>.md` filenames because those platforms surface
flat command names from markdown filenames in their command directories.

Gemini CLI command adapters use TOML under `.gemini/commands/sd/<command>.toml`
because Gemini derives command names from paths under `.gemini/commands/`, with
subdirectories becoming colon namespaces. Keep the `sd/` directory for Gemini;
it is what makes `/sd:<command>` appear. Give every Gemini command a useful
one-line `description`, since Gemini shows it in `/help`.

The `sd-start`, `sd-continue`, `sd-finish-work`, and `sd-update-spec` shared
skills are wrappers around Trellis-provided skills. Do not copy, fork, or
modify Trellis' built-in `trellis-start`, `trellis-continue`,
`trellis-finish-work`, or `trellis-update-spec` skills in `templates/`. Each
shared wrapper should locate the matching Trellis-provided skill in the target
repo and follow it as-is.

The `sd-update-spec` shared skill should locate the existing Trellis
`trellis-update-spec` skill, follow that skill as-is for its `.trellis/spec/`
update process, then refresh repo-owned repospec artifacts through existing
maintenance infrastructure when available, perform the pack-specific
architectural-overview gate, and rebuild the repo-local `.obsidian-kb` folder:

- If the repo has checked-in infrastructure for maintaining a repospec artifact
  (docs, scripts, package tasks, make targets, or similar), use that
  infrastructure to refresh the artifact.
- Do not hand-edit generated repospec output unless repo docs explicitly say
  that file is the source of truth.
- Do not create new repospec infrastructure or a new repospec artifact unless
  the user asks.
- When the repospec refresh uses Repomix or another repository-map tool, follow
  the target repo's documented output path. If no path is documented, prefer
  `docs/repomix-map.md` and report the chosen path.

- Search for an existing architecture overview, such as `ARCHITECTURE.md`,
  `docs/ARCHITECTURE.md`, or `.trellis/spec/**/architecture*.md`.
- Update it only when the work changes high-level architecture: packages,
  services, command surfaces, data flow, persistence, external integrations,
  config/env, or runtime/deployment topology.
- Do not create a new overview unless the user asks.
- Ensure `.obsidian-kb/` is listed in the repo root `.gitignore`.
- Run `python3 scripts/sd-ai-command-pack-update-spec-kb.py` to create or
  refresh `.obsidian-kb/` with real copies of repository-knowledge files such
  as README files, agent instructions, architecture and decision docs,
  `.trellis/spec/**/*.md`, `.trellis/workflow.md`, `.trellis/config.yaml`, and
  repo-owned repospec or Repomix outputs such as `docs/repomix-map.md`.
- The helper should place copies under visible semantic category folders rather
  than raw hidden source paths, and generated KB file/folder names should not
  start with `.` or use Trellis-specific naming.
- If an existing `.obsidian-kb/` folder came from the older symlink helper, the
  refresh should replace pack-owned relative symlinks with category-layout
  copies and report how many legacy symlinks were converted.
- The generated dashboard should link to the GitHub repository when `origin`
  resolves to GitHub, and `.obsidian-kb/LLM-KB - <repo>.md` should provide an
  indexable, self-contained overview for LLM and Obsidian use.
- Generated dashboard and overview sections should group links by semantic
  categories, not raw source folder names.
- The dashboard filename should be `Dashboard - <repo>.md`, and dashboard link
  entries should include brief one-line document descriptions.
- The overview filename should be `LLM-KB - <repo>.md`; old generated
  `LLM-KB.md` files with the pack marker should be pruned during refresh.
- Do not copy secrets, caches, build output, dependency/vendor directories,
  `.git/`, `.trellis/workspace/`, or broad source trees unless a specific source
  entrypoint is intentionally maintained as repo documentation.
- Report `Update-spec skill`, `Spec updates`, `Repospec`,
  `Architectural overview`, `Obsidian KB`, `Obsidian vault copy`, and
  `Validation` in the final response.

## Platform Adapter Pattern

Adapters should stay short and parallel:

1. State the command goal.
2. Tell the agent to read the matching `.agents/skills/<command>/SKILL.md`.
3. Summarize only the command's high-level behavior.
4. Include any command-specific safety stop condition.
5. Include the expected final reporting shape.

The Gemini adapter uses TOML because Gemini commands require it. GitHub Copilot
and OpenCode adapters use Markdown with short YAML frontmatter metadata.

## Drift Control

When changing adapter wording, check all adapters in the same pass. The
adapters intentionally have equivalent prompt text with only format-level
differences.

When changing workflow details, change the shared skill first. Adapter text
should only be updated if the summary becomes inaccurate.

## Anti-Patterns

- Do not copy the full shared workflow into every adapter.
- Do not introduce a platform-specific trigger unless the target platform
  requires it and the README/test coverage are updated.
- Do not describe unsupported shortcuts as reliable, such as assuming a reviewer
  bot comment trigger works everywhere.
- Do not let adapter files drift into different behavior for the same command.

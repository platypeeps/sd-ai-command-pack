# Adapter Guidelines

> How shared workflow instructions and platform entry points are written.

---

## Overview

The shared skill is the product. Platform adapters are thin entry points that
load the shared skill and summarize the required behavior.

Reference files:

- `templates/.agents/skills/trellis-review-pr/SKILL.md`
- `templates/.agents/skills/trellis-full-check/SKILL.md`
- `templates/.agents/skills/trellis-housekeeping/SKILL.md`
- `templates/.agents/skills/sd-continue/SKILL.md`
- `templates/.agents/skills/sd-finish-work/SKILL.md`
- `templates/.agents/skills/sd-full-check/SKILL.md`
- `templates/.agents/skills/sd-housekeeping/SKILL.md`
- `templates/.agents/skills/sd-review-pr/SKILL.md`
- `templates/.agents/skills/sd-refresh-specs/SKILL.md`
- `templates/.claude/commands/sd/continue.md`
- `templates/.claude/commands/sd/finish-work.md`
- `templates/.claude/commands/sd/review-pr.md`
- `templates/.gemini/commands/sd/review-pr.toml`
- `templates/.github/prompts/sd-review-pr.prompt.md`
- `templates/.opencode/commands/sd-review-pr.md`

## Shared Skill Pattern

Keep detailed workflow rules in the matching shared skill under
`templates/.agents/skills/<command>/SKILL.md`.

The `trellis-review-pr` shared skill should continue to define:

- required local checks before starting, including `gh --version`,
  `gh auth status`, and PR resolution from the current branch
- a local `HEAD` versus PR `headRefOid` check before marking a PR ready or
  requesting review, so Copilot reviews the pushed code the user intends
- dirty working-tree classification before staging or committing
- the Copilot review request path and fallback
- polling behavior that avoids fetching full comment bodies on every interval
- thread-aware review inspection through GraphQL when using `gh`
- CI check inspection and failed-log routing
- standing permission to reply to review comments and resolve addressed review
  threads without asking for separate approval
- reply, resolve, fix, commit, and push behavior
- the five-round limit before asking the user to continue
- automatic Trellis finish-work after a clean final review
- the final report fields

The `trellis-full-check` shared skill should continue to define the canonical
local verification script, deterministic checks, Prism behavior, optional Gito
behavior, skipped-check reporting, and no-edit safety rules.

The `trellis-housekeeping` shared skill should continue to define the
post-merge task list, the expected clean-state report, anomaly reporting, and
safety rules that prevent deleting branches unless GitHub confirms the PR is
merged and the local branch head matches that PR.

Codex does not read the platform command adapter directories for slash-command
completion. It exposes enabled skills in the slash list, so this pack also
installs thin `sd-*` wrapper skills under `.agents/skills/`. Keep those wrappers
parallel with the platform `sd` adapters.

GitHub Copilot prompt adapters use `.github/prompts/sd-<command>.prompt.md`
with YAML frontmatter descriptions and `mode: agent`, so prompt completion has
explicit metadata and runs in agent mode. OpenCode command adapters use flat
`.opencode/commands/sd-<command>.md` filenames because OpenCode derives command
names from markdown filenames in `.opencode/commands/`.

Gemini CLI command adapters use TOML under `.gemini/commands/sd/<command>.toml`
because Gemini derives command names from paths under `.gemini/commands/`, with
subdirectories becoming colon namespaces. Keep the `sd/` directory for Gemini;
it is what makes `/sd:<command>` appear. Give every Gemini command a useful
one-line `description`, since Gemini shows it in `/help`.

The `continue` and `finish-work` commands are adapter-only aliases in this
pack. Do not copy, fork, or modify Trellis' built-in `trellis-continue` or
`trellis-finish-work` skills in `templates/.agents/skills/`. Each wrapper
should read the matching Trellis-provided skill from the target repo and follow
it as-is.

The `refresh-specs` command is intentionally adapter-only in this pack. Do not
copy, fork, or modify Trellis' built-in `trellis-update-spec` skill in
`templates/.agents/skills/`. Each wrapper should locate the existing skill in
the target repo, follow that skill as-is for its `.trellis/spec/` update
process, then refresh repo-owned repospec artifacts through existing
maintenance infrastructure when available, and then perform the pack-specific
architectural-overview gate:

- If the repo has checked-in infrastructure for maintaining a repospec artifact
  (docs, scripts, package tasks, make targets, or similar), use that
  infrastructure to refresh the artifact.
- Do not hand-edit generated repospec output unless repo docs explicitly say
  that file is the source of truth.
- Do not create new repospec infrastructure or a new repospec artifact unless
  the user asks.
- When the repospec refresh uses Repomix, require the generated output path to
  be `docs/repomix-map.md`; do not leave a differently named Repomix map as the
  final artifact.

- Search for an existing architecture overview, such as `ARCHITECTURE.md`,
  `docs/ARCHITECTURE.md`, or `.trellis/spec/**/architecture*.md`.
- Update it only when the work changes high-level architecture: packages,
  services, command surfaces, data flow, persistence, external integrations,
  config/env, or runtime/deployment topology.
- Do not create a new overview unless the user asks.
- Report `Update-spec skill`, `Spec updates`, `Repospec`,
  `Architectural overview`, and `Validation` in the final response.

These adapter-only wrappers are intentional exceptions to the usual
pack-shared-skill adapter pattern. Do not force them to read
`.agents/skills/<command>/SKILL.md` unless this pack also starts installing and
owning that matching shared skill.

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
- Do not describe unsupported shortcuts as reliable, such as assuming an
  `@copilot review` comment trigger works everywhere.
- Do not let adapter files drift into different behavior for the same command.

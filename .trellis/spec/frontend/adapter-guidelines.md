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
- `templates/.claude/commands/sd/continue.md`
- `templates/.claude/commands/sd/finish-work.md`
- `templates/.claude/commands/sd/review-pr.md`
- `templates/.gemini/commands/sd/review-pr.toml`
- `templates/.github/prompts/sd-review-pr.prompt.md`
- `templates/.opencode/commands/sd/review-pr.md`

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

The `continue` and `finish-work` commands are adapter-only aliases in this
pack. Do not copy, fork, or modify Trellis' built-in `trellis-continue` or
`trellis-finish-work` skills in `templates/.agents/skills/`. Each wrapper
should read the matching Trellis-provided skill from the target repo and follow
it as-is.

The `refresh-specs` command is intentionally adapter-only in this pack. Do not
copy, fork, or modify Trellis' built-in `trellis-update-spec` skill in
`templates/.agents/skills/`. Each wrapper should locate the existing skill in
the target repo, follow that skill as-is for its `.trellis/spec/` update
process, and then perform the pack-specific architectural-overview gate:

- Search for an existing architecture overview, such as `ARCHITECTURE.md`,
  `docs/ARCHITECTURE.md`, or `.trellis/spec/**/architecture*.md`.
- Update it only when the work changes high-level architecture: packages,
  services, command surfaces, data flow, persistence, external integrations,
  config/env, or runtime/deployment topology.
- Do not create a new overview unless the user asks.
- Report `Update-spec skill`, `Spec updates`, `Architectural overview`, and
  `Validation` in the final response.

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
and OpenCode adapters use Markdown.

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

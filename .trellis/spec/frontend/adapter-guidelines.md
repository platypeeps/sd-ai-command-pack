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
- `templates/.gemini/commands/trellis/review-pr.toml`
- `templates/.github/prompts/review-pr.prompt.md`
- `templates/.opencode/commands/trellis/review-pr.md`

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

When changing adapter wording, check all adapters in the same pass. The current
three adapters intentionally have equivalent prompt text with only format-level
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

# Adapter Guidelines

> How shared workflow instructions and platform entry points are written.

---

## Overview

The shared skill is the product. Platform adapters are thin entry points that
load the shared skill and summarize the required behavior.

Reference files:

- `templates/.agents/skills/trellis-review-pr/SKILL.md`
- `templates/.gemini/commands/trellis/review-pr.toml`
- `templates/.github/prompts/review-pr.prompt.md`
- `templates/.opencode/commands/trellis/review-pr.md`

## Shared Skill Pattern

Keep detailed workflow rules in
`templates/.agents/skills/trellis-review-pr/SKILL.md`.

The shared skill should continue to define:

- required local checks before starting, including `gh --version`,
  `gh auth status`, and PR resolution from the current branch
- a local `HEAD` versus PR `headRefOid` check before marking a PR ready or
  requesting review, so Copilot reviews the pushed code the user intends
- dirty working-tree classification before staging or committing
- the Copilot review request path and fallback
- polling behavior that avoids fetching full comment bodies on every interval
- thread-aware review inspection through GraphQL when using `gh`
- CI check inspection and failed-log routing
- reply, resolve, fix, commit, and push behavior
- the five-round limit before asking the user to continue
- automatic Trellis finish-work after a clean final review
- the final report fields

## Platform Adapter Pattern

Adapters should stay short and parallel:

1. State the command goal: run the Trellis PR review loop.
2. Tell the agent to read `.agents/skills/trellis-review-pr/SKILL.md`.
3. Summarize the loop: ready PR, request Copilot review, wait, inspect
   comments and CI, address or rebut feedback, commit, push, repeat.
4. Include the sixth-loop stop condition.
5. Include the final documentation or pre-commit recommendations.

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

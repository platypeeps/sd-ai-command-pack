<!-- SD-AI-COMMAND-PACK:COPILOT-GUIDANCE:START -->
## Trellis And SD AI Command Pack Review Guidance

- Ignore copied-in Trellis runtime/platform files unless the PR explicitly
  changes Trellis integration or the copied file is the primary subject. This
  includes `.trellis/scripts/**`, `.trellis/agents/**`, `.agents/skills/trellis-*`,
  `.github/agents/trellis-*`, `.github/copilot/**`, `.github/hooks/trellis.json`,
  `.github/prompts/continue.prompt.md`, `.github/prompts/finish-work.prompt.md`,
  `.github/skills/trellis-*`, and the matching Trellis files under `.claude/`,
  `.codex/`, `.cursor/`, `.gemini/`, and `.opencode/`.
- Ignore files copied in from `sd-ai-command-pack` unless the PR explicitly
  changes the SD AI command pack integration. This includes `.agents/skills/sd-*`,
  `.agents/skills/sd-full-check/`, `.agents/skills/sd-housekeeping/`,
  `.github/prompts/sd-*`, `.claude/commands/sd/**`,
  `.cursor/commands/sd-*`, `.gemini/commands/sd/**`,
  `.opencode/commands/sd-*`, `.prism/rules.json`,
  `.sd-ai-command-pack/installed-targets.txt`, `docs/SD_AI_COMMAND_PACK.md`,
  `scripts/sd-ai-command-pack-full-check.sh`,
  `scripts/sd-ai-command-pack-housekeeping.sh`,
  `scripts/sd-ai-command-pack-review-scope.sh`,
  `scripts/sd-ai-command-pack-pr-body-scope.py`, and
  `scripts/sd-ai-command-pack-update-spec-kb.py`.
- For mixed PRs, spend review budget on app behavior, data contracts, specs,
  tests, operator docs, and repo-owned scripts. Only comment on copied
  Trellis/SD AI command pack files for obvious syntax breakage, secret leakage,
  or a direct mismatch with the PR's stated tooling goal.
- Keep strict review on application behavior, data/access/security boundaries,
  migrations and rollback behavior, token or invitation fail-closed behavior,
  tests, and operator-facing documentation.
- Before reviewing generated, copied, Trellis workspace, repository-map, or SD
  AI command pack files, inspect the PR body for a `Tooling/generated scope:`
  section. If that section is missing, request it once instead of scattering
  scope comments across affected files.
- For broad automation or CI/review diffs, expect `Automation scope:` or
  `CI/review scope:` when the pack PR-body scope check reports those categories.
  Repos may add their own runtime or docs categories through
  `.sd-ai-command-pack/pr-body-scope.json`.
- Group duplicate root causes into one comment, especially when generated,
  copied, or adapter files repeat the same issue.
- When deterministic local checks already cover a repeated issue class, prefer
  one concise pointer to the failing check over repeated inline comments.
<!-- SD-AI-COMMAND-PACK:COPILOT-GUIDANCE:END -->

<!-- SD-AI-COMMAND-PACK:COPILOT-GUIDANCE:START -->
## Trellis And SD AI Command Pack Review Guidance

- Trellis is the repository workflow foundation. The SD AI Command Pack adds
  Software Delivery command wrappers, local review tooling, post-merge
  housekeeping, and update-spec knowledge refreshes on top of Trellis. Useful
  repo-local entry points include `.trellis/workflow.md`,
  `.agents/skills/sd-*/SKILL.md`, and `docs/SD_AI_COMMAND_PACK.md`.
- Ignore copied-in Trellis runtime/platform files unless the PR explicitly
  changes Trellis integration or the copied file is the primary subject. This
  includes `.trellis/scripts/**/*`, `.trellis/agents/**/*`, `.agents/skills/trellis-*/**/*`,
  `.github/agents/trellis-*`, `.github/agents/trellis-*/**/*`, `.github/copilot/**/*`, `.github/hooks/trellis.json`,
  `.github/prompts/continue.prompt.md`, `.github/prompts/finish-work.prompt.md`,
  `.github/skills/trellis-*/**/*`, `.claude/commands/trellis/**/*`,
  `.codex/skills/trellis-*/**/*`, `.cursor/commands/trellis-*.md`,
  `.cursor/skills/trellis-*/**/*`, `.gemini/commands/trellis/**/*`,
  `.gemini/skills/trellis-*/**/*`, `.opencode/commands/trellis/**/*`, and
  `.opencode/skills/trellis-*/**/*`.
- Ignore files copied in from `sd-ai-command-pack` unless the PR explicitly
  changes the SD AI command pack integration. This includes `.agents/skills/sd-*/**/*`,
  `.github/prompts/sd-*`, `.claude/commands/sd/**/*`,
  `.cursor/commands/sd-*.md`, `.gemini/commands/sd/**/*`,
  `.opencode/commands/sd-*`, `.gito/config.toml`,
  `.gito/sd-ai-command-pack.env`, `.prism/rules.json`,
  `.prism/rules.schema.json`, `.sd-ai-command-pack/installed-targets.txt`,
  `docs/SD_AI_COMMAND_PACK.md`, and `scripts/sd-ai-command-pack-*`.
- Do not leave line comments on wording, spelling, links, formatting, examples,
  or implementation details inside copied Trellis skills/agents/commands or
  copied SD command-pack skills/prompts/scripts/docs/rules. Only comment when
  the PR changes local integration around those files, exposes secrets, breaks
  repository wiring, or makes the copied-file inventory/documentation
  inconsistent.
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
  one concise pointer to the failing check over repeated inline comments. If
  the check is fragile or missing, ask for one focused fixture in the local
  preflight or guard suite instead of repeating the same finding.
- Separate current, non-outdated unresolved findings from stale or outdated review threads.
  Treat copied or generated payloads as source/sync-contract review surfaces
  instead of style-review surfaces.
<!-- SD-AI-COMMAND-PACK:COPILOT-GUIDANCE:END -->

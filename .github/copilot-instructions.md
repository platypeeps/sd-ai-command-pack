# Repository Copilot Instructions

This repository is the sd-ai-command-pack source. The installed pack copies at
the repository root (for example `.claude/commands/sd/**`,
`.agents/skills/sd-*/**`, `.github/prompts/sd-*`, and
`scripts/sd-ai-command-pack-*`) are byte-verified mirrors of `templates/**`,
enforced by the full-check pack source drift gates and the test suite. Review
the `templates/` side of a change once and treat the mirrored root copy as
generated output; do not repeat the same finding on both copies.

<!-- SD-AI-COMMAND-PACK:COPILOT-GUIDANCE:START -->
## Trellis And SD AI Command Pack Review Guidance

- Trellis is the repository workflow foundation; the SD AI Command Pack adds
  Software Delivery command wrappers, local review tooling, post-merge
  housekeeping, and update-spec knowledge refreshes on top of it. Repo-local
  entry points: `.trellis/workflow.md`, `.agents/skills/sd-*/SKILL.md`, and
  `docs/SD_AI_COMMAND_PACK.md`.
- Treat copied-in Trellis and SD AI command pack payloads as vendored files:
  do not comment on their wording, style, examples, or implementation details
  unless the PR explicitly changes that integration, the copied file is the
  primary subject, it leaks a secret, breaks obvious syntax or repository
  wiring, or directly contradicts the PR's stated tooling goal. Copied
  payloads match these families:
  <!-- narrow-globs: skip - cross-platform generated payload families include optional platform anchors. -->
  - `.trellis/scripts/**` and `.trellis/agents/**`
  - `**/skills/trellis-*/**` and `**/skills/sd-*/**` under `.agents/`,
    `.claude/`, `.codex/`, `.cursor/`, `.gemini/`, `.github/`, `.opencode/`
  - Trellis and `sd` command or prompt files under `.claude/commands/`,
    `.cursor/commands/`, `.gemini/commands/`, `.opencode/commands/`, and
    `.github/prompts/` (including `continue.prompt.md` and
    `finish-work.prompt.md`)
  - `.github/copilot/**`, `.github/hooks/trellis.json`, and
    `.github/agents/trellis-*`
  - `scripts/sd-ai-command-pack-*`, legacy `scripts/trellis-*.sh`, and
    `scripts/update_repomix*`
  - `.gito/**`, `.prism/**`, `.sd-ai-command-pack/**`,
    `docs/SD_AI_COMMAND_PACK.md`, and legacy `docs/TRELLIS_REVIEW_PR_PACK.md`
- Spend review budget on app behavior, data contracts,
  data/access/security boundaries, migrations and rollback behavior, token or
  invitation fail-closed behavior, tests, operator-facing documentation, and
  repo-owned scripts.
- Before reviewing generated, copied, Trellis workspace, repository-map, or
  pack files, look for a `Tooling/generated scope:` section in the PR body.
  Broad automation or CI diffs use `Automation scope:` or `CI/review scope:`;
  repos add categories via `.sd-ai-command-pack/pr-body-scope.json`. If the
  matching section is missing, request it once instead of scattering scope
  comments across files.
- Group duplicate root causes into one comment. When deterministic local checks
  already cover a repeated issue class, point at the failing check once instead
  of repeating inline findings; if the check is missing or fragile, ask for one
  focused fixture in the local guard suite.
- Separate current, non-outdated unresolved findings from
  stale or outdated review threads. Treat copied or generated payloads as
  source and sync-contract review surfaces, not style-review surfaces.
<!-- SD-AI-COMMAND-PACK:COPILOT-GUIDANCE:END -->

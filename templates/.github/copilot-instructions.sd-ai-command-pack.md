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
    `.agent/`, `.claude/`, `.codebuddy/`, `.codex/`, `.cursor/`, `.devin/`,
    `.factory/`, `.gemini/`, `.github/`, `.kiro/`, `.kilocode/`,
    `.opencode/`, `.pi/`, `.qoder/`, `.reasonix/`, and `.trae/`
  - Trellis and `sd` command, prompt, or workflow files under
    `.agent/workflows/`, `.claude/commands/`, `.codebuddy/commands/`,
    `.cursor/commands/`, `.devin/workflows/`, `.factory/commands/`,
    `.gemini/commands/`, `.github/prompts/`, `.kilocode/workflows/`,
    `.opencode/commands/`, `.pi/prompts/`, `.qoder/commands/`,
    `.trae/commands/`, and `.zcode/commands/` (including
    `continue.prompt.md` and `finish-work.prompt.md`)
  - `.github/copilot/**`, `.github/hooks/trellis.json`, and
    `.github/agents/trellis-*`; platform hook/agent payloads under
    `.codebuddy/`, `.factory/`, `.qoder/`, `.trae/`, `.zcode/agents/`, and
    legacy `.zcode/cli/agents/`
  - `scripts/sd-ai-command-pack-*`, legacy `scripts/trellis-*.sh`, and
    `scripts/update_repomix*`
  - `.gito/**`, `.prism/**`, `.sd-ai-command-pack/**`,
    `docs/SD_AI_COMMAND_PACK.md`, and legacy `docs/TRELLIS_REVIEW_PR_PACK.md`
- Original Trellis-owned runtime/template copies are not valid modification
  targets for target-repo or sd-ai-command-pack PRs, and should not be reviewed
  line by line. Treat diffs in upstream Trellis-owned surfaces such as
  `.trellis/scripts/**`, `.trellis/agents/**`, and platform `trellis-*` skills,
  agents, commands, prompts, workflows, hooks, and settings as ownership/scope
  issues. This does not apply to repo-owned `.trellis/spec/**` guidance or
  `.trellis/tasks/**` task documents. If a change appears needed, leave one
  handoff comment instead:
  ```text
  Handoff for sd-ai-command-pack source session:
  A change appears needed in original Trellis-owned runtime/template files,
  which should not be edited in the consumer repo copy.
  Affected file(s): <paths>
  Desired behavior: <short behavior>
  Evidence/repro: <commands, review finding, or failure>
  Please decide whether this belongs in an sd-ai-command-pack wrapper/template,
  a pack-owned guard, or an upstream Trellis change, then implement the durable
  source-owned fix.
  ```
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
- On pack refresh PRs (typically titled
  `refresh sd-ai-command-pack to <version>`), the vendored payload was
  reviewed upstream in the
  sd-ai-command-pack repository before release; review this repo's
  integration (PR metadata, repo-owned files, wiring) rather than
  re-reviewing the vendored file contents line by line.
<!-- SD-AI-COMMAND-PACK:COPILOT-GUIDANCE:END -->

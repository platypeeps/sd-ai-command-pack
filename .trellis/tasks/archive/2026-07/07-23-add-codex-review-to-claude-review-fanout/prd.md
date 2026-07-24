# Add Codex review to Claude Code local review fan-out

## Goal

When `sd-review-local` runs in Claude Code, include the native Codex CLI review
as a peer local-review lane that executes concurrently with the
selected Prism, Gito, or configured local-provider stack and contributes to the
same verified finding-selection and fix loop.

## Requirements

- Add Claude-only orchestration to `sd-review-local`; do not add Codex as a
  generic tool name in `sd-ai-command-pack-review-local.sh` or change behavior
  on non-Claude platforms.
- In the normal current-diff/branch scope, start the selected shell review stack
  and the matching native `codex review` command concurrently, and collect both
  results before presenting findings.
- Use only the supported native targets: `codex review --uncommitted` for a
  dirty working tree and `codex review --base <resolved-ref>` for a clean-tree
  branch diff.
- Treat the Codex lane as additive even when the user explicitly selects Prism,
  Gito, or another configured runner tool. Existing runner tool-selection
  arguments continue to control only the runner stack.
- Verify and deduplicate Codex findings with the other provider findings before
  asking which findings to fix. Preserve provider attribution.
- Rerun Codex when verifying a selected Codex finding and include it in the
  final original-stack regression review when it was available initially.
- If the Codex CLI or required native review flags are unavailable, continue
  with the selected runner providers and report a visible, non-blocking Codex
  skip with actionable installation/authentication guidance.
- If Codex starts but fails, still collect the runner output, report the failed
  lane, and do not claim that the combined review is clean.
- Do not silently run Codex against a narrower target in `all` full-codebase
  mode. Continue the full-codebase Prism/Gito/configured-provider review and
  report that native Codex review lacks an equivalent repository-wide target.
- Keep the interaction surface clean: no new public `sd-review-local` argument,
  environment variable, or legacy alias is required for the automatic Claude
  lane.
- Do not require, inspect, patch, or install the OpenAI Codex Claude plugin. The
  feature must continue to work when that plugin is uninstalled.
- Document the Claude-specific fan-out, fallback, scope limitation, and Codex
  CLI prerequisite in the shipped guide and frontend adapter contract.

## Acceptance Criteria

- [ ] A generated Claude `sd-review-local` adapter backgrounds the selected
      provider lane, runs the matching native `codex review` lane concurrently,
      and joins both outputs before finding selection.
- [ ] Non-Claude generated adapters and the runner's generic `--list-tools`
      surface remain unchanged.
- [ ] Missing, unauthenticated, or incompatible Codex CLI state visibly falls
      back to the selected runner stack without failing that stack.
- [ ] Codex execution failure cannot be mistaken for a clean combined review.
- [ ] Full-codebase mode reports Codex as unsupported rather than mixing scopes.
- [ ] The workflow has no dependency on the Codex Claude plugin or its managed
      marketplace/cache paths.
- [ ] Focused tests cover pack generation, platform isolation, CLI capability
      fallback, scope mapping, and joined-result contracts.
- [ ] Generated surfaces are synchronized, the pack payload version/changelog
      and fleet candidate ledger are refreshed, and `make check` passes.

## Notes

- The Codex Claude plugin remains optional and independently managed. Users may
  uninstall it if they do not need its rescue, transfer, job-management, or
  stop-review-gate features.

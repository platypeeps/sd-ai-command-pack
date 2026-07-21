# Self-heal stale generated Obsidian KB during full-check

## Goal

Reduce full-check cycle time by repairing an existing stale generated Obsidian
KB during the default lane, then proving it is current in the same run. Keep
strict verification non-mutating and fail-closed.

## Background

- GitHub issue #204 reports that the default full-check stops when
  `sd-ai-command-pack-update-spec-kb.py --check` detects stale ignored output.
  Operators must run the normal refresh manually and restart the expensive
  gate.
- The full-check currently supports `SD_AI_COMMAND_PACK_FULL_CHECK_KB=auto`,
  `required`, and disabled values. Default `auto` skips repositories without
  `.obsidian-kb`, while `required` fails when the helper, Python, or a passing
  freshness check is unavailable.
- The canonical KB helper already owns refresh, check, conflict, stale-entry,
  dashboard, overview, and ignore-state behavior. Full-check must orchestrate
  that helper rather than duplicate KB generation logic.
- The shipped template is authoritative; the root script and installed docs or
  skill copies are synchronized mirrors.

## Requirements

- Preserve the current absent-KB opt-in boundary: default mode must not create
  `.obsidian-kb` in a repository where it does not exist.
- In default/non-required mode with an existing KB:
  1. run the current read-only freshness check;
  2. when it fails and `.obsidian-kb` is already ignored, invoke the canonical
     normal refresh once;
  3. rerun `--check` and continue only when the refreshed state passes;
  4. when `.obsidian-kb` is not ignored, fail without refreshing so full-check
     cannot repair generated state by changing tracked ignore configuration.
- In `required` mode, retain the current read-only, fail-closed contract. A
  stale or blocked KB must fail without an automatic refresh.
- Preserve disabled-mode behavior and existing availability handling for a
  missing helper or `python3`.
- Preserve helper diagnostics and print an actionable recovery command when a
  refresh or post-refresh check fails.
- Update the authoritative full-check template first and keep the root mirror,
  README, installed guide, and `sd-full-check` skill documentation consistent.
- Add focused regression coverage for fresh, absent, disabled, default stale
  repair, repair failure, post-repair verification, and strict stale behavior.
- Publish the shipped behavior through the normal manifest, provenance,
  changelog, generated-surface, and fleet candidate-validation process.

## Acceptance Criteria

- [x] A default full-check with an existing stale generated KB refreshes it,
      rechecks it, and completes without requiring a second full-check run.
- [x] A default full-check with an existing fresh KB remains read-only and
      invokes no refresh.
- [x] Default mode refuses to auto-refresh an unignored `.obsidian-kb` and
      leaves tracked ignore configuration unchanged.
- [x] A repository without `.obsidian-kb` still skips visibly and does not
      create the directory or an ignore entry.
- [x] `SD_AI_COMMAND_PACK_FULL_CHECK_KB=required` fails on stale KB state and
      does not refresh it.
- [x] Disabled mode continues to skip without running the helper.
- [x] Refresh or post-refresh verification failure stops full-check with the
      helper diagnostics and exact supported recovery command.
- [x] Template/root mirrors and installed documentation remain synchronized.
- [x] Focused tests and the canonical repository checks pass on the final
      shipped payload.

## Out of Scope

- Changing which files or categories the KB generator includes.
- Replacing the canonical KB helper or changing its standalone CLI contract.
- Creating `.obsidian-kb` for repositories that have not opted in.
- Changing lifecycle-owned post-finish refreshes in housekeeping or the
  autonomous work loop.

## Notes

- Origin: [platypeeps/sd-ai-command-pack#204](https://github.com/platypeeps/sd-ai-command-pack/issues/204).
- Planning decision: automatic repair is limited to already-ignored KB output;
  unignored or policy-invalid state remains fail-closed.
- This is a focused extension of the archived
  `07-06-full-check-kb-freshness-gate` contract. The executable behavior is
  captured in the `Full-Check KB Auto-Repair` adapter-guideline scenario.
- Validation: focused KB tests passed (4 tests); generated/template parity and
  `git diff --check` passed; `make check` passed with all coverage floors,
  Ruff, mypy, zizmor, install audit, KB freshness, and release gates green.
- Fleet candidate validation passed for all seven configured consumers against
  pack `0.25.4` and payload digest
  `sha256:c5c25497afdb073aad4326bd7a98e66ed76c1fc61d4bce3e87f2e43b922d686f`.

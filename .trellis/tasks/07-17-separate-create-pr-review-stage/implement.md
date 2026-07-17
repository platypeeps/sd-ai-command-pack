# Separate sd-create-pr Publish And Review Stages Implementation Plan

## Execution Order

1. Add the internal orchestration-context contract and early public-argument
   rejection to the shared `sd-create-pr` skill.
2. Make `sd-create-pr` Step 6 conditional: return a Stage 1 publish result for
   verified `sd-ship` delegation; otherwise retain the standalone review
   handoff.
3. Update `sd-ship` Stage 1 to supply the internal context explicitly and
   tighten Stage 2 review ownership for each `until=` mode.
4. Synchronize installed mirrors and update adapter guidance, usage docs,
   changelog, and manifest version.
5. Add focused lifecycle tests for `until=pr`, `until=review`, `until=merge`,
   standalone create-pr, and rejected public internal-mode arguments.

## Validation Plan

- Run the focused SDLC command tests.
- Run generated parity and installer contract tests touched by the payload.
- Run the canonical repository check with optional local AI providers disabled
  where the check contract permits it.
- Run fleet candidate validation required by the release metadata gate.

## Rollout And Compatibility

The behavior is additive for the composite and preserves standalone command
semantics. Consumers receive the shared skill and documentation changes on the
next pack refresh. Rollback is a normal pack downgrade; no consumer state or
receipt schema changes are involved.

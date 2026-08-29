# Fix Documentation And Help-Text Accuracy Batch Implementation Plan

## Execution Order

1. Fix `install.py` help text and add preserved-target/help assertions.
2. Update the manifest/filesystem spec symbol references.
3. Add the AGENTS contributor pointer block and SECURITY.md.
4. Update README and installed guide enumerations, keeping guide twins synced.
5. Decide and apply the FIRST_REPLY_NOTICE policy consistently across hooks.
6. Run docs and drift validation.

## Validation Plan

Run focused install/help tests, `python3 -m unittest tests.test_pack_drift
tests.test_generated_parity tests.test_review_preflight` as applicable, and
`git diff --check`.

## Documentation And Spec Updates

This task is primarily documentation/spec work. Keep edits scoped to confirmed
accuracy issues from the PRD.

## Review Notes

Reviewers should check that the help-text test derives preserved targets from
the registry rather than duplicating the same stale list.

## Follow-Ups

If FIRST_REPLY_NOTICE needs product judgment beyond "remove/gate hardcoded
locale text", park that single decision instead of blocking all doc fixes.

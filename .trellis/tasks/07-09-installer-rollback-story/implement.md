# Document Installer Rollback And Evaluate Two-Phase Apply Implementation Plan

## Execution Order

1. Update the installed guide twins with the rollback procedure and partial
   apply explanation.
2. Inspect current install flow and record the two-phase decision in this task.
3. If adopting two-phase apply, introduce a plan phase that computes
   would-write/would-conflict results before mutation.
4. Add a regression test proving a conflicted run writes zero files.
5. Run existing install, dry-run, force, backup, and remove tests.

## Validation Plan

Run focused installer tests plus the 100% installer coverage gate. Run the
review-preflight doc-path checker through full-check or its focused test.

## Documentation And Spec Updates

The guide update is mandatory. If two-phase apply is deferred, record the
rationale in this task artifact so future sessions do not rediscover it.

## Review Notes

Reviewers should check that default install output remains understandable and
that dry-run is still non-mutating.

## Follow-Ups

If two-phase apply grows beyond a small installer refactor, split it into a
dedicated task and land the rollback documentation first.

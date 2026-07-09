# Review Nits Cleanup Batch Implementation Plan

## Execution Order

1. Fix N1 and add/adjust housekeeping tests for auth failure messaging.
2. Fix N2 in shell-lib and sync template/root copies.
3. Guard the remaining symlink call or document the suite prerequisite.
4. Update `make test` to fail on skipped tests like CI.
5. Decide N5/N6; split only if implementation becomes broad.
6. Record N7 consumer coordination in the fleet task or separate consumer
   issues.

## Validation Plan

Run `python3 -m unittest tests.test_housekeeping tests.test_pack_drift`, then
`make test` after the skip-backstop change. Run shellcheck on changed shell
scripts.

## Documentation And Spec Updates

Document any intentional decisions for N5/N6 directly in this task or a small
maintainer note so future reviews do not reopen them.

## Review Notes

Reviewers should confirm the batch did not absorb new scope. If a nit starts
needing design, split it out.

## Follow-Ups

Consumer legacy references from N7 should be handled during the next fleet
touch, not as pack-owned payload.

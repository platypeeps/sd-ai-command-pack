# Guard Full-Check Against Disjoint-History Diffs Implementation Plan

## Execution Order

1. Update the template full-check script first, wrapping the base diff in
   explicit `set +e` status capture.
2. Add a helper or inline branch that recognizes merge-base/disjoint-history
   failures and appends `git ls-files` output as fallback.
3. Copy the template to the root script twin.
4. Add a disjoint-history fixture test in `tests/test_full_check.py`.
5. Add or preserve a non-base git-error test to prove errors are not swallowed.

## Validation Plan

Run `python3 -m unittest tests.test_full_check`, `bash -n` on both full-check
scripts, and the shipped-scripts coverage gate.

## Documentation And Spec Updates

No guide update is required unless the warning becomes part of documented
operator behavior.

## Review Notes

Reviewers should check bash 3.2 compatibility and ensure temp files still get
removed on all branches.

## Follow-Ups

If fallback-to-all-tracked proves too expensive, add a later tuning task with
evidence from real repos.

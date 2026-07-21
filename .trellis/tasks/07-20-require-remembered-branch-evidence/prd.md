# Require remembered branch for historical shipped evidence

## Goal

Close the first-time branch-evidence ancestry bypass found while refreshing AMC to sd-ai-command-pack 0.24.5.

## Requirements

- Tighten `validated_evidence()` so the post-squash historical shipped-SHA
  exception applies only when the ledger already contains a non-empty branch
  equal to the submitted branch and `baseBranch`.
- Preserve the valid recovery case where a previously verified base-branch
  ledger advances its head while retaining the immutable feature SHA.
- Add a regression proving newly supplied branch/head evidence cannot bypass
  the shipped-SHA ancestry check merely because the candidate branch equals
  the base branch.
- Keep the canonical template and installed script mirror byte-identical,
  update the executable reconciliation contract, and publish a new patch
  release with full fleet candidate evidence.

## Acceptance Criteria

- [x] First-time branch evidence with an unrelated remembered shipped SHA is
      rejected with `lastShippedSha evidence must belong to the shipped branch`.
- [x] Existing base-branch recovery after a squash merge still accepts a
      descendant head while retaining the historical feature SHA.
- [x] Focused work-loop tests, template parity, `make check`, and all seven
      configured consumer validations pass.
- [x] The corrective release candidate can refresh AMC PR #269 without the
      reported first-time branch-evidence ancestry bypass.

## Notes

- Triggered by Copilot review thread `PRRT_kwDOSJ6KbM6SaRbG` on AMC PR #269.
- This is a lightweight predicate-and-regression correction; `prd.md` is the
  complete planning artifact.

# Implementation Plan: Post-Archive Review Finalization

## 1. Specify The Receipt

- Extend backend quality and frontend adapter contracts with the completion
  successor subtype, evidence fields, limits, and stable error matrix.
- Define the repository-local ignored receipt store and strict parser.
- Keep `completion|planning` as the only public finalization modes.

## 2. Extend Canonical Validation

- Add bounded discovery/revalidation of a prior completion anchor.
- Validate the first-parent successor range and reject every bookkeeping change.
- Emit the exact-head completion successor receipt without mutations.
- Keep template and dogfood script copies synchronized.

## 3. Integrate Workflow Ownership

- Make `sd-finish-work` reuse/emit the receipt instead of recording a duplicate
  journal when the task is already archived.
- Make `sd-review-pr` retain the exact receipt after review convergence.
- Replace head-only eligibility/housekeeping input with independently verified
  receipt evidence and expose the subtype through status.
- Remove retired head-attestation readers/options after all internal callers
  migrate; do not keep aliases.

## 4. Add Failure And Idempotence Coverage

- Build the PR #253-shaped positive fixture.
- Cover missing/ambiguous anchors, invalid prior completion, bookkeeping drift,
  stale/forged receipts, head/repository mismatch, merges, missing objects, and
  bounds.
- Prove repeated finish-work and housekeeping retries create no extra journal,
  archive, commit, push, review request, or CI-triggering change.
- Preserve all existing completion/planning/recovery fixtures.

## 5. Validate And Roll Out

- Run focused validator, recorder, SDLC-command, eligibility, housekeeping,
  result, and status tests.
- Run template/root identity checks, Node/Python syntax and type checks,
  `sd-check`, and `make check`.
- Refresh provenance, KB, release metadata, and fleet candidate evidence when
  shipped payload changes require them.
- Re-run finish-work and housekeeping on PR #253 only after its exact final head
  passes the new receipt and review/CI gates.

## Rollback

- Disable completion-successor selection and remove its receipt from ignored
  runtime state.
- Leave ordinary completion/planning behavior intact; affected PRs return the
  prior `finish_work_missing` block rather than merging with weaker evidence.

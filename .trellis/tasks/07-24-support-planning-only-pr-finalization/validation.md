# Integration validation: planning-only PR finalization

Status: validated on the stabilization branch (2026-07-28). Owner task:
`07-24-support-planning-only-pr-finalization`; work-package 3 of the
single-merge stabilization umbrella.

## Implementation provenance

The deterministic finalization machinery required by R1–R12 already landed in
`origin/main` before this campaign and is not re-implemented here. It ships as:

- The versioned `final-bundle --mode <completion|planning>` evaluator in
  `scripts/sd-ai-command-pack-review-preflight.mjs` (template-first, root
  mirror), reusing the shared bookkeeping validator for task/topology/journal
  rules and computing mode from repository evidence, never caller prose.
- The `sd-finish-work` skill's Step 7 mode-specific final gate, its
  `journal-only-recovery` planning subtype and `post-archive-review-successor`
  completion subtype, and idempotent single-successor behavior.
- Typed finalization evidence consumed by `sd-ai-command-pack-pr-eligibility.py`
  (independent recompute against Git/GitHub) and by housekeeping/status, with
  the bare `finishWorkHead` attestation retired (see the sibling decision in
  `07-28-decide-housekeeping-result-schema-compatibility`).

Representative already-merged commits: `02128a9` (support post-archive review
finalization), `ab82fde` (validate finish-work receipt subtypes), `49aabeb`
(separate receipt schema version), `1603947` (checkout-portable receipts),
`7afc5f9` (re-read PR head at eligibility completion). All are ancestors of
`origin/main`.

## Campaign-scoped validation

The stabilization branch integrates this feature with package 1 (lifecycle
boundary contract) and package 2 (schema-compatibility decision). Re-ran the
focused finalization lifecycle battery on the branch head:

- `test_bookkeeping_validator`, `test_review_preflight` (final-bundle evaluator,
  both modes and subtypes),
- `test_pr_eligibility` (typed evidence recompute, exact-head re-read),
- `test_housekeeping`, `test_housekeeping_result` (merge gate + typed result),
- `test_review_stage` (shipping composition).

Result: 212 tests, all pass. Generated parity and command-surface coverage are
exercised separately in packages 1–2 and again in cumulative integration.

## Acceptance criteria disposition

- Planning/completion selection, topology validation, fail-closed boundaries,
  retry idempotence, eligibility rejection, and no-new-public-command criteria
  are covered by the passing focused tests above.
- End-to-end dogfood (PR #244 or a fresh planning-only PR): satisfied by this
  umbrella's own single-merge finish/housekeeping path; its exact-head receipt,
  CI/review, merge, task preservation, and cleanup identities are recorded at
  the campaign finalization stage, not per package.
- Program integration H09 with `07-22-validate-sd-workflow-program-integration`:
  fed stability evidence but explicitly not a release blocker for this
  bootstrap, per the umbrella directive.

No code change is required for this package; its deliverable is the integration
proof recorded here.

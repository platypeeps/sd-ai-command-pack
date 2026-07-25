# Design: review-family convergence gate

## Design Summary

Add a family-level convergence layer inside the unified review controller. It
does not replace individual findings or provider receipts. It derives a stable
family for each actionable finding, records family recurrence across exact
heads in one PR lifecycle, and changes the next transition from `redispatch` to
`sibling-audit-required` when the same family appears twice.

## Data And State

The parent review state stores a bounded entry for each finding:

```json
{
  "findingId": "provider-stable-id",
  "provider": "copilot",
  "round": 2,
  "headOid": "<40-char oid>",
  "family": "boundary-validation",
  "disposition": "fix",
  "fixCommit": null,
  "siblingAuditId": null
}
```

Family vocabulary and path-family hints come from the typed review-learning
report. Unknown findings use `other`; classification failure is visible and
does not dismiss the finding. Raw provider text remains on its existing local
or GitHub surface and is not copied into controller state.

## Transition Flow

1. Ingest all current provider findings and GitHub threads for the exact head.
2. Normalize family and retain individual disposition authority.
3. Count actionable family observations across rounds in the current PR
   lifecycle, not across unrelated PRs.
4. On the second observation, enter `sibling-audit-required` before another
   remote request.
5. Build a checklist from the family's known dimensions plus changed paths and
   task design invariants; run the configured local adversarial reviewer.
6. Combine current remote findings and newly discovered siblings into one
   disposition/fix batch, then run `sd-check` and publish one focused commit.
7. Record the audit receipt and permit normal routing for the new exact head.
8. If the same family returns again, stop at `round-extension-required` and use
   the parent's structured decision contract.

Head changes invalidate readiness but do not erase the PR-lifecycle recurrence
record. A superseding finding may reference its prior identity, family, and fix
commit; it never inherits an older head's review confidence.

## Audit Matrix

The matrix is configuration-backed and bounded. Boundary/stateful changes cover
strict types, normalization, persistence invariants, transitions, replay,
idempotency, attempts, exact identity/head binding, subprocess failures,
permissions, paths, symlinks, TOCTOU, and controlled errors. Generated-surface,
contract, task-metadata, and test-harness families receive their own concrete
dimensions.

The matrix asks for evidence or a reasoned not-applicable disposition. Token or
test-name matching cannot mark a dimension covered automatically.

## Safety And Rollback

- The gate can stop redispatch but cannot approve fixes, resolve threads, or
  merge.
- Provider unavailability and classifier ambiguity retain zero confidence.
- Rollback disables family-level transitions and returns to the parent's lower
  round budget; it does not delete finding or review receipts.

## Delivered Internal Boundary

This child lands the executable family gate in the already shipped internal
exact-scope local-review stage. The future public `sd-review` controller owns
persisting its bounded `--family-evidence` payload and supplying current remote
finding, audit, check, batch, and structured-extension records. The child does
not introduce a second public command, dispatch a remote provider, or duplicate
the parent controller.

The stage validates and projects that payload into its plan and receipt. A
second same-family round automatically selects the repeated-family local plan
and blocks remote eligibility until the parent records a complete audit bundle.
A post-audit recurrence returns a controlled block before local provider
execution until the existing `review.round-extension` decision is present.
This contract lets the parent compose the behavior without keeping safety
transitions only in prompt prose.

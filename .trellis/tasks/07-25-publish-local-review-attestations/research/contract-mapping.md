# Local Review Attestation Publisher Contract Mapping

## Accepted Boundary

- The unified `sd-review` coordinator is the only local review producer. No new
  public command or retired review surface is added.
- Publication is selected only for an explicit compatible v2 local-attested
  route after exact-head local review reaches a terminal normalized result.
- The command pack publishes the router-owned bounded envelope through the
  trusted repository workflow. It does not choose trust policy, map branch-
  protection outcomes, or write stable Checks directly.
- Publication is idempotent and exact-head-bound. Wrong-head, rejected,
  conflicting, or ambiguous publication fails closed without remote fallback.
- The final report says local review was performed and its result was
  `repository_attested`; it never claims independent GitHub verification.

## Cross-Repository Dependency

The publisher consumes contracts delivered by:

- `platypeeps/sd-github-review:07-25-define-local-review-attestation-contracts`
- `platypeeps/sd-github-review:07-25-ingest-local-review-attestations`
- `platypeeps/sd-github-review:07-25-project-local-review-assurance`

## Authoritative Workspace Anchors

- `.trellis/tasks/07-25-publish-local-review-attestations/prd.md`
- `.trellis/tasks/07-25-publish-local-review-attestations/design.md`
- `.trellis/tasks/07-22-integrate-routed-review-backends/design.md`

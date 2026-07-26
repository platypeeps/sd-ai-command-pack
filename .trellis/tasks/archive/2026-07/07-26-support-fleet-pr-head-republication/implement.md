# Implementation plan

1. Add a named `pr-head-advanced` reason constant and validate its result/stage boundary before state mutation.
2. Extend the retryable transition so the first eligible old-head receipt routes to the next `pr-publication` attempt; preserve generic retry behavior and exhaustion.
3. Add focused unit tests for review and merge-eligibility republication, successor epoch progression, invalid uses, immutable failure state, and retry exhaustion.
4. Update the fleet controller spec and source rollout documentation with the exact operator sequence and corrective-recovery distinction.
5. Run focused controller tests and coverage, formatting/lint checks, `make check`, and the source full check.
6. Review the final diff for schema compatibility, exact-head enforcement, and source-only scope before commit and PR publication.

## Rollback points

- Stop before recording any live campaign receipt if focused tests or state-validation replay fails.
- Do not use the new path in the live campaign until the source change is reviewed and merged.

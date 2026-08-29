# Design: final PR-head eligibility proof

## Design Summary

Extend the existing eligibility completion boundary so both evaluation modes
observe the exact pull request twice: once with the readiness payload and once
by retained PR number immediately before returning. Local-branch mode keeps its
independent final local-head read. Either identity becoming unreadable or
changing invalidates all earlier evidence and produces a retryable
`indeterminate` result.

This remains a read-only correction inside the canonical evaluator. It does
not move merge authority out of housekeeping or replace the mutation-boundary
`--match-head-commit` check.

## Evidence Contract

The first `gh pr view` continues to populate `pullRequest.headOid`. Add
`pullRequest.finalHeadOid`, initially `null`, and populate it from one bounded
`gh pr view <number> --json headRefOid` call in the common completion path.
Use the retained integer PR number, never the branch name, for the final read.

The field is additive within output schema major 1:

- `pullRequest.headOid` is the strict full OID observed with checks and PR
  readiness;
- `pullRequest.finalHeadOid` is the strict full OID observed at completion, or
  `null` when the observation cannot be trusted;
- local mode keeps `head.startOid` and `head.endOid` as its initial and final
  local branch observations; and
- dependency mode keeps its current `head` semantics while also emitting the
  normalized final PR field.

The shell receipt remains unchanged. Housekeeping embeds the JSON document and
continues to consume its established identity fields, so no caller migration
or schema-major bump is required.

## Completion Sequence

For local-branch evaluation:

1. collect local, remote, initial PR, checks, finish-work, merge-state, and
   paginated review-thread evidence through the existing gates;
2. retain `pr.number` and `pr.headOid` after the initial PR query;
3. on every return path after that query, read the exact PR head again and
   store `pullRequest.finalHeadOid`;
4. re-read the local branch head and store `head.endOid`; and
5. apply the final identity precedence before rendering one result.

Return paths before a PR is successfully identified still perform the existing
local final-head read but cannot fabricate a final PR observation.

Dependency mode continues its existing double-read sequence and populates the
new normalized field from the same final query rather than issuing a third
provider call.

## Failure And Precedence

Final observations are collected even when an earlier gate already produced a
blocked or indeterminate candidate. Identity failures override that candidate:

1. an unavailable initial or final local head returns retryable
   `head_unavailable` with a local diagnostic;
2. a changed local head returns retryable `head_changed` with a local
   diagnostic;
3. an unavailable final PR head returns retryable `head_unavailable` with the
   exact PR number in the diagnostic;
4. a changed PR head returns retryable `head_changed` with both OIDs in the
   diagnostic; and
5. only stable identity evidence preserves the candidate result.

This ordering retains existing local failure behavior when more than one
identity changes while ensuring a stable local branch can never conceal a
moved or unreadable PR. Command failure, timeout, malformed/non-object JSON,
missing field, non-string value, and non-full-lowercase OID all normalize to an
unavailable final PR observation without traceback.

## Ownership, Compatibility, And Rollback

- Change the template evaluator first and regenerate the root mirror with the
  normal synchronization workflow.
- Update the quality contract and fixtures with the additive evidence field;
  do not add a second evaluator or a caller-side reimplementation.
- Keep the evaluator bounded and mutation-free; final reads use existing
  command timeouts and no retry loop.
- `07-24-support-planning-only-pr-finalization` may later replace finalization
  attestation fields, but it consumes this final-head proof rather than
  redefining it.
- Rollback removes the additive field and local final PR read together; it does
  not weaken housekeeping's mutation-boundary head check.

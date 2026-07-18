# Separate fleet preparation from candidate validation

## Goal

Make fleet candidate validation consistently prepare generated structural maps
before running read-only repository checks, without disguising a mutating
refresh command as a validation check.

## Background

The fleet validator installs a candidate into disposable consumer clones and
then runs each repository's declared `candidateChecks`. Six current fleet
members own both a repository-local Repomix refresh command and a tracked
structural-map artifact, but only
`hoa-manager` currently runs the generator before its preflight. Its refresh
command is embedded in `candidateChecks`; the other five map-owning consumers
do not regenerate their maps during candidate validation. `se-ai-command-pack`
owns neither the generator nor the artifact.

## Requirements

- Add a distinct, declarative `candidatePrepare` phase to the fleet manifest
  and shared fleet-consumer model.
- Require every fleet consumer to declare `candidatePrepare` explicitly as an
  argv-array list. Empty preparation is valid; malformed commands are rejected
  before any clone or install work begins.
- Configure every fleet member that owns a Repomix refresh command and tracked
  structural-map artifact to run that command during preparation.
  Configure `se-ai-command-pack` with an empty preparation list rather than
  inventing a structural-map implementation in this task.
- Run preparation only in disposable candidate clones, after candidate install
  and install audit and before `candidateChecks`.
- Execute preparation directly without shell interpolation, with the same
  bounded timeout, environment isolation, and continue-after-consumer-failure
  behavior used by candidate checks.
- Keep repository preflight and review checks read-only. Do not add generated
  artifact mutation to a consumer's validator.
- Record the exact preparation commands in candidate evidence and verify them
  when checking the ledger.
- Expose preparation commands in fleet preflight JSON so operator tooling sees
  the complete declared candidate contract.
- Update the fleet schema and candidate-ledger schema when their required
  shapes change. Update tests, backend contract documentation, and rollout
  documentation in the same change.
- Do not modify active fleet worktrees. Candidate preparation remains confined
  to temporary clones.

## Out Of Scope

- Adding a structural map to a repository that does not currently own one.
- Automatically mutating a developer's worktree from a preflight command.
- Changing individual consumers' Repomix refresh implementations.
- Rolling a new pack version into consumers; this is source-owned fleet tooling
  and does not change the installed payload.

## Acceptance Criteria

- [x] The fleet manifest requires explicit `candidatePrepare` arrays for all
  seven consumers.
- [x] The six map-owning consumers run their repository-local Repomix refresh;
  `se-ai-command-pack` prepares with `[]`.
- [x] Candidate validation runs install, audit, preparation, and checks in that
  order inside a disposable clone.
- [x] A preparation failure identifies the consumer and preparation index,
  skips that consumer's checks, continues the fleet run, and cannot replace
  canonical all-pass evidence.
- [x] Empty preparation succeeds and malformed preparation declarations fail
  schema validation.
- [x] Candidate evidence records and validates both preparation and check
  command arrays.
- [x] Fleet preflight JSON reports `candidatePrepare` and `candidateChecks`.
- [x] Focused fleet parser, candidate, preflight, ledger, parity, and coverage
  tests pass.
- [x] The canonical repository check and deterministic full-check pass.

## Notes

- `templates/**` remains the source of truth for shipped payload. This feature
  changes source-owned fleet tooling and documentation, so no template twin is
  expected unless implementation discovery proves otherwise.

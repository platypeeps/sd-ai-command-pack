# Recover Paused Work-Loop Checkpoints Design

## Overview

Checkpoint state is operational metadata layered over a lifecycle phase. The
current schema instead replaces the phase with `checkpoint`, then compares that
synthetic phase numerically with observed lifecycle phases. Preserve the owning
phase explicitly and use it for verified recovery.

## State Contract

Add an optional `resumePhase` field to checkpoint state while retaining schema
version 1:

```json
{
  "state": "paused",
  "target": "PR #15 remote review after quota reset",
  "reason": "Remote review did not materialize",
  "resumePhase": "shipping"
}
```

New checkpoint and pause operations capture the prior lifecycle phase before
entering synthetic `checkpoint`. Cleared and terminal checkpoints use
`resumePhase: null`. Validation accepts only lifecycle phases that can own a
checkpoint.

For older ledgers, recovery resolves the effective phase in this order:

1. checkpoint `resumePhase`;
2. a `target` value that is itself a valid lifecycle phase; or
3. an explicit CLI resume-phase argument supplied during verified recovery.

Human targets are never interpreted heuristically.

## Reconciliation Flow

When the ledger phase is `checkpoint` and verified recovery is requested:

1. Resolve the effective ledger phase.
2. Confirm that the observed phase is the same phase or a permitted forward
   recovery. Do not use the ordinal position of synthetic control phases.
3. Require every non-null recorded current-state field plus all proposed
   advancing evidence.
4. Validate the candidate through the existing evidence validator using the
   observed lifecycle phase. This preserves merge-boundary, PR, stable-identity,
   branch, commit, and ancestry checks.
5. Commit current evidence, observed phase, checkpoint clearing, and context
   health in one atomic ledger write.

A verified phase advance records the existing continuation-summary signal and
remains amber until an exact reconciliation confirms the new state. Any
validation failure records one bounded red contradiction without partially
applying the candidate.

## Compatibility And Boundaries

- Keep schema version 1 and make `resumePhase` additive so deployed ledgers
  remain readable.
- Preserve the existing direct evidence rule for active lifecycle phases.
- Do not add `checkpoint` broadly to `ACTIVE_EVIDENCE_PHASES` or
  `MERGE_EVIDENCE_PHASES`; doing so would lose the owning lifecycle context.
- Keep stopped/completed runs terminal. The recovery contract applies to active
  or resumed paused runs with a held lock.
- Continue to avoid network access in the helper; the controller supplies
  already-verified GitHub facts and the helper validates local invariants.

## Affected Surfaces

- `templates/scripts/sd-ai-command-pack-work-loop.py` and root mirror.
- `templates/.agents/skills/sd-work-backlog/SKILL.md` and root mirror.
- `tests/test_work_loop.py`.
- `scripts/sd-ai-command-pack-status.py` and status tests if checkpoint
  normalization exposes `resumePhase`.
- Command documentation, changelog/version metadata, manifest, and provenance.

## Rollback

Revert the helper, skill, documentation, and release metadata together. The
optional field is backward compatible, so existing ledgers containing it remain
readable if validation tolerates unknown checkpoint keys; otherwise retain a
small compatibility reader until the field has aged out.

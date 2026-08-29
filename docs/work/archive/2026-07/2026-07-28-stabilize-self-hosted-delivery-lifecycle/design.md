# Single-merge self-hosting stabilization design

## Delivery topology

One umbrella task owns one feature branch and PR. The eleven existing tasks
remain the authoritative work-package specifications and retain their existing
program parents. They share the umbrella branch, implementation window, final
review head, and completion bundle; they do not receive independent branches,
PRs, merges, releases, or fleet campaigns.

The investigation task remains the planning and evidence parent. The rollout
task remains planning until the successor release exists. Neither is archived
with the implementation packages.

## Work-package order

### 1. Contract and compatibility decisions

- `07-28-clarify-completion-housekeeping-obligations`
- `07-28-decide-housekeeping-result-schema-compatibility`

Settle the lifecycle representation and result compatibility first so later
validators and result composers implement one contract.

### 2. Core self-hosted lifecycle

- `07-24-support-planning-only-pr-finalization`
- `07-28-validate-finish-work-receipt-path`
- `07-28-route-housekeeping-by-pr-lifecycle-state`

Implement deterministic finalization selection, early receipt diagnostics,
and PR-lifecycle routing. These changes make the branch-local finish and
housekeeping path suitable for its own final delivery.

### 3. Truthful archive enforcement

- `07-28-enforce-pre-archive-acceptance-readiness`

Implement the settled obligation contract in the canonical pre-archive gate.

### 4. Persistence and ownership correctness

- `07-25-user-scope-toolchain-caches`
- `07-25-fix-work-loop-lock-race`
- `07-25-backlog-selector-blocked-markers`
- `07-24-track-clean-recovery-artifacts`

Repair cache, lock, selection, and temporary-artifact ownership before the
cross-command recovery contract consumes those boundaries.

### 5. Typed environmental recovery

- `07-28-standardize-environment-blocked-recovery-evidence`

Integrate the typed boundary/checkpoint result across the already-corrected
recorder, finalization, housekeeping, work-loop, KB, cache, and managed-payload
owners.

### 6. Cumulative stability and release preparation

Run the umbrella matrix across every package and the repository's full release
gate. Feed the resulting evidence into
`07-22-validate-sd-workflow-program-integration` without completing that
broader program task.

## Session and checkpoint model

- The umbrella is the active session task.
- Every package is marked `in_progress` and assigned the same branch before its
  first code change.
- Each package ends with focused tests, a local routed-review disposition, one
  or more focused commits, and a `progress.md` checkpoint.
- A new session resumes the umbrella from the checked-out branch and the last
  checkpoint. It does not run finish-work merely because the conversational
  session ended.
- Pushing the feature branch for backup is not a publication milestone and
  does not permit a partial PR or merge.

## Review model

Local review is incremental and package-scoped. Remote review is cumulative
and exact-head scoped after all packages and the release gate pass. If review
findings advance the head, rerun affected focused tests and the cumulative
matrix, then rebind the remote and completion evidence to the successor head.

The existing multi-task-directory preflight warning is expected and must be
explicitly dispositioned as one cohesive self-hosting outcome. Any unrelated
source or task artifact is removed from the PR rather than justified by the
umbrella.

## Finalization model

Capture the finalization base only after code, tests, templates, release
metadata, candidate evidence, and task acceptance records are committed. Run
one pre-archive invocation across the umbrella and all eleven package task
directories. Archive only that exact set, then record one journal entry for the
campaign and validate one completion bundle across every archive mapping.

The active investigation and rollout tasks remain outside the finalization
range. The repaired branch-local scripts own the operation and remain fail
closed; the single-merge design is not permission to bypass receipt, CI,
review-thread, exact-head, or branch-deletion proof.

## Rollback and failure handling

- Before merge, revert or repair one focused package commit without disturbing
  other validated packages; rerun every downstream package that consumes its
  contract.
- If scope exceeds provider or human review capacity, stop and reduce
  implementation complexity or add bounded local review passes. Do not merge a
  partial stabilization solely to reduce PR size.
- If branch-local finalization fails, repair it on the same branch and rerun
  the canonical gate. Do not fall back to the old workflow or manual merge.
- After merge but before fleet rollout, a release-blocking regression is fixed
  in this source repository and receives a new successor release; consumers
  remain untouched until candidate validation is clean.

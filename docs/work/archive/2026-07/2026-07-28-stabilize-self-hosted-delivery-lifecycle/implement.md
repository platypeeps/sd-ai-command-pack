# Single-merge stabilization implementation plan

## Pre-start review gate

- Obtain explicit approval of this final PRD, design, and implementation plan
  before starting the task.
- Create one `codex/stabilize-self-hosted-delivery-lifecycle` branch from clean,
  synchronized `main`.
- Commit the current planning/handoff surface as the first bounded branch
  commit; do not create a planning-only PR.
- For the umbrella and each exact R2 work-package task, run the repo task
  tooling to set `status: in_progress` and assign the same feature branch. Start
  the umbrella last so it remains the session pointer.
- Initialize `progress.md` with the planning baseline commit and verify the
  active investigation and rollout tasks remain planning.

## Package execution loop

For each package in the design order:

1. Read its full PRD, design, implementation plan, and relevant repository
   specifications before changing code.
2. Implement only that package's bounded contract, changing templates first
   and synchronizing mirrors as required.
3. Run its focused tests plus applicable shell, static, parity, and negative
   fixtures.
4. Run a package-scoped local routed review; fix, rebut with evidence, or
   record every finding disposition.
5. Commit the focused code/tests/docs and then update `progress.md` with task
   ID, commit, checks, review result, dependencies satisfied, and next package.
6. Do not archive, journal-finalize, open another PR, merge, release, or refresh
   consumers. A later session resumes from the progress checkpoint.

## Cumulative integration

After all packages pass independently:

1. Run the complete R7 self-hosting matrix, including fail-closed and restart
   cases for every lifecycle epoch.
2. Run cross-package schema and compatibility tests, template/root parity,
   generated-surface checks, install audit, `make sync`, and `make check`.
3. Update version and changelog metadata and run `make release-prep` to produce
   current full-fleet candidate evidence in disposable consumer clones. This is
   candidate validation, not consumer rollout.
4. Run a cumulative local routed review of the full base-to-head diff and
   reconcile every finding.
5. Verify the diff contains only the umbrella outcome and explicitly
   disposition the expected multi-task-directory scope warning.

## Single publication and finalization

1. Publish or update exactly one stabilization PR after cumulative local gates
   pass; request the normal configured exact-head reviews.
2. Resolve all findings and required CI without splitting or partially merging
   the work packages. Rerun affected focused and cumulative tests after every
   successor head.
3. At the final reviewed code head, capture the finalization base and run the
   canonical pre-archive validator once with the umbrella plus all eleven exact
   work-package directories.
4. Archive that exact set through Trellis, record one campaign journal entry,
   and generate the canonical multi-task completion receipt. Do not archive the
   investigation, rollout, or broad program-integration tasks.
5. Push the bookkeeping successor, rerun exact-head review/CI/thread settlement
   as required, and merge once through `sd-housekeeping` with the unchanged
   valid receipt.
6. Verify clean synchronized `main`, no residual feature branch, no completed
   task outside archive, and a release-ready source tree.

## Post-merge boundary

- Publish the successor release from the merged stabilization outcome through
  the repository's normal release path.
- Do not begin `07-28-roll-out-stabilized-pack-release-to-fleet` until the tag,
  payload, candidate ledger, and source identity all verify.
- Leave broader program integration and local Trellis-checkout work in their
  existing non-blocking tasks.

## Stop conditions

- A work package cannot satisfy its own acceptance criteria or conflicts with
  a previously settled package contract.
- The cumulative matrix exposes an unsafe state transition, non-idempotent
  retry, merge bypass, or destructive cleanup path.
- An unrelated task or source change enters the branch.
- Review size prevents credible coverage after bounded local decomposition.
- Finalization cannot validate every intended task archive and exact head.
- A safe solution appears to require upstream Trellis publication; stop and
  present the exact evidence before expanding scope.

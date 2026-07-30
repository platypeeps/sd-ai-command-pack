# Remediation design for recurring Trellis workflow instability

## Design objective

Close the two command-pack gaps found by the session review without weakening
exact-head merge safety, adding another merge authority, or conflating
environmental permission failures with repository defects.

## Invariants

- Housekeeping remains the only merge and branch-cleanup mutation owner.
- An open PR requires the full finish-work, CI, review-thread, merge-state, and
  exact-head eligibility gate.
- An already-merged PR requires deletion proof, not merge eligibility.
- Environment failures never authorize automatic escalation, broader retries,
  bypasses, or destructive recovery.
- Retries resume from a verified checkpoint and remain idempotent.
- Templates remain authoritative and generated/root mirrors stay synchronized.
- Upstream Trellis changes or pull requests remain separately consent-gated.

## Work package A: route housekeeping by PR lifecycle state

Owner: `07-28-route-housekeeping-by-pr-lifecycle-state`.

### Current defect

`templates/scripts/sd-ai-command-pack-housekeeping.sh` calls
`maybe_merge_ready_open_pr "$START_BRANCH"` before
`cleanup_current_branch_if_merged "$START_BRANCH"`. The first call can emit
`finish_work_missing` even when GitHub already reports the PR as merged and no
merge eligibility question remains.

### Proposed state dispatcher

After refresh/default-branch discovery, resolve bounded PR identity for the
starting feature branch and route once:

| PR state | Action |
| --- | --- |
| `OPEN` | Run exact-head eligibility; merge only if eligible; refresh PR identity before cleanup. |
| `MERGED` | Skip eligibility; run exact-head merged-branch cleanup directly. |
| `CLOSED` | Report one `pull_request_not_merged` anomaly; do not run eligibility or delete. |
| unavailable/ambiguous | Report one indeterminate PR-identity anomaly; do not merge or delete. |

The dispatcher should pass the already-resolved PR identity into the cleanup
path when no merge occurred. After an actual merge, cleanup must reread GitHub
state so deletion remains bound to the merged PR head and merge timestamp.

### Result contract

- Already-merged cleanup has `eligibility: null` because no merge evaluation
  applied.
- Successful single-run cleanup returns `outcome.status: clean` when final
  delegated status is clean.
- The result records `pull_request_merge_confirmed`, branch deletion, default
  synchronization, and final status actions without retaining an irrelevant
  pre-cleanup anomaly.

## Work package B: standardize environment-blocked recovery evidence

Owner: `07-28-standardize-environment-blocked-recovery-evidence`.

### Design boundary

Do not infer permissions from arbitrary stderr after the fact. Each owning
mutation boundary already knows the operation and should compose a shared
typed blocker when that operation fails for a known environment boundary.

### Shared blocker fields

- `reasonCode: environment_blocked`
- `boundary`: bounded enum such as `git-metadata`, `user-state`, `tool-cache`,
  `kb-target`, or `managed-payload`
- `operation`: bounded command-owned operation identifier
- `retryable`: boolean
- `checkpoint`: last verified lifecycle checkpoint
- `recoveryAction`: bounded argv-style action or skill-owned instruction
- `mutationState`: `none`, `partial-recoverable`, or `unknown`
- `diagnostic`: bounded human text without secrets or uncontrolled raw paths

The object should be a shared schema fragment consumed by existing command
results, not a new public command and not a universal exception wrapper.

### Initial owning boundaries

1. Recorder staging/commit after a successful journal append.
2. Finish-work Git metadata and retained-receipt writes.
3. Housekeeping fetch/prune, KB refresh, default-branch switch, and deletion
   proof operations.
4. Work-loop user-local lock, heartbeat, checkpoint, and reconciliation writes.
5. Toolchain cache creation/ownership checks.

Every caller preserves its existing failure/exit semantics. Skills interpret
the structured blocker and request only the narrowly required retry authority.
They do not automatically escalate or restart the complete lifecycle.

### Coordination with existing tasks

- Build on completed `07-24-standardize-sandbox-safe-tool-cache-routing`.
- Coordinate cache ownership with `07-25-user-scope-toolchain-caches`.
- Keep artifact ownership in `07-24-track-clean-recovery-artifacts`.
- Keep lock correctness in `07-25-fix-work-loop-lock-race`.
- Keep receipt-path input validation in
  `07-28-validate-finish-work-receipt-path`.
- Do not widen `07-25-harden-toolchain-failure-paths`, whose current scope is
  GraphQL pagination and descriptor ownership.

## Upstream Trellis reconciliation

The completed task left outside the local Trellis source checkout's archive is
an operational repository inconsistency, not a third command-pack work
package. Verify its task evidence there, archive it through that repository's
own Trellis workflow, and publish any resulting upstream change only after
separate approval.

Two Trellis-owned planning tasks now capture the investigation's durable
upstream gaps:

- `07-28-harden-add-session-retry-convergence` owns accurate commit subjects
  and retry-safe producer behavior.
- `07-28-restore-install-safe-opencode-mem-reader` owns complete OpenCode
  session coverage without native install fragility.

Neither task changes command-pack ownership, and neither authorizes an upstream
implementation or pull request.

These upstream tasks do not block command-pack remediation, integration,
release, or fleet rollout. Prefer local pack compensation or local-only work in
the Trellis checkout. Reclassify an upstream change as required only when the
final integration matrix proves that no safe local mitigation exists.

## Compatibility and rollout

- Work package A is a behavioral correction under the existing housekeeping
  result schema; add explicit compatibility fixtures for `eligibility: null`.
- Work package B should version its schema fragment independently or land with
  the housekeeping-result compatibility decision if it changes an existing
  result object.
- Ship both through normal template synchronization, release metadata, pack
  validation, and fleet refresh.
- Add both scenarios to `07-22-validate-sd-workflow-program-integration` before
  program closure.

## Single-merge bootstrap boundary

Owner: `07-28-stabilize-self-hosted-delivery-lifecycle`.

Deliver every pack-owned remediation from F1, F3, F4, and F5 on one branch and
through one PR/merge. Retain the existing tasks as focused acceptance and test
contracts, but do not use separate planning or implementation merges. The
umbrella runs the bounded self-hosting matrix required for safe release; the
broader `07-22-validate-sd-workflow-program-integration` task consumes that
evidence later and does not expand the bootstrap PR.

Use focused commits, package-local tests and reviews, and `progress.md`
checkpoints between sessions. Run finish-work, multi-task archive, journal,
exact-head remote review, and housekeeping only once at the cumulative head.
The successor release and fleet rollout remain outside this PR.

## Rollback

- Package A can revert to the previous dispatcher without changing receipt
  formats; merge safety remains fail closed.
- Package B is additive until every command consumes the fragment. A command
  without support retains its current bounded failure result rather than
  accepting partial evidence.

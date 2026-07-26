# Design: Post-Archive Review Finalization

## Decision

Model post-archive review fixes as a verified successor of an already-valid
completion, not as a new planning bundle or a second completion mutation.
Externally the result remains `mode: completion`; typed evidence carries an
internal `post-archive-review-successor` subtype.

This keeps the lifecycle honest: the task was completed once, its journal was
recorded once, and later code-review fixes are still reviewed and tested at the
exact final head without manufacturing more bookkeeping.

## Evidence Model

The evaluator produces one schema-versioned receipt containing bounded,
repository-relative evidence:

- repository/branch identity and PR base identity when available;
- original completion base and bookkeeping head OIDs;
- canonical completion-validator result and archived task directories;
- completed journal file and session identity;
- ordered successor commit OIDs, subject digests, and changed-path summary;
- exact final head OID;
- `mode: completion` and
  `completionSubtype: post-archive-review-successor`; and
- stable reason codes and recovery provenance.

Receipt persistence uses the command pack's repository-local ignored runtime
state, resolved through a shared helper. It is a cache and handoff, not an
authority: eligibility recomputes Git identity and critical invariants before
merge.

## Resolution Flow

1. Normal finish-work first evaluates active-task completion and planning
   finalization exactly as today.
2. Only when no active completion/planning mutation applies, look for a prior
   completion receipt reachable from the exact current head.
3. For pre-receipt branches such as PR #253, perform one bounded first-parent
   search for an unambiguous adjacent archive/journal tail. Revalidate its
   original base-to-bookkeeping-head range with the canonical completion
   validator.
4. Validate the bookkeeping-head-to-current-head successor range:
   - first-parent linear and bounded;
   - every object available;
   - no task, workspace, or finalization bookkeeping changes; and
   - exact current branch/head identity.
5. Emit and retain the successor receipt without modifying the worktree, index,
   refs, journal, task metadata, or Trellis session pointer.
6. `sd-review-pr` hands the receipt forward after the clean exact-head review
   loop. Housekeeping eligibility loads it, checks the current head, and
   independently verifies the completion anchor and successor invariants before
   applying its existing CI/thread/merge gates.

## Failure Semantics

- No reachable completion anchor: `completion_successor_anchor_missing`.
- More than one equally valid anchor: `completion_successor_anchor_ambiguous`.
- Invalid historical completion: preserve the canonical completion findings
  and add `completion_successor_anchor_invalid`.
- Successor changes bookkeeping: `completion_successor_scope_invalid`.
- Nonlinear, missing-object, or oversized history: a specific
  `completion_successor_history_*` invalid or indeterminate result.
- Receipt/head/repository mismatch: `completion_successor_receipt_mismatch`.

Every non-valid result stops before staging, committing, pushing, review
requests, or merge. Diagnostics remain bounded and repository-relative.

## Rejected Alternatives

- Passing the current OID through `--finish-work-head`: proves only equality,
  not that finish-work occurred.
- Recording a second journal entry for review fixes: duplicates completion
  history and triggers another CI/review cycle.
- Editing session 230: rewrites historical bookkeeping.
- Relaxing journal-only planning recovery to accept code: erases the boundary
  between planned artifacts and implemented work.
- Skipping housekeeping or forcing merge: bypasses the sole merge authority.

## Compatibility And Rollout

- No third public command or user-selected mode.
- Migrate finish-work, review, eligibility, housekeeping, and status together;
  remove the bare head attestation when all internal consumers use receipts.
- Retain a bounded historical-anchor recovery only for branches completed
  before receipt persistence existed. It follows the same validator and does
  not accept weaker evidence.
- Roll back by disabling successor recognition; ordinary completion/planning
  flows remain unchanged and affected PRs safely return blocked.

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

Receipt persistence is a private, caller-owned temporary file created with
`mktemp`. It is a handoff, not repository state, a durable cache, or an
authority: eligibility reruns the canonical validator with the receipt's exact
mode/base/head and requires complete JSON equality before any remote query or
merge. The owner preserves it across a clean downstream handoff and deletes it
after housekeeping consumes it, the proof is abandoned, or the lifecycle
blocks.

## Resolution Flow

1. Normal finish-work first evaluates active-task completion and planning
   finalization exactly as today.
2. Only when no active completion/planning mutation applies, invoke completion
   validation on the empty exact-head range.
3. Perform one bounded first-parent search for the nearest adjacent
   archive/journal tail. Revalidate its original base-to-bookkeeping-head range
   with the canonical completion validator. The 100-commit search bound applies
   to distance from the current head, not total repository history.
4. Validate the bookkeeping-head-to-current-head successor range:
   - first-parent linear and bounded;
   - every object available;
   - no task, workspace, or finalization bookkeeping changes; and
   - exact current branch/head identity.
5. Emit the deterministic successor receipt into a private temporary file
   without modifying tracked files, the index, refs, journal, task metadata, or
   Trellis session pointer.
6. `sd-review-pr` hands the receipt forward after the clean exact-head review
   loop. Housekeeping eligibility loads it, checks the current head, and
   independently verifies the completion anchor and successor invariants before
   applying its existing CI/thread/merge gates.

## Failure Semantics

- No reachable completion anchor: `completion_successor_anchor_missing`.
- Invalid historical completion: preserve the canonical completion findings
  and add `completion_successor_anchor_invalid`.
- Successor changes bookkeeping: `completion_successor_scope_invalid`.
- Nonlinear, missing-object, or oversized history: a specific
  `completion_successor_history_*` invalid or indeterminate result.
- Receipt branch/head mismatch: `finish_work_stale`; invalid replay:
  `finish_work_invalid`; valid-but-different replay:
  `finish_work_receipt_mismatch`; unavailable replay:
  `finish_work_unavailable`.

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
- Retain bounded historical-anchor recovery as the deterministic source of the
  successor receipt. No repository-local receipt store or compatibility alias
  is introduced.
- Roll back by disabling successor recognition; ordinary completion/planning
  flows remain unchanged and affected PRs safely return blocked.

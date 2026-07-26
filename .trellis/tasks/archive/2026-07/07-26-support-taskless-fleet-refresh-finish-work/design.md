# Taskless fleet refresh finish-work design

## Context

The fleet controller published `rwbp-coordinator` PR #177 from a checkout with no active Trellis task. The merge action correctly delegated to `sd-finish-work`, which added a journal-only planning commit. The final-bundle validator rejected the cited installer commit because journal-only recovery intentionally proves only active-task artifact commits. That fail-closed rule is correct; the fleet workflow failed to establish the task evidence its merge tail requires.

## Decision

Use ordinary Trellis task lifecycle evidence for every future consumer lane and add one explicit controller recovery transition for already-published taskless lanes.

### Future lanes

After a clean checkout and refresh branch are established, `checkout-validation` creates and activates one dedicated lightweight consumer task named for the target pack version. The task PRD records the immutable release, managed scope, preparation command, checks, and finish-work expectation. Those task artifacts travel in the initial PR. The normal merge tail archives that task and records the journal, so existing completion validation and housekeeping receipts remain unchanged.

### Existing blocked lane

After a corrective source release, `resume --recover-consumer <name> --corrective-release <version>` may reopen only a terminal `review-finding` lane that is marked `packBlocker`, stopped at `merge`, and retains an exact PR/head. The transition preserves all old receipts, records bounded recovery evidence, increments the attempt, and returns the lane to `pr-publication` so the controller owns the next push.

Within that issued publication action, append one planning recovery task to the consumer branch. Keep the existing unpushed journal commit unchanged, commit the new task artifacts, rerun `final-bundle --mode planning` over the original finalization base, and require a valid exact-head receipt before pushing. Reuse the existing PR, record the new head, rerun review and CI, and pass the retained receipt to housekeeping if the reviewed head remains unchanged.

## Safety invariants

- Do not broaden journal-only planning recovery to arbitrary implementation commits.
- Do not amend, reset, drop, force-push, or fabricate a task at a historical commit.
- Do not reopen ownership skips, product failures, non-pack findings, or lanes without exact PR/head evidence through corrective recovery.
- Do not replay the prior merge action; recovery starts a new publication attempt and preserves the original blocker receipt.
- Require the named corrective release to differ from the campaign target and to be the version in the current source manifest before reopening a lane.
- Preserve existing exact-head rules from publication through review, eligibility, finish-work, and housekeeping.

## Contract-surface sweep

| Surface | Included contract |
|---|---|
| Fleet skill | Dedicated task creation before install; append-only blocked-lane recovery; retained finish-work receipt handoff |
| Controller CLI/state | Mutually exclusive corrective recovery argument, strict preconditions, attempt/stage reset, recovery evidence and reports |
| Consumer task lifecycle | Active task for new lanes; planning task only for append-only recovery; substantive PRD in both modes |
| Finish-work validator | Existing planning/completion rules remain unchanged and fail closed for arbitrary non-task commits |
| PR publication/review | Existing PR reuse, exact new head, remote fallback when task/workspace paths are present |
| Housekeeping | Existing receipt recomputation and exact-head comparison remain authoritative |
| Templates/mirrors | No shipped consumer runtime change is required for the recovery itself; source-only fleet surfaces remain single-copy |
| Failure behavior | Invalid corrective release, wrong stage/result, missing head/PR, dirty unrelated work, or invalid final bundle pauses without mutation |

Excluded: changing upstream Trellis task semantics, weakening generic bookkeeping validation, rewriting the blocked consumer branch, and automatically closing or replacing PR #177.

## Validation

- Controller unit tests for allowed recovery, every rejected precondition, report/state persistence, mutual exclusivity, and next-action sequencing.
- Static skill-contract tests for proactive task lifecycle and append-only recovery wording.
- Existing bookkeeping validator tests prove the recovery task plus journal bundle while retaining rejection of arbitrary journal-only implementation commits.
- Hermetic candidate diagnostics, full-fleet candidate validation, install audit, and `make check` before the corrective release.

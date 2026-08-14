# Classify the settled-blocked watch outcome

Upstream record: issue #412. Observed on `platypeeps/se-ai-command-pack`
PRs #155 and #157.

## Goal

Make the Stage 3 watch coordinator's `settled-blocked` outcome say which of
its at-least-three underlying conditions was observed, because they demand
opposite responses:

1. **Infrastructure failure** (zero-step cancelled lanes, `Set up job`
   failures, `Service Unavailable`) — cleared by waiting/retrying, never by
   code changes.
2. **Real check failure** — never cleared by retrying.
3. **Unresolved review threads** — merge state blocks while every check is
   green; the documented short-circuit guarantees `threads: null` in exactly
   this case, so the one field that would name the cause is absent.

## Requirements

- Add a classification field (or additional outcomes) to `settled-blocked`,
  derived only from evidence the probe already obtains or one bounded
  read-only call: check-run conclusions, `Set up job` step status, per-lane
  durations, unresolved-thread count when merge state blocks.
- An unclear signal still fails toward blocking.
- The classification must not feed merge eligibility; housekeeping's atomic
  recomputation remains the only merge authority.

## Relationship to neighbours

- Issue #414 / `08-07-eligibility-superseded-runs` fixes the upstream
  `parse_checks` CANCELLED misclassification; this task is the outcome
  vocabulary of the watch coordinator, per #414's own not-a-duplicate note.
- `08-08-pr-eligibility-stale-blocked-review` handles `mergeStateStatus`
  staleness in pr-eligibility. Keep the three scopes disjoint.

## Acceptance Criteria

- [ ] Each of the three conditions above produces a distinct, documented
      classification in the watch report, backed by a test or recorded
      fixture per condition.
- [ ] The unresolved-thread case reports the thread count instead of
      `threads: null`.
- [ ] Ambiguous evidence yields an explicit `unclassified` value, still
      blocking.
- [ ] Merge eligibility behaviour is byte-identical before and after.
- [ ] Issue #412 is closed by the shipping PR.

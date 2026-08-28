# A successful worktree merge reports verdict blocked because status expectations ignore the held default branch

## Goal

A housekeeping run that merges a pull request successfully should not report `verdict: blocked`
and exit nonzero. When the only outstanding condition is a default branch held by another live
worktree, housekeeping already classifies that as advisory; the status expectations it
delegates to do not, and their blocking codes decide the verdict.

## Origin

Observed twice on 2026-08-28, merging PR #580 and PR #581 from linked worktrees while the
primary checkout held `main`. Both merges succeeded and were confirmed:

```text
pull_request_merged           merged PR #581 with merge strategy
pull_request_merge_confirmed  confirmed PR #581 merged at 2026-08-28T20:36:54Z
```

The run's own anomalies were correctly advisory:

```text
default_branch_held_elsewhere  main is checked out in worktree <primary>; this checkout
                               stays on task/08-28-preflight-branch-name-vs-path
branch_retained_default_held   still on task/...; skipped branch deletion
```

And the verdict was still:

```text
verdict: blocked
reasonCodes: status_current_branch_unexpected,
             status_local_source_branch_retained,
             status_remote_source_branch_retained
```

Exit status 1. Nothing was wrong with the merge; only post-merge cleanup was deferred, for a
reason the operator could not resolve from that worktree.

## The mechanism

Two layers disagree, and only one of them knows about the held default branch.

**The housekeeping layer already handles it.** `ADVISORY_ANOMALY_CODES`
(`scripts/sd-ai-command-pack-housekeeping-result.py:64-69`) contains exactly
`default_branch_held_elsewhere` and `branch_retained_default_held`, and its comment states this
task's whole thesis:

> A verdict that blocks on a normal steady state fires on every successful merge and stops
> carrying information, which is the failure this set exists to prevent.

**The status expectation layer does not.** The three codes that actually blocked are produced by
the strict expectation evaluation in `scripts/sd-ai-command-pack-status.py`, and housekeeping
prefixes them `status_`. Each fails differently:

1. `current_branch_unexpected` (`:2723-2730`) fires unconditionally on `branch != default`.
   Staying on the source branch is the documented, correct behaviour when the default branch is
   held, but this check has no notion of that.

2. `local_source_branch_retained` (`:2789-2795`) *does* have holder awareness, and it still
   misses this case. The holder scan (`:2766-2773`) requires

   ```python
   and not row.get("current")
   ```

   so it only recognises a branch held by *another* worktree, emitting the advisory
   `local_source_branch_held_elsewhere`. Here the source branch is held by the **current**
   worktree — the one running housekeeping, which could not switch away because `main` was
   held elsewhere. That falls through to the blocking `else`.

3. `remote_source_branch_retained` (`:2807-2813`) has no holder awareness at all. The remote
   branch was retained only because the local deletion it follows was skipped.

All three trace to one root condition that the layer above already calls advisory.

## Prior art

`.trellis/tasks/archive/2026-08/08-07-status-housekeeping-anomaly-disagreement` solved this
exact disagreement once, for the anomaly channel. `ADVISORY_ANOMALY_CODES` and its collector
twin are that fix. The expectation channel was not covered, so the same disagreement returned
through a second door.

## Requirements

- A run whose pull request merged and confirmed, and whose only unmet expectations follow from a
  default branch held by another live worktree, reports a non-blocking verdict and exits zero.
- The advisory demotion is driven by the same held-branch evidence the anomaly channel already
  uses, not by a second hand-maintained list that can drift from it. The existing collector/result
  pairing is pinned by a test for precisely that reason; a third copy should not be introduced.
- A branch held by the **current** worktree is recognised as held. The `not row.get("current")`
  condition is correct for reporting *who else* holds a branch, but wrong as the gate on whether
  deletion was possible.
- Every one of the three codes stays blocking in its ordinary case. A source branch retained
  with no worktree holding it, a current branch that differs from the default for any other
  reason, and a retained remote branch on a normal run all still block.
- The deferred cleanup remains visible. Demoting the verdict must not hide that a branch still
  exists; the advisory anomalies and the follow-up that names them are the surface for that.

## Non-goals

- Making housekeeping switch or delete the default branch while another worktree holds it.
- Changing `ADVISORY_ANOMALY_CODES` membership, which is deliberately narrow and correct.
- Any change to the merge, eligibility, or deletion gates. This is verdict classification after
  those gates have already done their work correctly.

## Acceptance criteria

- [ ] A test reproduces the observed shape — merge confirmed, default branch held by another
      worktree, source branch retained — and asserts `verdict` is not `blocked` and the exit
      status is zero. It fails against the current code.
- [ ] The same test asserts the advisory anomalies and the retained-branch follow-up are still
      present in the result, so the demotion did not silence the condition.
- [ ] A source branch retained with **no** worktree holding it still yields a blocking verdict,
      pinned by its own test so the fix cannot over-reach.
- [ ] `current_branch_unexpected` still blocks when the current branch differs from the default
      for a reason unrelated to a held default branch.
- [ ] A branch held by the current worktree is treated as held; a test covers that path
      specifically, since the existing `not row.get("current")` guard is what excludes it.
- [ ] All four copies of every changed script stay byte-identical and `make generate` reports
      `shipped-surface closure: clean`.

## Related

- `.trellis/tasks/archive/2026-08/08-07-status-housekeeping-anomaly-disagreement` — the same
  disagreement, fixed for the anomaly channel.

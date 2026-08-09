# sd-status reports no worktrees, including ones holding branches it lists

## Goal

Make `sd-status` report the repository's Git worktrees, and mark the local
branches that are checked out in one, so a reader can tell which branches are
actually free.

## Problem

The status collector has no worktree inventory. Not an incomplete one — none:

```text
$ grep -in "worktree" scripts/sd-ai-command-pack-status.py
$
```

Zero matches in the whole collector. The only path that touches worktrees at
all is `collect_recovery` (`scripts/sd-ai-command-pack-status.py:1353`), which
delegates to the recovery-artifacts helper's read-only classifier. That helper
deliberately ignores worktrees it does not own
(`scripts/sd-ai-command-pack-recovery-artifacts.py:818-865`):

```text
"""Report pack-shaped artifacts that lack a receipt; never adopt or delete.

Genuine user stashes and worktrees (no pack marker, outside the pack
worktree base) are intentionally ignored: taking ownership of them is out of
scope.
"""
```

It matches only paths under the pack's own `worktree_base(digest, state_root)`
(`:277`, `:508`, `:848`). Everything else is invisible by design.

**That design is correct and must not change.** Ownership is receipt-based:
an artifact with no receipt is unowned and is never touched. The defect is not
that the classifier ignores foreign worktrees — it is that `sd-status` has no
*other* source of worktree information, so "ignored for cleanup" silently
became "absent from the report".

### Observed

On 2026-08-07, with five linked worktrees live:

```text
==> Recovery Artifacts
- state: no tracked recovery artifacts
```

and the classifier returning all-zero counts with `"unowned": []`. Meanwhile
the same report listed twelve local branches with no indication that six of
them were checked out elsewhere.

### Why it matters

The pack's own workflow creates worktrees. `sd-housekeeping` merges one PR at
a time and checks out the default branch to do it; the documented way to run
several PRs without branch contention is a worktree per branch. Four were
created and removed by hand in one session while shipping #352, #353, #354,
and #355.

Three concrete failures follow from the blind spot:

1. **A listed branch may not be checkoutable.** `git worktree add` and
   `git checkout` both refuse a branch already checked out in another
   worktree. Status presents every local branch identically, so the refusal
   arrives as a surprise at mutation time.
2. **Housekeeping switches to the default branch.** If `main` is held by a
   worktree, that step fails in the middle of a merge sequence rather than
   before it.
3. **A leaked worktree is never surfaced.** A run that fails partway leaves
   one behind. Nothing in any report mentions it, so it is found by accident
   or not at all — and its branch stays locked in the meantime.

## Requirements

1. The status collector inventories the repository's worktrees from Git itself
   — `git worktree list --porcelain` is the enumerating source — rather than
   from the receipt-scoped recovery classifier.
2. Each row reports the worktree path, its checked-out branch (or detached
   HEAD), and whether its tree is clean. Paths outside the repository are
   reported as-is; the collector does not resolve or follow them beyond what
   Git reports.
3. The local-branch listing marks each branch that is checked out in a
   worktree other than the reporting one, so the two sections cannot
   disagree.
4. The reporting worktree identifies itself, because "the current checkout" is
   one of the rows and reading the list is useless without knowing which.
5. This is read-only, like the rest of `sd-status`: no worktree is created,
   pruned, adopted, repaired, or removed, and no receipt is written.
6. The recovery-artifacts classifier keeps its current ownership semantics
   unchanged. Worktrees it does not own stay unowned; the new inventory is a
   separate, additive report section and must not be routed through
   `active` / `safe-cleanable` / `needs-review` / `missing-artifact` /
   `unowned-artifact`, which mean specific things about receipts.
7. Absent or unavailable worktree information is reported explicitly, not
   silently converted into an empty healthy result — the same rule the skill
   already applies to GitHub and version discovery.
8. `--json` carries the same inventory in structured form under the existing
   schema version rules.
9. Worktree paths are externally controlled strings. They are bounded and
   control-character-filtered like every other externally controlled row.

## Acceptance criteria

- With N linked worktrees present, the report lists N rows plus the reporting
  checkout, and `git worktree list --porcelain` agrees row for row.
- A branch checked out in another worktree is marked as such in the
  local-branch listing, and — under git's normal exclusive-checkout
  invariant (no `worktree add -f` forced duplicates) — the marked set
  exactly equals the set `git checkout` would refuse from the reporting
  worktree. A forced duplicate of the reporting branch is still marked
  (it is genuinely held elsewhere) even though checking it out here
  would no-op succeed.
- A repository with no linked worktrees reports the empty state explicitly
  rather than omitting the section.
- Running status leaves `git worktree list --porcelain` byte-identical before
  and after, and creates or modifies no receipt.
- The recovery-artifact classifications for an unchanged repository are
  identical before and after this change, verified against the existing
  helper output.
- A worktree whose path no longer exists on disk (`prunable`) is reported as
  such and is not pruned.

## Out of scope

- Adopting foreign worktrees into pack ownership, or creating receipts for
  them. Ownership stays receipt-based.
- Pruning, removing, or repairing any worktree from `sd-status`. Retirement of
  proven-safe pack-owned artifacts remains `sd-housekeeping`'s.
- The `sd-status` / `sd-housekeeping` anomaly disagreement, owned by
  `08-07-status-housekeeping-anomaly-disagreement`.
- Fleet mode, which reports one bounded row per consumer and has its own
  size constraints.
- Deciding whether a leaked worktree is an anomaly. This task makes it
  visible; classifying it is a follow-on once there is something to classify.

---
title: Build an unmanaged repository's item to a draft pull request
created: 2026-11-06
item: sd:7868
---

# Design — unmanaged-build

## Problem

The Build press and auto-pickup refuse a ready item whose repository is
registered with `repo.managed = 0`: `build._repo_refusal` says "is not
managed". Such a repository belongs to someone else (memory-experiment
sd:7832 is one), so no lane, merge or pack file may reach it. The operator
ruled (sd:7868 note #46131) that a build there still runs: the same builder,
`sd-review --scope branch` and the repository's own tests, then a pushed
branch and a draft pull request that the owners merge.

## Approach

Keep the run's steps and their compare-and-sets; change what two steps do
when the run's repository reads unmanaged.

- Press and pickup: `_repo_refusal` drops the managed rule. An unmanaged
  repository instead needs a GitHub remote, and each item must be a
  `task`: its pull request is tracked as the task's contribution
  `pull_url`, which `contributions.configure` writes for tasks only.
- `reviewing`: `sd-review` already runs review-only there (its gate
  skips an unmanaged checkout, sd:5953). After a clean or advisory review
  the supervisor runs the repository's own checks, as `sd-check` detects
  them (`sd_lib.detect_entrypoints`: the local block, Makefile, Taskfile,
  package.json, Cargo.toml, pyproject.toml), each through `sd gate run`
  so it queues for a machine gate slot. A failure goes back to the
  builder as a blocker, as `gate_failed` does. No entrypoint found is
  noted on the lead item and is no failure.
- `enqueuing`: the same compare-and-set, delivery read, title check and
  `sd-docs-lint --pr-body`. Then, instead of `sd-ship lane enqueue`:
  `git push origin <head>:refs/heads/<branch>`, find the open pull
  request for that head branch with `gh pr list`, or open one with
  `gh pr create --draft`, then link it on the lead task with
  `contributions.configure(pull_url=...)`. The run's `detail` names the
  draft, and `build.enqueued` ends the members `done` with the lease
  released, as for the lane.
- Title and body: the builder writes both, as for the lane; the same
  line check and leak guard (`enqueue_refusals`) run before the review.
- `enqueued`: the tick's `watch` reads a run whose `detail` names a draft
  pull request from the contribution observation (`contribution_sync`
  observes every task `pull_url`), never the lane. Merged: the delivered
  tasks still `in_progress` move to `done`, and the run goes to
  `cleaning` (never `checking`: a merge in someone else's repository
  deploys nothing here). Closed without merge: the run ends
  `lane_failed`, its items left for the operator. Open: nothing.
- Item status: `in_progress` until the merge, as a lane-held item is.
  With sd:7859, Queue shows it as waiting on the pull request. A draft
  pull request the operator wrote, linked to an item, reads `awaiting_you`
  with the reason "Draft pull request: mark it ready for review", so the
  operator sees it until it is marked ready (note #46134). The Builds
  panel's Open PR link reads the lead task's `pull_url` when the run's
  repository is unmanaged.

Rejected: letting `sd-check` or `sd-ship` run in an unmanaged checkout.
Both refuse there on purpose (sd:2566), and `sd-ship` writes receipts and
merges. Rejected: a new run column for the mode. The run's `detail` is
unset on an open run until it ends, so it carries the draft's address at
`enqueued` with no schema change.

No new command, flag, setting or table. `Tools` gains two argv seams,
`gh` and `gate`, which tests fill with fakes.

## Non-goals

- No merge, no `sd/local-gate`, no lane entry, no ship receipt.
- No pack file written into the repository: the title and body live in
  the run's log folder; the worktree holds only the builder's commits.
- No `work` or `report` items in an unmanaged repository.
- No marking ready for review: the operator does that on GitHub.

## Failure table

```text
Step     | State moved            | Failure              | Recovery                        | Test
-------- | ---------------------- | -------------------- | ------------------------------- | -----------------------------
claim    | assignment running,    | repo turned managed  | _refused_repo blocks a queued   | test_build: press and pickup
         | item in_progress, run  | or lost its GitHub   | build whose repo now refuses;   | take an unmanaged task;
         | and lease              | remote after press   | item left as it is              | refuse a non-task, no GitHub
worktree | git worktree, branch   | fetch or add fails   | run ends blocked; reap retries  | unchanged (managed tests)
         |                        |                      | a lost run once at `worktree`   |
build    | builder commits        | builder fails        | as managed: blocked or retried  | unchanged
review   | review_round           | review blocks        | fix round, at most 3            | unchanged
tests    | review_round on fail   | a check exits non-0  | blocker to the builder, rerun   | test_build_run: unmanaged
         |                        |                      | review and tests on the fix     | tests fail, fix, pass
tests    | none                   | supervisor lost      | reap retries at `reviewing`,    | resume at reviewing reruns
         |                        | mid-test             | which runs review and tests     | the tests
push     | remote branch at head  | push fails           | run ends blocked, nothing       | test_build_run: push refused
         |                        |                      | opened; Retry pushes again      | blocks, no PR call
push     | remote branch at head  | lost after push      | retry at `enqueuing` pushes the | lost after the push: the
         |                        |                      | same head again (a no-op)       | retry opens one PR
draft PR | an open draft PR       | gh refuses           | run ends blocked with gh's text | gh create refused
draft PR | an open draft PR       | lost after create    | retry finds the open PR for the | lost after the create:
         |                        |                      | branch with gh pr list, opens   | retry lists and creates none
         |                        |                      | no second one                   |
link     | lead task's pull_url   | configure refuses    | run ends blocked naming the URL | link refused blocks
end      | detail, members done,  | lost before enqueued | retry redoes push, list, link:  | covered by the two above
         | lease released         |                      | each finds its state done       |
merge    | tasks done, run at     | observation unread   | nothing moves; next tick reads  | watch: open, merged, closed,
         | cleaning               | or stale             | again                           | unread
merge    | run lane_failed        | closed unmerged      | operator reopens or cancels;    | watch: closed ends lane_failed
         |                        |                      | worktree kept                   |
```

## Acceptance criteria

- [ ] A press on a ready task in an unmanaged repository with a GitHub
  remote queues; `make test SUITE=sd_db` style focused runs of
  `tests/sd_db/test_build.py` pass.
- [ ] A supervised unmanaged run ends `enqueued` with a draft pull
  request, no `sd-ship` call, the branch on the fixture origin, and the
  lead task's `pull_url` set; `tests/sd_db/test_build_run.py` passes.
- [ ] Every managed-path test in both files passes unchanged.

## Risks

- A push to a third-party remote publishes. It happens only in a build
  the operator pressed or auto-pickup they turned on; tests push to a
  fixture bare repository and fake `gh`.
- Commits carry `Closes: sd:N` trailers into the owners' history. The
  delivery read needs them; they name an item number, nothing private.
- The merge closes the items only once `contribution_sync` observes it,
  which runs on its own schedule.
- The draft's "needs you" reason waits for the first observation.
- Evidence: the watch ties a merge to the run by the pull request URL
  the run recorded and the observation keyed by that URL; the tests'
  pass is tied to the head the review read.

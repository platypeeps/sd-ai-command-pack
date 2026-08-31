---
name: sd-rebase-hygiene
description: Use when the user explicitly asks to rebase a long-lived branch or worktree — user-invoked only, never triggered automatically. Fetch before trusting local state, dry-run the merge before touching the working tree, pre-plan every conflict resolution, and verify the remote ref after a user-approved force-with-lease push.
---

# SE Rebase Hygiene

Run the rebase ritual for a long-lived branch: establish ground truth
with a fetch, discover the real conflict surface with a dry run before
the working tree is touched, resolve conflicts to a plan agreed in
advance, and prove the push landed by checking the remote ref — not the
exit code.

The ritual exists to prevent three specific failures: rebasing onto a
stale base because the fetch was skipped, hitting conflicts mid-rebase
with no plan and resolving them ad hoc, and reporting "pushed" while the
remote still shows the old head.

## When to use

Use only when the user explicitly invokes it. Rebasing rewrites shared
history, so it is a deliberate operator action — never start this
workflow because a branch merely looks behind, and never model-trigger
it as a side effect of other work.

Typical explicit occasions: bringing a long-lived feature branch up to
date with its base, cleaning up a branch before a pull request, or
untangling a worktree whose base has moved. For pre-merge quality checks
on the resulting diff, use `sd-gate-probes`; the review verdict stays
with the sd-review lane.

## Arguments

None. The branch to rebase and the base to rebase onto arrive as free
text with the invocation; when either is unstated, confirm both with the
user before step 1 — never guess the base.

This skill takes no `key=value` arguments.
Unknown argument names are an error — stop and report them before starting.

## Workflow

1. **Fetch first — never trust local state.** Start from a clean
   working tree: `git status --porcelain` must be empty, since a rebase
   refuses to start over uncommitted changes and a stash hidden mid-plan
   is how a resolution gets silently dropped. Resolve the remote name
   rather than assuming `origin`: `git config branch.<branch>.remote` is
   the starting guess, not the answer — in a fork workflow the base lives
   on a different remote from the one this branch pushes to, so confirm
   with the user which remote carries the base whenever
   `git ls-remote --exit-code --heads <remote> <base>` does not find it.
   Do not derive the base from the branch's own upstream — that is this
   branch's remote copy (`<remote>/<branch>`), not what you rebase onto;
   the base is the one the user named. Fetch that remote, then rebase onto
   the base's remote-tracking ref (`<remote>/<base>`), never the bare local
   branch name: a fetch updates `<remote>/<base>` and leaves a local
   `<base>` exactly as stale as it was. In a worktree, confirm which
   checkout is active (`git worktree list`) and that the branch tracks the
   remote the user thinks it does (`git branch -vv`). State the resolved
   branch, base, and their current heads.
2. **Dry-run the merge before touching the working tree.** Enumerate
   both sides (`git log --oneline <remote>/<base>..HEAD` and
   `git log --oneline HEAD..<remote>/<base>`), then compute the overlap: files
   changed on both sides since the merge base. Run
   `git merge-tree --write-tree <remote>/<base> HEAD` (git 2.38+) and
   report the conflicts it finds. Treat that as a lower bound, not the
   whole list: it simulates one merge of the two endpoints, while a rebase
   replays your commits one at a time, so an intermediate commit can
   conflict where the endpoint merge is clean. Record the base head you
   planned against (`git rev-parse <remote>/<base>`); step 3 checks it
   again. Report the conflict surface before rebasing anything.
3. **Pre-plan every resolution.** For each conflicting file, decide the
   resolution before the rebase starts: which side wins, or what the
   merged shape is, and why. Present the complete resolution plan to the
   user and get their go-ahead. Approval takes as long as it takes, and
   the base moves while it does: re-fetch and compare
   `git rev-parse <remote>/<base>` against the head recorded in step 2
   before touching anything. A base that moved invalidates the plan the
   user approved — re-run step 2 and re-present it, rather than rebasing
   onto commits nobody looked at. Before the rebase rewrites anything, cut
   a recovery ref at the current head (`git branch backup/<branch>-<date>`)
   so the pre-rebase history stays reachable without digging through the
   reflog, and check for merge commits on your side
   (`git log --merges --oneline <remote>/<base>..HEAD`): a plain rebase
   flattens them away, so either rebase with `--rebase-merges` or agree
   with the user to linearize deliberately. Only then rebase, applying
   exactly the planned resolutions. If a conflict appears that the plan
   did not predict, `git rebase --abort` and re-plan — abort, not pause,
   because a paused rebase leaves HEAD detached partway through the
   replay, where step 2's `<remote>/<base>..HEAD` ranges describe a
   history that does not exist yet. Re-plan from what actually conflicted:
   the endpoint simulation already failed to predict it, so re-running it
   unchanged predicts the same nothing. Name the commit that conflicted
   (the rebase reports it) and diff that commit against the base for the
   files it touches, then fold the result into a revised plan and take it
   back to the user. Never improvise mid-rebase.
4. **Push only with approval, then verify the remote moved.** A rebased
   branch needs a force push, and this repository forbids unapproved
   force pushes: present the exact push command
   — `git push --force-with-lease=<remote-branch>:<observed-sha> <remote>
   <local-branch>:<remote-branch>`, pinning the lease to the SHA you
   actually inspected and naming both sides, since the lease is checked
   against the remote-side name and the two need not match — and wait for the
   user's explicit approval before running it. Never bare `--force`, and
   never bare `--force-with-lease`: the bare form checks against your
   remote-tracking ref, so any fetch since you last looked silently
   refreshes it and the lease passes over commits you never saw.
   After the push, prove it landed: `git fetch <remote>` — bare
   `git fetch` refreshes the default remote, which need not be this one —
   then compare
   `git rev-parse HEAD` with `git rev-parse <remote>/<remote-branch>` —
   the remote-side name, which need not match the local one — and they
   must be equal. The push command exiting zero is not the check; the remote
   ref is.

## Safety rules

- This skill plans and verifies; the user approves the push. Never
  force-push on this skill's own authority — the ritual reaching step 4
  is not approval, and invocation of the skill is not approval. The
  approval is the user's explicit yes to the exact command shown.
- Never use bare `--force`; `--force-with-lease` only, so a remote that
  moved underneath the plan rejects the push instead of being
  overwritten.
- Do not start the rebase until steps 1 and 2 are complete and the
  resolution plan from step 3 has the user's go-ahead.
- Stop on any surprise: an unplanned conflict, a lease rejection, or a
  base that moved after step 1 invalidates the plan — re-vet from
  step 2 rather than pressing on.
- Never discard work to make a conflict disappear: no `checkout
  --ours`/`--theirs` shortcuts that were not part of the agreed plan,
  and no dropping of commits the plan said to keep.
- Report state honestly: "pushed" only after the remote-ref check in
  step 4 passes; anything else is reported as its exact partial state.

## Final report

- **Ground truth** — branch, base, tracking remote, and both heads after
  the fetch;
- **Conflict surface** — commits on each side, overlapping files, and
  the dry-run conflict list from `git merge-tree`;
- **Resolution plan and outcome** — the pre-agreed resolution per file
  and whether the rebase applied it exactly, including any stop-and-
  re-vet cycles;
- **Push authorization** — the exact command shown, and the user's
  approval or its absence;
- **Remote verification** — the local and remote head hashes after the
  push, matching or not — or `not run` when the push was not approved;
- **Exact end state** — rebased and verified, rebased but unpushed,
  aborted, or untouched, in one sentence.

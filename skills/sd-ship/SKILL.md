---
name: sd-ship
description: Take committed work from a verified branch to a merged pull request, committing only enumerated paths.
disable-model-invocation: true
---

# sd-ship

`sd-ship` sequences the stages between "the work is done" and "the branch is
gone". Invocation is explicit approval for the in-scope commits, the PR-branch
push and the merge — and for nothing outside the paths you enumerate. It is
not approval to delete anything local: not a branch, not a worktree, not a
checkout. Step 8 reports those and leaves them standing.

## Where the review happens

The adversarial pass that gates the push runs on the machine, in step 2, where
it is `sd-review`, costs nothing but time, and answers to the *code, before
merge* row of the review table. The lane on the pull request is advisory and
this command asks for none of it: where GitHub requests a review of its own
when the pull request opens, those findings are read and dispositioned — fixed,
or recorded with the reason they stand — they block no merge, and `sd-ship`
requests neither a first round nor a second. `WORKFLOW.md`'s advisory section
is the rule; a review held in public one finding per round is the cost of
pushing a head no adversary has seen, which is what step 2 exists to prevent.

## The sequence

Eight steps. Before the first of them every acceptance criterion in the item's
`prd.md` is checked, with the actual check run and its output seen. A partial
pass is not a pass.

1. **Commit enumerated paths only** — the exact paths you can name.
2. **Local review.** `sd-review --scope branch --challenge` on the commits,
   before anything leaves the machine, and `sd-docs-lint` with all five rules
   enforced locally regardless of repo mode: shape · ready · decision shape ·
   spec index · PR link. The review is the development flow's *code, before
   merge* point, and its cap is that row's in
   `.claude/rules/sd-planning-adversarial-review.md`. Dispose every blocking
   finding here: fix it, or record the decision and the reason it stands. A fix
   is not dispositioned until it is committed and the lane has run again — the
   head that gets pushed must be the head the lane passed, not the one it
   failed.
3. **Push** the PR branch. This is the first irreversible act in the sequence
   and the thing that wakes every remote reader.
4. **Open the pull request** with a `Work:` line resolving to the item, 0
   unchecked boxes. The line is there when the item is, and absent when the
   change has none. There is no placeholder form of it.
5. **Wait for CI once.** One background wait, started once and left to run:
   `gh pr checks <N> --watch` in the background, not a foreground sleep and not
   a loop that re-asks every few seconds. The merge waits for CI and nothing
   else, so one wait is one answer — a red one ends the run rather than
   starting a second wait, and a fix to it re-enters at step 1.
6. **Merge**: `gh pr merge --squash --match-head-commit <the reviewed sha>
   -t "<title> (#N)" -b "<body>"`. The explicit `-t`/`-b` is the wip-eraser:
   `wip:` subjects must never reach main. `--match-head-commit` is what refuses
   a head that moved under the review; a merge carrying only a title and a body
   refuses nothing. Not `--delete-branch`, whose own help reads "Delete the
   local and remote branch after merge" — it does the local deletion this
   command forbids, which is exactly the kind of thing a flag name hides.
7. **Close the item on the default branch.** The closure is a trailer on that
   merge, never a commit or a pull request of its own. Every merge `sd-ship`
   makes carries `Item: <item>`, which ties the commit to the item and closes
   nothing; the one merge that delivers carries `Delivers: <item>` as well —
   `sd-ship --deliver`, or your own hand in the merge message. On that merge
   and on no other the item is closed, nothing is written into a file for it,
   and its directory stays. A delivery whose merge went out without the
   trailer is marked by the next merge message `sd-ship` writes in this
   repository, which carries `Closes: <item>` for it; nothing here pushes to
   the default branch to say so.
8. **`git fetch -p`, then report the local.** The remote branch is the
   repository's to remove: `delete_branch_on_merge` is on here, so the branch
   is already gone and this step deletes nothing. Fetching prunes its tracking
   ref, which is what makes the report accurate; pruning other dead tracking
   refs alongside it is the same operation doing its job, not a side effect to
   avoid. Advancing local `main` is left to the checkout that owns it — git
   refuses to update a branch checked out in another worktree, and this command
   supports concurrent worktrees. Then stop, and report: name the local branch
   and any worktree still holding it, and leave both standing. This step cannot
   tell which local refs are disposable — "did this run create it?" needs an
   ownership record a prose sequence does not keep, and `pwd` is a long-lived
   working checkout at least as often as it is a scratch worktree. Leave a
   worktree you did not create standing, whatever `git worktree list` says
   about it: one writer per checkout is the rule that makes concurrent sessions
   safe, and cleaning up after another one breaks it.

`sd-spec` is not in that sequence. It refreshes `docs/spec/**` on the PR
branch, and it runs when a change alters behaviour `docs/spec/` documents and
the operator asks for it.

## Flags

| Flag | Effect |
|---|---|
| `--pr N` | settle an existing PR rather than opening one |
| `--backlog` | loop over ready items (acceptance criteria present, no open BLOCKING) |
| `--author <entry>` | the registry entry that does the work in `--backlog`; `SD_AUTHOR` names it too, and the registry's resolved `author` role is the default |
| `--deliver` | this merge is the item's delivery: its message carries `Delivers:` |
| `--jobs N` | concurrent worktrees, default 1, **hard ceiling 3** |
| `--cap N` | items per invocation, default 3 |
| `--dry-run` | print selected items, worktree paths, resolved budget; exit |
| `--tier` | override the routed review tier |
| `--no-github` | local stages only |

## The autonomous lane (R10-D1)

`--backlog --author <entry>` runs each item as a non-interactive run of that
entry's start command, sandboxed to a workspace it may write, in its own fresh
worktree cut off `origin/main` at the item's `branch:`. The prompt is built
**from the item's own artifacts** — prd + design + implement + the `## Log`
tail, the same context a reattaching session reads — never a bespoke prompt
file. Green `sd-check` in the worktree opens a **draft** PR carrying the
`Work:` line; red, timeout, or rate-limit appends a `handoff:` entry to
`## Log` and leaves the worktree standing for inspection.

Its bounds are not negotiable:

- **It never merges and never marks a PR ready-for-review.** Not even in a repo
  with no branch protection at all — which is exactly the repo where the
  distinction matters. It produces reviewable drafts and nothing else.
  Settling is a human running `sd-ship --pr N`.
- **One writer per checkout.** Worktree isolation is the mechanism; `--jobs` is
  capped because the merge lane is serial regardless.
- **No silent death.** Every item gets an explicit wall-clock budget; exceeding
  it is a reported failure with a `## Log` entry, never a skipped item.
- **Rate-limited is not unavailable.** A quota stop ends the run cleanly with
  the remaining items untouched and named. No retry-thrash, no falling through
  to another provider.
- Runs here are subscription-only: the same preflight env scrub and
  subscription-auth assertion `sd-review` applies (R10-D4).
- The repo's `CLAUDE.local.md` marked block is prepended to the prompt this
  lane builds (R10-D7).

## Never

- **Never `git add -A`, `git add .`, or `git commit -a`.** Commit the exact
  paths you enumerated and can name. This is the single hardest constraint in
  this command.
- **No write after settled-green.** Once the PR is green and settled, sd-ship
  stops writing: no follow-up commit, no amend, no force-push, no "one more
  fix". A new finding is a new branch.
- **Never ask for a review on the pull request.** Not a first round, not a
  second, not one to close out a fix. Where the remote posts one unasked its
  findings are dispositioned and the merge is not held on them; where findings
  stop converging the answer is another local round, never another remote one.
- **Never push a head the local lane has not seen.** Step 2 is not optional
  because the change looks small. A blocking finding may be dispositioned as
  recorded-with-a-reason, never as unseen.
- **Never delete a branch to finish the job.** The remote branch is
  `delete_branch_on_merge`'s to remove, and no local branch, worktree or
  checkout is this command's — not the one this run is standing in, not one it
  believes it created. Report them by name and let the person who knows what is
  in them decide.
- **Never accept a repo path** (R10-D6) — the repository is the one enclosing
  cwd.
- **Never claim merge authority the config does not provide.** Merge authority
  is GitHub branch protection *where it is enforcing*; where it is not, say so
  (`sd-status` prints the gaps) rather than asserting the merge was gated.
- **Never weaken a test, skip a check, or bypass a guard to reach green.**
- **In `mode: guest`, never post reviews or labels** in the upstream repo.

## State of the tooling

There is no `bin/sd-ship` yet. Today the agent runs the stages: `sd-check`,
`sd-review`, `sd-docs-lint`, then `git` and `gh` by hand under the constraints
above. `--backlog`/`--author` is not implemented; do not simulate it with
ad-hoc worktree scripting.

Steps 2 and 7 are therefore conventions an agent follows rather than things a
runner enforces, and that is the honest description of them until there is one.
Step 2 has a mechanical assist available now: it is one command. Step 7 does
not. Its row is the library's, which the pack's installer provisions and which
is not installed here yet, so until it is, the word also sits in the file: a
delivered item's `prd.md` goes to `status: done` and drops its `branch:` field
on the default branch, in the next commit made here rather than in a pull
request of its own.

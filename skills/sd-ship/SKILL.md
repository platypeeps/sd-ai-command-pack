---
name: sd-ship
description: Take committed work from a verified branch to a merged pull request, committing only enumerated paths.
disable-model-invocation: true
---

# sd-ship

`sd-ship` sequences the stages between "the work is done" and "the branch is
gone". Invocation is explicit approval for the in-scope commits, the PR-branch
push, the configured review request, and the deletion of the **remote** branch
it merged — and for nothing outside the paths you enumerate. It is not approval
to delete anything local: not a branch, not a worktree, not a checkout. Step 11
reports those and leaves them standing.

## Where the review happens, and how much of it

Step 7 used to read "request Copilot once per head SHA, never again for the
same head". That is a rule about *duplicates* which reads as a mandate about
*frequency*, and on a branch that takes eighteen commits it authorises eighteen
reviews. Measured on this repository: **#718 drew 15 Copilot reviews across 18
commits**, #715 drew 10 across 11. Three things compounded to produce that — a
review requested per push, a reviewer running at Lite effort that returns
roughly one finding per pass, and no adversary between the work and the push,
so every finding arrived after the branch was already public.

The sequence below moves the unbounded lane onto the machine, where it is
`sd-review` and costs nothing but time, and bounds the lane that is not.
**#720 shipped under this shape: 3 Copilot rounds across 10 commits**, four
local rounds before the first push, and the two findings that would have been
most expensive — a subtitle claiming `mentions:@me` was nobody's to answer, and
its replacement pointing Jira rows at a GitHub URL — were both caught locally,
before anything was pushed.

## The sequence

1. **Verify acceptance.** Every acceptance criterion in the item's `prd.md` is
   checked, with the actual check run and its output seen. A partial pass is
   not a pass.
2. **`sd-spec`** — refresh `docs/spec/**` on the PR branch.
3. **`sd-docs-lint`** — all five rules enforced locally regardless of repo
   mode: shape · ready · decision shape · spec index · PR link.
4. **Commit enumerated paths only.**
5. **`sd-review --scope branch --challenge`** — the adversarial pass, on the
   commits, before anything leaves the machine. Dispose every blocking finding
   here: fix it, or record the decision and the reason it stands. A fix is not
   dispositioned until it is committed and the lane has run again — the head
   that gets pushed must be the head the lane passed, not the one it failed.
   A push is the first irreversible act in this sequence and the thing that wakes every
   remote reviewer, so a head that has not survived one adversary turns a
   review into a conversation held in public, one finding per round.
6. **Push** the PR branch.
7. **Open the PR** with a `Work:` line resolving to the item (0 unchecked
   boxes), or `Work: none - <reason>` under 800 lines with no sensitive path.
8. **Request Copilot when the PR is ready, and bound the rounds.** Once the PR
   is ready for review — not once per head — then **at most three** rounds
   that produce findings, every fix in a round batched into one push. Where
   review is automatic the unasked first review **is** round one, not a free
   extra: the budget counts findings arriving, never requests going out. The fix
   answering the third round still gets one verification pass: a budget that
   leaves the last remediation unreviewed is not a bound, it is a blind spot.
   Every finding on the final head is dispositioned — fixed, or recorded with
   the reason it stands — and an undispositioned blocking finding stops the
   merge whatever the budget says. If the verification pass finds something,
   stop and do not merge: the answer is a local round or a human, never a
   fourth remote one. Where the repository has automatic Copilot
   review enabled, the first round arrives without anyone asking — do not spend
   a request on it.
9. **Settle loop** — wait for checks and required reviews.
10. **Merge**: `gh pr merge --squash -t "<title> (#N)" -b "<body>"`. The
    explicit `-t`/`-b` is the wip-eraser: `wip:` subjects must never reach main.
11. **Clean up the remote, and report the local.** The remote branch is this
    step's only deletion, and it is deleted explicitly:
    `git push origin --delete <branch>`, or the equivalent
    `gh api --method DELETE repos/<owner>/<repo>/git/refs/heads/<branch>`.

    Not `gh pr merge --delete-branch`, whose own help reads "Delete the local
    and remote branch after merge" — it does the local deletion this command
    forbids two paragraphs above, which is exactly the kind of thing a flag
    name hides. Not `delete_branch_on_merge` either: that is a repository
    setting, it may be off, and a step that depends on it reports success
    having done nothing.

    Where it is *on*, the branch is already gone by the time this step runs and
    `git push origin --delete` exits non-zero with `remote ref does not exist`.
    That is this step succeeding, not failing: the goal is an absent branch, not
    a delete that did the absenting. Treat an already-absent ref as done — the
    branch listing below is what decides, and it cannot tell which command
    removed the branch, only that it is gone.

    Verify it against the branch *list*:
    `gh api repos/<owner>/<repo>/branches --paginate --jq '.[].name'` must
    succeed and must not contain the branch. Not `gh api .../branches/<branch>`
    answering 404 — GitHub returns a byte-identical 404 when the repository is
    unreachable or the credentials are wrong, so that check reads "cleaned up"
    and "cannot see the repository at all" the same way. The list call proves
    access by succeeding and answers deletion by omission, in one call —
    `--paginate` may spend several HTTP requests on a repository with many
    branches, but it is still one question asked once, not two checks whose
    answers can disagree.

    Locally: `git fetch -p`, and stop there. Fetching prunes the tracking ref
    for the branch just deleted, which is what makes the report below accurate;
    pruning other dead tracking refs alongside it is the same operation doing
    its job, not a side effect to avoid. Advancing local `main` is left to the
    checkout that owns it — git refuses to update a branch checked out in
    another worktree, and this command supports concurrent worktrees, so a step
    that fast-forwards `main` fails in the shape the rest of the document is
    written for.

    **Then stop, and report.** Name the local branch and any worktree still
    holding it, and leave both standing. This step does not delete local refs,
    and the reason is that it cannot tell which ones are disposable. "Did this
    run create it?" needs an ownership record a prose sequence does not keep,
    so a resumed or concurrent session cannot answer it. `pwd` is worse rather
    than better: it is a long-lived working checkout at least as often as it is
    a scratch worktree, and a step that deletes `pwd` deletes somebody's
    uncommitted work the first time someone ships from the repository they
    actually work in. Both readings were tried here and both were wrong, which
    is the argument for a runner that records the paths it created rather than
    prose that infers them.

    A squash merge is also why the local side cannot be settled locally: the
    squash commit is not the branch's commit, so `git branch -d` refuses every
    time, and `git diff origin/main..<branch>` is non-empty as soon as any
    other pull request lands — it compares whole trees, not this branch's
    contribution, so it reports "not merged" for a branch that merged perfectly.
    The merged state is GitHub's answer to give: `gh pr view N --json state`
    reading `MERGED`. Whoever deletes the local branch should read that first.

    Leave a worktree you did not create standing, whatever `git worktree list`
    says about it. One writer per checkout is the rule that makes concurrent
    sessions safe, and cleaning up after another one breaks it.

## Flags

| Flag | Effect |
|---|---|
| `--pr N` | settle an existing PR rather than opening one |
| `--backlog` | loop over ready items (acceptance criteria present, no open BLOCKING) |
| `--agent claude\|codex` | who does the work in `--backlog` (default `claude`) |
| `--jobs N` | concurrent worktrees, default 1, **hard ceiling 3** |
| `--cap N` | items per invocation, default 3 |
| `--dry-run` | print selected items, worktree paths, resolved budget; exit |
| `--tier` | override the routed review tier |
| `--no-github` | local stages only |

## The autonomous lane (R10-D1)

`--backlog --agent codex` runs each item as a non-interactive
`codex exec --sandbox workspace-write` in its own fresh worktree cut off
`origin/main` at the item's `branch:`. The prompt is built **from the item's
own artifacts** — prd + design + implement + the `## Log` tail, the same
context a reattaching session reads — never a bespoke prompt file. Green
`sd-check` in the worktree opens a **draft** PR carrying the `Work:` line; red,
timeout, or rate-limit appends a `handoff:` entry to `## Log` and leaves the
worktree standing for inspection.

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
- Codex runs here are subscription-only: the same `codex_preflight` env scrub
  and `auth_mode == chatgpt` assertion `sd-review` applies (R10-D4).
- The repo's `CLAUDE.local.md` marked block is prepended to the prompt this
  lane builds (R10-D7).

## Never

- **Never `git add -A`, `git add .`, or `git commit -a`.** Commit the exact
  paths you enumerated and can name. This is the single hardest constraint in
  this command.
- **No write after settled-green.** Once the PR is green and settled, sd-ship
  stops writing: no follow-up commit, no amend, no force-push, no "one more
  fix". A new finding is a new branch.
- **Never request Copilot twice for the same head, and never a fourth round of
  fixes.** Once per head is the duplicate rule; three rounds that produce
  findings is the budget, plus the single verification pass that closes the
  last of them. A fourth round of fixes is the signal that the findings are not
  converging, and the answer to that is a local round, not another remote one.
- **Never push a head the local lane has not seen.** Step 5 is not optional
  because the change looks small. A blocking finding may be dispositioned as
  recorded-with-a-reason, never as unseen.
- **Never leave a merged remote branch behind**, and never report it deleted
  without a successful branch listing that omits it. Not a 404 on the branch
  endpoint: an unreachable repository returns the same 404, so that reading
  cannot tell "gone" from "cannot see it".
- **Never delete a local branch, worktree or checkout.** Not the one this run
  is standing in, not one it believes it created. Report them by name and let
  the person who knows what is in them decide.
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
above. `--backlog`/`--agent codex` is not implemented; do not simulate it with
ad-hoc worktree scripting.

Steps 5, 8 and 11 are therefore conventions an agent follows rather than
things a runner enforces, and that is the honest description of them until
there is a runner. Two of the three have a mechanical assist available now:
step 5 is one command, and step 11's check is a successful
`gh api repos/<owner>/<repo>/branches --paginate` that does not list the
branch — not a 404 on the branch endpoint, which reads the same whether the
branch is gone or the repository is unreachable. Step 8's bound is the one with nothing behind it — a per-push
`PostToolUse` hook on the operator's machine asks for the review, so the
budget lives in whoever reads this. Across this repository's whole
organisation the ask is redundant on open: automatic Copilot review is
enabled, and GitHub requests the reviewer within a second or two of the pull
request opening. Measured, not assumed — sampled across `platypeeps`, this
repository and `system`, `loadsmith`, `anomaly-metric-creator`,
`sd-writing-pack` and `people-profiles` among them, the first
`review_requested` event landed 0-2s after `created_at` every time. That
request is attributed to the pull request author, so in the timeline it is
indistinguishable from a human one and only the timing separates them; read
without the timing, #718 looks like fifteen deliberate requests rather than one
automatic request and fourteen from the hook.

The hook's exit is gated on the remote's owner, because no file can derive
this: automatic review is an organisation or repository setting with no
representation in the tree. An earlier cut keyed it on `.github/sd-review.json`
and so covered a single repository, which is both too narrow and the wrong
question — that file declares local reviewer tiers and says nothing about
Copilot. The owner list is observed, not derived; before adding one, check that
its pull requests really do draw a review unasked, because a wrong entry
silently costs reviews instead of failing loudly.

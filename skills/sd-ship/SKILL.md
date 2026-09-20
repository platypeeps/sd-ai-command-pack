---
name: sd-ship
description: Take committed work from a verified branch to a merged pull request, committing only enumerated paths.
disable-model-invocation: true
---

# sd-ship

Deliver only the enumerated scope.
Invocation authorizes its scoped commits, branch push, and merge, subject to execution permissions and existing gates.
Invocation alone authorizes no local branch, worktree, or checkout deletion.
Use STE-Concise; report delivery state, decisive checks, blockers, and retained worktrees.

## Standing permission

Read `sd config get sd.merge_authorization` before relying on standing permission.
`controlled` permits active, in-scope PR delivery in user-controlled repositories, unless they explicitly say wait.
`ask`, or no setting, requires task-specific permission.
Installation grants no permission.
Shared contributors do not revoke permission; existing ownership, protection, review, and CI gates still apply.
A refusal stops execution.
Do not change gates to obtain a merge.
An existing manual operator path needs separate authorization; a gate refusal does not grant it.
Standing permission starts no background work and does not enable runner `merge: auto`.

Read `sd config get sd.external_reviews` separately.
Apply the sd-ai-command-pack checkout's `.claude/rules/sd-operator-defaults.md`.
Inspect the complete reviewer chain before expensive checks.
Do not substitute an unrequested provider.

## The sequence

Nine steps coordinate the executable operations below.
First verify the actual scope and inspect its check output.
A slice may ship with later item criteria open.
Only `--deliver` claims the whole item; every acceptance criterion then needs evidence.
Small changes need no placeholder work item.

1. **Commit enumerated paths only.**
   In the pack, system repository, and writing repository, follow `WORKFLOW.md` for the `Needed-by:` trailer.
   Its forms are `Needed-by: <item id>`, `Needed-by: cost`, `Needed-by: efficiency`, and `Needed-by: visibility`.
   A present trailer produces no warning.
   A missing trailer warns; the sequence continues with the commit.
2. **Review locally before publication.**
   Use `sd-review --scope branch --challenge` for the *code, before merge* point.
   Read its cap on that row in the sd-ai-command-pack checkout's `.claude/rules/sd-planning-adversarial-review.md`.
   Run `sd-docs-lint` against the built PR body.
   With no work root, use `--body-only`; do not create planning files to satisfy tree checks.
   Dispose every blocker.
   Commit fixes and verify the diff since the preceding reviewed head, including current source for prior findings.
   An incomplete review needs full-branch coverage.
   An unchanged complete review can use explicit evidence-backed acceptance; a reason alone grants no clearance.
3. **Push only the cleared head.**
   Push refuses unless the current sha matches the head the local review cleared.
   A changed head returns to review.
   The remote merge also checks the expected head.
4. **Open or reconcile the pull request.**
   Include `Work:` only when an associated item exists.
   The line is absent otherwise; it is not a completion claim.
   After exact-head confirmation, request Copilot when repository policy selects the final tier.
   `--copilot-review request` permits one explicit request.
   `--copilot-review skip` needs explicit task direction and suppresses automatic selection.
   Suppression persists for the task until a later explicit request replaces it.
   Automatic selection applies only to full-owned, non-draft pull requests.
   Never repeat an automatic request on later pushes.
5. **Wait for CI once.**
   Start `gh pr checks <N> --watch --fail-fast` once in the background, or use the adapter's bounded watch.
   Do not start both.
   A failed check ends the run; a fix returns to step 1.
6. **Check dependent pull requests.**
   Run `gh pr list --base <this branch> --state open` before merging.
   A failed query or non-empty answer stops the run.
   The executable merge does not perform this query.
   Retargeting metadata alone leaves inherited commits in child diffs.
   Repair requires `git rebase --onto <base> <this branch> <child branch>`, an authorized force-push, and renewed review.
   Stop and obtain permission before that history rewrite.
7. **Merge through the authorized adapter.**
   It uses `gh pr merge --squash --match-head-commit <the reviewed sha> -t "<title> (#N)" -b "<body>"`.
   Keep the explicit title and body; exclude `wip:` subjects from main.
   Put contiguous trailers in the body's final paragraph.
   Never use the CLI's branch-deletion option.
   Missing protection remains a refusal; this workflow adds no exception.
8. **Record verified delivery.**
   An associated merge carries `Item:`; only whole-item delivery adds `Delivers:`.
   Record the row only after the remote confirms the merge.
   Read `skills/sd-ship/references/delivery.md` in the sd-ai-command-pack checkout before delivery, cancellation, or completion reporting.
   A slice leaves its item open.
   No-item changes create no row or placeholder trailer.
9. **Complete post-merge closeout.**
   After every confirmed in-scope merge, read `skills/sd-ship/references/post-merge-closeout.md` in the sd-ai-command-pack checkout.
   Run `git fetch -p`; repository `delete_branch_on_merge` owns remote branch removal.
   Review remaining findings and inventory refs, branches, stashes, and worktrees.
   Retain local branches, stashes, and worktrees until one exact target list receives separate approval with verified recovery evidence.
   Do not move another checkout's main branch.
   Report the branch, worktree, merge, and installation state separately.

`sd-spec` is outside this sequence.
Use it on the PR branch when documented behavior changes and the operator requests it.

## Executable interface

The Git repository enclosing cwd determines the target.
Use the matching installed `sd_db` library.
`--database PATH` selects an explicitly provisioned receipt/provider database; otherwise use operator HOME.
The runner uses its provisioned interpreter.

For itemless work, reuse its stable review ID.
For genuinely new work, allocate it with `sd-ship review --no-item --create-record --assert-new-work --json`.
Use `--no-item --review-id ID` instead of `--item ID` for prepare, merge, observe, and reconcile.
Prepare reuses complete exact-head review evidence and acceptance; otherwise it follows the same review gates.
Itemless merge requires `--manual` and `--expected-head SHA`.
Itemless publication rejects commit flags, runner authority, and whole-item delivery flags.
It creates no task row, `Work:` line, `Item:`, or `Delivers:` trailer.
Never allocate another review ID to reset spent passes or discard history.

- `sd-ship prepare --item ID --json` reviews, pushes, and opens or reconciles the PR.
  It returns `ready_to_send` and never merges.
  `--title` and `--body-file` supply the PR description.
  Reprepare preserves the saved description and delivery claim.
- Optional commits require `--path FILE` for each file, `--message-file FILE`, and `--author ENTRY`.
  Directories and a pre-populated index are invalid.
  Actual provider/vendor attribution belongs on the commit.
- `sd-ship merge --item ID --expected-head SHA --manual --json` performs an explicit operator merge.
- `sd-ship merge --item ID --expected-head SHA --run RUN-ID --json` requires its exclusive runner lease and matching clone.
  Matching item/head and repository `merge: auto` are also required.
  An author assignment cannot use this authority.
- Both merge forms require fresh sole-operator ownership, enforcing protection, current default branch, exact reviewed head, and passing required checks.
  GitHub's merge rules must also pass.
  A refusal returns `manualRequired: true`; it changes no protection and requests no reviewer.
- `--watch --wait-seconds 900` starts one bounded fail-fast CI watcher.
  Its persisted start prevents another automatic watch on rerun.
- `sd-ship observe --item ID --json` reads receipt and remote state without changing files, refs, or database.
- `sd-ship reconcile --item ID --json` fetches merge evidence in an owned clone.
  Observation alone does not establish ancestry.
  Reconciliation removes no branch, worktree, or clone.

Add `--reuse-check` to prepare or standalone review only when explicitly reusing eligible deterministic-check evidence.
Before opting in, read `skills/sd-check/references/check-receipts.md` in the sd-ai-command-pack checkout.
Reuse requires complete local-only dependencies and unchanged before-and-after identity; legacy receipts rerun.
This flag does not reuse incomplete reviews or bypass source, policy, or receipt validation.

Add `--provider NAME` to prepare or standalone review only for an explicitly requested reviewer.
The selection applies to this invocation, without fallback or changes to the automatic order.
Inspect `sd-review --explain --json` with the same scope, database, history inputs, review modifiers, and `--provider NAME`.
Existing independence, capability, availability, consent, and spending checks still apply.
A conflicting selection cannot replace a completed receipt or grant another pass.
Omitting the flag preserves automatic selection for new dispatches and permits reuse of existing valid evidence.
Results report `review_selection.requested_provider` and the actual `reviewed_by` list from the retained report.
Read the recovery reference before retries, fix verification, or additional reviews with an explicit provider.

`--copilot-review auto` is the prepare default.
It reads `copilot_review.automatic_deep` through the retained local review report.
An absent policy defaults to `false` and keeps Copilot explicit-only.
Each request binds one exact head and persists before merge.
Merge waits for a submitted review, stable review material, and verified finding dispositions.
An automatic request occurs once per pull request.
Later pushes still require a local review for the exact head and exact-head CI.
The completed Copilot review must cover the exact merge head.
Use `--copilot-review request` when a later push makes the automatic review stale.
The adapter permits at most three Copilot requests per pull request.
At that cap, use existing history or a separately authorized manual abandonment.
Use `--abandon-copilot-review REASON` only during merge.
It stops waiting for the request basis on the current pull request and reviewed head.
The basis contains exact-head receipts when present.
Otherwise, it contains the latest receipt for that pull request.
No local receipt means there is nothing to abandon, and the command refuses.
It preserves request history and records a separate abandonment.
Only submitted, non-pending reviews mark matching request heads complete.
Published Copilot findings still require disposition.

The additive `workflow` object reports `schema_version`, `phase`, `state`, `blocker`, and `next_action`.
States are `success`, `retryable_failure`, `operator_decision`, and `policy_block`.
Blockers identify `code`, `boundary`, `retryable`, and `approval_required`.
Existing result fields and exit meanings remain authoritative; the new object does not grant permission.

Receipts bind repository, branch, item or review identity, exact head, tools, policy, and review history.
`--expected-head` compares evidence; it does not replace evidence.
There is no `--reviewed-head` override.
An interrupted review retains its reserved pass.

## What a rerun reconciles

Resume the existing receipt rather than starting another review or PR.
A lost create or merge response requires reconciliation with the same remote operation.
An empty search after uncertain creation does not authorize another PR.
A merged PR is evidence to inspect, not permission to merge again.
Before interruption recovery, read `skills/sd-ship/references/recovery.md` in the sd-ai-command-pack checkout.
Read its review-retry section only when a review stopped or exhausted its automatic allowance.

## Evidence-backed disposition acceptance

Use acceptance only for a complete review of the exact clean head with passing deterministic checks.
It cannot waive missing depth, incomplete transport, failed checks, or changed source.
Fixes still require verification on their new head.
Before proposing or accepting dispositions, read `skills/sd-ship/references/adjudication.md` in the sd-ai-command-pack checkout.
Standing merge permission does not approve individual findings.
Do not invent acceptance for the operator.

## Remote findings

Complete local review before any Copilot request.
Request automatically only through the configured `deep` tier.
Honor repository restrictions and avoid repeated automatic requests after later pushes.
Read and disposition findings posted independently.

After push, the adapter can record `fixed <commit>` for findings supported by new changes to the named file.
Unchanged files remain unanswered; existing acknowledgements remain intact.
A person supplies `dismissed <reason>`.
Acknowledgement failures produce warnings, not review clearance.

## Never

- Never `git add -A`, `git add .`, or `git commit -a`.
- Never push a head the local lane has not seen.
- Never weaken checks, permissions, review depth, or ownership/protection gates to reach green.
- Never treat a written reason as executable clearance.
- Never delete local branches, worktrees, or checkouts as an implicit shipping step.
  Routine closeout inventories retained work; a separate, explicitly approved cleanup may remove only its enumerated targets.
- Never accept a repository path; cwd determines the checkout (R10-D6).
- Never post reviews or labels in a guest upstream repository.
- Make no further change after settled-green.
  A new finding requires a new branch, not an amend or force-push.

A remote mode reduction records a reason once per item and remote.
That note grants no permission; the push or merge still stops.
Queue execution, process ownership, and clone retention belong to `sd runner`.
Refresh commands and the matching shared library together before claiming installed behavior.

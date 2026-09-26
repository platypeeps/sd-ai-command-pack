# Post-merge closeout

Run this after every confirmed in-scope merge.
Routine closeout includes review findings and local inventory, even when the user requested no deletion.
Confirm the exact PR, reviewed head, and remote merge evidence first.
A closed PR is not necessarily merged.

## Review findings

Read every inline thread and review-body finding, including all result pages and late Copilot comments.
Use `sd-review-ack --pr N --json` to inspect the explicit PR, including a merged PR.
Use `--check` to identify findings without local acknowledgements.
Local acknowledgement does not post a response or resolve a GitHub thread.

Apply the `sd-receive-review` disposition procedure to each finding.
That skill remains local-only.
Choose one supported result:

- Fixed: name the landed commit and decisive verification evidence.
- Rebutted or already addressed: state the reason and supporting code or test evidence.
- Carried forward: verify a durable successor, its scope, owner, and acceptance condition.
  Link it where the reviewer can access it.

Record local acknowledgements through `--ack ID` with `--fixed COMMIT`, `--dismiss REASON`, or `--carried ITEM`.
Answer a cosmetic finding with `--dismiss 'cosmetic: ...'`; never `--carried`.
Confirm that the chosen evidence and destination satisfy the command's checks.
A reason string alone does not establish a valid disposition.

Authorized shipping closeout owns remote replies and resolution.
Post the concise disposition and its evidence or verified successor link.
Then resolve that eligible inline thread and read back the resulting state.
Do not repeat an existing evidenced reply or resolved disposition.
Keep uncertain, unfixed, or untraceable findings open.
Do not dismiss formal reviews, delete comments, or request another Copilot review.

Create follow-ups only within existing authorization.
For an authorized local follow-up, use `sd task add TITLE --kind followup --here --body BODY --json`.
Read back its identity and scope before acknowledging a carried finding.
Creating an external issue needs authorization for that destination.
If that authorization is absent, record the follow-up locally and disclose its limited visibility.
Do not present a local path as a public successor link.
If no accessible successor or accepted disposition exists, leave the thread open.

## Local inventory

Fetch and prune remote-tracking refs before comparing local state.
Inventory exact branch names and tips, worktree paths and HEADs, dirty state, locks, and stash selectors with full object IDs.
Inspect tracked and untracked stash contents locally; do not dump sensitive contents into reports.
Check active processes, ownership, installed command links, and shared runtime dependencies.
Report retained work and cleanup candidates separately.
Stash selectors share the repository's common state across worktrees.
If ownership is uncertain or concurrent stash activity occurs, retain the stash.

Retain dirty, active, locked, unrelated, primary, and serving worktrees.
Retain shared virtualenv/cache targets and any work whose ownership is uncertain.
Retain branches or stashes with unique or unverified contents.
Neither age nor `git branch --merged` alone proves that a branch is redundant after a squash merge.
Compare the actual delivered content and record recovery evidence.

## Approved cleanup only

Preserve each selected stash by its full object ID, including index and untracked parents, before proposing its deletion.
A bundle of `refs/stash` alone can omit older reflog entries.
Verify recovery of each selected object and its required parents.
If recovery is uncertain, retain the stash.
Git bundles do not preserve uncommitted files; preserve those separately when needed.

Propose one consolidated exact target list with each target's reason, current identity, and verified recovery path.
Obtain explicit approval for that list before deleting branches, worktrees, or stashes.
Without approval, retain them and report that state; retention is not a failure.

Verify backups by read-back before any approved irreversible action.
Re-read each target's identity, HEAD, dirty state, and ownership immediately before the approved action.
Drift or new activity stops that action.
Identify a stash by its full object ID and confirm its current selector before any approved drop.

Never use `git stash clear`, broad deletion patterns, or forced worktree removal to finish closeout.
Do not rename or reset shared stash state to stabilize a selector.
Do not infer deletion permission from a clean checkout or successful merge.
After approved cleanup, verify the exact targets and report what was removed, retained, and recoverable.

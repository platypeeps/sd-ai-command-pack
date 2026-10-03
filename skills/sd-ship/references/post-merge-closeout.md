# Post-merge closeout

Run this after every confirmed in-scope merge.
Routine closeout includes review findings, local inventory and automatic cleanup of safe targets.
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
Report retained work and cleanup targets separately.
Stash selectors share the repository's common state across worktrees.
If ownership is uncertain or concurrent stash activity occurs, retain the stash.

Retain dirty, active, locked, unrelated, primary, and serving worktrees; remove only stale ones, as below.
Retain shared virtualenv/cache targets and any work whose ownership is uncertain.
Retain branches or stashes with unique or unverified contents.
Neither age nor `git branch --merged` alone proves that a branch is redundant after a squash merge.
Compare the actual delivered content and record recovery evidence.

## Automatic cleanup

The operator authorized this cleanup on 2026-10-02; it needs no further approval.
After a confirmed merge, remove the merged PR's local branch, remote branch, stashes, refs and stale worktrees when each one is safe.
Confirm the merge from the `sd-ship merge` receipt or GitHub's merged state.

A target is safe only when every condition holds:

- It belongs to this PR: its branch is the PR's head branch, or a stash was made on that branch.
- It holds nothing the merge did not deliver.
  A branch tip is the merged PR head or an ancestor of it.
  A stash's working tree, its index parent and its untracked parent each match the merge commit, path by path.
  Staged work can differ from the working tree, so a match on the working tree alone is not enough.
- No worktree has it checked out, no process uses it, and no lock holds it.
- It is not a default branch, a protected branch, or the head or base of another open PR.
- Its identity did not change since the inventory; re-read it immediately before removal.

Keep the target and report it when any condition fails or cannot be checked.
Retention is not a failure.

Write a recovery record before each removal: an `sd task note` on the item.
Name the target and its full object ID; for a stash, also name its index and untracked parents.
Locally, `git branch <name> <id>` or `git stash store <id>` restores a removed target until garbage collection.
That window is short, which is why every condition above must hold: the merge must already carry the content.
Then remove the targets one by one:

- Local branch: `git branch -d`, or `git branch -D` only for a tip the PR head contains.
- Remote branch: `git push --force-with-lease=<branch>:<recorded id> origin --delete <branch>`, only when `delete_branch_on_merge` left it.
  The lease makes the delete refuse when the remote tip moved after the re-read.
- Stash: confirm the selector still names the recorded object ID, then `git stash drop <selector>`.
- Other refs that point only at the PR's delivered commits: `git update-ref -d <ref> <recorded id>`.

Never use `git stash clear`, broad deletion patterns, a force push that overwrites a branch, or forced worktree removal.
Do not rename or reset shared stash state to stabilize a selector.
Report what was removed with its recovery ID, and what was kept and why.

## Stale worktrees

The same authorization covers the merged PR's stale worktrees.
A worktree is stale and safe to remove only when every condition holds:

- Its HEAD is the merged PR's branch or a detached commit that the PR head contains.
- `git status --porcelain` is empty: no tracked change and no untracked file.
- Its ignored files are only build output or caches, such as `target/`, `node_modules/`, `.venv/` or `__pycache__/`.
- No process runs in it or holds a file in it, and `git worktree list` shows no lock.
- It is not a primary checkout, not under `~/repos`, and no service, LaunchAgent or installed link points into it.

Record its path and HEAD in an `sd task note` first.
Remove it with `git worktree remove <path>`, never forced; then remove its branch as above.
Run `git worktree prune` for entries whose folder is already gone; it changes only Git's metadata.
Keep a worktree that fails any condition, and report the reason.

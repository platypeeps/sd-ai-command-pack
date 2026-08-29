---
title: "PARKED: Add sd-submit-pack-task to file or revise a pack task without disturbing a live session"
status: planning
created: 2026-08-07
---
# PARKED: Add sd-submit-pack-task to file or revise a pack task without disturbing a live session

## Goal

One command that proposes a change to this repository's Trellis backlog end to
end — its own worktree, branch, task directory edit, commit, push, and pull
request — without touching the checkout the caller is sitting in. The proposed
change is either a **new task** or a **revision to an existing one**; both modes
share the whole mechanism and differ only in what they write.

## Naming

The command is `sd-submit-pack-task`, and it covers both modes. A rename to
`sd-propose-pack-task` was considered on the grounds that "submit" reads as
filing something new, and rejected: the two modes are one flow with one set of
isolation and publishing rules, and splitting the name from the behaviour buys
less than the churn costs. What the update mode needs is documentation and an
explicit mode argument, not a different word on the front. Both modes stop at
an open PR and neither one lands the change.

## Problem

Changing a task today mutates whatever working copy is in front of you. The
documented flow is `task.py create` or an editor, then commit, push, open a PR —
every step against the current checkout, on the current branch, in the current
working tree.

That is fine alone and wrong the moment a second session is running, which for
this repository is routine. Concrete instances observed while filing the four
defect tasks in #354 and shipping #352, #353, and #355:

- **The checkout is occupied.** A concurrent session held
  `fix/pack-helper-defaults-and-guards` in the primary working copy for hours.
  Changing anything there meant either switching its branch or committing onto
  it.
- **Merging is not a substitute.** Every filing branch eventually needs `main`
  merged in. Doing that in the shared checkout moves a branch the other session
  is mid-edit on.
- **Worktrees are not free either.** They need setup, they hold branches
  exclusively (`git worktree add` refuses a branch already checked out), and
  they are easy to leave behind. Four were created and removed by hand while
  shipping the PRs above.
- **The per-working-copy files do not come along.** `.trellis/.developer` is
  gitignored, so a fresh worktree fails immediately:

  ```text
  Error: Developer not initialized.
  Run: python3 ./.trellis/scripts/init_developer.py <your-name>
  ```

  It had to be copied by hand into three separate worktrees in one session.
  `08-07-provenance-concurrent-session-collision` files the sibling case for
  `provenance.json`.

**Revising an existing task hits every one of those, plus its own.** This is not
a hypothetical extension of the filing case; it is the more common operation and
it was exercised twice while this very task was being written:

- Review on PR #361 found that `task.py create` had seeded `base_branch` from
  the filing branch. Fixing it meant editing an already-committed task from
  inside the same borrowed worktree — the update path, run by hand.
- This PRD is itself being revised right now, by hand, in a scratchpad worktree,
  for exactly the reason the command exists.

Update mode also carries risks filing does not, and they are the reason it needs
a command rather than a habit:

- **The base is stale by construction.** The run sees committed state on the
  default branch. Another session may hold uncommitted edits to the same task,
  or an open PR that already rewrites it. Nothing in the working copy reveals
  either.
- **Silent scope creep is easy.** Hand-editing a task directory invites fixing
  an unrelated field "while you are in there" — a stray `base_branch`
  correction, a status nudge — none of which the PR title announces.
- **Live tasks have owners.** An `in_progress` task is being implemented by
  someone right now. A PR rewriting its plan mid-flight is precisely the
  collision this command exists to prevent.

The workaround is known and repeatable, which is exactly the argument for
making it a command instead of a habit.

## Requirements

### Mode

1. The command has two explicit modes: **create** a new task, and **update** an
   existing one. The mode is stated by the caller, never inferred from whether
   a slug happens to resolve. Inference fails badly in both directions — a
   mistyped slug would silently create a near-duplicate task, and a colliding
   slug would silently overwrite someone else's work.
2. Create mode refuses when the target slug already exists on the resolved
   default branch, naming the existing task directory.
3. Update mode refuses when the target does not exist on the resolved default
   branch. If the task exists only on an unmerged branch, the error names that
   branch rather than falling back to creating a second copy.
4. Update mode refuses an archived task under `.trellis/tasks/archive/`.
   Reopening archived work is a lifecycle decision, not an edit.
5. Update mode refuses a task whose status is `in_progress`, naming the status
   and the branch recorded in `task.json`, unless the caller passes an explicit
   override. That task has a live owner; the default must be to leave it alone.

### Isolation

6. The command performs every mutation in a private worktree created for the
   run. The caller's checkout — branch, HEAD, index, working tree, stash — is
   unchanged at exit, on the success path and on every failure path.
7. The worktree is created from the resolved remote default branch
   (`origin/main`), never from the caller's current branch or local `main`,
   which may be ahead, behind, or diverged. Local `main` sitting one unpushed
   commit ahead of `origin/main` was the live state while this task was filed.
8. The run seeds the per-working-copy files a fresh worktree lacks, starting
   with `.trellis/.developer`, from the caller's checkout. A missing source file
   is a clear precondition error naming `init_developer.py`, not a stack trace.
9. The worktree is removed when the run completes. A run that fails partway
   leaves it in place and reports its path, because a half-written task
   directory is evidence, not garbage.

### Create mode

10. Arguments cover what `task.py create` needs — title, slug, priority,
    description, optional parent and package — plus the PRD body, which is the
    actual content and must come from a file or stdin rather than a shell
    argument.
11. The command runs `task.py create --no-start`. It files a task; it does not
    activate one. Activating a task in a worktree that is about to be deleted
    would leave the caller's session pointing at a directory that no longer
    exists.
12. `--assignee` is required by `task.py create` in this repository — omitting
    it fails with `No developer set`. The command resolves it from the developer
    file rather than making the caller repeat it.
13. Manifests are written with real entries or left for the caller to fill
    deliberately. The `_example` placeholder line must not survive into a
    submitted task: it is a documented review finding, and the scaffold is
    present in a large fraction of existing tasks precisely because nobody
    removes it.
14. `base_branch` is corrected to the default branch before the commit.
    `task.py create` seeds it from the current branch, so filing from a worktree
    on a filing branch records that branch as the PR target — wrong, and caught
    by review on both PRs that filed these two tasks. Because this command always
    runs on a purpose-made branch, it would reproduce the defect on every single
    invocation unless it calls `task.py set-base-branch <dir> <default>`. The
    underlying defect is `08-06-task-create-base-branch-seed`; this command must
    not wait for it.

### Update mode

15. The editable surface is the task's artifact files — `prd.md`, `design.md`,
    `implement.md`, `implement.jsonl`, `check.jsonl`. Each is supplied from a
    file or stdin, same as the create-mode PRD body. An artifact the caller does
    not supply is left byte-identical.
16. A supplied artifact replaces the file whole. The command does not patch,
    merge, or append by inference — a prose-level partial edit cannot be
    verified, and a wrong one is invisible in review because the diff looks
    intentional. Creating an artifact the task does not yet have is the same
    operation as replacing one it does.
17. Title and description changes are separate explicit arguments, because they
    live in `task.json` rather than in an artifact. When the title changes, the
    `prd.md` H1 and the `task.json` title are updated together — they are
    parallel copies today and drift silently.
18. Update mode changes nothing else in `task.json`. Lifecycle and linkage
    fields — `status`, `branch`, `commit`, `pr_url`, `completedAt`, `subtasks`,
    `children`, `parent` — are left exactly as found. In particular it does not
    "helpfully" correct an existing task's `base_branch`: requirement 14 applies
    to tasks this command creates, and silently retargeting someone else's PR
    base is the scope creep this requirement exists to forbid.
19. Renaming a task — its slug or directory — is not an update. It is a
    directory move plus an identity rewrite with different failure modes, and it
    is out of scope.
20. Before writing, the command reports the state it is editing against: the
    base commit, the commit that last touched the task directory, and any open
    pull request whose files include that directory. An existing open PR is
    reported, not silently blocked — two independent revisions to one task are
    legitimate — but the caller must be told before the second one is opened.

### Publishing

21. One commit, scoped to the single task directory and nothing else. The
    command never sweeps unrelated dirty paths — there should be none in a fresh
    worktree, and if there are, that is an error.
22. A run that produces no change to the task directory is an error, not an
    empty PR. In update mode, supplying an artifact byte-identical to the one
    already committed is the ordinary way to reach this state.
23. Push creates the branch on the remote. Never a force push, never a push to
    the default branch. Branch names are deterministic and distinguish the
    modes — a filing branch and a revision branch for the same slug must not
    collide.
24. A pull request is opened against the default branch with a body derived
    from the change. `mcp__github__create_pull_request` returns
    `403 Resource not accessible by personal access token` on this repository,
    so PR creation must go through `gh pr create`. In update mode the body names
    which artifacts changed, so a reviewer sees the shape of the edit before
    opening the diff.
25. The command stops at the open PR. It does not review, merge, archive, or
    run housekeeping — `sd-housekeeping` is the only merge authority, and a
    proposed task change is not a merged one.

### Reporting

26. The final report gives the mode, the task directory, branch, commit, PR
    number and URL, the artifacts written, and an explicit statement that the
    caller's checkout was not modified.
27. Every failure names the stage that failed and what remains on disk.

## Acceptance criteria

Shared:

- Running the command from a checkout with a dirty tree on a feature branch
  leaves that branch, HEAD, and working tree byte-identical, verified before and
  after.
- Running it twice concurrently produces two independent branches and PRs with
  no interference and no worktree collision.
- The branch is based on `origin/main` even when local `main` is ahead.
- A run against a checkout with no `.trellis/.developer` fails before creating
  anything, naming `init_developer.py`.
- The command never merges, and never pushes to the default branch.
- The commit touches exactly one task directory and no other path.
- A run that would produce no change exits with an error and opens no PR.
- The worktree is gone after a successful run and present after a failed one,
  with its path reported.

Create mode:

- The submitted task contains no `_example` placeholder line.
- The submitted task's `base_branch` is the default branch, never the filing
  branch, verified by reading `task.json` after a run.
- A slug that already exists is refused, naming the existing directory.

Update mode:

- Supplying only `prd.md` leaves every other file in the task directory
  byte-identical, verified by diffing the committed tree against the base.
- `task.json` differs from its base only in the fields the caller explicitly
  asked to change; `status`, `branch`, `commit`, `pr_url`, `completedAt`,
  `subtasks`, `children`, `parent`, and `base_branch` are unchanged.
- A title change updates both the `task.json` title and the `prd.md` H1.
- A task that exists only on an unmerged branch is refused with that branch
  named, and no task is created.
- An archived task is refused.
- An `in_progress` task is refused without the override, and the message names
  the status and the recorded branch.
- An existing open PR touching the same task directory is reported before the
  new PR is opened.

## Open decisions

**Where the logic lives.** A skill under `.agents/skills/sd-submit-pack-task/`
with a shipped helper script is the shape the pack uses for everything with real
control flow. A skill alone would put a multi-step Git sequence into prose,
which is what this task exists to stop. Recommendation: helper script plus a
thin skill, matching `sd-status` and `sd-housekeeping`.

**Scope of "pack task".** As named, this proposes changes to *this* repository's
backlog. The same problem exists for any Trellis repo the pack installs into,
and the requirements above are not repository-specific. Recommendation: build it
for this repository first and keep the argument surface free of anything that
would block generalizing later.

## Surface footprint

A new `sd-*` command is not one file. `sd-status` is registered across:

```text
manifest.json                        .sd-ai-command-pack/manifest.json
.agents/skills/sd-status/SKILL.md    .claude/skills/sd-status/SKILL.md
templates/.agents/skills/...         .claude/commands/sd/status.md
.gemini/commands/sd/status.toml      .opencode/commands/sd-status.md
.agents/skills/sd-help/references/command-catalog.md   (+ .claude, + templates)
README.md                            docs/SD_AI_COMMAND_PACK.md
```

There is no generator for these; `scripts/sd-ai-command-pack-surface-check.py`
verifies them after they are authored by hand. The implementation plan must
enumerate the full set from the repository rather than from this list, which is
a snapshot and will drift.

Shipping a new payload also trips the release version gate: the manifest version
must bump with a matching CHANGELOG top heading, and
`docs/fleet/candidate-validation.json` must be regenerated.

## Out of scope

- Reviewing, merging, or archiving the proposed change.
- Renaming or moving an existing task (requirement 19).
- Task lifecycle transitions: `start`, `finish`, `archive`, and status edits are
  not artifact edits and belong to their existing owners.
- Proposing changes to repositories other than this one, beyond not foreclosing
  it.
- Replacing `task.py create`. This command wraps it.
- The gitignored-file collision class itself, owned by
  `08-07-provenance-concurrent-session-collision`. This task only seeds what it
  needs and reports clearly when it cannot.

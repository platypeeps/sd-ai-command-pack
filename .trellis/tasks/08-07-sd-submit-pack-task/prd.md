# Add sd-submit-pack-task to file a pack task without disturbing a live session

## Goal

One command that files a new Trellis task into this repository end to end — its
own worktree, branch, task directory, commit, push, and pull request — without
touching the checkout the caller is sitting in.

## Problem

Filing a task today mutates whatever working copy is in front of you. The
documented flow is `task.py create`, write `prd.md`, fill the manifests, commit,
push, open a PR — every step against the current checkout, on the current
branch, in the current working tree.

That is fine alone and wrong the moment a second session is running, which for
this repository is routine. Concrete instances observed while filing the four
defect tasks in #354 and shipping #352, #353, and #355:

- **The checkout is occupied.** A concurrent session held
  `fix/pack-helper-defaults-and-guards` in the primary working copy for hours.
  Filing anything there meant either switching its branch or committing onto it.
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

The workaround is known and repeatable, which is exactly the argument for
making it a command instead of a habit.

## Requirements

### Isolation

1. The command performs every mutation in a private worktree created for the
   run. The caller's checkout — branch, HEAD, index, working tree, stash — is
   unchanged at exit, on the success path and on every failure path.
2. The worktree is created from the resolved remote default branch
   (`origin/main`), never from the caller's current branch or local `main`,
   which may be ahead, behind, or diverged. Local `main` sitting one unpushed
   commit ahead of `origin/main` was the live state while this task was filed.
3. The run seeds the per-working-copy files a fresh worktree lacks, starting
   with `.trellis/.developer`, from the caller's checkout. A missing source file
   is a clear precondition error naming `init_developer.py`, not a stack trace.
4. The worktree is removed when the run completes. A run that fails partway
   leaves it in place and reports its path, because a half-written task
   directory is evidence, not garbage.

### Filing

5. Arguments cover what `task.py create` needs — title, slug, priority,
   description, optional parent and package — plus the PRD body, which is the
   actual content and must come from a file or stdin rather than a shell
   argument.
6. The command runs `task.py create --no-start`. It files a task; it does not
   activate one. Activating a task in a worktree that is about to be deleted
   would leave the caller's session pointing at a directory that no longer
   exists.
7. `--assignee` is required by `task.py create` in this repository — omitting it
   fails with `No developer set`. The command resolves it from the developer
   file rather than making the caller repeat it.
8. Manifests are written with real entries or left for the caller to fill
   deliberately. The `_example` placeholder line must not survive into a
   submitted task: it is a documented review finding, and the scaffold is
   present in a large fraction of existing tasks precisely because nobody
   removes it.
9. `base_branch` is corrected to the default branch before the commit.
   `task.py create` seeds it from the current branch, so filing from a worktree
   on a filing branch records that branch as the PR target — wrong, and caught
   by review on both PRs that filed these two tasks. Because this command always
   runs on a purpose-made branch, it would reproduce the defect on every single
   invocation unless it calls `task.py set-base-branch <dir> <default>`. The
   underlying defect is `08-06-task-create-base-branch-seed`; this command must
   not wait for it.

### Publishing

9. One commit, scoped to the new task directory and nothing else. The command
   never sweeps unrelated dirty paths — there should be none in a fresh
   worktree, and if there are, that is an error.
10. Push creates the branch on the remote. Never a force push, never a push to
    the default branch.
11. A pull request is opened against the default branch with a body derived
    from the PRD. `mcp__github__create_pull_request` returns
    `403 Resource not accessible by personal access token` on this repository,
    so PR creation must go through `gh pr create`.
12. The command stops at the open PR. It does not review, merge, archive, or
    run housekeeping — `sd-housekeeping` is the only merge authority, and a
    filed task is not a merged task.

### Reporting

13. The final report gives the task directory, branch, commit, PR number and
    URL, and an explicit statement that the caller's checkout was not modified.
14. Every failure names the stage that failed and what remains on disk.

## Acceptance criteria

- Running the command from a checkout with a dirty tree on a feature branch
  leaves that branch, HEAD, and working tree byte-identical, verified before and
  after.
- Running it twice concurrently produces two independent tasks, branches, and
  PRs with no interference and no worktree collision.
- The submitted task contains no `_example` placeholder line.
- The created branch is based on `origin/main` even when local `main` is ahead.
- The submitted task's `base_branch` is the default branch, never the filing
  branch, verified by reading `task.json` after a run.
- A run against a checkout with no `.trellis/.developer` fails before creating
  anything, naming `init_developer.py`.
- The command never merges, and never pushes to the default branch.
- The worktree is gone after a successful run and present after a failed one,
  with its path reported.

## Open decisions

**Where the logic lives.** A skill under `.agents/skills/sd-submit-pack-task/`
with a shipped helper script is the shape the pack uses for everything with real
control flow. A skill alone would put a multi-step Git sequence into prose,
which is what this task exists to stop. Recommendation: helper script plus a
thin skill, matching `sd-status` and `sd-housekeeping`.

**Scope of "pack task".** As named, this files tasks into *this* repository.
The same problem exists for any Trellis repo the pack installs into, and the
requirements above are not repository-specific. Recommendation: build it for
this repository first and keep the argument surface free of anything that would
block generalizing later.

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

- Reviewing, merging, or archiving the submitted task.
- Filing into repositories other than this one, beyond not foreclosing it.
- Replacing `task.py create`. This command wraps it.
- The gitignored-file collision class itself, owned by
  `08-07-provenance-concurrent-session-collision`. This task only seeds what it
  needs and reports clearly when it cannot.

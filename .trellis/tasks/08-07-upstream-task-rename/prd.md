# task.py has no rename, so renaming a task is a four-place hand edit that breaks parent and child links

## Goal

Give Trellis a `task.py rename` that moves a task directory and rewrites every
identity field and back-reference together, so renaming stops being a hand edit
that silently dangles the task tree.

## Problem

`task.py` has no rename subcommand:

```text
{create,add-context,validate,list-context,start,current,finish,set-branch,
 set-base-branch,set-scope,archive,list,add-subtask,remove-subtask,list-archive}
```

Renaming therefore means editing four places by hand:

1. the directory name under `.trellis/tasks/`, via `git mv`;
2. `task.json` `id`;
3. `task.json` `name`;
4. `task.json` `title` — and the `prd.md` H1, which is a parallel copy of the
   title with nothing keeping the two in sync.

Done exactly that way on 2026-08-07 to rename `08-07-sd-submit-pack-task` to
`08-07-sd-propose-pack-task`. It worked only because that task had
`parent: null` and no children.

### The part that actually breaks

Linkage fields store **directory names**, while `id` stores the slug. From a
live parent/child pair:

```text
// 07-22-streamline-sd-skill-workflows/task.json
{ "id": "streamline-sd-skill-workflows",
  "children": ["07-22-evaluate-sd-github-review-consolidation",
               "07-22-centralize-pr-eligibility-gates", "..."] }

// 07-24-correct-sd-skill-contract-drift/task.json
{ "id": "correct-sd-skill-contract-drift",
  "parent": "07-22-streamline-sd-skill-workflows" }
```

Renaming a directory therefore invalidates every reference to it, in files the
renamer never opened. The larger the tree, the worse: one parent in this
repository lists more than a dozen children.

Nothing prevents this. Something does *detect* it, later:
`validateBookkeepingTopology` in `scripts/sd-ai-command-pack-review-preflight.mjs:845`
raises `task_topology_missing` when a reference resolves to no task record, and
`task_topology_not_reciprocal` when a parent does not list the child back. So a
hand rename of a linked task surfaces as a preflight failure at review or merge
time — the most expensive point, and attributed to whichever change happened to
be in flight rather than to the rename.

### The rest of the blast radius

- **The active-task pointer.** Trellis stores it per session under
  `.trellis/.runtime/sessions/` (`.trellis/scripts/common/active_task.py`). A
  rename while the task is active leaves that pointer at a path that no longer
  exists.
- **`task.json` title versus `prd.md` H1.** Two copies of one string, no
  sync, and a rename is precisely when they diverge.

## Requirements

1. `task.py rename <task-dir> <new-name>` moves the directory and updates the
   task's own `id`, `name`, and directory name as one operation. A partial
   result is a failure, not a rename.
2. Every back-reference is updated in the same operation: the `parent` field of
   each child, and the `children` and `subtasks` entries of the parent. After a
   rename, `validateBookkeepingTopology` reports no `task_topology_missing`
   and no `task_topology_not_reciprocal` for any task in the tree.
3. A title change is a separate, explicit argument, not implied by the rename.
   When supplied, `task.json` `title` and the `prd.md` H1 are updated together.
4. The command refuses when the destination directory already exists, naming
   it. It never merges into or overwrites an existing task.
5. The command refuses to rename an archived task. Archive paths are
   referenced by date-scoped directory and renaming under them is a different
   operation with different consequences.
6. Renaming a task that is `in_progress`, or that is the active task for any
   recorded session, is refused by default and names what holds it. That task
   has a live owner whose paths would break underneath them.
7. The rename is a pure metadata and path operation. It does not touch
   `status`, `branch`, `commit`, `pr_url`, `base_branch`, `completedAt`,
   `worktree_path`, or any artifact content beyond the H1 in requirement 3.
8. The operation is verifiable after the fact from the repository alone: the
   final report names the old path, the new path, and every task file it
   rewrote.

## Acceptance criteria

- Renaming a leaf task moves the directory, updates `id` and `name`, and
  changes no other `task.json` field.
- Renaming a task with a parent leaves the parent's `children` array containing
  the new name and not the old one, verified by reading the parent's
  `task.json`.
- Renaming a parent updates the `parent` field of every child, verified by
  reading each child's `task.json`.
- Running the preflight bookkeeping validator over the whole task tree after a
  rename produces no `task_topology_missing`, `task_topology_not_reciprocal`,
  or `task_topology_ambiguous` finding that was not present before.
- A rename into an existing directory name is refused and changes nothing on
  disk.
- A rename of an archived task is refused.
- A rename of an `in_progress` or active task is refused by default, naming the
  status or the session that holds it.
- With `--title`, both the `task.json` title and the `prd.md` H1 change; with
  no `--title`, neither does.
- A rename that fails partway leaves the repository in its pre-rename state, or
  reports precisely what was written.

## Open decisions

**Upstream or local.** `.trellis/scripts/task.py` is vendored upstream Trellis,
so this belongs upstream, alongside
`07-30-upstream-task-start-branch-recording` and
`08-06-task-create-base-branch-seed`. Recommendation: file it upstream and do
not carry a local fork of `task.py` for it — the hand-edit workaround is
tolerable at the observed frequency, and forking the task store to avoid it
costs more than it saves.

**Whether the H1 coupling belongs here.** The `task.json` title and `prd.md` H1
being unsynchronized parallel copies is a defect on its own, independent of
renaming. It is included here because a rename is the operation that most
reliably exposes it, and because fixing it separately would leave this command
having to choose a behavior anyway. It can be split out if it grows.

## Out of scope

- Renaming across the archive boundary, in either direction.
- Changing the slug/id scheme, the date prefix convention, or how directory
  names are derived at creation.
- The `task.py create` base-branch seeding defect, owned by
  `08-06-task-create-base-branch-seed`.
- Repairing task trees already broken by a hand rename. This command prevents
  new breakage; existing damage is found by the preflight topology validator
  and repaired case by case.

# Design — the proposed WORKFLOW.md

This is the page requirement 1 lands at the repository root, in full. It is
held here rather than at the root because it describes behaviour the pack does
not have yet: `sd-spec` is still in the ship path, the `Work:` line is still
unconditional, and `delete_branch_on_merge` is not set. A policy page that
states rules the payload contradicts is the stale-document failure this item
exists to remove, so the page moves to the root in the commit that makes it
true.

Open question 1 in `prd.md` applies to the Overrides section below: the three
keys it names do not exist in `sd_lib.py`, which reads `mode:` and `check:`
only.

---

# Workflow

How the pack expects to be used. One person does most of the work. Other
people see pull requests and merged commits, and nothing else the pack makes.
Every default below serves that person. Anything that would show a personal
process to someone else is off unless this file says otherwise.

## Defaults

These run without being asked.

- `sd-status` reports. It never writes.
- `sd-review --scope branch --challenge` runs on the machine before a push.
  Blocking findings are fixed or recorded before the branch leaves.
- CI runs on the pull request. The merge waits for CI and nothing else.
- `sd-ship` commits enumerated paths, pushes, opens the pull request, waits
  for CI once in the background, merges with an explicit title and body, and
  runs `git fetch -p`. The repository setting `delete_branch_on_merge` removes
  the remote branch.
- `make check` runs `sd-docs-lint` rules 1 to 4 whenever `docs/work/` exists.

## Opt-in

These run only when asked by name.

- A work item under `docs/work/<date>-<slug>/prd.md`. Create one when the
  work spans more than one session or more than about 300 changed lines.
  `design.md` and `implement.md` exist only when you ask for them.
- `sd-spec`. Run it when a change alters behaviour that `docs/spec/` documents.
- A second-model review. Ask for it per work item. The one lane is
  `sd-review --scope planning`. One round by default. The concern ledger, the
  hash baselines, and the cross-artifact sweep apply only to paths listed under
  `sensitive` in `.github/sd-review.json`. Rounds are counted per work item; a
  scope cut does not reset the count. Three rounds is the cap.
- `sd-handoff`. Write a packet when you stop mid-task and want the next
  session to pick it up.

## Advisory

- Copilot review. GitHub requests it on its own when the pull request opens.
  Its findings are read and dispositioned. They never block a merge and the
  pack never requests a second round.

## Never in a shared repository

A shared repository is one where someone else also merges. In it:

- No `Work:` line in a pull request body unless the pull request resolves a
  work item that lives in that repository.
- No `docs/work/`, `docs/spec/`, or `docs/decisions/` commits. Planning
  artifacts for a shared repository live in an untracked local path that the
  global git excludes cover, the same way `CLAUDE.local.md` does.
- No labels, review comments, reviewer requests, or bot posts from any pack
  surface. `sd-review` and `sd-receive-review` never post.
- No workflow files or repository settings unless the owner of that
  repository asked for them.

## The path for a change

Small change: branch, commit, `sd-review`, push, pull request, CI, merge.
Eight commands, one local review, no artifacts.

Change that earns a work item: `sd-plan` writes `prd.md` after asking three to
five questions. Then the small-change path. After the merge the item is marked
`done` and its directory is deleted at the next sweep. Git history keeps it.
An unmerged item parks after 45 days.

## Modes

`CLAUDE.local.md` carries one `mode:` line per repository. The installer writes
the block; the file is untracked by construction.

| Mode | Where planning artifacts go | What ships |
|---|---|---|
| `full` | `docs/work/` in the repository | everything above |
| `minimal` | nowhere; no work items | the small-change path only |
| `guest` | untracked local path | the small-change path; no posts, no labels |

A repository you do not own defaults to `guest`.

## Overrides

Set these in the `CLAUDE.local.md` block to change a default for one
repository.

    mode: full | minimal | guest
    check: <the command that verifies this repo>
    spec: on            # run sd-spec inside sd-ship
    codex: on           # request the second-model lane on every work item
    copilot: block      # let Copilot findings block the merge

Omit a key and the default above applies.

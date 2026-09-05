# Design — the proposed WORKFLOW.md

This is the page requirement 1 lands at the repository root, in full. It is
held here rather than at the root because it describes behaviour the pack does
not have yet: `sd-spec` is still in the ship path, the `Work:` line is still
unconditional, and `delete_branch_on_merge` is not set. A policy page that
states rules the payload contradicts is the stale-document failure this item
exists to remove, so the page moves to the root in the commit that makes it
true.

The Overrides section carries the keys `sd_lib.py` already reads and no others.
Three further keys were drafted and cut on 2026-09-05: an opt-in lane is asked
for by name, which needs no configuration to read, no default to resolve and no
key to go stale.

The read set is `mode:` plus `check:`, `test:` and `lint:` — the last three are
`CHECK_NAMES` at `bin/sd_lib.py:36`, consumed together at
`_local_block_entrypoints` (`:391-412`). The first draft of this page named only
`mode:` and `check:`, which was wrong by two.

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
- No `docs/work/`, `docs/spec/`, or `docs/decisions/` commits. `mode: guest`
  already carries this: planning artifacts go to the fork's integration branch,
  and every writing skill refuses the upstream tree.
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
| `guest` | the fork's integration branch | the small-change path; no posts, no labels |

A repository you do not own defaults to `guest`.

## Overrides

The `CLAUDE.local.md` block carries these keys, and the pack reads no others.

    mode: full | minimal | guest
    check: <the command that verifies this repo>
    test: <optional, when the repo spells its tests separately>
    lint: <optional, same>

`check`, `test` and `lint` run in that order and are each optional; a repository
that spells everything as one command sets `check` alone.

Everything under **Opt-in** above is asked for by name, in the moment, rather
than switched on in a file. Naming it is already the whole cost, and a key that
turns a lane on permanently is a default in disguise — it stops being a decision
you make about this change and becomes one you made about this repository, months
ago, for reasons the file does not record.

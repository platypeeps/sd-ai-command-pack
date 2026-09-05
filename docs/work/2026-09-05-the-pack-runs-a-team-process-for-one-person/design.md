# Design — the proposed WORKFLOW.md

This is the page requirement 1 lands at the repository root, in full. It is
held here rather than at the root because it describes behaviour the pack does
not have yet: the ship path still asks questions, the review points have no
caps, `paths.json` and `contrib/` do not exist, and the database the spine
depends on is item B in the system repository. A policy page that states rules
the payload contradicts is the stale-document failure this item exists to
remove, so the page moves to the root in the commit that makes it true.

The Overrides section carries the keys `sd_lib.py` already reads and no others:
`mode:` plus `CHECK_NAMES` at `bin/sd_lib.py:36`, consumed together at
`_local_block_entrypoints` (`:391-412`). Three further keys were drafted and cut
on 2026-09-05; an opt-in lane is asked for by name, which needs no key to go
stale.

The provider registry section documents a file that B's library reads. Its
format is fixed here so that skills can name roles today and resolve them the
day the library exists.

---

# Workflow

How the pack expects to be used. One person does most of the work. Other
people see pull requests and merged commits, and nothing else the pack makes.
Every default below serves that person. Anything that would show a personal
process to someone else is off unless this file says otherwise.

## Two flows, one spine

The spine is the **item**: one row in the local database, one screen on the
dashboard, and the files in git the row points at. Every flow starts by
creating or picking an item and ends by closing it.

**Research.** Sources, understanding, brief, decisions, handoff or publish. The
research kit lays out the repository; the item tracks what is open. You sit at
the end: external publish or filing is the one gate, and it is yours.

**Development.** Pick the item. The loop writes the prd and design when the
change earns them, implements, tests, reviews, pushes, and merges where you
have allowed it. A repository merges unattended only when you set `merge: auto`
on its row, once, from the dashboard; there you review the result on the item
screen after it lands, and revert is one action. Everywhere else the loop stops
at pull-request-ready and the pull request waits in the send box.

The loop asks no questions while it runs. Where it would have asked, it decides,
records the choice on the item as a proposal, and continues. You veto after. It
stops, and marks the item `blocked` with the reason, on a failing test, a
blocking review finding still open once the review cap is spent, or a write
outside the repository.

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
- A commit to the pack, the system repository or the writing repository names
  what needed it: `Needed-by: <item id>` or `Needed-by: cost | efficiency |
  visibility`. `sd-ship` warns when the trailer is missing and ships anyway.
  The weekly count of missing trailers is on the dashboard.

## Opt-in

These run only when asked by name.

- A work item under `docs/work/<date>-<slug>/prd.md`. Create one when the
  work spans more than one session or more than about 300 changed lines.
  `design.md` and `implement.md` exist only when you ask for them. Status is on
  the item's row, never in the file; `ready_to_send` marks a finished artifact
  waiting on you.
- `sd-spec`. Run it when a change alters behaviour that `docs/spec/` documents.
- A review pass beyond the table below. Ask for it by name; the item records
  that you did.
- `sd-handoff`. Write a packet when you stop mid-task. Followups, decisions and
  open questions are already on the item; the packet carries only what is not.

## Reviews

Adversarial review runs at four points, each with a cap on automatic passes.
When the cap is spent no further pass starts on its own. The artifact moves on,
to the send box, to implementation, to merge, once every blocking finding is
addressed or rebutted with evidence on the item. A blocking finding still open
past the cap marks the item `blocked`; non-blocking findings hold nothing.

| Flow | Point | What it checks | Cap |
|---|---|---|---|
| Research | After the brief and decisions | Claims against sources, gaps, wrong calls | 2 |
| Research | Final product, before the send box | The piece, page or ticket as a reader sees it | 1 |
| Development | prd and design | Scope, missing requirements, wrong assumptions | 1 |
| Development | Code, before merge | Defects a second reader finds | 1 |

The reviewer is a different vendor from the author, always. Skills name the
roles `author` and `reviewer`; the provider registry below maps them.

The code point is an experiment until the numbers say otherwise: findings
accepted against findings rejected over ten pull requests, cost logged per pass,
thirty percent accepted to stay.

## Advisory

- Copilot review. In an organisation or shared repository GitHub requests it on
  its own when the pull request opens. Its findings are read and dispositioned.
  They never block a merge and the pack never requests a second round. On a
  repository you pay for personally it is off.

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
- No merge. The loop stops at pull-request-ready.

## The path for a change

Small change: branch, commit, `sd-review`, push, pull request, CI, merge.
Eight commands, one local review, no artifacts.

Change that earns a work item: `sd-plan` writes `prd.md` after asking three to
five questions, or none when the loop runs unattended. Then the small-change
path, with the two development review points. After the merge the item's row is
`done` and its directory is deleted at the next `sd-plan` run, when every file
in it is tracked and committed; otherwise it stays and the run names the files.
Git history keeps what is deleted.

## Modes

`CLAUDE.local.md` carries one `mode:` line per repository. The installer writes
the block; the file is untracked by construction.

| Mode | Where planning artifacts go | What ships |
|---|---|---|
| `full` | `docs/work/` in the repository | everything above; merge only with `merge: auto` on the row |
| `minimal` | nowhere; no work items | the small-change path only |
| `guest` | the fork's integration branch | the small-change path to pull-request-ready; no posts, no labels |

Ownership decides where artifacts go, whichever organisation holds the
repository. Without a `mode:` line, the pack asks three questions of the
remote: is the owner you, is it not a fork, are you the only collaborator. Three
yes: `full`. Anything else, including no answer: `guest`. A root with no remote
is `full`; there is no one to expose anything to. Mode never decides merging.
`merge: auto` is a per-repository policy you set once on the dashboard, off by
default, and nothing derives it.

## Providers

One file, read by the library, maps roles to providers. Skills name roles and
never vendors.

    providers:
      claude:  { start: "claude -p", roles: [author, reviewer], cost: subscription }
      codex:   { start: "codex exec", roles: [author, reviewer], cost: subscription }
      exo:     { url: "http://localhost:52415/v1", roles: [author, reviewer], cost: local }
    roles:
      author:   claude
      reviewer: codex

Adding a provider is an entry. Changing who writes or who reviews is a role
line. The two roles never resolve to the same provider.

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
turns a lane on permanently is a default in disguise: it stops being a decision
you make about this change and becomes one you made about this repository,
months ago, for reasons the file does not record.

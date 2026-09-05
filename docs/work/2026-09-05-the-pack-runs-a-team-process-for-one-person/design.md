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
  for CI once in the background, merges with an explicit title and body,
  lands the item's closure commit on the default branch, and runs
  `git fetch -p`. The repository setting `delete_branch_on_merge` removes
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
  `design.md` and `implement.md` exist only when you ask for them. Status lives
  on the item's row; the file's `status:` line is a mirror the library writes
  in the checkout on the item's branch, for checkouts and CI runners that have
  no database. `ready_to_send` marks a finished artifact waiting on you.
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
| Development | prd and design | Scope, missing requirements, wrong assumptions | 5 |
| Development | Code, before merge | Defects a second reader finds | 1, plus one verification of the fix |

The code pass reads a head. A fix that changes it gets one verification pass
over the diff since the reviewed head, the last automatic pass on that pull
request; `sd-ship` pushes only the reviewed head or a verified fix of it.

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
`done`, and `sd-ship` lands one closure commit on the default branch, a
direct push where the branch accepts one and a second pull request
otherwise, that writes `done` into the mirror so that `main` and CI read it
without the database, and deletes the directory when every file in it is
tracked and committed and nothing untracked or ignored sits beside them;
otherwise it stays and the commit names the files. The branch itself never
says `done`, so a merge that fails leaves the item open. Git history keeps
what is deleted.

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

    bills:
      anthropic: { cost: subscription }
      openai:    { cost: subscription }
      moonshot:  { cost: prepaid }
      minimax:   { cost: prepaid }
      baseten:   { cost: company, cap_usd_month: 50 }
      local:     { cost: local }
    providers:
      claude:  { start: "claude -p",  vendor: anthropic, bill: anthropic, roles: [author, reviewer], reader: claude-json }
      codex:   { start: "codex exec", vendor: openai,    bill: openai,    roles: [author, reviewer], reader: codex-json }
      kimi:    { url: "https://api.moonshot.ai/v1", model: kimi-k3, vendor: moonshot, bill: moonshot,
                 roles: [reviewer], max_tokens: 16384, price: { in: 3.00, out: 15.00 } }
      minimax: { url: "https://api.minimax.io/v1", model: MiniMax-M3, vendor: minimax, bill: minimax,
                 roles: [reviewer], max_tokens: 16384, price: { in: 0.30, out: 1.20, unverified: true } }
      prism:   { start: "prism", model: deepseek-ai/DeepSeek-V4-Pro-0813, vendor: deepseek, bill: baseten,
                 roles: [reviewer], max_tokens: 16384, price: { in: 1.32, out: 3.96 }, reader: prism-json }
      gito:    { start: "gito",  model: deepseek-ai/DeepSeek-V4-Pro-0813, vendor: deepseek, bill: baseten,
                 roles: [reviewer], max_tokens: 16384, price: { in: 1.32, out: 3.96 },
                 enabled: false, reason: "start line and report reader unverified" }
      exo:     { url: "http://localhost:52415/v1", model: "<pinned>", vendor: local, bill: local,
                 roles: [author, reviewer], enabled: false, reason: "model not pinned" }
    roles:
      author:   [claude, codex]
      reviewer: [codex, claude, kimi, minimax, prism, gito, exo]

Pins as of 2026-09-05, each read from the vendor's model list on that day:
`kimi-k3` is Moonshot's current flagship with a one-million-token window;
`MiniMax-M3` is MiniMax's newest, and its price is a proxy from an index
because the vendor publishes none, hence `unverified`, which Today shows
beside the number until a real price replaces it; the two Baseten tools pin
DeepSeek V4 Pro, whose 0813 build is the cheapest of Baseten's frontier
reviewers. `max_tokens` is the same on all four because a review reply that
needs more than sixteen thousand tokens is a review that should have been
scoped. A pin is changed by editing this file, never by a page.

Adding a provider is an entry; adding money is a bill. Both role lines are
read in order. `author` is picked when an assignment starts and never switched
mid-item; outside the runner, `SD_AUTHOR` or `--author` names it, `sd-ship`
stamps it on each commit as `Authored-with:`, and a branch with no author
named is refused, not guessed. `reviewer` is the first entry that is enabled, is not the author's
vendor, has budget left on its bill, and answers its preflight. A rate limit,
a missing binary, a failed run or a timeout falls through to the next, and the
run says which one reviewed and why the earlier ones did not. With none left,
the review refuses by name rather than reading its own work. `vendor` is the
maker of the model, not the tool; `bill` is whose money. A bill with
`cap_usd_month` is enforced per call: the library reserves each call's bound,
prompt plus `max_tokens` at the entry's price, against the month's settled and
reserved rows in one transaction, refuses the call when the bound would pass
the cap, and skips that bill in fallthrough for the rest of the month; a
direct pick of it refuses with the month's total. Entries with
`url` share one OpenAI-compatible client and one reader. This file is
identity and seed; enabled, order and caps are rows the dashboard edits, and
the library merges file and rows on every read.

`sd-review --provider <name>` picks one entry for one run. The dashboard's
item screen offers the same list, with vendor, cost and reason beside each
name. Copilot and Greptile are not entries: they post on the pull request, and
this lane never posts.

This file is the only list of providers. `sd-review` reads it through the
library; `.github/sd-review.json` carries repository policy, paths and the
severity floor, and names no provider and no chain. The `reviewer` line above
is the chain.

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

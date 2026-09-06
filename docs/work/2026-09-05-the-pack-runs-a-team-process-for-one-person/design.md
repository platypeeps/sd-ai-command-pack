# Design — the proposed WORKFLOW.md

This is the page requirement 1 lands at the repository root, in full. It is
held here rather than at the root because it describes behaviour the pack does
not have yet: the ship path still asks questions, the review points have no
caps, `paths.json` and `contrib/` do not exist, and the database the spine
depends on is item B in the system repository. A policy page that states rules
the payload contradicts is the stale-document failure this item exists to
remove, so the page moves to the root in the commit that makes it true.

The Overrides section carries the keys `sd_lib.py` already reads, `mode:`
plus `CHECK_NAMES` at `bin/sd_lib.py:36`, consumed together at
`_local_block_entrypoints` (`:391-414`), and one more, `reviewers:`, added on
2026-09-05 because consent to disclose a repository's diff is per repository
and per machine and belongs in the file the operator writes by hand. Three
further keys were drafted and cut the same day; an opt-in lane is asked for
by name, which needs no key to go stale.

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
on its row, once, from the dashboard, and only while the remote still answers
that the repository is yours alone, asked again at every merge; there you
review the result on the item
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
  for CI once in the background, merges with an explicit title and body
  whose trailer names the item, and runs `git fetch -p`. The repository
  setting `delete_branch_on_merge` removes
  the remote branch.
- The default branch is protected: pull requests only, CI required, branches
  up to date before they merge, no required approvals. `sd-status` reports
  it, the dashboard sets it in one
  action on a repository you own, and an unattended merge into a branch
  that is not refuses naming the setting.
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
  on the item's row and nowhere in the file; a checkout or CI runner with no
  database asks git whether the item is delivered, by the merge trailers, and
  nothing else once the line has retired. `ready_to_send` marks a finished
  artifact waiting on you.
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
request; `sd-ship` pushes only the reviewed head or a verified fix of it,
and merges naming that head with `gh pr merge --squash --match-head-commit <the
reviewed sha>` — equivalently `PUT /repos/{owner}/{repo}/pulls/{n}/merge`
with `sha=` — so a head that moved after the review is refused at GitHub with
a 405. The flag is what does the refusing, and until 2026-09-05 neither page
named it: `skills/sd-ship/SKILL.md:70` passes `-t` and `-b` alone, which are
message text and refuse nothing, so criterion 32's "asserts the merge call
named the reviewed head and was refused" was asserting against a call that
could not refuse.

The reviewer is a different vendor from the author, always. Skills name the
roles `author` and `reviewer`; the provider registry below maps them.

The code point is an experiment: over ten pull requests, findings accepted
against findings rejected with each accepted finding's severity, and cost
logged per pass. The experiment ends in a report on the item, and you
decide whether the point stays; no ratio decides for you.

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
- No issue filed. `sd-suggest` writes a row everywhere; `sd suggest publish`
  files one when you run it, to the destination you name with `--to`.

## The path for a change

Small change: branch, commit, `sd-review`, push, pull request, CI, merge.
Eight commands, one local review, no artifacts.

Change that earns a work item: `sd-plan` writes `prd.md` after asking three to
five questions, or none when the loop runs unattended. Then the small-change
path, with the two development review points. An item is not one pull
request; it lands in as many as its slices need. Every merge `sd-ship`
makes carries `Item: <item>` in its message, which ties the commit to
the item and closes nothing: after it, whether `sd-ship` made it or you
did, and a merge you make is confirmed by the runner's watch on the pull
request or by the next `sd-ship` run here, the squash commit goes on a
note, and the item stays open. The one
merge that delivers carries `Delivers: <item>` as well: `sd-ship
--deliver`, the runner on a row you marked final, or your own hand in
the merge message; for a hand merge without it, the item screen's
`deliver` does the same after the fact. On that merge, and on no other,
the row is `done`, nothing is written into a file, and the directory
stays. A delivered item that got no `Delivers:` of its own, a hand merge
you delivered after the fact or a cancel, is marked by the next merge
message `sd-ship` writes here, or by one empty commit on its own branch
when the triad never left it.
A reader with no database asks git first: a `Delivers:` or `Closes:`
commit on the default branch means delivered, an `Item:` commit alone
means nothing, and a shallow clone that cannot tell says so and picks
nothing. The branch itself never
says `done`, so a merge that fails leaves the item open. Delete a `done`
directory yourself, with `git rm -r`, when you want the listing short;
nothing in the pack does. When the default branch moved while the pull
request waited, `sd-ship` merges it in once, reviews the combined head
once, spends no pass on it, waits for CI and merges; moved again, the run
stops at `ready_to_send` and says so, and the next run makes the next
update. A conflict ends the item `blocked` naming the files. In `guest`
mode the mark is one empty commit on the fork's integration branch, where
the triad lives, and nothing goes upstream.

## Modes

`CLAUDE.local.md` carries one `mode:` line per repository. The installer writes
the block; the file is untracked by construction.

| Mode | Where planning artifacts go | What ships |
|---|---|---|
| `full` | `docs/work/` in the repository | everything above; merge only with `merge: auto` on the row |
| `minimal` | nowhere; no work items | the small-change path only |
| `guest` | the fork's integration branch | the small-change path to pull-request-ready; no posts, no labels |

Access decides where artifacts go, whichever namespace holds the
repository. Without a `mode:` line, the pack asks three questions of the
remote: can you administer it, is it not a fork, can anyone else push. Admin,
not a fork, nobody else: `full`, in your namespace or an organisation's.
Anything else, including no answer: `guest`. A root with no remote, **or
no git at all**, is `full`; there is no one to expose anything to. The
no-git case is named and asserted on its own, because criterion 11 requires
exactly that (`prd.md:1375-1380`) — it is the case that otherwise gets
swept into whichever exception branch the remote lookup raises. The questions are asked
again before every artifact write and every push, and a `no` makes the
run `guest` whatever the line says: a `mode: full` you wrote is a ceiling,
never a floor — detection lowers it and never raises it, which is
`prd.md:1380-1381`'s "wins over detection downward and never upward" — so a repository that gains a collaborator stops
receiving your planning artifacts before the next push, not after the
next merge. The push check is of the destination: your fork's integration
branch is your own remote, and the guest push there proceeds while the
same branch offered upstream is refused. Mode never decides merging.
`merge: auto` is a per-repository policy you set once on the dashboard, off by
default, and nothing derives it. It is necessary, not sufficient: every merge
asks the same three questions again, one function for both gates, and a no
suspends it with the reason shown.

## Providers

One file, read by the library, maps roles to providers. Skills name roles and
never vendors.

    bills:
      anthropic: { cost: subscription }
      openai:    { cost: subscription }
      moonshot:  { cost: prepaid }
      minimax:   { cost: plan, meter: "https://www.minimax.io/v1/token_plan/remains" }
      baseten:   { cost: company, cap_usd_month: 50 }
      local:     { cost: local }
    providers:
      claude:  { start: "claude -p",  vendor: anthropic, bill: anthropic, roles: [author, reviewer], reader: claude-json }
      codex:   { start: "codex exec", vendor: openai,    bill: openai,    roles: [author, reviewer], reader: codex-json }
      kimi:    { url: "https://api.moonshot.ai/v1", model: kimi-k3, vendor: moonshot, bill: moonshot,
                 roles: [reviewer], max_tokens: 16384, price: { in: 3.00, out: 15.00 } }
      minimax: { url: "https://api.minimax.io/v1", model: MiniMax-M3, vendor: minimax, bill: minimax,
                 roles: [reviewer], max_tokens: 16384, price: { in: 0, out: 0 } }
      baseten: { url: "https://inference.baseten.co/v1", model: deepseek-ai/DeepSeek-V4-Pro-0813, vendor: deepseek,
                 bill: baseten, roles: [reviewer], max_tokens: 16384, price: { in: 1.32, out: 3.96 } }
      exo:     { url: "http://localhost:52415/v1", model: "<pinned>", vendor: local, bill: local,
                 roles: [author, reviewer], enabled: false, reason: "model not pinned" }
      # Shipped disabled, faithful to `prd.md:448-451`. Criterion 6's test
      # adds an `exo` entry and resolves it, and a disabled entry never
      # resolves — so that test writes its own enabled entry into a fixture
      # registry rather than reading this one.
    roles:
      author:   [claude, codex]
      reviewer: [codex, claude, minimax, kimi, baseten, exo]

A capped bill takes `url` entries only, because the library makes those
calls and can refuse one before it is sent; a `start` entry on a capped
bill is refused when the file is read. That is why `baseten` is one `url`
entry and the `prism` and `gito` CLIs are gone: they pointed at the same
endpoint and added limits of their own.

Each entry also carries `env`, the list of variables the entry's process
receives beside `PATH`, `HOME`, `LANG`, `TERM` and `TMPDIR`, `env:
[OPENAI_API_KEY]` for `codex`; left out of the example above for width. A
session inherits the variables its own entry names and no other entry's.
That is inheritance, not isolation: the session runs as you, in your
`HOME`, and can read the file the keys live in.

Pins as of 2026-09-05, each read from the vendor's model list on that day:
`kimi-k3` is Moonshot's current flagship with a one-million-token window;
`MiniMax-M3` is MiniMax's newest, and it runs on the Token Plan the
operator has already paid, so the entry's price is zero and the bill
carries a meter instead: the plan grants use in a five-hour window and a
weekly window, and `GET /v1/token_plan/remains` on `www.minimax.io`, with
the same key, answers with `current_interval_remaining_percent` and
`current_weekly_remaining_percent` for `model_name: general`, probed
2026-09-05. The meter writes those two percents as `meter` rows, Today
shows them beside the bill, a `plan` bill reserves no dollars, and
fallthrough skips it while either window reads zero; the two Baseten tools
pin
DeepSeek V4 Pro, whose 0813 build is the cheapest of Baseten's frontier
reviewers. `max_tokens` is the same on all four because a review reply that
needs more than sixteen thousand tokens is a review that should have been
scoped. A pin is changed by editing this file, never by a page.

Adding a provider is an entry; adding money is a bill. Both role lines are
read in order. `author` is picked when an assignment starts and never switched
mid-item; outside the runner, `SD_AUTHOR` or `--author` names it to
`sd-ship`, which stamps it on each commit it makes as `Authored-with:
<name>/<vendor>`, the vendor as the registry gave it at commit time. The
review reads no declaration: every commit in the reviewed range is attributed
by its own trailer, or by an `Attributes: <sha> <name>/<vendor>` trailer on a
later commit in the range that `sd attribute` makes, and a commit with neither
refuses the review by name rather than being guessed. `reviewer` is the first entry that is enabled, is of no vendor the
range's trailers carry, has budget left on its bill, and answers its preflight. A rate limit,
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
is the chain, intersected with the repository's `reviewers` line in
`CLAUDE.local.md`, the entries you have allowed to receive that repository's
diff; the entry is the recipient and the line names the recipient beside the
entry, so a second host for the same model is a second name to allow and a
host moved under the same name is refused until you rewrite the line;
without the line, no reviewer resolves.

## Overrides

The `CLAUDE.local.md` block carries these keys, and the pack reads no others.

    mode: full | minimal | guest
    check: <the command that verifies this repo>
    test: <optional, when the repo spells its tests separately>
    lint: <optional, same>
    reviewers: <entry@recipient pairs that may receive this repository's diff, e.g. claude@claude+3f9a1c2e, baseten@inference.baseten.co>

`check`, `test` and `lint` run in that order and are each optional; a repository
that spells everything as one command sets `check` alone. `reviewers` is
consent: you write it, nothing derives it, it names entries because the entry
is who receives the diff, and each entry carries its recipient, the host of a
`url` entry, or the executable of a `start` entry with a fingerprint of its
line and `env` names, so an entry edited to point elsewhere is refused until
you rewrite the line; a `start` session is refused any variable whose value
is a URL, and the tool's own configuration file is yours to keep; without
the line no
reviewer resolves for the
repository. The installer asks for it once per repository when it writes the
block, offering the enabled entries and taking none as an answer; it fills in
no default, keeps your answer on every rerun, and a repository you skipped
refuses its first review naming the key.

Everything under **Opt-in** above is asked for by name, in the moment, rather
than switched on in a file. Naming it is already the whole cost, and a key that
turns a lane on permanently is a default in disguise: it stops being a decision
you make about this change and becomes one you made about this repository,
months ago, for reasons the file does not record.

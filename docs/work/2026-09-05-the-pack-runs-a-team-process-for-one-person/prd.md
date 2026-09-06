---
title: the pack runs a team process for a repository with one person in it
status: planning
created: 2026-09-05
branch: feat/solo-first-workflow-policy
---

# PRD — the process outgrew the person it serves

## Problem

The pack's contracts were written one gate at a time, each one answering a real
defect. Nothing ever asked what they cost together, and the answer turned out to
be most of the working day.

Measured across the last eight days, three repositories, sixty-nine sessions and
17,821 tool calls:

| Where the time went | Calls | Wall time |
|---|---|---|
| Hand-rolled polling loops waiting on GitHub | 417 | 770 min |
| All `gh` invocations | 3,172 | 1,100 min |
| Test runs (`make check` 599, `unittest` 786, `pytest` 331) | 1,876 | 898 min |
| Local review lane | 377 | 61 min |
| Status reporting | 228 | 23 min |

Ninety-eight pull requests opened and 102 merged in eight days, by one person.

The pack's own history is the sharpest example. One 291-line skill file drew
eight adversarial review rounds and 45 findings across a single evening,
producing an 855-line `prd.md`. Roughly a third of those findings were genuine
behavioural improvements; roughly a third were the same value stated in three
artifacts and drifting between them; roughly a quarter were defects introduced
by the previous round's own fix.

Four signals say the process serves nobody:

- **The framework gets the work, not the work.** In the same eight days the
  operator's own commits split 327 to 62: pack 244, system 48, writing pack 35,
  against 55 in `mezmo-world-simulator` and about seven in `mcp-research`. Those
  two repositories are the stated priority. Five commits on the tool for every
  one on the thing the tool is for.
- **Nobody reads the artifacts.** `docs/work/archive/` holds 487 items. A full
  enumeration of the git history, replacing an earlier sample of fifteen, shows
  386 arrived already `done` in one import commit (`46ec7fb85`) and were never
  active here; the other 100 were bulk-parked in one commit (`5278b0d28`). Five
  items in the whole history were ever touched by more than two commits, and
  four of those are open today. The archive is an import, not a record.
- **Skill usage cannot be measured, in either direction.** Three counts over
  identical eight-day data give six skills, thirteen, and eighty-one. No surface
  records "this skill's instructions governed this turn". Every "unused" claim
  in the audit that opened this item was unfalsifiable, and the twelve-of-82
  figure it carried is withdrawn. What the count did show is a second surface:
  270 Codex sessions against 2,487 Claude Code transcripts, with `sd-red-team`
  and the six `sd-rust-*` skills living almost entirely on Codex.
- **Finished work does not leave.** Four blog pieces at `ready` since
  mid-August, zero published. Six `mcp-research` handoff drafts written on
  2026-09-03, none filed. The operator's own account of the stall: not perfect
  yet, another pass first. A framework that can always run one more pass has no
  end state.

The rules that fail are the ones written as prose. The global "never `cd`,
always absolute paths" rule is contradicted by 9,455 of 16,033 Bash calls in the
sample window, by the same agents that read it every session.

## Why the obvious fix is wrong

**Not "delete the skills".** Skills cost nothing at rest; they render once at
install and sit in a catalog until named. What costs is the *mandatory path*:
the gates that run whether or not the change needs them. Cutting sixty skills
would remove capability the owner might want next month and would not save a
single one of the 770 polling minutes. And the usage evidence for any cut does
not exist. The skills stay; what changes is which of them install, and how that
is decided.

**Not "remove the gates".** The adversarial review lane is the single measured
win in the pack's history: it took one branch from fifteen remote review rounds
down to three, and seven passes on `mezmo-world-simulator` found real defects
each time. What is wrong is not that reviews exist; it is that they have no
cap, so a finished artifact can always be reviewed once more instead of sent.

**Not a new abstraction.** The pack already carries three review lanes, three
repository modes, a routing policy, a plugin registry and a fleet dashboard.
Another layer to decide when the other layers apply is the disease, not the
cure. What is missing is one page saying which defaults hold, one place that
holds state, and the existing knobs wired to both.

**Not "make everything opt-in".** A default nobody sets is a gate nobody runs.
The distinction that matters is *who sees the output*: a gate that runs on the
owner's machine and prints to the owner's screen is cheap and stays on by
default; a gate that writes to a shared repository, posts to a pull request, or
blocks a merge is expensive and turns off unless the work earns it.

**Not a bigger command line.** The operator is visual and forgets commands and
their options. Every prior fix added a command. The 82 skill names are a memory
load, which is one reason they go unused. The front door has to be a screen that
shows what is possible; the command line is the agent's surface, not the
operator's.

## What this changes

One page, `WORKFLOW.md`, states the pack's policy for a repository with one
person in it, and the pack's surfaces are brought into line with it. The policy
in one sentence: **anything the pack does should help the person running it,
without exposing or imposing that person's process on anyone else.**

The page describes two flows on one spine. The **research flow** runs sources,
understanding, brief, decisions, handoff or publish; the operator sits at the
end, and external publish is the only gate. The **development flow** runs prd,
design, implement, test, review, push, merge; in a repository the operator owns
it runs without a gate and the operator reviews the result after it lands. The
spine both flows share is the **item**: one row in a local database, one screen
on a dashboard, and the artifacts in git that the row points at.

That spine is not built here. This item was opened as one piece of work and,
after a second interview on 2026-09-05, became three:

- **A — this item, the pack.** Policy, the tiered ship path, review points and
  caps, the vendor rule and the provider registry, which skills install and how
  they are promoted, the filing skill, the handoff skill. Everything that
  describes behaviour or ships in the payload.
- **B — the system repository.** The database at `~/.local/share/sd/sd.db`,
  the one library that owns its schema and every write, the dashboard as the
  operator's front door with five sections, the migrations that fill it, the
  vault crons stopped, the fixture harness, and the terminal-multiplexer
  wrapper. Everything that runs on the machine and is not the runner.
- **C — the writing repository.** A stub: ideas and pieces move into the
  database after B's library exists. Nothing else until one piece publishes.
- **D — the runner.** Split from B on 2026-09-05 by the operator's decision:
  `local-sd-runner/`, the process that turns an assignment row into a
  session, runs batches, watches pull requests and merges. It lands last, in
  the order recorded under Landing order below.

B's library lands first, because requirements 5, 10, 11 and 12 below write to
it, because requirement 2 reads `merge: auto` from a repository row and writes
proposals as rows, and because requirement 3 resolves the registry through it.
Until the library is installed: the loop never merges, since no row can say
`auto`, and it records proposals in the item's log in the format
`sd-receive-review` defines; `sd-review` resolves `providers.yaml` through a
file-only reader in the pack, which the library's resolver replaces the day it
lands, and a test asserts both return the same order from the same file. The
provider table in `bin/sd-review` goes in the commit that adds that reader,
not before. Requirements 1, 4 and 6 through 9 need nothing from B and land in
any order.

Decisions taken in the two interviews are the requirements below.

### Requirement 1 — the policy page exists and is discoverable

`WORKFLOW.md` at the repository root states, for a consuming repository: the two
flows and the spine they share; what runs by default, what is opt-in, what is
advisory, what never touches a shared repository; the review table with its
caps; the path for a change at each size; and the modes and how they resolve.
`sd-help` names it. The `CLAUDE.local.md` block the installer writes links to it.

The block carries the keys the pack already reads and no others: `mode:`, plus
the entrypoint names `check:`, `test:` and `lint:` from `CHECK_NAMES`
(`bin/sd_lib.py:36`, consumed at `:391-412`). Every opt-in lane is asked for by
name in the moment. A key that turns a lane on permanently is a default in
disguise: it converts a decision about one change into a decision about the
repository, taken once and unrecorded.

### Requirement 2 — the ship path is tiered, and it can run unattended

Today `sd-ship` applies eleven steps to a one-line fix. After this item the
default path is: commit enumerated paths, local review, push, open the pull
request, wait for CI once, merge, close the item on the default branch,
`git fetch -p`.

- `sd-spec` leaves the default path. It runs when a change alters behaviour that
  `docs/spec/` documents, and the operator asks for it.
- Step 11's remote-branch deletion is replaced by the repository setting
  `delete_branch_on_merge`. The step shrinks to the local report.
- The settle loop is one background wait on CI, not a shell loop. The 417
  hand-rolled polling loops in the measurement window, forty of which hit a tool
  timeout and were reissued, are the thing being removed.
- The 70 lines of pull-request history in the skill file (the `#718` and `#720`
  narratives) collapse to one paragraph stating the resulting rule.
- The path merges on its own when tests, review and CI pass, and reports, only
  in a repository whose row in the database carries `merge: auto`. The operator
  sets that once per repository from the dashboard; the default is off, and no
  detection sets it. Everywhere else the path stops at pull-request-ready. Mode
  decides where artifacts go; the merge policy decides whether the loop merges,
  and the two are separate because remote ownership can suggest the first and
  cannot authorize the second. Consent goes stale, though, and a row set
  once does not know that a collaborator arrived since: so at the moment of
  the merge `merge: auto` is necessary and not sufficient, and the path asks
  the remote requirement 6's three questions again, can the operator
  administer it, is it not a fork, can anyone else push, one predicate in
  the library that the artifact gate and this gate both call and neither
  restates, from A's round twenty-seven, whatever the `mode:` line says,
  so that an organisation repository the operator alone administers
  merges unattended under `merge: auto` as requirement 6 keeps it `full`. Any no, or
  no answer, and the merge does not happen: the item ends `ready_to_send`
  with a note naming the answer that changed, the row keeps `merge: auto`
  and the dashboard shows it suspended with the same reason, and the
  operator decides. Nothing merges into a repository someone else can also
  merge into, whatever a row from before they arrived says.
- Nothing on the path asks a question mid-run. Where a skill would ask today, it
  decides, records the choice on the item as a proposal, and continues. The
  operator vetoes after, not before. A test failure, a blocking review finding
  left open once the review cap is spent, or a write outside the repository
  stops the run and marks the item `blocked` with the reason.
- Every commit to the pack, the system repository or the writing repository
  names what needed it: a `Needed-by:` trailer carrying an item id or one of the
  three lanes `cost`, `efficiency`, `visibility`. `sd-ship` warns when it is
  missing and ships anyway. The weekly count of missing trailers is a number the
  dashboard shows. This is the guard against the 327-to-62 split, chosen soft
  because the operator asked for framework work to continue in those lanes.

### Requirement 3 — review points, caps, and the vendor rule

Three lanes review the same planning artifacts today: a host lane in the
contract, `sd-review --scope planning`, and a hand-launched background task
named in `AGENTS.md`. Two of them are the same external model reading the same
files. None of them has a cap.

After this item, adversarial review happens at four named points, each with a
cap, and nowhere else unless the operator asks by name:

| Flow | Point | What it checks | Cap |
|---|---|---|---|
| Research | After the brief and decisions | Claims against sources, gaps, wrong calls | 2 |
| Research | Final product, before the send box | The piece, page or ticket as a reader sees it | 1 |
| Development | prd and design | Scope, missing requirements, wrong assumptions | 5 |
| Development | Code, before merge | Defects a second reader finds | 1, plus one verification of the fix |

The cap bounds automatic passes, not the disposition of what they find. When a
point's passes are spent, no further pass starts on its own; the artifact moves
on only once every blocking finding is dispositioned, addressed or rebutted with
evidence recorded on the item. A blocking finding still open past the cap marks
the item `blocked`, and the operator decides. Non-blocking findings never hold
an artifact. A further pass needs the operator to ask for it by name, and the
item records that it was asked for. This is the fix for "not perfect yet,
another pass first": the review ends; the findings do not vanish.

The code point's pass reads a head. A fix that changes the head after the
pass gets one verification pass over the diff since the reviewed head, and
that is the last automatic pass on the pull request: a blocking finding from
it marks the item `blocked`. `sd-ship` pushes a head that is the reviewed head
or a verified fix of it, and nothing else; a further commit waits for the
operator to ask for a pass by name. That rule governs the author's
changes. The base's changes are governed by another, because the default
branch moves while a pull request waits, another item's merge, and the
protection then refuses the pull request until it
carries the move: an integration update, the default branch merged into
the branch with nothing else in the commit, is not a fix and spends no
pass, and it is bounded, from A's rounds seventeen and eighteen and B's
round thirty. `sd-ship` makes at most one per run: it merges the default
branch in, reviews the combined head once with the branch review, since
two changes each reviewed alone were never reviewed together, waits for
CI, and merges naming that head; when the base moved again in between,
GitHub refuses the merge and the run ends with the item `ready_to_send`
naming the reason rather than updating again, and the next run, the
operator's or D's merge row's, makes the next one. Under D's runner the
merge row holds the repository's serial merge lane from the update to
the merge, so the pack's own merges cannot move the base under it and one
update is the rule; a hand can, so a second update is the bound and the
row ends `blocked` past it. A blocking finding from an integration review
marks the item `blocked` like any other; a clean one merges the head it
reviewed. A conflict in the update ends the item `blocked` naming the
files, and `sd-ship` resolves none. Three settings without the update
were tried on 2026-09-05 and withdrawn the same day: without the
up-to-date requirement, two parallel authors that each pass alone can
merge without a textual conflict and break the default branch, which CI
finds after delivery, when a successor has already been dispatched onto
it.

**The reviewer is a different vendor from the author, by policy.** Today Claude
writes and Codex reviews. If the primary moves to OpenCode or a local model, the
pair changes and the rule holds. The pack's skills name *roles*, `author` and
`reviewer`, never vendors. A **provider registry**, one config file read by B's
library, maps each role to a provider: name, how to start it, which roles it
may fill, cost basis. Adding exo, another commercial API, or a second local
model is an entry, not code. Each entry names the environment variables its
process needs, `env: [OPENAI_API_KEY]`, and a session or a review call
started for that entry inherits those, a fixed base, `PATH`, `HOME`,
`LANG`, `TERM`, `TMPDIR`, and nothing else, asked for on 2026-09-05: the
runner and `sd-review` read the operator's environment file for themselves
and pass on only what the entry names. What that buys is stated exactly,
from A's round nineteen: a session does not inherit another vendor's
key, so a tool that reads its own environment, and a log or a crash dump
that prints it, carry one vendor's key and not all of them. It is not a
boundary. The session runs as the operator with the operator's `HOME`,
can read `~/.config/shell/env.sh`, and a login shell it starts sources
that file back; a session that wants another key can have it, and this
design says so rather than claiming otherwise. The boundary a key needs,
a per-vendor account and a per-session credential store, is not built
here. The registry's format and the role vocabulary are
defined in this item; the file lives with the database.

The registry is static and the author is not. `author` is a list too,
`[claude, codex]`, read in order when an assignment starts and never switched
mid-item: a Claude outage sends the next assignment to Codex, not the one in
flight. Whichever provider authored, a single-name `reviewer` line would
resolve to the vendor that wrote the code. So resolution takes the author into
account: the reviewer is the first entry on the `reviewer` list whose vendor
is not the author's, and the library refuses by name when none differs. Under
the runner the assignment row names the author. Outside it the author is
an input at commit time and never at review time: `sd-ship` takes
`--author <provider>` or `--author human`, defaulting to `SD_AUTHOR`, which
the runner and B's terminal wrapper set for every session they start, and
stamps each commit it makes with an `Authored-with: <name>/<vendor>`
trailer, the entry and the vendor the registry gives it at commit time,
refusing an entry the registry does not have, and `human` bare, from A's
round thirty-five: the independence rule reads the vendor from the
trailer and never from the registry at review time, so an entry
repointed to another vendor's model or removed after the commit changes
no history, misidentifies no author, and blocks no review of an older
branch.
Reviewer resolution walks every commit in the reviewed range, the branch
since its slice base, and builds the set of authors from what the range
carries: each commit's own trailer, or an `Attributes: <sha>
<name>/<vendor>` trailer on a later commit in the range, the vendor
resolved the same way when the attribution is written, which `sd
attribute <sha> <name>` writes as one empty commit on the branch, one
trailer per attributed
commit, run by the operator per commit or per range, `sd attribute
<from>..<to> <name>`, and stamped `Authored-with: human` itself, because
the operator made it, so that the repair never needs repairing, from
A's round nineteen. The trailer names a commit as it is, and a rewrite
of the branch that changes an attributed commit's hash, a rebase or an
amend, loses it: the review then refuses again naming the commits that
lost their attribution, and one range attribution restores it. That is
deliberate and rare, from A's round twenty: the pack never rewrites a
branch, D's dispatch and `sd-ship`'s integration both merge and never
rebase, so the case arises only from the operator's own rewrite, and a
trailer that followed content across rewrites would have to be matched
by a patch id, which a conflict resolution changes. It is a commit and
not a note
because a notes ref is one mutable ref the whole repository shares, and
two clones attributing different commits from the same tip diverge, the
second push fails, and a force would drop the first; a commit on the
branch is branch-local, travels with the push, is read by CI and by the
merge row, and is squashed away with the rest at the merge. A commit with neither is refused
naming the commit and the command, not reviewed on the strength of the
tagged ones, and no flag or variable at review time attributes history:
a session's identity says who is working now, not who wrote an older
commit, and a handoff from one agent to another is ordinary, so a review
that took `--author` for the whole range would let the first agent review
its own untagged work under the second's name. The set is the commits
of `HEAD` reachable from neither the default branch nor the row's
`slice_base`, `git rev-list HEAD --not <default> <slice_base>`, from
A's rounds forty-two and forty-three: `slice_base` is the branch head
the row recorded when it recorded a slice's squash commit, requirement
5, written in that transaction, and excludes that slice's own commits,
which the squash carries as a diff and not by identity, so they would
stay in a range from the merge base for the branch's life; the default
branch excludes the squash commit itself and what came in with the
merges of the default into the branch, which are nobody's authorship
here, since a squash is no ancestor of the head it squashed and a base
alone cannot exclude it; the merge commits themselves are on the
branch and carry the trailer `sd-ship` gave them, or are refused like
any other. A fresh branch cut from the default after the merge has
the same set by the same rule with no `slice_base`. The vendors the
trailers carry are joined by the row's `authors`, from A's round
forty-four: every session the runner or B's wrapper starts on the
item's branch adds its vendor to the row's set for the slice in the
transaction that starts it, whether it commits or not, and an
entry lives from the session's start until its work is in a recorded
slice, because a session that edits and leaves without committing has
authored what the next session commits under its own name, and a
trailer names who committed and not everyone who wrote: the wrapper
and the runner's supervisor record at the session's end whether `git
status --porcelain` named anything and the branch head at that moment,
an entry that ended clean clears at once, its work being in commits
that carry its trailer, and an entry that ended dirty, or a session
still running, stays until the first commit on the branch after its
recorded head is an ancestor of `slice_base`, the commit that carried
its edits having been in a recorded slice, from A's rounds forty-five
and forty-six; the transaction that records a squash clears the
entries that rule clears then, and a review clears none, so a second
slice's edits left by one session, committed by another and squashed
later keep the first session in the set until that later squash;
the operator's terminal outside the wrapper is the operator, `human`,
which adds nothing to skip. The
reviewer is the first entry whose vendor is in no member of the set, the
vendors the trailers carry, so a
branch two providers wrote is reviewed by a third or refused; a set that is
`human` alone is reviewed by the first entry, and `human` beside a provider
adds nothing to skip.

One list of providers on the machine. `bin/sd-review` carries its own table,
`BACKENDS` at `bin/sd-review:195`, and `.github/sd-review.json` names providers
again under `challenge_providers` and `planning_providers`. Both go. The
registry entry holds what the table held: the start line, and the reader for
the provider's output. `sd-review.json` keeps what is repository policy and
nothing about vendors or chains: categories, paths, `sensitive`, the
severity floor. Who may read a repository's contents is consent, not
policy, and it lives where the operator's other per-repository, per-machine
decisions live, the `CLAUDE.local.md` block, as a fifth key: `reviewers`,
the registry entries that may receive this repository's diff. The entry is
the recipient, not the model's maker: the `baseten` entry sends the diff
to Baseten, whoever trained the model it serves, so consent names
`baseten`, and a second
host for the same model is a second entry that no repository has consented
to until its line names it. The line names the recipient beside the
entry, `baseten@inference.baseten.co`, the host of a `url` entry's
address, and for a `start` entry the executable with a fingerprint of
the whole start line and the entry's `env` names,
`codex@codex+3f9a1c2e`, from A's rounds twenty-seven and twenty-eight,
because an entry is a name in a file the operator edits and a name is
not a recipient, and an executable alone is not one either, since an
argument or a variable can send the same tool elsewhere: the library
derives each named entry's recipient from the registry at every review
and compares it with the line, and an entry whose recipient moved
under its name is refused naming what was consented to and what was
found, with no request sent, until the operator rewrites the line; a
bare name in the line is refused the same way, naming the form. What
the fingerprint cannot see is where a tool is told to talk by the
value of a variable it is handed or by its own configuration file, so
the library refuses to start a `start` session when any variable it
passes has a URL for a value, naming the variable and never the value,
and the tool's own configuration is named here as the operator's to
keep and the one place consent does not reach; a remote the operator
wants to choose is a `url` entry, where the library owns the transport
and the host is the recipient. `vendor` stays what it is, the maker, for the
independence rule alone, read from the trailer for the author and from
the registry for the candidate reviewer. Fallthrough is dispatch, not authorization: the
chain is intersected with `reviewers`, and with no entry left, or with no
`reviewers` line at all, the review refuses naming the key and the file
rather than sending the diff to the next entry with budget. Nothing is
derived: not from the `author` line, which says who is available and not
who was consented to; not from the mode; not from who authored the branch;
not from a vendor already allowed under another entry. One line per
repository, written by the operator, and an entry added to the registry
reaches no repository that did not name it. The installer asks for the
line once per repository, when it writes the block, offering the enabled
registry entries with their recipients, writing the pairs, and taking
none as an answer; it fills in no default,
writes no line for none, keeps the answer on every rerun, and a
repository the operator skipped refuses its first review naming the key,
by the operator's decision on 2026-09-05: install is the one moment the
operator is present per repository, and a default would be a derived
grant. A guest repository gets the line the same way, in its untracked
block. The tiers go with the `tiers`
key, by the operator's decision
on 2026-09-05: the registry's reviewer order is the one chain, and `deep` had
already collapsed into `standard` the day gito was disabled.

**Fallback is the reviewer list, read in order, and the order follows the
bill.** Every entry names a `bill:`, and the registry's `bills:` section says
whose money it is: `subscription` for Codex and Claude, `plan` for MiniMax,
the Token Plan the operator has paid for the year, which grants use in a
five-hour window and a weekly window that the vendor's `token_plan/remains`
endpoint reports as a remaining percent each, `prepaid` for the Moonshot
balance the operator has already paid, `company` for
Baseten, `local` for exo. The `reviewer` line runs subscription first, the
plan next, because its monthly tokens lapse unused where a prepaid balance
keeps, prepaid after that, company last: `[codex, claude, minimax, kimi,
baseten, exo]`, with one `url` entry,
`baseten`, in place of the `prism` and `gito` CLIs that pointed there,
from A's round twenty-two. The first entry that is
enabled, carries the role, is not the author's vendor, has budget left on its
bill, and passes its preflight reviews. Claude sits second so a change Codex
authored is reviewed on a subscription before any prepaid balance is
touched, and the vendor rule keeps either from reading its own work. A rate
limit, a missing binary,
failed authentication, a non-zero exit and a timeout each fall through to the
next, and the run records which provider reviewed and why the earlier ones
did not, on the assignment row and in the JSON it emits. Fallthrough happens
on its own, onto prepaid and company bills included, and only among the
entries the repository's `reviewers` line allows; every pass writes a cost
row and Today shows it.

One bill has a cap from day one. `baseten` is company money, and its bill
carries `cap_usd_month: 50`. The library enforces the cap per call, not per
month in arrears: before each dispatch it computes a bound, prompt tokens
plus the entry's `max_tokens` at the entry's price, and reserves it against
the bill in one transaction with the month's settled and still-reserved
rows, as B's requirement 6 specifies; a bound that would carry the month
past the cap is refused before anything is sent, so two calls racing for
the last dollar cannot both go. A `start` entry makes its own calls, and
no number the library holds stands in front of them, so a capped bill
takes `url` entries only: the registry reader refuses a `start` entry
whose bill carries a cap, naming the entry and the bill, from B's round
thirty-four, which overturns the session bound of round thirty-three
because a declared bound is a guess a retry passes. The operator points
such an entry at the vendor's endpoint as a `url` entry, so the library
makes the calls, or takes the cap off the bill, which makes the number
an alert. Round twenty-one said the two Baseten entries were `url`
entries already; they were not, the design's registry had `prism` and
`gito` as `start` lines, the CLIs, which the reader would refuse. So the
CLIs leave the registry and one `url` entry, `baseten`, takes their
place, through the library's client that already carries Kimi and
MiniMax, from A's round twenty-two; the CLIs added only their own limits.
The reservation settles to the real
cost after. At the cap, fallthrough skips every provider on that bill,
direct choice refuses by name with the month's total, reserved included,
and Today shows spend against cap. The dashboard raises the cap in one action, and it enables, disables and
reorders providers the same way: the registry file holds identity and seeds
B's `provider` and `bill` tables, the rows hold what the page changes, and
the library merges the two on every read, so the file is never edited from a
page. No other bill has a cap. An API entry carries `price:` per million
tokens in and out, so a cost row is tokens times price without a billing API;
a subscription entry logs tokens alone.

An entry carries `vendor:`, the maker of the model behind it, and the
different-vendor rule compares vendors, not names or bills. `baseten` is
a bill and an endpoint, not a vendor: the entry's vendor is the model it
serves, pinned on the entry. `kimi` is Moonshot, `minimax` is MiniMax, `exo` is
whatever model it serves. Entries carrying a `url:` run through one
OpenAI-compatible client in the library, with `model:` and `max_tokens:` from
the entry and one reader for all of them that takes the answer from
`content`, strips a `<think>` block, and ignores `reasoning_content`. That
client is what makes the prepaid balances usable: `prism` hardcodes 8,192
output tokens and a 120-second deadline, which is why `~/.prism/.env` records
Kimi and MiniMax as disabled there. The `kimi` CLI and `gito` ship disabled
until each has a verified start line and a reader; the Moonshot balance is
reached through the `url:` entry meanwhile. An entry also carries `enabled:`,
with `reason:` when false. Enabling one is a verified start line and a reader,
and the entry flips.

Choosing directly is one flag and one picker. `sd-review --provider <name>`
runs one named provider for one run, validated against the registry, and the
item records the choice. The dashboard's item screen offers the same picker
over the registry table, with vendor, cost, enabled and reason beside each
name. Switching the default is the `reviewer` line. GitHub-side reviewers,
Copilot and Greptile, are not registry entries: they post on the pull request,
which the local lane never does, and they stay advisory under requirement 4.
The local lane runs before every push regardless, so a Copilot outage costs
nothing; the local list is its fallback by construction.

**Code review is an experiment, not yet a rule.** The seven passes already run
on `mezmo-world-simulator` are scored first: findings accepted against findings
rejected, per pass, and each accepted finding's severity beside it. Then the
other vendor reviews the next ten code pull requests, and cost is logged per
pass. The experiment ends in a report on this item, not in a rule that
fires, from A's round nineteen: accepted against rejected, the highest
severity accepted and what it would have cost to ship, and the cost per
pass. A reviewer that finds one data-loss defect in ten passes and nine
rejected findings is worth its cost at any ratio, and one that finds
ten typos is not, so no percentage removes the code point; the operator
reads the report and decides, and the decision is recorded here with
the report.

The one lane is `sd-review --scope planning`. The concern ledger, the pre-edit
hash baselines and the per-round cross-artifact sweep apply only to paths listed
under `sensitive` in `.github/sd-review.json`. The codex appendix under `docs/`
and the `AGENTS.md` bullet that mandates the second lane are deleted.

### Requirement 4 — Copilot advises, on the repositories where the organisation pays

Merge blockers are the local review lane and CI. Copilot review is advisory:
GitHub requests it automatically when a pull request opens in an organisation or
shared repository, its findings are read and dispositioned, and it never blocks
a merge. The pack never requests a second round. On repositories the operator
pays for personally it is off. GitHub spend is the one cost line the operator
named as a worry, and this is the part of it the pack controls. The user-global
`PostToolUse` hook that asks for a Copilot review after every push is deleted;
it is not installed by the pack, and it duplicates what GitHub already does.

### Requirement 5 — a work item exists only when it earns one, and its state lives in the database

A work item is created when the work spans more than one session or roughly 300
changed lines. `design.md` and `implement.md` are written when asked for, not by
default. `sd-plan` asks three to five questions before it writes anything, and
in an unattended run it asks none and records its assumptions.

**Git owns the artifacts; the database owns the state.** `prd.md`, `design.md`
and `implement.md` stay in the repository as the decision trail. The item row in
`sd.db` holds status, dates, links and notes, and points at the files by path.
The `status:` line leaves `prd.md`, by the operator's decision on 2026-09-05
after A's round thirty-three: the migration that fills the database, B's
requirement 2, reads every item's line outside `docs/work/archive/` into
its row, `done` ones included, and is additive first and retires last,
from A's round thirty-six: its import lands the rows beside the lines in
B's first slice and removes nothing, and the rows it lands are a
rehearsal copy and not the record; this item's second slice lands the
reader, which asks the repository's row in the database which source is
the record, `status_source`, `file` until the sitting, `retiring`
while it runs, and `row` after it,
from A's rounds thirty-seven and thirty-eight: under `file` it reads
the line, because until the retire the line is what every writer still
writes, the status commands and `sd-plan` and `sd-ship` among them, and
a row imported earlier says what the item was and not what it is; under
`row` it reads the row and ignores a line wherever one is found, a
branch or a linked worktree kept across the retire, reporting the line
by name as stale with the integration update as its repair, and every
status writer refuses under `retiring`, the sitting's own value, and
the old ones under `row`, naming the sitting, from B's round
forty-nine; with no database it asks git for delivery, as above, and
reads the line as well until the repository itself says the retire
happened: the retire step's one commit adds a tracked marker,
`docs/work/.status-source`, one line, `row`, beside removing the lines,
from A's round forty-one, so that a clone or a CI runner with no
database and without that commit, taken between this item's reader and
the retire, reads the historical `done` items as `done` from their
lines and picks none of them, their `Closes:` arriving only with the
retire step's pull request, and one holding the marker reads no line
at all; a checkout with a database asks the row and never the marker,
since a retained worktree lacks the marker until the integration
update merges it in and the row is right at once. The
presence of a line is never the marker of the migration's state, since
every checkout that predates the retire keeps its lines until the
default branch's deletion merges into it, which requirement 3's
integration update does before any merge and CI's lint refuses to skip.
The same slice lands the trailer-writing ship path and the `PR_BODY`
setting.
The migration's retire step runs after that in a pull request of its
own, and it is B's one sitting: set the repository's row `retiring`,
which is the freeze, every status writer refusing under it, import
once more so
that every row says what its committed line says now, on every branch
of the remote and not the default alone, refusing naming an item whose
branches disagree, from B's round fifty-four, the import and
the verify reading committed trees and refusing on a dirty `docs/work`,
from C's round eight, verify by content, snapshot,
set the repository's `status_source` to `row`, and only then remove
every line in one commit, refusing to run while the
installed `sd_lib` has no `delivered`, naming the version, and lifting
the freeze, `file` again, with nothing removed when the verify names a
difference; `row` before the removal and never after, from C's round
five, because the sitting spans the database, the files and a commit,
and a run that dies between two steps is rerun, each step idempotent:
before `row` every line is in place and the rerun imports and
continues, after it the lines left are ones every reader ignores and
the lint names, and the rerun removes them;
the lint's rule that no line remains switches on where that commit's
marker is present, and from
it the row is the record, and a status change writes the row. After it
nothing writes a status into a file again. A `done`
item the default branch does not mark, which is every historical one,
four in this repository today, is an unmarked `done` row from the import,
and the pull request that lands the retire step carries `Closes:` for
each, as every pull request `sd-ship` opens does below, from A's round
thirty-four; so the terminal state moves from the file into the merge
commit in one landing, the file says `done` on the default branch until
that merge and the trailer says it after, and the retire step's own branch
before its merge is the one checkout that reads those items as open.
Rounds eleven to thirty-two kept the
line as a derived mirror the library wrote, and the mirror needed an identity,
`rev`, a guard on every write, `--rebind` for the guard's misses, a refresh
command, a lint comparison, a rule for each way a squash merge moved the
branch, and a closure to carry `done` into the file after the merge, by a
second pull request until round thirty-one and by the next commit after; each
round from thirty to thirty-three found the next case the guard or the
closure got wrong, and the word they carried is one git already holds. The
row carries the item's branch, and a status change writes the row and nothing
else, in any checkout and in any state of the branch: no file changes, no
commit follows, and nothing is pushed.

A reader with no database, CI, a fresh clone, a linked worktree on another
branch, asks git one question, whether the item is delivered, and nothing
else; every other state lives on the row, and the surfaces that act on it
have the database. One function, `sd_lib.delivered`, answers `yes` when a
commit reachable from the remote's default branch as just fetched, or
from the checkout's branch as just fetched from its upstream, or from
`HEAD`,
carries `Delivers: <item>` or `Closes: <item>`, never on `Item:` alone, `no`
when none does, the history is whole, and the history is current, and
`unknown` otherwise: when the checkout is shallow, `git rev-parse
--is-shallow-repository`, because the trailer may sit past the boundary,
from A's round twenty-two; and when the checkout has a remote and this
run's fetch of the default branch from it, `git fetch <remote>
<default>`, did not succeed, because a whole history is not a current
one, and a clone retained while another machine delivered or cancelled
the item holds neither trailer and would answer `no` for finished work,
from A's round thirty-nine. The function fetches the default branch
first and answers `yes` from it alone when it carries the trailer, from
A's round forty-one, and only otherwise fetches the checkout's branch
from its upstream, `git fetch <remote> <branch>`, because the mark for
a branch-only cancel and for a guest delivery lives on the item's
branch and on no other, from A's round forty, so a clone retained on
that branch is current only once it has that branch's tip; a branch
the remote no longer has, deleted by requirement 2's
`delete_branch_on_merge` at its merge, git's refusal naming the ref, is
nothing to be behind, and the function answers from the default branch
as fetched and `HEAD`, `no` when that merge was a slice's, while a
fetch of the branch that fails for any other reason, the remote
unreachable, is `unknown`, since the tip it lacks may carry the mark. A
checkout with no remote has nothing to be behind and answers from what
it has, and an `unknown` names the boundary or the remote and the fetch
as the repair. Every reader
that picks an item, `sd-review --scope planning` and `sd-plan` among them,
excludes a `yes` and treats an `unknown` as not selectable, refusing by name
with the boundary and `git fetch --unshallow` as the repair, since a reader
that cannot establish delivery must not restart delivered work; so a
delivered item is never the "single open item" of a checkout that has no
database. The lint in CI, which `make check` runs with no database, checks
that no `prd.md` under `docs/work/` outside `docs/work/archive/` carries a
`status:` line, and nothing else about status.

`done` reaches the row after the merge is confirmed and never before, so a
rejected merge, a failed CI run or a ship killed after the push leaves the
item exactly as open and as selectable as it was. Nothing here pushes to the
default branch: the default branch is protected in every repository the pack
merges into, by the operator's decision on 2026-09-05, pull requests only, CI
required, branches up to date with the default branch before they merge, and
no required approvals because there is no second person to give one. The
up-to-date requirement was dropped with the deletion below on 2026-09-05 and
restored the same day, because two parallel pull requests that each pass
alone can merge without a conflict and break the default branch, so the
combination is tested before the merge and not after, requirement 3.
`sd-status` reports those four settings and the merge-message setting
below, an unattended merge into a default
branch that does not require pull requests and CI refuses naming the
setting, and a ship the operator runs by hand is warned, not stopped. A run
that restarts reconciles before it acts, from A's round thirty-nine: the
row names the pull request from the moment it is opened, and the run
asks GitHub for that pull request's state and `merge_commit_sha` and
applies what GitHub confirms and the row does not yet carry, `done` when
the merge commit's message carries `Delivers:` and the squash commit on
a note otherwise, in one idempotent step that a second run repeats to no
effect; GitHub's acceptance and the row's write are two systems, a
process can die between them, and a run that trusted the row alone
would treat delivered work as open. After that step a run that finds
the row `done` and the trailer on the default branch has nothing
further to do. An item is not
one pull request: the landing order below splits this one into slices, and
a merge is a delivery only when it says so, from A's round twenty-three.
Every merge `sd-ship` makes carries `Item: <item>`, which associates the
commit with the item and closes nothing; the merge that delivers carries
`Delivers: <item>` as well, written when the operator ships with
`--deliver`, or when D's runner merges an assignment whose row was created
as the item's last slice, `final` on the row from the run dialog. A merge
without `Delivers:` leaves the row `in_progress` and records the squash
commit in a note naming the slice: the branch continues, or the next slice
is prepared in a second worktree of the branch, or cut fresh from the
updated default branch, and nothing checks which, since no write depends on
the branch's ancestry; the squash reaches the branch through requirement 3's
integration update before the next merge, which is where it is needed.
`sd-ship` says so in its last line, naming `--deliver` for next time. The
row turns `done` on the confirmed merge that carries `Delivers:`.

Two trailers, and a mark for the cases the delivering merge does not cover.
`Delivers:` is written by the merge that delivered. `Closes:` is written
where a row is `done` and no commit on the branch a database-free checkout
would read carries `Delivers:` for it, so that such a checkout stops picking
the item, by one of two means, from A's round thirty-three. Where the item's
triad reached the default branch, a slice merged, the next pull request
`sd-ship` opens in that repository, of whatever item, carries `Closes:
<item>` for every such row in that repository, in its body's trailer block
beside `Item:` and, with `--deliver`, `Delivers:`, and the merge message is
that block: `sd-ship` writes it through the API when it merges, and a hand
squash merge takes it from the body because the repository's
`squash_merge_commit_message` is `PR_BODY`, a fifth setting the installer
sets beside the four protections and `sd-status` reports, from A's round
thirty-four, so that under the default policy the operator types no
trailer and the merge dialog's prefilled message carries them all. The
trailers change no tree and no reviewed head, and ride whatever pull
request merges next, so they cost nothing and touch nothing. Until that
merge, a database-free checkout of the default branch still picks the
item, which is the one residue, bounded by the next pull request in that
repository, and `sd-status` names such rows as unmarked while they wait;
nothing that has the database picks them. Where the triad never
left the item's branch, or lives on a guest fork's integration branch,
requirement 6, the mark is one empty commit on that branch, `git commit
--allow-empty`, carrying `Closes: <item>` and the reason in its body, made
in the item's kept worktree where one exists and otherwise in a temporary
one the library cuts from the branch and removes, pushed to the branch where
the branch has a remote and nowhere else; the branch is retained and never
merged, and a checkout of it reads the mark from its own history.

The cases. A `cancel`, item B's requirement 1, writes `done` with a
`cancelled` note in the row and marks by whichever means fits where the
triad is; a cancelled row whose mark has not landed is finished by the next
`sd-ship` run the same way, so no other checkout and no CI reads a cancelled
item as open for longer than one ship. A merge the operator makes by hand,
the default policy, is confirmed the same way by whichever next asks GitHub
about the item's pull request, D's runner, which watches every
`ready_to_send` item's pull request, or the next `sd-ship` run in that
repository before D exists, and the same step follows when the merge message
carries `Delivers:`, which a hand squash merge carries when the pull request
was opened with `--deliver` or the operator added the line to the body or
the dialog: the row `done`; without it, the squash commit goes on a note,
the item stays open, and the item screen offers `deliver` for a merge that
was the last one, which writes `done` and leaves the mark to the next pull
request. Under `mode: guest` the upstream merge is the maintainer's and
carries no trailer of the pack's, so the row decides, from A's round
thirty-four, by the same word as anywhere else: the ship that offered the
pull request ran with `--deliver`, the row was `final` from the run dialog,
or the operator says `deliver` on the item screen after the fact; a
confirmed upstream merge without that is a slice, the squash commit goes on
a note, and the item stays open. On the delivery the row is `done` with the
squash commit recorded as the merge, and the mark commit goes on the
integration branch, pushed to the fork, with no pull request and nothing
upstream. Until B's library exists the frontmatter is the only copy, and the
switch is one migration.

The status vocabulary gains one state, `ready_to_send`, for a finished artifact
waiting on the operator's external action, and keeps `blocked`. Nothing else
changes.

No sweep, no park, no archive, and no deletion at delivery. A merged item
is `done` in the row, its delivering merge says so in git,
and the directory stays, by the operator's decision on 2026-09-05. The
rule that deleted it took seven fixes in sixteen rounds, a reader scan by
literal path, a second by resolved link, a lint rule on the merged tree,
an up-to-date protection setting, a re-cut path and a single-caller
guard, and the reviewer said three times that keeping the directory
was the simpler design. It is. A `done` directory costs a
line in a listing, every reader that picks an item already excludes a
delivered item, and the pack has the case today: `2026-08-29-artifacts-as-product`
is `done` and fourteen lines in twelve tracked files link into it, which
a deletion would have had to detect and a kept directory serves. No pack
surface deletes an item directory. When the operator wants the listing
short, once a quarter or never, they delete with `git rm -r` in a change
of their own, and a link that breaks then is theirs to see. The lint
rule, the two reader scans, the eligibility function and the re-cut path
are not built; the up-to-date setting stays for the reason requirement 3
gives, which is not this one.
`docs/work/archive/` stays as it is, by the operator's decision on
2026-09-05 after A's round twenty, which overturns the first draft's
answer to its third question. The pack stops reading it instead:
`work_item_dirs` skips that one directory by name, and no other surface
knows it exists, so the 386 imported and the 100 parked items are files
in git and nothing else, the eleven tracked files that link into the
archive keep links that resolve, and the ignore pattern in
`.gito/config.toml` stays. The deletion took two rounds to make safe, a
recovery commit named by full hash, every permalink checked against its
tree, every reader migrated, and it bought a shorter listing of a
directory nobody opens; git holds the archive either way, and a
directory the pack does not read costs nothing. The pack makes no
deletion at all. A backlog nobody opened in four months is still not a
backlog, and B names one surface for later work.

### Requirement 6 — nothing personal reaches a shared repository, and ownership decides

A shared repository is one where somebody else also merges. Ownership decides
the mode; the organisation name does not. `mezmo-world-simulator` sits in the
`answerbook` organisation, has one author, and runs `full` with its triad
pushed and Notion mirrors for its audience. That is intended and stays.

- The `Work:` line appears in a pull request body only when the pull request
  resolves a work item that lives in that repository. The `Work: none - <reason>`
  form is deleted, and rule 5 of the documentation lint becomes conditional on a
  work item existing.
- Planning artifacts stay out of the shared tree through `mode: guest`, which
  already carries this rule across six skills: the triad goes to the fork's
  integration branch (`sd-plan/SKILL.md:105`), `sd-spec` never touches the
  upstream tree (`:41`), `sd-review` refuses outright (`:106`), `sd-ship` posts
  no reviews or labels (`:206`), and `sd-suggest` files nothing upstream
  (`:44`). No new mechanism is built.
- A repository the operator does not own resolves to `mode: guest` without an
  explicit line. Today `sd_lib.mode()` reads the local block and falls back to
  `full`, so an unconfigured shared repository gets the most invasive mode by
  default. This is the one piece of requirement 6 that is new code: the fallback
  asks three questions of the remote before returning `full`: the operator
  holds admin permission on it, in a personal namespace or in an
  organisation alike, the repository is not a fork, and nobody else has
  push or higher on it, direct collaborators, organisation members and
  teams counted the same way, from A's round twenty-six; the questions
  ask who can merge and who can read, never whose name the namespace
  carries, which is what keeps `mezmo-world-simulator` `full` under
  `answerbook`. Any other answer, and any failure to answer, returns `guest`
  for the artifact question while leaving the merge question to the policy
  above, which is off unless set. A personal fork of a shared upstream and a
  personally owned repository with collaborators both resolve to `guest`.
  The answer is live, not stored, from A's round twenty-five: a stored
  `mode: full` is a floor the operator set and never a ceiling, so the
  three questions are asked again before every write that places a
  planning artifact in the tree, `sd-plan`'s commit of the triad, and
  before every push `sd-ship` makes, not only at merge time, and a `no`
  makes the effective mode `guest` for that run whatever the line says:
  the write goes to the fork's integration branch or, where the operator
  holds no fork, to a local branch that no push carries, naming the
  answer, the collaborator, the fork or the permission; a push that
  would carry the triad to the remote that answered `no` is refused the
  same way before anything leaves the machine, and the check is of the
  destination and not of the branch, from A's round twenty-six: the
  fork's integration branch is the guest destination, a remote the
  operator alone holds, so the commit that carries the triad
  there is the guest path and proceeds, and the same branch offered to
  the upstream is refused; and a note on the item records the demotion. What
  is already in the shared tree from before the answer changed is the
  operator's to move, and `sd-status` names it. An explicit `mode:
  guest` is never raised by a `yes`. The
  three modes are named in `README.md`, which mentions none of them today.
- `README.md`'s claim that the pack writes "nothing, ever" in a repository is
  rescoped to the installer, which is where it is true. The skills that write
  tracked files by design are named.

### Requirement 7 — the checks that cannot fail are removed or wired up

- `sd-docs-lint` runs in no Makefile target and no workflow. Rules 1 through 4
  move into `make check`, conditional on `docs/work/` existing.
- The 100% coverage floor stays for `bin/sd_install.py`, which writes files under
  the operator's home directory. It is dropped elsewhere.
- The four line-count ceilings print a warning and stop failing the suite. They
  were re-derived five times in five days and cost more in bookkeeping than the
  headroom they defend.
- `make check` gains a fast path over changed files. The full suite runs once
  before a push.
- The `bash32` job builds bash from source to lint the repository's own scripts,
  guarding a premise that stopped being true when shipped shell was deleted. It
  is cut. The `security` job folds into `lint`.
- `tests/test_selector_contract_drift.py` tests a contract its own docstring
  calls retired. `generated/registry-snapshot.json` and the `plugins/sd` stub are
  residue from a deleted architecture. All three are deleted.

### Requirement 8 — the instruction layers stop contradicting each other

- Every mention of Trellis leaves the routing block and the planning contract;
  no such directory exists in this repository. The two `.trellis` allow rules
  leave the global settings.
- The fourteen `Read()` deny globs and the global "never `cd`" rule are dropped
  together. The globs guard build artifacts rather than secrets, and their
  presence is what forces the path-resolution prompts the rule exists to dodge.
  The rule is contradicted by 59% of Bash calls, which is the definition of a
  rule that does not work.
- Four MCP pull-request tools join the permission allowlist. Nine merges in the
  measurement window were blocked by the classifier because the guidance says
  "MCP before `gh`" while only the `gh` form is allowed.
- Dated narrative leaves the governing documents. `CONTRIBUTING.md` is about 45%
  history and the system repository's guide about 36% incident write-ups. Each
  keeps its present-tense rules, plus one sentence where a rule needs its reason.
- The four files stating the planning review rule collapse to one under
  `.claude/rules/`, and that one states the review table from requirement 3.
- The pull-request template points contributors at `docs/SD_AI_COMMAND_PACK.md`,
  which does not exist. Fixed or removed.

### Requirement 9 — one terse-style mechanism

The output style already enforces short sentences everywhere. The caveman plugin
enforces a second, overlapping style through a session hook, and the writing
repository carries an override forbidding it. The plugin is uninstalled and the
override deleted, leaving the output style as the single mechanism.

### Requirement 10 — a skill installs because a path names it, or because it was used

Usage counts cannot decide what stays, because none exist. Cohesion can.

- `skills/paths.json` names three paths and the skills on each: research
  (sources to brief to handoff), development (plan to build to ship), and act
  (brief to draft to send). The installer renders only what a path names. A
  directory under `skills/` that no path names fails `make check`. The list is
  enumerated at install, never recited.
- `contrib/` holds every skill no path names. In git, not installed. Every
  adoption from outside lands in `contrib/` first; adopting is cheap, promotion
  costs a trial.
- `sd skill try <name>` installs a `contrib/` skill on this machine for thirty
  days and writes a trial row. Direct use during the trial lands in the
  `skill_use` table B's library owns: a `PreToolUse` hook on the `Skill` tool
  and on reads of `skills/*/SKILL.md`, a `UserPromptSubmit` hook for typed
  `/sd-*` commands (marked `direct`), a nightly parse of `~/.codex/sessions`
  for the same, and an OpenCode plugin when that surface is in use.
- Promotion is a pull request that moves `contrib/<name>` to `skills/<name>` and
  adds it to a path; direct use counts as a path of length one. Demotion is the
  reverse. A trial that expires with zero rows is removed at the next install
  run, which says so. A path skill with no use in ninety days is proposed for
  demotion. No demotion on counts happens before ninety days of data exist.
- The dashboard's skills section (B) is a catalog: what each skill does, when to
  use it, use per surface, trials and their expiry, and three buttons. Promote
  and demote call the library to open the pull request. Review runs one
  reviewer pass on the skill, installed, on trial or in `contrib/`, for
  internal consistency and for fit with the installed set, and files each
  recommendation as a proposal; accepted proposals ship as one pull request.
  The operator merges. The dashboard never writes to git.

### Requirement 11 — filing an improvement is one skill and one row

Internal GitHub issues stop being the place new work is filed. Two are open
across repositories the operator contributes to (`sd-ai-command-pack` 1,
`mezmo_benchmark` 1). They are shadowed, not imported: `sd shadow sync` keeps
their state, both stay open on GitHub, and neither is closed with a pointer,
from the operator's decision of 2026-09-05. `mezmo_benchmark` is
`answerbook`'s and eight people can read it, so an issue closed with a pointer
to a database only the operator can reach would take information away from
every other reader and give them nothing. "Owns" was wrong of both
repositories here before that decision: the operator owns
`sd-ai-command-pack` and is the main contributor to `mezmo_benchmark`, which
belongs to the employer.

`sd-suggest` is the one way to file, for the operator and for the agent. It
captures a fixed small set: repository, what happened, what it cost, what was
expected, and the session it came from. It writes a row, in every
repository and every mode, and files nothing anywhere on its own: a
suggestion that belongs in another person's tracker leaves the database
only by `sd suggest publish <row> --to <owner/repo>`, run by the operator,
to the destination the run names, or the one on the repository's row in
B's database once it exists, never a sixth key in `CLAUDE.local.md`, and
refused without one, so that an unattended session cannot turn a
framework incident into someone else's issue, from A's round eighteen and
in line with requirement 6 and the skill's own rule. Issues other people
file on GitHub arrive as read-only shadow
rows through B's sync, with the operator's notes beside them.

The vault `skill-proposal` database, its kind in the writing manifest, and
`sd-propose-skills`'s vault write all go; they were the previous answer to this
requirement, and the routine they depended on, `skill-proposal-accept`, never
existed.

### Requirement 12 — handoff loses nothing, because nothing lives only in context

`sd-handoff` exists and has been used once. It is manual by design: a hook
cannot write `summary`, `next` and `dont`, only the model can, and a model that
has to be asked is not asked.

After this item the packet is the last resort, not the mechanism. Followups,
decisions, proposals and open questions are written to the item's rows as the
session produces them, through the library; nothing that matters lives only in
the conversation. A `PreCompact` hook and a `SessionEnd` hook prompt the model
to write the packet for whatever is left. The `SessionStart` hook loads the
item's open rows, the packet if one exists, and the `claude-mem` context it
loads today. The test of this requirement is a session killed mid-task and
restarted: every followup it had named is on the item, and the new session
begins from them without being told.

### Requirement 13 — the review's confirmed cuts and bugs land

On 2026-09-05 three read-only reviewers read the research flow, the
development flow and the shared scripts against the decisions above. What
follows is every finding they confirmed by source reading, with the seven the
operator's session re-checked by hand. Each line is a cut or a fix; nothing
here adds a mechanism. Plausible findings that need a fixture first are in the
log, not here.

**Development flow.**

- `skills/sd-plan/SKILL.md`: step 6, archive and park (:49-54), goes, with
  `sd-status --parked` (`skills/sd-status/SKILL.md:79`) and the sweep sentence
  in `skills/sd-plan/templates/work-README.md:11`. The flags table for a
  `bin/sd-plan` that does not exist (:57) and
  `--from-suggestion`/`--from-proposal` (:122) go. One
  work-item threshold, the page's, more than one session or about 300 lines
  (:17); `skills/sd-ship/SKILL.md:54` cites it instead of naming 800. Step 1's
  delegation to `sd-grill` (:23) goes: attended, `sd-plan` asks its three to
  five questions itself; unattended, none. `sd-grill` moves to `contrib/` and
  a trial decides whether it stays, by the operator's decision on 2026-09-05.
- `skills/sd-ship/SKILL.md`: rule 5 runs when the pull request exists, at
  step 7 with `--pr-body`, not at step 3 (:41). Step 8 reads Copilot findings
  and never gates; the round budget and the Never at :185 go. The flags table
  and autonomous lane for a `bin/sd-ship` that does not exist (:135-175), the
  pull-request history (:16-34) and the hook narrative (:208-243) go, with the
  standalone `sd-check` run that `sd-review` already performs. Step 11's branch
  deletion (:72) becomes three lines: delete remote, `git fetch -p`, report the
  local branch. `--agent claude|codex` (:141) and `codex exec` (:150) become
  roles. The skill writes the statuses it sets to the row and to no
  file, requirement 5.
- `skills/sd-status/SKILL.md:27` stops listing Lane B carrier branches;
  the accepted-gap ledger (:54) goes with the machinery below. The docstring
  and the table say eight sections while `collect` emits nine; both lists are
  asserted against `collect` in a test.
- `skills/sd-handoff/SKILL.md`: `--push`/`--park` (:104-117) go; the
  `cron-jobs.sh` claim (:84) becomes "headless jobs export
  `SD_HANDOFF_RESTORE=0`"; `Codex/OpenCode` (:73) becomes a role.
- "The five gates" (`skills/sd-spec/SKILL.md:34`), "Standing rule 1"
  (`skills/sd-suggest/SKILL.md:38`, `templates/decision.md:26`) and
  R10-D1 to D7 (`sd-plan:51,97`, `sd-ship:148`, `sd-review:48`) are defined
  nowhere; each citation inlines its rule or goes.
- `--scope planning` reviews one item: the one whose `branch:` is checked out,
  else the single non-done item, `ready` included; more than one candidate
  refuses (`bin/sd-review:514`, `skills/sd-review/SKILL.md:39`), unless
  `--item <directory name>` names one, added 2026-09-05 so that a
  repository with two active items can review one at a time.
- One review-record format, defined in `skills/sd-receive-review/SKILL.md:71`;
  `sd-plan`'s `## Review` (:41) and `sd-ship`'s "record the decision" (:46)
  cite it. Once B lands the record is rows on the item.
- The pre-edit hash baseline in `.claude/rules/sd-planning-adversarial-review.md:4`
  goes; the trigger is that `sd-plan` wrote a planning file.
- `skills/sd-typed-holes/SKILL.md`: the flow commits the skeleton (:64), not
  the user; `agents/sd-rust-reviewer.md` and the step 8 mention go, since a
  same-vendor advisory read is not the reviewer; the `--locked`/`--offline`/
  `build.rs` paragraph in `agents/sd-rust-write.md:56` and
  `agents/sd-rust-fill.md:53` moves to one shared reference; expect markers and
  the grep baseline (:46) go, the clippy `todo` lint stays, warn then deny.
- `skills/sd-red-team/SKILL.md` stays out of the flow; its dispatch section
  (:108-162) moves into `_shared/references/subagent-dispatch.md`.
- The dispatch boilerplate repeated in seven skills (`sd-research:71-116`,
  `sd-fact-check:83-123` and five more) becomes one citation of
  `_shared/references/subagent-dispatch.md`. The "Active item" hook-injection
  clause (`sd-research:112-116`, `sd-fact-check:119-123`, `agents/*.md:17-23`)
  goes; no hook injects it. `references/argument-vocabulary.md`, cited at line
  30 of 56 skills, is an authoring convention: the line goes and the file stops
  shipping.
- `skills/sd-deps/SKILL.md` goes, by the operator's decision on 2026-09-05.
  It restates the classification rules of `local-dependabot/ROUTINE.md` in
  the system repository, for one repository on demand, with no `bin/sd-deps`
  behind it and its own "state of the tooling" admission that the agent
  does the work by hand. Two copies of one rule set is one too many. The
  morning job merges the safe class fleet-wide, and B's Dependencies list
  gives the held rest a filter, a selection and a bulk merge; `ROUTINE.md`
  is the one place the rules live.

**Research flow.**

- `adversarial-gate run` in the system repository's `local-adversarial-gate`
  is the one reviewer entry point. It resolves the reviewer role from the
  registry, takes the document by `--set DOC_PATH=` and drops the diff framing
  (`conventions.md:192-198`, `bin/sd_research_review.py:238-241`), applies the
  `--timeout` it parses (`adversarial-gate.sh:103`), refuses an empty or
  missing `--out` (`:114`), parses the lens's YES/NO line and the CERTAIN count
  and exits non-zero on NO, and writes `pass=N` into the stamp and refuses past
  the table's cap.
- `skills/sd-research/SKILL.md:64-65` and `skills/sd-decide/SKILL.md` gain the
  reviewer step at the point the table names; `skills/sd-publish/SKILL.md`
  gains it before the send box.
- Vendor names go to roles in `skills/sd-research-repo/references/conventions.md:167,175,182-185,224`,
  `skills/sd-research-repo/SKILL.md:84` (which names the plugin the
  conventions forbid), `bin/sd_research_review.py:237-260` and
  `skills/sd-research-repo/templates/CLAUDE.md:87-93`. The three inline
  reviewer prompts (`conventions.md:203-210`, `templates/CLAUDE.md:87-93`,
  `sd_research_review.py:245-250`) go; `render` prints the lens. The
  cross-reference at `conventions.md:176` to a document the installer never
  ships goes. `templates/CLAUDE.md:6-112` shrinks to the pointer at lines 1-4
  and the per-repository Notion folder line.
- `bin/sd_research_review.py`: no `research.conf.py` exits 2 (:173-175, :277);
  an unrendered document fails or the freshness check goes (:197-199).
- `agents/sd-claim-verifier.md:41` emits the five verdicts
  `skills/sd-fact-check/SKILL.md:64-70` requires, verbatim.
- One citation shape, in `_shared/references/source-standards.md`; the review
  greps for it on load-bearing claims or stops implying it checks citations
  (`conventions.md:69,113`, `sd_research_review.py:49-65`).
- `bin/sd-research-kit:132-135` accepts `-C DIR`.
- `skills/sd-brief/SKILL.md:34-39` reads topics from
  `sd store list sdw.topic --status active` and the last-brief date from the
  item row; "saved preferences" goes.
- `skills/sd-paper/SKILL.md:72,81-86,93-97`: `bounds=` on the interview, the
  author approves the brief, the workspace is the item's rows.
- `skills/sd-publish/SKILL.md:57-62,86-92,98-102,152-153`: the source,
  adaptation and omission ledgers and the approval states become one change
  list, and the author approves; the omission ledger stays only for a target
  published under the company's name, by the operator's decision on
  2026-09-05. The 182-line profile contract becomes `tone=`.
  `skills/sd-distill/SKILL.md:60-63,89-90` names `wc -w` or drops the ratio.
- Recorded here, lands with item C,
  `2026-09-05-the-writing-pipeline-runs-on-the-row` in `sd-writing-pack`,
  created 2026-09-05: `sd-writing-pack/scripts/pack.py:735-757`
  refuses `ready` on a NO verdict or a CERTAIN finding without a resolution
  entry, and `pass=N` in the reconcile stamp caps re-runs
  (`sdw-draft/SKILL.md:44`, `pipeline.md:213`, `conventions.md:224`).

**Shared scripts.**

- Bugs: `bin/sd-status:851` passes `root` to `handoff.resolve_root`;
  `bin/sd-docs-lint:242` compares the token before ` - ` with `none` instead
  of `startswith`.
- Cuts: protection gap analysis, acknowledgement loading, both schema files
  and `.github/sd-status.json` (`bin/sd-status:226-836`) become one
  `protected: yes/no` line; `bin/sd_sweep.py`, the `sweep` verb
  (`bin/sd:2703-2737,2916-2925`) and `tests/test_sd_sweep.py`; the archive
  walk and the `archived` and `parked` fields (`bin/sd_lib.py:355-368`,
  `:271-282`, `:302-303`, `:350`) and every reader (`bin/sd-status:183,190,
  1122-1129,1234-1242,1254-1287`, `bin/sd-docs-lint:87-91`), so
  `work_item_dirs` is one `iterdir` that skips `archive` by name; `bin/sd_ledger.py` moves to B with the
  database; `record_load` (`bin/sd-handoff-restore:157-288`); the six helpers
  copied from `bin/sd-handoff` (`bin/sd-handoff-restore:72-140,356-370`) are
  imported the way `bin/sd-status:96` does; the `authors` policy key
  (`bin/sd-review:287`, `:1092`, `bin/sd_setup_github.py:230,267`, the schema,
  `.github/sd-review.json`); the unreachable gito and kimi argv branches
  (`bin/sd-review:830-834`) and `except Refusal` (`:1354-1356`); the constant
  `posted` key and its grep test (`bin/sd-review:1110`,
  `tests/test_sd_review_boundary.py:167`); the second BACKENDS table
  (`bin/sd-status:917`), derived from the registry instead; the residue
  detectors (`bin/sd-status:960-1018`) after one clean run across the fleet;
  the history comments in `Makefile`; `--stash-ref` (`bin/sd-handoff:374`) and
  `carrier_branches` (`bin/sd-status:885-908`); `_git` (`bin/sd-status:123-135`)
  and the other four git wrappers (`bin/sd_lib.py:107`, `bin/sd-pr-state`,
  `bin/sd-handoff:80`, `bin/sd-handoff-restore:72`) become one with a timeout
  argument; `bin/sd-docs-lint:52,72-82,148` imports the vocabulary, the
  directory walk and the in-progress rule from `sd_lib`.
- Consistency: a configuration error exits 2 everywhere (`bin/sd:2930-2946`,
  `bin/sd-status:1269`, `bin/sd-check`, `bin/sd-review:1329`) and JSON
  envelopes carry one version key; one ACTIVE status set in `sd_lib` serves
  `bin/sd-status:1107-1108`, `dashboard/work.py:50` and `bin/sd-review:514`;
  the tiers in `.github/sd-review.json:8` go with their key, since the
  registry order is the chain; settled 2026-09-05.

## What leaves this item

Two requirements of the first draft are gone, recorded here so the trail holds.

- **The writing pipeline** (was requirement 10) moves to C,
  `2026-09-05-the-writing-pipeline-runs-on-the-row`, created 2026-09-05
  in `sd-writing-pack`. Blog writing is
  third in priority behind `mezmo-world-simulator` and `mcp-research`, and its
  ideas and pieces belong in the database, which does not exist yet. The four
  cuts it named (`sdw-review-push`, `sdw-review-pull`, `sdw-help`,
  `sdw-blog-research` folding into `sdw-research`) go with it.
- **One surface per question** (was requirement 11) is superseded. It merged
  three vault databases into one vault backlog. Obsidian is now a knowledge
  base, not a process surface: no ladders, no tasks, no crons, no state the pack
  reads. The backlog is a table in `sd.db`. The two defects that requirement
  found stand as evidence: nine of ten pieces disagree with the vault note they
  name, and the `skill-proposal-accept` routine does not exist.

## Landing order

Items A, B and D depend on each other in both directions, so they land in
slices, each its own pull request, in the order B's `prd.md` records under
the same heading, by the operator's decision on 2026-09-05: B's fixture
harness, library and migrations as rehearsals that retire nothing; then
this item's registry reader, tiered ship path and protection, with the
reader that reads the line or the row as the repository's
`status_source` says; then the `docs/work` migration's retire step, B's one sitting that
freezes, imports once more, verifies and removes the lines, in a pull
request after the one that lands the reader, from A's rounds thirty-six
and thirty-seven, so that the pack installed at every point between
reads every item as it is; then B's dashboard,
read-only and then writing; then D's runner. A slice claims only the
criteria its text names, and only the last slice's merge delivers the
item, `Delivers:` on its message; the others carry `Item:` and leave the
row open, requirement 5. Before the second slice, criteria 13 and 32 are
recorded as waiting, and until D lands a merge the operator makes is
confirmed by the next `sd-ship` run alone.

## Acceptance criteria

1. `WORKFLOW.md` exists at the repository root, states the two flows and the
   spine, the default, opt-in, advisory and never-in-a-shared-repository sets,
   the review table with its caps, and the modes with their resolution rule. It
   is reachable from both `sd-help` and the `CLAUDE.local.md` block the
   installer writes. A test asserts the installer's block names it. A test
   asserts the set of keys `WORKFLOW.md` documents equals the set `sd_lib.py`
   reads, enumerated from `MODES` and `CHECK_NAMES` in the source rather than
   from a list written down beside it, with the consent key beside them. The
   set today is `mode`, `check`, `test`, `lint`, `reviewers`; the test must
   fail if a sixth key is added to either side alone.
2. `sd-ship` invoked on a change with no work item performs no `sd-spec` run, no
   `Work:` line, and no remote-branch deletion command, and its settle step
   issues no shell polling loop. Asserted against the skill text, not inferred.
3. `sd-ship` warns on a commit to the pack, system or writing repository whose
   message lacks a `Needed-by:` trailer, and ships. A test covers the warning
   path and the pass path. The count of missing trailers per week is readable
   from the database once B exists, and from the git log before that.
4. Exactly one second-model lane is named anywhere in the payload, the
   contract, or `AGENTS.md`. A grep of the governed tree for the deleted
   lane returns nothing outside `CHANGELOG.md`. The governed tree, for
   this and every absence assertion below, from A's round twenty-three,
   is what runs or governs: `bin/`, `skills/`, `templates/`, `dashboard/`,
   `tests/`, `.claude/`, `.github/`, `CLAUDE.md`, `AGENTS.md`, `README.md`
   and `docs/spec/`; `docs/work/`, this item and the archive alike, and
   `CHANGELOG.md` are history and are excluded by name, since the archive
   is kept unchanged and holds every name the cuts remove.
5. The review table appears in exactly two places, `WORKFLOW.md` and the one
   rule file under `.claude/rules/`, and a test asserts the two copies are
   identical. Every skill that runs a review names its point in the table and
   reads the cap from it. A grep of the payload for a vendor name (`codex`,
   `claude`, `openai`, `anthropic`) inside a skill's instructions returns only
   the provider-registry documentation.
6. The provider registry format is documented in `WORKFLOW.md` with the role
   vocabulary `author` and `reviewer`, and a test asserts the registry the
   library ships resolves both roles to different providers. Adding a provider
   entry named `exo` with an OpenAI-compatible URL needs no code change,
   asserted by a test that adds one and resolves it. Resolving `reviewer` for
   a change authored by the registry's reviewer provider returns a different
   provider, and fails by name when no other provider carries the role; a test
   asserts both, and asserts that a change authored by `codex` resolves to
   `claude` and one authored by `claude` resolves to `codex`, for every entry
   on the `author` line. The cap: a test sets a bill's remaining room to less
   than one call's bound and asserts the call is refused before dispatch
   naming the bill and the month's total; a second test starts two calls
   concurrently against room for exactly one and asserts one goes and one is
   refused, with the settled rows summing under the cap afterwards. Outside
   the runner: a test ships two commits under
   `SD_AUTHOR=codex` and asserts both carry `Authored-with: codex/openai`
   and that resolution skips every openai entry, and still does after the
   `codex` entry is repointed to an anthropic model and after it is
   removed, with the review of the older branch proceeding in both cases
   and refusing the same vendor; `SD_AUTHOR=nosuch` is refused at commit
   naming the registry; the trailer forms the design page documents,
   `Authored-with:` and `Attributes:`, are asserted equal to the forms
   `sd_lib.py` writes and reads, enumerated from the source; a branch
   with one `claude` and one
   `codex` trailer resolves to the first entry of neither vendor; a branch
   with no trailer and no `--author` is refused naming the flag; a branch
   with one untagged commit followed by one `Authored-with: codex` commit
   is refused naming the untagged commit and `sd attribute`, and after
   `sd attribute <sha> claude` resolves to the first entry of neither,
   the attributing commit itself carrying `Authored-with: human` and
   being accepted by the scan without a second `sd attribute`; a rebase
   of the branch that rewrites the attributed commit makes the review
   refuse again naming the rewritten commit, and one `sd attribute
   <from>..<to> claude` over the rewritten commits resolves it, with
   the attributing commit asserted on the fixture remote after the push
   and its `Attributes:` trailer naming the sha and `claude/anthropic`;
   a Claude-authored slice squash-merged, the default merged back into
   the branch by `sd-ship`, and the branch continued with a
   Codex-authored second slice resolves a Claude reviewer, the set
   excluding the first slice's commits by `slice_base` and the squash
   by the default, and a fresh branch cut from the default with the
   same second slice resolves the same, from A's rounds forty-two and
   forty-three; a Claude session started by the wrapper that edits and
   exits without committing, followed by a Codex session that commits
   the edits with `--author codex`, resolves neither Claude nor Codex,
   a third vendor or a refusal, the row's `authors` naming both, and
   the set is empty after the squash is recorded, both having ended
   clean, from A's round forty-four; a Claude session that exits dirty
   in a second worktree of the branch before the first slice's squash
   is recorded, a Codex session that commits those edits and exits
   clean, and then the first slice's squash recorded, resolves neither
   for the second slice, Claude's entry bound to Codex's commit and
   that commit in no recorded slice, and the entry is gone once the
   second slice's squash is recorded, from A's rounds forty-five and
   forty-six;
   two
   clones attributing two different commits of one branch in turn both
   push without force and the review reads both; `sd attribute <sha>
   human` on an untagged branch resolves to the
   first enabled entry; `sd-review --author claude` is refused as not a
   review flag, and `SD_AUTHOR=codex` in the review's environment changes
   nothing about an untagged commit. Consent at install: the installer writing the block for
   a fixture repository with a two-entry registry asks once and writes the
   answered entries with their recipients as the `reviewers` line, writes
   no line for an empty
   answer, and on a rerun keeps the line it finds and asks nothing; a
   non-interactive run takes `--reviewers` and otherwise writes no line.
   Authorization: a block
   whose `reviewers` line names `claude@claude` alone, with author
   `claude`, refuses naming the key; `claude@claude, codex@codex` with
   author `claude` resolves to
   `codex`, and with `codex` rate-limited refuses rather than reaching
   `minimax`; no `reviewers` line refuses naming the key whatever the
   `author` line holds; a registry with a new entry added resolves nothing
   to it in a repository whose line does not name it, and a second entry
   for a vendor the line already allows under another entry, `baseten`
   allowed and a new `baseten-openrouter` with the same `vendor`, is not
   resolved until the line names it; the `baseten` entry's `url` host
   edited to another host in a repository whose line names
   `baseten@inference.baseten.co` is refused naming both hosts with the
   fixture seeing no request, a `start` entry's executable edited the
   same way is refused naming both, an argument added to its start line
   with the executable unchanged is refused naming the fingerprint, a
   variable in its `env` list whose value in the fixture environment is
   a URL refuses the session naming the variable with no value printed
   and no process started, and a line carrying a bare name is refused
   naming the form; each asserted with a recording fixture
   that sees no request leave for any other entry. The plan: the `minimax` meter reads the two remaining percents
   from a recorded `token_plan/remains` answer and writes them as `meter`
   rows, and a bill whose five-hour or weekly window reads zero is skipped
   in fallthrough and refused by name on a direct pick, asserted with both
   windows in turn. `bin/sd-review` contains no provider table, `sd-review.json`
   contains no key ending in `_providers` and no `tiers` key, and the only
   provider names anywhere in the pack are in the registry. The
   reviewer list falls through: a test disables the first entry, then makes
   it fail preflight, and asserts the second reviews and the output names the
   fallthrough. `sd-review --provider <name>` refuses a name not in the
   registry, and refuses a disabled one by its reason. Every entry carries
   `vendor:`, and a test asserts an entry whose vendor matches the author's
   is skipped. Fallthrough skips every provider on a bill at its cap: a test
   writes cost rows to `cap_usd_month` and asserts resolution passes over the
   bill, and that `--provider` on it refuses with the month's total. A `url:`
   entry whose response carries a `<think>` block and `reasoning_content`
   yields a clean finding list, asserted against a fixture response.
7. The seven `mezmo-world-simulator` passes are scored, accepted against
   rejected per pass with each accepted finding's severity, and the scores
   are recorded on this item before the code review point runs on any new
   pull request. After the ten, a report with the ratio, the highest
   severity accepted, and the cost per pass is on this item, and the code
   point stays or goes by a recorded decision, not by a threshold: a grep
   of `bin/` and `skills/` for a percentage that disables a review point
   returns nothing.
8. The concern-ledger and cross-artifact-sweep obligations are stated as
   conditional on a `sensitive` path in every place they appear.
9. No pack surface requests a Copilot review. The global settings contain no
   Copilot-requesting hook. Both asserted by grep over the rendered payload and
   the settings file. `WORKFLOW.md` states that Copilot review is off on
   repositories the operator pays for personally.
10. A pull request body carries a `Work:` line only when the item exists; the
    `none - <reason>` form appears in no skill, tool, or lint rule. The lint's
    rule 5 passes on a body with no `Work:` line when no work item is present,
    and still fails a body naming an item that does not resolve.
11. Without an explicit `mode:` line, `full` is the resolved mode only when the
    operator holds admin permission on the remote, the repository is not a
    fork, and nobody else has push or higher on it; every other answer
    resolves to `guest`. A test covers six cases: a personal remote only
    the operator can push to, an organisation remote only the operator can
    push to, which resolves to `full`, a remote the operator cannot
    administer, a personal fork of a shared upstream, an owned remote
    with a second collaborator, and a root with no remote or no git at
    all. The last resolves
    to `full` for artifacts, since a local scratch repository has no one to
    expose anything to, and is named and asserted as its own case rather than
    left to whichever branch an exception reaches. An explicit `mode:` line
    wins over detection downward and never upward: a test installs a
    repository with `mode: full`, ships one item, adds a second
    collaborator to the fixture remote, and asserts that the next
    `sd-plan` write places the triad on a local branch naming the
    collaborator, since the fixture holds no fork, that `sd-ship`
    refuses to push a branch carrying the triad to that remote with the
    fixture remote seeing no push, that the item carries a demotion
    note, and that `sd-status` names the artifacts already in the shared
    tree; that with the collaborator removed the next run is `full`
    again with no edit to the line; and, on a guest fixture with a fork
    of the operator's own, that the commit carrying the triad
    reaches the fork's integration branch while the same branch offered
    to the upstream is refused with the upstream seeing no push. Unattended
    merge is never derived from mode: a
    test asserts the loop stops at pull-request-ready in a `full` repository
    whose row lacks `merge: auto`; a second enables `merge: auto` on an
    organisation remote only the operator can push to and asserts the
    merge happens unattended, and a grep of `bin/` for the collaborator
    query finds one function that both gates call; and another enables
    `merge: auto`, ships
    once to merge, adds a second collaborator to the fixture remote, ships
    again and asserts the second stops at `ready_to_send` with the
    collaborator named, the row still `merge: auto`, and the remote asked at
    merge time rather than at dispatch. An unattended merge against a
    fixture remote whose default branch does not require pull requests
    refuses naming the setting, and no test above pushes to the default
    branch, asserted by the fixture remote seeing none. All three modes
    appear in `README.md`.
12. `README.md`'s writes-nothing claim names the installer as its subject and
    lists the skills that write tracked files.
13. Once B's library exists: `sd_lib.py`, `sd-status` and `sd-docs-lint`
    derive an item's status from its row on a machine with the database,
    and once the retire step has run a `prd.md` under `docs/work/`
    outside the archive carries no `status:` line, asserted by the lint
    failing on one seeded, from A's round thirty-three; the migration
    that fills the database reads every item's line outside the archive
    into its row in its import and removes it in its retire step,
    asserted by a test that runs both against a fixture repository
    holding a `done` item and two open ones, diffs after each, and
    asserts that after the import alone every line is still there and
    the pack installed at B's first slice reads them as before, that
    with one open item's line changed to `done` by the old command after
    the import the pack installed at this item's slice reads the line,
    `done`, and not the stale row, under `status_source: file`, and
    answers `unknown` for none, that the retire step refuses
    under a pack whose `sd_lib` has no `delivered`, naming the version,
    that its final import moves that row to `done` and its verify passes,
    that a verify difference seeded after the freeze lifts the freeze
    with every line in place, that an uncommitted `prd.md` makes the
    sitting refuse naming it, from C's round eight, that the sitting killed after the import
    and before `row` reruns to the same rows with every line in place
    until `row`, and killed after `row` and before the commit reruns to
    the commit, from C's round five, that after the retire both `done` items'
    rows are `done` and unmarked, the pull request `sd-ship` opens for
    the retire step carries `Closes:` for both, a database-free clone
    of the default branch at each installed slice, after B's import,
    after this item's reader and before the retire, and after it, picks
    neither, reading the line while the marker is absent and git alone
    once it is present, from A's round forty-one, and a linked
    worktree kept across the retire on a branch still carrying its lines
    reads the row after a status change made in the database, has
    `sd-status` name its line as stale, has the old status command refuse
    naming the sitting, and loses the line in the integration update
    before its merge, CI's lint refusing a pull request that still
    carries one, from A's rounds thirty-four to thirty-eight. A
    status change touches no file, asserted by a test that changes status
    three times and hashes the item's files. In a checkout with no
    database, as in CI, every reader that picks an item asks
    `sd_lib.delivered` and nothing else, asserted by a recording double
    on the library. A test ships an item with `--deliver`, then reads the
    default branch with no database and asserts the merge commit carries
    `Item:` and `Delivers:`, `sd_lib.delivered` answers `yes`, `sd-status`
    reports it done, and `sd-review --scope planning` and `sd-plan` in a
    fresh clone of the default branch do not pick it and, with no other
    item open, refuse naming none; a hand merge through the fixture
    remote with no trailer leaves the row `in_progress`, notes the squash
    commit, and is still picked, and after `deliver` on the item screen
    the row is `done`, `sd-status` names it as unmarked, and the item is
    picked in a database-free checkout until the next pull request in
    that repository merges, its message carrying `Closes:` for it, and
    not after; two slices shipped in turn, the first without `--deliver`,
    leave the row `in_progress` after the first with the squash commit on
    a note, `delivered` answering `no` on an `Item:` merge, and the item
    still picked, and after the second with `--deliver` the row is `done`
    and the fixture remote saw one pull request per slice and no third,
    the same with the second slice continued on the branch, prepared in a
    second worktree of the branch before the first merges, and cut fresh
    from the updated default branch, with no ancestry check anywhere; and
    a clone of the default branch at depth one, taken after one more
    commit lands past the merge, has `sd_lib.delivered` answer `unknown`,
    `sd-review --scope planning` refuse naming the boundary, and after
    `git fetch --unshallow` answer `yes` and not pick the item; a whole
    clone retained before the item is delivered from a second clone
    answers `yes` once its fetch succeeds, `unknown` naming the remote
    and the fetch while the fixture remote is unreachable, and `no`
    never, and a checkout with no remote answers `no` from its own
    history; a whole clone retained on the item's branch while the item
    is cancelled from a second clone, the mark pushed to that branch,
    answers `yes` after its fetch of the branch with the default branch
    unchanged, `unknown` while the remote is unreachable, and `no`
    never, and a guest clone retained on the fork's integration branch
    across a guest delivery the same; a retained worktree on a branch
    the fixture remote deleted at its merge answers `yes` after a
    delivering merge and `no` after a slice's, `unknown` for neither,
    from A's round forty-one. A test
    rejects the merge, and another kills `sd-ship` after the push, and
    both assert that the item is still picked, the directory is
    untouched, and the row is not `done`; a third kills `sd-ship` after
    the API double has accepted the `--deliver` merge and before the
    row's write, and asserts the row is still `in_progress` until the
    next `sd-ship` run, which reconciles it to `done` from the pull
    request the row names with no merge call, and that a run after that
    changes nothing; the same kill on a slice merge reconciles the
    squash commit onto a note and leaves the row open; a fourth cancels, from item
    B's screen, an item whose first slice merged and whose second lives
    on its branch with three implementation commits, and asserts no pull
    request is opened, nothing is pushed, `sd-status` names the row as
    unmarked, the next merge of another item in that repository carries
    `Closes:` for it in its message and changes nothing for it in the
    tree, none of the three commits is in the default branch's history,
    and no `Delivers:` is anywhere in it; a cancel of an item whose triad
    exists on its branch alone leaves the default branch unchanged and
    writes one empty commit on the branch carrying `Closes:` and the
    reason, and in both cases a database-free checkout of the retained
    branch runs `sd-review --scope planning` and `sd-plan` and neither
    picks the item; a fifth cuts a second item's branch before the first
    delivers, delivers the first, and asserts `sd-plan` and `sd-ship` on
    the second's branch touch no file of the first and read no commit of
    the first. The fixture remote is asserted to require pull requests,
    CI and branches up to date, to take the squash message from the pull
    request body, and `sd-status` to report five settings; a hand squash
    merge on the fixture with the dialog's prefilled message is asserted
    to carry every trailer the body carried.
    A test moves the fixture's default branch after the review and
    asserts one integration update, one branch review over the combined
    head that spent no pass, CI, and a merge naming that head; moved
    again during the wait, the run ends `ready_to_send` naming the reason
    with no second update, and the next run makes one; a seeded conflict
    in the update ends the item `blocked` naming the file with no merge
    call. A test ships a guest-mode item whose triad sits on the fork's
    integration branch in two slices, merges the first upstream pull
    request by hand on the fixture, and asserts the row is `in_progress`
    with the squash commit on a note and no mark commit, then ships the
    second with `--deliver`, merges it the same way, and asserts the row
    is `done`, one empty commit carrying `Closes:` is on the integration
    branch, no pull request was opened by the pack, and nothing was
    pushed upstream. A test ships under the default
    policy to `ready_to_send`, merges the pull request by hand on the
    fixture remote with `Delivers: <item>` written in the merge message,
    runs `sd-ship` again in that repository, and asserts the row turned
    `done` and no second pull request was opened; the same hand merge
    without the trailer leaves the row `in_progress` with the squash
    commit on a note, and the item screen's `deliver` then writes `done`;
    the delivering case on a fixture remote that gained a collaborator
    leaves the row `done`, the merge confirmed, and nothing further to
    merge. Every merge test above merges with an actual squash merge and
    asserts that no test pushed to the default branch and no test wrote a
    status into a file. Tests cover all five. The
    pack's installer installs B's
    `sd_db` into the pack's virtualenv as a built copy at the system
    checkout's tag and never editable, from B's round forty-five,
    asserted by a test that runs the
    installer against a fixture system checkout, imports it, and checks
    the imported file is not under that checkout. Before B
    exists, this criterion is recorded as waiting, not as met.
14. `make check` runs documentation-lint rules 1 through 4 when `docs/work/`
    exists, and skips them cleanly when it does not.
15. The coverage floor applies to `bin/sd_install.py` and to no other file. The
    four line-count ceilings emit a warning and exit zero when exceeded. A test
    asserts the warning path, not only the passing one.
16. `make check` accepts a changed-files fast path, and the full suite remains
    the default when no such argument is given.
17. The `bash32` job, `tests/test_selector_contract_drift.py`,
    `generated/registry-snapshot.json` and the `plugins/sd` stub are absent, and
    the `security` job's steps run inside `lint`.
18. A grep of the governed tree, criterion 4, for `Trellis`, `.trellis`
    and `task.py` returns nothing.
19. The global settings contain no `Read()` deny rule and no `.trellis` allow
    rule, and do contain the four MCP pull-request tools. The global guide
    contains no `cd` prohibition.
20. Exactly one file states the planning adversarial review rule.
21. `docs/work/archive/` is untouched: the branch's diff against its base
    under that path is empty, and no pack surface reads it: a test puts a
    `planning` item under `docs/work/archive/` and asserts that
    `sd-status`, `sd-plan` and `sd-review --scope planning` see no item
    there. No item directory is deleted by any pack surface: no mark
    touches a file, `sd-plan` moves, parks and sweeps nothing and deletes
    nothing, no sweep or park code path remains, and a grep of `bin/` and
    `skills/` for `git rm`, `rmtree` and `rmdir` names nothing outside the
    installer's own temporary paths. A test ships a `done` item and runs
    `sd-plan` and `sd-ship` again in that repository, and asserts the
    directory is untouched.
22. The pull-request template links only to files that exist. A test walks its
    links.
23. The caveman plugin is absent from the global settings, and the writing
    repository's style override is deleted.
24. `skills/paths.json` exists, names three paths, and every directory under
    `skills/` appears on at least one. The installer renders exactly the union
    of the paths plus active trials, asserted by a test that adds an unlisted
    skill directory and sees `make check` fail. `contrib/` exists and the
    installer never renders from it without a trial row.
25. `sd skill try <name>` installs from `contrib/`, writes a trial row with an
    expiry, and prints the date. The next install run after expiry with no
    `skill_use` rows removes the skill and says so. Both asserted by tests
    against a temporary database.
26. The `PreToolUse` and `UserPromptSubmit` hooks write `skill_use` rows with
    `surface`, `mode` and `cwd`, and the Codex nightly parse writes the same
    shape. A test feeds one recorded session of each kind and asserts the rows.
27. Promotion and demotion each produce one pull request that moves the
    directory and edits `paths.json`, opened by the library and never by the
    dashboard directly. A test asserts the branch content.
28. `sd-suggest` writes a row in every mode and files nothing, asserted by a
    test per mode against a recording GitHub fixture that saw no call; `sd
    suggest publish` files one issue at the destination `--to` names,
    refuses without one, and is no palette entry, asserted by enumerating
    `commands.yaml`. The two open internal issues stay open on GitHub and
    appear as `shadow` rows after a sync, asserted by a test that runs the
    sync against a recording fixture holding both and then asserts the rows
    and that the fixture saw no close call. The
    `skill-proposal` kind is absent from the writing manifest and
    `sd-propose-skills` writes no vault note.
29. A session killed mid-task and restarted in the same directory begins from
    the followups it had named, with none lost. The test writes three followups
    through the library, ends the session without calling `sd-handoff`, starts a
    new one, and asserts all three are in the injected context.
30. `make check` passes.
32. `sd-ship` pushes only a reviewed head or a verified fix of it, and
    merges naming that head, so a head that moved after the review refuses
    at GitHub rather than merging unreviewed: a test reviews a branch,
    commits a fix, asserts one further pass runs over the fix's diff alone,
    then commits again and asserts the push is refused with the reviewed
    head named, and a test moves the remote head after the review and
    asserts the merge call named the reviewed head and was refused. Before B's library is installed, a test
    asserts the file-only reader and, once it exists, the library resolver
    return the same reviewer order from the same `providers.yaml`, and that
    the loop stops at pull-request-ready in every repository.
31. Requirement 13 is closed line by line. One test lists the symbols, flags
    and files the cuts remove and asserts a grep of the governed tree,
    criterion 4, for each returns nothing: `sd_sweep`, `parked`, `archived`, `record_load`,
    `carrier_branches`, `_protection_gaps`, `load_acknowledgements`,
    `--stash-ref`, `--push`, `--park`, `authors`, `argument-vocabulary`,
    `Standing rule`, `R10-D`, `five gates`, `cron-jobs.sh`, `Active item:`,
    `sd-rust-reviewer`, `sd-deps`. Each bug has a regression test: planning scope on a
    fixture with two planning items and one `ready` item picks the item
    whose branch is checked out and refuses when none is; `sd-status <path>`
    run from another checkout reports the packet under `<path>`;
    `Work: nonexistent-item` fails as an unresolved path, not as a missing
    reason; `adversarial-gate run --timeout 1` against a sleeping command
    exits non-zero within two seconds, and a run whose `--out` is empty
    exits non-zero and names the file; `sd_research_review` on a directory
    without `research.conf.py` exits 2; `sd-research-kit -C <dir> <verb>`
    runs from another working directory; the verdict set in
    `agents/sd-claim-verifier.md` equals the set in
    `skills/sd-fact-check/SKILL.md`, read from both files. One provider
    list, one git wrapper, one status vocabulary and one ACTIVE set exist,
    asserted by a grep that finds no second definition of each.

## Open questions

The five questions the first draft carried and the three the 2026-09-05
review raised are settled and recorded in the log under their dates. None
are open. New questions raised during implementation are filed as rows on
this item once B's library exists, and in the log before.

Nothing waits on the operator. The model pins were written on 2026-09-05,
and the MiniMax plan's windows are read from the vendor's endpoint, not
from a number the operator types.

## Log

- **2026-09-05** — Item opened on `feat/solo-first-workflow-policy`, from a
  five-round interview covering the pack, the writing pack, the system
  repository and the global instruction layer. Six read-only audit agents
  supplied the evidence: the mandatory process path, teammate-visible surfaces,
  skill usage against machine history, cross-layer rule consistency, tooling
  weight, and writing-pipeline throughput. Twenty decisions recorded as
  requirements 1 through 10. The policy page draft exists and lands with the
  first implementation commit.
- **2026-09-05** — Open question 1 settled: the drafted `spec:`, `codex:` and
  `copilot:` keys are cut, and opt-in lanes are asked for by name. Requirement 1
  and acceptance criterion 1 now bound the key set to what `sd_lib.py` already
  reads, checked by enumeration rather than by a list.

  Writing that criterion found a defect in the same edit that introduced it: the
  first draft said the block carries `mode:` and `check:`. It carries four keys,
  `mode:` plus the three `CHECK_NAMES` entrypoints, so the page was wrong by two
  before it was ever written down as policy. Enumerating from `sd_lib.py` caught
  it; reading the draft would not have.
- **2026-09-05** — Open question 2 settled: guest mode covers the shared-repository
  case and the drafted untracked local path is cut. Requirement 6 keeps one piece
  of new code, the mode fallback, and its criterion names three cases including
  the detection-failure path.
- **2026-09-05** — Tracking surfaces consolidated into a requirement 11 that no
  longer exists; see "What leaves this item". Verifying it found two live
  defects that stand as evidence: `skill-proposal-accept`, which
  `sd-propose-skills/SKILL.md:126` relies on, is not in the vault's scheduled
  tasks, which is why `accepted` holds zero notes; and nine of ten pieces
  disagree with the vault note their `obsidian_source` line names, two of them
  active against notes marked `declined`.
- **2026-09-05** — Open questions 3, 4 and 5 settled. Three: delete both
  archive groups, git is the archive; the full enumeration replaced the sample
  and is now in the problem statement. Four: the writing publish closes its
  requirement and defects open their own item; moot an hour later when the
  requirement left this item. Five: the skill-usage undercount is real, uneven,
  and unfixable by counting; the twelve-of-82 figure is withdrawn and no figure
  replaces it, and requirement 10 now installs by path rather than by count.
- **2026-09-05** — Second interview, on the operator's goals rather than the
  pack's defects. Priorities: `mezmo-world-simulator` and `mcp-research` first,
  blog writing third. The operator is visual, forgets commands, tinkers, and
  wants tools perfect before use; the framework has been the rabbit hole, at
  327 commits to 62. Twenty-three decisions taken, and the item split into
  three. What moved into this item: the two-flow policy page, the unattended
  ship path with a soft `Needed-by:` guard, the review table with caps and the
  different-vendor rule, the provider registry, Copilot scoped to where the
  organisation pays, ownership deciding mode, state leaving frontmatter for the
  database, path-based skill installation with `contrib/` and trials, one
  filing skill, and handoff on rows. What moved out: the writing pipeline to C;
  the vault consolidation, superseded by Obsidian's exit from process. What
  moved to B: the database, the library, the runner, the five-section
  dashboard, migrations, the vault crons stopping, and the multiplexer wrapper.

  This week's deliverables, outside this item: the six `mcp-research` drafts
  filed, and `mezmo-world-simulator` Phase 1 to `done`. The seven
  `mezmo-world-simulator` passes are scored before any new code review runs.

  One decision from the interview is corrected here. The 104 Codex sessions
  that run from the Obsidian vault are not scheduled jobs: no launchd job or
  cron script spawns Codex. They are the writing pipeline's hostile-read
  fan-out, `pack.py review adversarial` through `adversarial-gate.sh`, one
  `codex exec` per piece, in bursts of up to eighteen when the pipeline runs.
  There is nothing to unload. The cap in requirement 3 is what governs them.
- **2026-09-05** — Planning review, round one, `sd-review --scope planning
  --challenge` through Codex. Four blocking findings, all addressed.
  - C-1, `design.md` modes: remote ownership cannot establish that nobody else
    merges; a personal fork or an owned repository with collaborators would
    resolve `full` and merge unattended. Addressed: mode detection asks owner,
    not-a-fork, and sole-collaborator, and any other answer is `guest`;
    unattended merge is a separate per-repository policy, `merge: auto`, set
    once by the operator and never derived. Requirement 2, requirement 6,
    criterion 11.
  - C-2, requirement 5: status only in a machine-local database leaves CI's
    documentation lint with nothing to read. Addressed: the `status:` line
    stays as a derived mirror the library writes; the machine reads the row and
    fails on disagreement, CI reads the mirror, `sd-ship` refreshes it before
    committing. Criterion 13.
  - C-3, requirement 5: deleting a `done` directory on the row alone destroys
    untracked or uncommitted files. Addressed: deletion requires a clean, fully
    tracked directory, else the run keeps it and names the files. Criterion 21.
  - C-4, requirement 3: "moves on when the cap is spent" contradicted "blocked
    on an open blocking finding past the cap". Addressed: the cap bounds
    automatic passes; advancement needs every blocking finding dispositioned;
    an open one past the cap marks the item `blocked`. Requirement 2 and 3, and
    the page.
- **2026-09-05** — Planning review, round two, same lane. Three blocking
  findings: two addressed, one recorded on the item it belongs to. This is the
  last remediation round the contract allows.
  - C-5, requirement 5: `git status --porcelain` omits ignored files, so the
    deletion guard could pass over ignored notes or evidence and delete them
    beyond recovery. Addressed: the guard adds `--ignored`, the deletion is
    `git rm -r` of the paths `git ls-files` enumerates and nothing else, and a
    directory left non-empty stays. Criterion 21 gains the ignored-file case.
  - C-6, requirement 5: one machine-local row over a versioned mirror had no
    revision identity; with linked worktrees, a second checkout's committed
    mirror would fail lint, and refreshing it would commit `done` onto
    unfinished work. Addressed: the row carries the item's branch, git holds a
    branch in one worktree at a time, the library writes the mirror only in
    that checkout, comparison happens only there, a `done` row compares with
    nothing, and `done` is never written into a mirror because `done` deletes
    the directory. Every other checkout reads the mirror as CI does. Criterion
    13 gains the three cases; B's `item` table gains the `branch` column.
  - C-7, `2026-09-04-the-sweep-trusts-a-branch-field-it-never-resolves`,
    criterion 5: remote-tracking refs stay until pruned, so counting them does
    not establish that a branch is live. Valid, and not this item's: criterion
    21 removes the sweep, so that item is superseded when this one lands. The
    finding is recorded on that item's Log so it survives if the sweep outlives
    this item. Not addressed here.
- **2026-09-05** — Two gaps recorded from the operator's question on code
  review. First: the registry is static, so a Codex-authored change would
  have resolved `reviewer` to Codex. Resolution now takes the author into
  account and falls through to the next provider carrying the role.
  Second: `bin/sd-review` and `.github/sd-review.json` each carried their own
  provider list beside the registry. The registry owns providers; the other
  two keep policy only. Requirement 3 and criterion 6.
- **2026-09-05** — Fallbacks and direct choice, from the operator's question.
  The `reviewer` line becomes an ordered list; rate limit, missing binary,
  failed authentication, failed run and timeout fall through, and the run
  records which provider reviewed. `sd-review --provider <name>` and a
  dashboard picker choose one directly. Entries gain `vendor:`, `enabled:`,
  `reason:` and `reader:`. Checked while writing this: `prism` and `gito`
  both run `openai/gpt-5.6-sol` through OpenRouter, per `~/.prism/.env` and
  `~/.gito/.env`, so they are OpenAI-vendor reviewers on a metered bill, not
  a second vendor beside Codex; `local-prism/README.md` still says the active
  provider is Moonshot and is stale. `gito` and `kimi` stay disabled until
  each has a verified start line and a reader. Copilot has no local fallback
  to add: the local lane runs before every push, and Copilot only advises.
  Requirement 3 and criterion 6.
- **2026-09-05** — Four answers from the operator, and two corrections.
  Fallthrough runs on its own with the cost logged; `author` is a list picked
  at assignment start; the dashboard is this Mac only; the palette's
  execution model stays open on B. The corrections: the operator
  holds prepaid balances on Moonshot and MiniMax and prefers them over
  OpenRouter, so the reviewer order is subscription, then prepaid, then
  company; and `prism` and `gito` move from OpenRouter to Baseten, which is
  company money and gets the first cap, fifty dollars a month, on its bill.
  The registry gains `bills:`, and entries gain `bill:`, `price:`, `model:`
  and `max_tokens:`. The prepaid balances need the library's own
  OpenAI-compatible client, because `prism`'s fixed output cap is why both
  are recorded as disabled in `~/.prism/.env`. Requirement 3, criterion 6,
  and B's requirements 4, 5 and 6.
- **2026-09-05** — Correction to the entry above: the dashboard is not this
  Mac only. The operator works mostly from an iPad, so B serves it over
  Tailscale, bound to the tailnet address, identified by `tailscale whois`.
  Nothing in this item changes; recorded so the two ledgers agree.
- **2026-09-05** — Carried from item B's planning review, finding C-2 there:
  writing the mirror on every status change was a dual write with no
  recovery path. A status change now writes the row only; `sd-plan` and
  `sd-ship` write the mirror; the lint reports a stale mirror with its repair
  and does not fail. Requirement 5 and criterion 13. Also on criterion 13, by
  the operator's choice: the pack's installer provisions `sd_db`, one
  installer and one place that knows the path. This item's three review
  rounds are spent, so these edits are unreviewed by the lane; the operator
  reads them.
- **2026-09-05** — The operator raised the planning review contract from
  three automatic rounds to five, after item B's third round still found
  three blocking defects. The contract file changes in this commit. The
  review table's prd-and-design cap moves from 1 to 5 to match, in both
  copies, so the page does not contradict the contract the day it lands; the
  operator can set it lower once the first items under the new spine show
  what a round finds.
- **2026-09-05** — Operator request, not reviewed by the lane: the skills
  section gains a review button beside promote and demote. Requirement 10;
  the pass, the lens, the `skill-review` item and the apply path live on
  item B's requirement 5 and criterion 19.
- **2026-09-05** — The operator raised the planning review contract to
  fifteen automatic rounds for this planning exercise. The contract file
  changes in this commit; the review table's cap stays at five, since the
  table is the policy that lands and the contract is the lane running now.
  Item B's round five had found two more blocking defects.
- **2026-09-05** — Requirement 13 and criterion 31, from the review of both
  flows: three read-only reviewers, one per flow and one for the shared
  scripts, 80 findings, 26 of the plumbing set and every flow finding
  confirmed by source reading, seven re-checked by hand in the operator's
  session. Verdicts: neither flow tight; about 1,780 cuttable lines in the
  scripts. Four plausible findings are not recorded as requirements until a
  fixture confirms them: `bin/sd-docs-lint:113,135` bare `read_text`,
  `bin/sd-docs-lint:47` `\bBLOCKING\b` matching prose, `bin/sd_lib.py:92-99`
  closing frontmatter on any `---` prefix, `bin/sd-review:341-342`
  `validate_policy` mutating its argument. The full reports are in the
  session's scratchpad, not in the repository. Three open questions
  reopened; see that section. Requirement 13 is unreviewed by the lane
  until the next round runs.
- **2026-09-05** — Planning review, round three, the first after the cap
  rose to fifteen. Three blocking findings, all addressed. The subject was
  five files, since `--scope planning` still concatenates every planning
  item; requirement 13 fixes that.
  - C-8, requirement 3: with a cap of one on the code point, the fix for a
    blocking finding merged unreviewed. Addressed: one verification pass over
    the diff since the reviewed head, the last automatic pass on that pull
    request; `sd-ship` pushes only the reviewed head or a verified fix. Table
    cell in both copies, criterion 32.
  - C-9, rollout: requirements 2 and 3 were said to need nothing from B while
    reading `merge: auto` from a row and resolving the registry through the
    library. Addressed: the library is a prerequisite for both; until it
    lands the loop never merges, proposals go to the log, and a file-only
    reader in the pack resolves the registry, replaced by the library's
    resolver with a test that both agree. Criterion 32.
  - C-10, design: the reviewer order omitted `claude`, so a Codex-authored
    change went straight to a prepaid balance. Addressed: `claude` second on
    the `reviewer` line, in both copies; criterion 6 asserts resolution for
    every author.
- **2026-09-05** — Planning review, round four. Two blocking findings, both
  addressed.
  - C-11, requirement 5: the branch name was the mirror's identity, so a
    checkout at an older commit on the same branch, after a reset, a rebase
    or in another clone, inherited the row's status and `sd-ship` wrote it
    into the mirror. Addressed: the row carries `rev`, the commit that last
    wrote the mirror; every mirror write refuses unless `HEAD` contains it,
    `--rebind` is the explicit override with a note, and the lint reports a
    checkout behind `rev` instead of comparing. Criterion 13; B's `item` row
    gains the column.
  - C-12, the sweep item's criterion 5: remote-tracking refs do not
    establish liveness, as its own log had recorded from this item's round
    two. Addressed on that item: branch liveness is advisory, one fresh
    `ls-remote` per root, failure reported as unknown, and unknown never
    excludes an item. Requirement 13 still deletes the sweep.
- **2026-09-05** — The three questions from the flow review, settled by the
  operator. `sd-grill`: the `sd-plan` delegation goes and the skill moves to
  `contrib/`, a trial decides; requirement 13. Tiers: dropped, the registry's
  reviewer order is the one chain and `.github/sd-review.json` keeps paths,
  categories, `sensitive` and the severity floor; requirement 3, criterion 6,
  requirement 13, and the design's Providers section. `sd-publish`: one
  change list, the author approves, the omission ledger only for a target
  published under the company's name; requirement 13.
- **2026-09-05** — Planning review, round five. Two blocking findings, both
  addressed.
  - C-13, the sweep item: its criteria 2 and 4 still excluded on liveness
    while its criterion 5 annotated. Addressed on that item: all six
    criteria annotate, nothing excludes.
  - C-14, requirement 3: the assignment row was the only author identity,
    and the small-change path has no row, so a hand-started session could
    be reviewed by its own vendor or refused outright. Addressed: `--author`
    and `SD_AUTHOR` name the author outside the runner, `sd-ship` stamps
    `Authored-with:` on each commit, resolution skips every vendor the
    branch's trailers name, `human` is reviewed by the first entry, and an
    unnamed author is refused with the flag named. Criterion 6; the
    design's Providers section.

- **2026-09-05** — Planning review, round six of fifteen: two blocking
  findings, both addressed.
  - C-15, requirement 5: `done` was never written into a mirror and the
    directory was deleted only at a later `sd-plan` run, so `main`, every
    database-free checkout and CI read a merged item as still open, and the
    single-open-item fallback for `sd-review --scope planning` could pick a
    finished item. Addressed: `sd-ship` writes `done` into the mirror as the
    branch's last commit before the merge; every reader that picks an item
    excludes a `done` mirror; criterion 13 tests the merged tree without a
    database.
  - C-16, requirement 3: the company cap was checked against settled cost
    rows only, so two calls racing for the last of the month could both go,
    and a single call whose cost exceeded the remaining room was not refused
    before dispatch. Addressed: the cap is enforced per call through B's
    reservation, a bound reserved in one transaction with the month's
    settled and reserved rows, refused when it would pass the cap; criterion
    6 gains the oversize-bound and concurrent-call tests.
  - Model pins written into the design's registry block on the operator's
    yes: `kimi-k3`, `MiniMax-M3` with its price marked `unverified`,
    DeepSeek V4 Pro 0813 for both Baseten tools, `max_tokens` 16384 on all.

- **2026-09-05** — Planning review, round seven of fifteen: one blocking
  finding, addressed.
  - C-17, requirement 5: round six's fix wrote `done` into the mirror before
    the merge, so a rejected merge, a failed CI run or a ship killed after
    the push left unmerged work marked `done`, excluded by every picker, and
    eligible for deletion. Addressed: the branch's mirror never says `done`;
    after the confirmed merge `sd-ship` lands one closure commit on the
    default branch that writes `done` and deletes the clean directory, a
    direct push where the branch accepts one and a second pull request
    otherwise; the row records the closure commit and the next `sd-ship`
    run finishes a closure that was interrupted. Criterion 13 tests the
    rejected merge, the killed ship and the interrupted closure.

- **2026-09-05** — Planning review, round eight of fifteen: one blocking
  finding, addressed.
  - C-18, requirement 5: every mirror write requires `HEAD` to contain the
    row's `rev`, and `sd-ship` squash-merges, so the closure commit on the
    default branch would have refused every time and left the row `done`
    while database-free readers still picked the item. Addressed: on the
    confirmed merge the row's branch and `rev` move to the default branch
    and the pull request's `merge_commit_sha`, in the step that sets `done`,
    so the closure is an ordinary mirror write; criterion 13 merges with a
    real squash merge and asserts the guard passed without `--rebind`.
- **2026-09-05** — Cross-item, from B's round thirteen: the closure commit
  carries a `Closes: <item>` trailer, the mark B's runner reconciles against
  when a merge row restarts after the merge. Requirement 5.
- **2026-09-05** — Planning review, round nine of twenty: two blocking
  findings, both addressed, and one operator decision.
  - C-19, requirement 3: fallthrough sent a repository's diff to any
    enabled vendor with budget, and the repository policy file had lost its
    provider lists, so a subscription outage would have shipped confidential
    code to a prepaid or company vendor with no repository-level say.
    Addressed: `.github/sd-review.json` carries `vendors`, the vendors that
    may read the repository; the chain is intersected with it and refuses
    when nothing is left; absent, the author vendors only. Criterion 6;
    design's Providers section.
  - C-20, sweep item: one remote query per root filtered by one item's
    branch could not classify a second remote-only branch in the same root.
    Addressed on the sweep item: every remote head fetched once per root,
    matched locally; fixture with two remote-only branches.
  - Operator decision: `sd-deps` goes; `ROUTINE.md` in the system
    repository is the one rule set and B's Dependencies list is the
    surface. Requirement 13, criterion 31. The open-questions note about
    model pins is closed, the pins having been written.
- **2026-09-05** — Planning review, round ten of twenty: two blocking
  findings, both addressed, and one correction from the operator.
  - C-21, requirement 3: the default for a missing `vendors` list was the
    `author` line, a global list of who is available, not a repository's
    consent, so a shared repository used only with Codex would have sent
    its diff to Claude, and a vendor added globally would have reached every
    such repository. Addressed: `vendors` moves to the `CLAUDE.local.md`
    block as a fifth key, consent written by the operator per repository
    and per machine, derived from nothing; without it no reviewer resolves.
    Criterion 6; design's preface, Providers and Overrides.
  - C-22, requirement 2: `merge: auto` on a row outlived the facts that
    justified it, so a repository that gained a collaborator kept merging
    unattended. Addressed: at every merge the path re-asks the remote the
    three questions, and a no suspends the merge, item `ready_to_send` with
    the answer named, row unchanged and shown suspended. Criterion 11.
  - Operator correction: MiniMax is an annual plan with a monthly token
    grant, not a prepaid balance. Bill basis `plan`, price zero, the grant
    on the bill as `tokens_month`, reservation in tokens; `minimax` moves
    ahead of `kimi` in the reviewer order because plan tokens lapse and a
    prepaid balance keeps. The grant number waits on the operator.
- **2026-09-05** — Operator decision: the default branch is protected in
  every repository the pack merges into, pull requests only and CI required,
  no required approvals. The closure commit is always a second pull request;
  the direct-push path goes; `sd-status` reports the settings and an
  unattended merge into an unprotected branch refuses. Requirement 5,
  criterion 11, design's Defaults.
- **2026-09-05** — The MiniMax Token Plan has no monthly token number: it
  grants use in a five-hour window and a weekly window, and
  `GET https://www.minimax.io/v1/token_plan/remains` with the operator's
  key answered on 2026-09-05 with a remaining percent for each. The
  `tokens_month` placeholder from round ten goes; the bill carries the
  meter, fallthrough skips the bill while either window reads zero, and
  nothing waits on the operator. Requirement 3, criterion 6, design's
  Providers.
- **2026-09-05** — Planning review, round eleven of twenty: two blocking
  findings, both addressed.
  - C-23, requirement 3: consent was keyed to the vendor, the model's
    maker, while the recipient of the diff is the host, so allowing
    DeepSeek allowed Baseten, and a second host for the same model would
    have inherited the consent. Addressed: the key is `reviewers` and names
    registry entries, the recipients; a second host is a second entry with
    no consent until named; `vendor` stays for independence only. Criterion
    6 adds the same-vendor second-entry test.
  - C-24, requirement 3: trailers on some commits were read as provenance
    for the whole range, while only `sd-ship` stamps them, so an untagged
    Claude commit beside a tagged Codex commit let Claude review its own
    work. Addressed: every commit in the range is attributed, by trailer
    or by the declared author, and an untagged commit with no declaration
    refuses naming it. Criterion 6 adds the mixed fixture.
- **2026-09-05** — Cross-item, from B's round seventeen: `sd-ship` merges
  naming the reviewed head, so a head that moved after the review refuses
  at GitHub. Criterion 32; design's Reviews.
- **2026-09-05** — Operator decision: protecting the default branch is one
  dashboard action on an owned repository, B's requirement 5; the design's
  Defaults name it beside the report and the refusal.
- **2026-09-05** — Two decisions of the operator's, shared with B.
  - Requirement 2: a merge made by hand is confirmed by whichever next
    asks GitHub, B's runner watching `ready_to_send` pull requests or the
    next `sd-ship` run, and the same confirmed-merge step follows. The
    closure pull request merges on its own under both policies, since it
    carries only the item's own mirror. Criterion 13 gains the hand-merge
    case.
  - Requirement 5: the installer asks once per repository for the
    `reviewers` line, no default, none accepted, answer kept on rerun.
    Criterion 6 asserts it. Criterion 1 still named four keys and a
    fifth-key failure after C-21 added the fifth; it names five and fails
    on a sixth.
- **2026-09-05** — Planning review, round twelve of twenty: one blocking
  finding, addressed. The first run of the round produced nothing, codex
  timed out, and was rerun.
  - C-25, requirement 5: the closure deleted a clean, committed directory
    with no regard for tracked files outside it that link in, and the pack
    already has a `done` item, `2026-08-29-artifacts-as-product`, linked
    from fourteen lines in twelve files, `AGENTS.md` and seven `docs/spec/`
    pages among them. Addressed: deletion also requires `git grep` to find
    no tracked file outside the directory naming it; otherwise the
    directory stays and the closure names the files that link in.
    Criterion 13 asserts both sides.
- **2026-09-05** — Cross-item, from B's round nineteen: a restart between
  the closure pull request's opening and its merge found no closure commit
  and opened a second pull request. The closure branch is `closure/<item>`
  and a restart finds the open pull request by that head and finishes it.
  Criterion 13 kills `sd-ship` at that point.
- **2026-09-05** — Planning review, round thirteen of thirty: one blocking
  finding, addressed. The round's first run timed out at fifteen minutes
  and was rerun with thirty.
  - C-26, requirement 5: the reader guard matched the literal
    repository-relative path, so a relative link, `work/<item>/design.md`
    from `docs/guide.md` or `../<item>/prd.md` from a sibling item, was
    not a reader and the closure deleted a linked directory. Addressed:
    markdown links are resolved against their source file's directory and
    any that land under the item's directory keep it, beside the literal
    grep. Criterion 13 tests both relative forms and a prefix near-miss.
- **2026-09-05** — Planning review, round fourteen of thirty: two blocking
  findings, both addressed.
  - C-27, requirement 5: the reader scan ran on the closure branch's
    checkout, cut from the merge commit, so a link added to the default
    branch after that was never seen and the deletion merged cleanly
    around it. Addressed: `sd-docs-lint` gains a rule that every link
    into `docs/work/` resolves, required CI runs it on the merge ref, the
    protection requires branches up to date, and a failing closure is
    re-cut with the directory kept. Four protection settings now.
  - C-28, requirement 5: `--author` and `SD_AUTHOR` attributed every
    untagged commit in the range at review time, so a handoff let the
    first agent review its own untagged work under the second's name.
    Addressed: authorship is recorded at commit time only, by trailer or
    by a note `sd attribute <sha> <name>` writes; review takes no author;
    a commit with neither is refused naming the command. Criterion 6.
- **2026-09-05** — Planning review, round fifteen of thirty: three
  blocking findings, all addressed.
  - C-29, design: the workflow page still attributed untagged commits by
    the session's declaration after C-28 removed that from the
    requirement. Addressed: the page reads as the requirement does.
  - C-30, requirement 3: attribution as a note under a shared notes ref
    diverged between two clones, and a force dropped the first. Addressed:
    `sd attribute` writes one empty commit on the branch with
    `Attributes: <sha> <name>` trailers, branch-local, squashed away at
    the merge. Criterion 6 pushes from two clones.
  - C-31, criterion 21: `sd-plan` deleted a clean `done` directory on its
    own, without the reader guard, so a directory the closure kept was
    taken on the next planning run. Addressed: the closure is the one
    deleter, through one eligibility function with one caller; `sd-plan`
    deletes nothing. Criterion 21 runs `sd-plan` over a kept directory.
- **2026-09-05** — Planning review, round sixteen of thirty: two blocking
  findings, both addressed.
  - C-32, requirement 3: the reviewed-head rule had no path for a branch
    the default branch left behind, so under the up-to-date protection a
    second pull request finishing beside a first needed the operator to
    ask for a pass its own changes had not caused. Addressed: an
    integration update, the default branch merged in and nothing else, is
    not a fix and spends no pass; `sd-ship` makes it, reviews the combined
    head once, waits for CI and merges, unattended, as often as the base
    moves.
  - C-33, requirement 5: the archive's 941 files were deleted in one
    commit with no regard for the eleven tracked files that link into the
    archive, `docs/spec/guides/index.md` and the retained
    `artifacts-as-product/design.md` among them. Addressed: the deletion
    commit migrates every reader, links to permalinks at `46ec7fb85`,
    prose gains the commit, the ignore pattern goes. Criterion 21 lints
    the resulting tree.
- **2026-09-05** — Planning review, round seventeen of forty: two blocking
  findings, addressed. The cap was raised from thirty to forty automatic
  rounds by the operator on 2026-09-05, in the contract.
  - C-34, requirement 5: the archive deletion named `46ec7fb85`, the
    import, as the commit that recovers any deleted file, and that tree
    lacks 136 of the 941 files at their current paths, verified by
    `git ls-tree` against `git ls-files`. Addressed: the deletion commit
    names its own parent, the permalinks point there, and every permalink
    path is checked against that tree before the commit is made.
    Criterion 21 reads the hash from the message and checks both.
  - C-35, requirement 3: an integration update exempt from every cap, made
    as often as the base moved, was an unbounded review loop on a busy
    base, and the closure pull requests fed it. Addressed by removing the
    thing that caused it: the up-to-date protection setting is gone, so a
    mergeable pull request merges as reviewed and no automatic integration
    update exists; a conflict ends the item `blocked` for the operator's
    hand, whose integration commit spends no pass and is reviewed once.
    Criterion 13 covers the conflict path and the three settings.
  - Operator's decisions, the same day, from the improvement list: a
    `done` item's directory is kept, never deleted by the pack, which
    removes the reader scans, the lint rule, the eligibility function, the
    re-cut path and the up-to-date setting from requirement 5 and criteria
    13 and 21; each registry entry names its `env` variables and a session
    receives those and a fixed base only, requirement 3 and the design's
    Providers section; the runner is split out of B into item D, and the
    references here follow; the three items land in slices in the order
    under Landing order, recorded in full on B.
- **2026-09-05** — Planning review, round eighteen of forty: two blocking
  findings, addressed; and one cross-item correction from B's round thirty.
  - C-36, requirement 11: `sd-suggest` filed a GitHub issue in a repository
    someone else merges, against requirement 6 and the skill's own rule,
    and an unattended session could file it. Addressed: a row everywhere,
    nothing filed on its own; `sd suggest publish <row>` is the operator's
    step, to a configured destination, and no palette entry. Criterion 28.
  - C-37, requirement 5: the closure assumed the merged tree held the
    mirror, and in `guest` mode the triad lives on the fork's integration
    branch, so rebinding to the upstream squash commit left the closure a
    tree with no mirror. Addressed: the guest closure is one commit on the
    integration branch, `rev` moves there, nothing upstream. Criterion 13.
  - Cross-item, from B's round thirty and D's round one: three protection
    settings with no integration update, round seventeen's C-35 fix, let
    two parallel pull requests that each pass alone merge clean and break
    the default branch after delivery. Withdrawn: the up-to-date setting is
    back, the integration update is back and bounded, one per `sd-ship`
    run and one per merge-lane turn, a second on a hand-moved base and
    `blocked` past it. Requirements 3 and 5, criterion 13, the design's
    Defaults and path.
  - Self-found, the same hour: the first wording of C-36 put the publish
    destination in `CLAUDE.local.md`, a sixth key that criterion 1 refuses.
    The destination is `--to` on the run, or the repository's row once B
    exists.
- **2026-09-05** — Planning review, round nineteen of forty: three
  blocking findings, addressed.
  - C-38, requirement 3: filtering the inherited environment was called
    credential isolation, and a session that runs as the operator in the
    operator's `HOME` can read the environment file and a login shell it
    starts sources it back. Addressed by scoping the claim to what it is:
    a session does not inherit another vendor's key, and nothing more.
    D's criterion 5 asserts the gap with a child login shell. The design's
    Providers section says the same.
  - C-39, requirement 3: a thirty-percent acceptance ratio removed the code
    review point on its own, and a reviewer that catches one data-loss
    defect in ten passes fails that ratio. Addressed: the experiment ends
    in a report with severity and cost beside the ratio, and the operator
    decides, recorded here. Criterion 7.
  - C-40, requirement 3: `sd attribute` wrote an empty commit with no
    `Authored-with:` trailer of its own, so the repair created what it
    repaired. Addressed: the attributing commit is stamped `Authored-with:
    human`. Criterion 13's attribution test covers it.
- **2026-09-05** — Planning review, round twenty of forty: two blocking
  findings, addressed.
  - C-41, requirement 3: an `Attributes: <sha>` trailer names a hash, and a
    rebase or an amend of the attributed commit changes it, so resolved
    authorship became unknown again with no stated repair. Addressed by
    stating it: the pack never rewrites a branch, both integrations merge,
    so the case is the operator's own rewrite; the review refuses naming
    the rewritten commits and one range attribution, `sd attribute
    <from>..<to> <name>`, restores it. Criterion 13's attribution test
    rebases and re-attributes.
  - C-42, design: the page that ships as `WORKFLOW.md` still made thirty
    percent accepted the condition for keeping the code point, which
    requirement 3 and criterion 7 had withdrawn in round nineteen.
    Addressed: the page requires the severity-and-cost report and the
    operator's decision, with no threshold.
- **2026-09-05** — Operator's decisions after round twenty, from the list
  of seven presented with it.
  - Two: `docs/work/archive/` stays, and the pack stops reading it. This
    overturns the first draft's answer to open question 3, and the
    machinery of C-33 and C-34, the recovery commit, the permalinks, the
    migrated readers, is not built. Requirement 5, requirement 13's
    `work_item_dirs` cut, criterion 21.
  - Six: the environment gap of round nineteen, inheritance and not
    isolation, is accepted for now. A per-vendor credential store is not on
    this item and no criterion claims one.
  - Three: `sd-review --item` names one active item in a repository that
    has two, so that B is reviewed alone while D waits for its spike.
    Requirement 13's `--scope planning` line; landed in the pack the same
    day with its test.
- **2026-09-05** — Operator's decision one, the last of the seven: the four
  protection settings stay, pull requests only, CI required, branches up to
  date, no approvals, with the bounded integration update of round
  eighteen. Three settings and a red-main gate was the alternative. No text
  changes; requirement 3 and criterion 13 already say this.
- **2026-09-05** — B's C-59, cross-item: a `start` entry on a capped bill
  carries `session_bound_usd`, reserved at session start; the reader
  refuses one without it. Requirement 3's cap passage.
- **2026-09-05** — Planning review, round twenty-one of forty, the first
  on this item alone: two blocking findings, addressed.
  - C-43, requirement 3: the session bound of B's round thirty-three was a
    reservation and not a limit; a subprocess that retries or takes one
    more turn passes it with the money spent, and settling the usage read
    finds the cap broken after the fact. Addressed as B's C-60, the same
    finding: a capped bill takes `url` entries only, the reader refuses a
    `start` entry on one naming both, and `session_bound_usd` is gone.
    Today both `baseten` entries are `url` entries.
  - C-44, requirement 5: the closure pull request was the only path by
    which a database-free reader learned an item was delivered, and its
    convergence had no bound while closure CI was red. Addressed: the
    merge message carries an `Item:` trailer, `sd_lib.delivered` derives
    `done` from the default branch's history, every picker excludes a
    delivered item, and the closure is left with putting the word in the
    file; the hand-merge residue is stated. Criterion 13.
- **2026-09-05** — Planning review, round twenty-two of forty: two
  blocking findings, addressed.
  - C-45, requirement 5: `delivered` read the default branch's history as
    if it were whole, and a shallow clone taken after a later commit can
    hold neither the trailer nor a `done` mirror while closure CI is red.
    Addressed: `delivered` answers `yes`, `no` or `unknown`, `unknown` on a
    shallow checkout with no trailer in reach, and a picker refuses an
    `unknown` naming the boundary and the fetch that resolves it.
    Criterion 13 clones at depth one.
  - C-46, design: the registry still had `prism` and `gito` as `start`
    entries on the capped Baseten bill, which requirement 3 refuses, and
    round twenty-one had said they were `url` entries; they were not.
    Addressed: the two CLIs leave the registry and one `url` entry,
    `baseten`, takes their place through the library's client; the
    reviewer list, the consent line and the vendor passage follow.
- **2026-09-05** — Planning review, round twenty-three of forty: two
  blocking findings, addressed.
  - C-47, requirement 5: one merge turned the row `done`, landed the
    closure and made `delivered` exclude the item, while the landing order
    splits this item over several pull requests. Addressed: `Item:`
    associates and closes nothing; the delivering merge carries
    `Delivers:`, written by `sd-ship --deliver`, by D's runner on a row
    marked `final`, or by the operator's hand, and `delivered` answers on
    `Delivers:` and `Closes:` only; the item screen offers `deliver` for a
    hand merge that was the last. The landing order says so; criterion 13
    ships two slices.
  - C-48, criteria 4, 18 and 31: repository-wide absence greps hit the
    archive, kept unchanged since round twenty and holding `R10-D6` among
    every name the cuts remove, so `make check` would fail for good.
    Addressed: the absence assertions grep a governed tree named once in
    criterion 4, code and governing files, with `docs/work/` and
    `CHANGELOG.md` excluded by name as history.
- **2026-09-05** — Planning review, round twenty-four of forty: one
  blocking finding, addressed.
  - C-49, design and criterion 13: the page that ships as `WORKFLOW.md`
    still closed the item on any confirmed merge, and criterion 13 still
    asserted completion on a hand merge with no delivery trailer, both
    behind round twenty-three's `Delivers:` rule. Addressed: the page
    states the one delivery transition, `Item:` associates and
    `Delivers:` closes, with the item screen's `deliver` for a hand merge;
    every completion assertion in criterion 13 names `--deliver` or
    `deliver`, and the residue passage says the row is `done` from
    `deliver` and git knows at the closure.
- **2026-09-05** — Planning review, round twenty-five of forty: one
  blocking finding, addressed.
  - C-50, requirement 6: a stored `mode: full` kept placing and pushing
    planning artifacts after the repository gained a collaborator, since
    the three questions were asked again only at merge time, after the
    push had disclosed them. Addressed: the questions are asked before
    every artifact write and every push, a stored `full` is a floor and
    never a ceiling, a `no` makes the run `guest` and refuses the push
    naming the answer, and `sd-status` names what is already in the tree.
    Criterion 11 installs `full`, adds a collaborator, and asserts the
    demotion; the design's Modes section says the same.
- **2026-09-05** — Planning review, round twenty-six of forty: two
  blocking findings, addressed.
  - C-51, requirement 6: the first of the three questions asked whether
    the owner is the operator, which `mezmo-world-simulator` under the
    `answerbook` organisation can never answer yes, and round twenty-five
    had made the live answer override a stored `full`, so the contract
    demoted the repository the requirement names as staying `full`.
    Addressed: the questions ask about access, admin permission for the
    operator and push for nobody else, and never about the namespace.
    Criterion 11 gains the organisation case; the design's Modes section
    says the same.
  - C-52, requirement 6: the pre-push rule refused any branch carrying
    the triad whenever the remote answered `no`, and requirement 5's guest
    closure pushes exactly such a branch to the fork's integration branch,
    so no guest closure could complete. Addressed: the check is of the
    destination, the fork's integration branch is the operator's own
    remote and the push there proceeds, the same branch offered upstream
    is refused, and an owned repository with no fork keeps the triad on a
    local branch. Criterion 11 asserts both pushes on a guest fixture.
- **2026-09-05** — Planning review, round twenty-seven of forty, with B's
  round forty-one in the same batch: two blocking findings here,
  addressed, and one cross-item change from B's C-72.
  - C-53, requirement 2: the merge gate still asked whether the owner is
    the operator after round twenty-six had made requirement 6 ask about
    access, so an organisation repository the operator alone administers
    was `full` for artifacts and refused for unattended merge. Addressed:
    one predicate in the library, called by both gates and restated by
    neither. Criterion 11 merges unattended on an organisation fixture
    and greps for one function; the design's Modes section follows.
  - C-54, requirement 3: consent was bound to an entry's name, and an
    entry whose `url` was edited to another host kept every repository's
    grant. Addressed: the line names the recipient beside the entry,
    `baseten@inference.baseten.co`, the library derives the recipient
    from the registry at every review, and a mismatch refuses naming both
    with no request sent. Criterion 8 edits an allowed entry's host and
    executable; the design's Providers and Overrides sections follow.
  - B's C-72: `cancel` lands the same closure as delivery, with the
    `cancelled` note and no delivering merge, so a cancelled item is
    closed in every checkout. Requirement 5, criterion 13.
- **2026-09-05** — Planning review, round twenty-eight of forty: two
  blocking findings, addressed.
  - C-55, requirement 5: round twenty-seven had `cancel` reuse the
    delivery closure, whose `rev` guard fails for an item whose commits
    live on its branch alone and whose closure would carry the abandoned
    branch into a pull request that merges on its own. Addressed: a
    cancellation closure of its own, cut from the default branch, touching
    the mirror's status line and note alone, outside the `rev` guard, and
    landed only where the default branch holds the mirror; otherwise no
    closure and a note naming the branch. Criterion 13 cancels a
    half-merged item and asserts none of its branch lands.
  - C-56, requirement 3: an executable's name did not identify the
    recipient of a `start` review, since an argument, a configuration
    file or a variable can send the same tool elsewhere. Addressed: the
    recipient of a `start` entry is the executable with a fingerprint of
    its line and `env` names, a session is refused any variable whose
    value is a URL, and the tool's own configuration is named as the one
    place consent does not reach. Criterion 8 changes an argument and a
    variable with the executable unchanged; the design's Overrides follow.
- **2026-09-05** — Planning review, round twenty-nine of forty: two
  blocking findings, addressed.
  - C-57, requirement 5: a cancelled item whose triad lived on its branch
    alone got no closure, and a database-free checkout of that retained
    branch read an open mirror with no trailer in default-branch history,
    so its pickers selected the cancelled item again. Addressed: `cancel`
    writes one terminal commit on the item's branch, the status line and
    the note with `Closes:`, and the branch's own mirror says `done`.
    Criterion 13 picks from a database-free checkout of the branch in
    both cancellation cases.
  - C-58, criterion 13: the default-policy hand-merge test had `sd-ship`
    close the item on a merge that carried no `Delivers:`, which
    requirement 5 says leaves it open. Addressed: the fixture's hand
    merge writes the trailer, and the same merge without it is asserted
    to leave the row `in_progress` until the item screen's `deliver`.
- **2026-09-05** — Planning review, round thirty of forty: one blocking
  finding, addressed. The first run of this round timed out in the
  provider and was rerun.
  - C-59, requirement 5: every merge moved `rev` to its squash commit,
    and a second slice continued on the item's branch does not contain
    that commit, so the next mirror refresh refused and `--rebind` sat on
    the ordinary path of every item that lands in more than one pull
    request. Addressed: a slice merge leaves `rev` with the branch and
    notes the squash commit; only the delivering merge moves `rev` and
    the branch. Criterion 13 ships two slices three ways, continued on
    the branch, prepared in a second worktree before the first merges,
    and cut fresh, all without `--rebind`; the design page follows.
- **2026-09-05** — Cross-item change from B's round forty-five, C-77:
  the installer installs `sd_db` as a built copy at the system checkout's
  tag, never editable. Criterion 13 follows.
- **2026-09-05** — Planning review, round thirty-one of forty: two
  blocking findings, addressed. The first run of this round timed out in
  the provider and was rerun with a longer timeout.
  - C-60, requirement 5: with `rev` left on the branch after a slice
    merge, a second slice cut fresh from the updated default branch
    contained the squash and not `rev`, so the guard refused what
    criterion 13 said passes. Addressed: the guard also accepts a `HEAD`
    that contains the newest squash commit the row noted, the item's own
    confirmed merge, and moves `rev` to it with a note. Criterion 13's
    fresh-slice case says so.
  - C-61, requirement 5: the closure was a status-only pull request after
    every delivery, a second CI-and-merge cycle per item that moved the
    protected default branch under every other open pull request and
    left a retry obligation while red, to put in a file a word the
    delivering commit's trailer already carries. Addressed: no closure
    pull request; the next commit `sd-plan` or `sd-ship` makes in the
    repository refreshes every `done` mirror and carries `Closes:` for
    each, cancellation on the default branch rides the same way, the
    guest fork's one commit and the branch-only cancel commit stay, and
    the residue is bounded by the next ship and named by `sd-status`.
    Criterion 13 asserts one pull request per slice and no third, the
    refresh in a later ship, and the killed-ship cases; criterion 11's
    closure assertion becomes no push to the default branch. Items B and
    D follow; the operator's decision that the closure is the one merge
    not made by hand is moot and recorded so.
- **2026-09-05** — Planning review, round thirty-two of forty: one
  blocking finding, addressed.
  - C-62, requirement 5: round thirty-one's refresh of every `done`
    mirror ran the delivered item's guard against another item's
    checkout, and a branch cut before that delivery does not contain the
    squash, so the other item's next commit refused. Addressed: the
    refresh takes only the mirrors whose `rev` the checkout contains and
    leaves the rest pending; `sd-ship` refreshes after its integration
    update, so a branch that reaches the merge carries every closure the
    default branch held; the refresh moves no `done` row's `rev`, and the
    row records its closure on the confirmed merge whose message carries
    `Closes:` for it. Criterion 13 cuts a second item's branch before the
    first delivers and asserts both commits.
- **2026-09-05** — Planning review, round thirty-three of forty: one
  blocking finding, addressed by the operator's decision that also
  closes rounds thirty to thirty-two.
  - C-63, requirement 5: the deferred refresh added a commit after the
    integration update, so the reviewed head and the pushed head
    differed, and the unattended path either pushed an unreviewed commit
    or stopped for a pass. The reviewer offered the simpler design,
    deriving terminal state from git trailers with no rewrite of other
    items' files, and the operator took it: the `status:` line leaves
    `prd.md`, the migration reads it into the row and removes it, a
    status change writes the row and nothing else in any checkout, and a
    database-free reader asks `sd_lib.delivered` and nothing else. With
    the line go `rev`, the guard, `--rebind`, `sd mirror refresh`, the
    lint comparison, the closure, and `closure pending`. `Closes:` stays
    for the two cases with no `Delivers:` of the pack's on the branch a
    checkout reads: the next merge message `sd-ship` writes in the
    repository, at merge time through the API and touching no tree, and
    one empty commit on the item's own branch, for a branch-only cancel
    and for the guest fork. Requirement 5 and criterion 13 rewritten,
    criteria 11 and 12 and the design page follow; items B and D follow.
- **2026-09-05** — Planning review, round thirty-four of forty: two
  blocking findings, addressed.
  - C-64, requirement 5: the migration read only open items, and a
    historical `done` item outside the archive, four in this repository,
    either failed the new lint or lost its terminal state with its line.
    Addressed: the migration reads every item outside the archive, a
    `done` one lands as an unmarked `done` row, and the pull request that
    lands the migration carries `Closes:` for each. With it, the mark
    moves from the merge message alone into the pull request body's
    trailer block, which `sd-ship` writes into the merge message and a
    hand squash merge takes from the body through the repository setting
    `squash_merge_commit_message: PR_BODY`, a fifth setting the installer
    sets and `sd-status` reports; under the default policy the operator
    types no trailer, and the residue is bounded by the next pull request
    rather than the next unattended merge. Criterion 13's migration
    fixture holds a `done` item; the fixture remote takes the squash
    message from the body.
  - C-65, requirement 5: guest mode wrote `done` on any confirmed
    upstream merge, so a first slice closed the item. Addressed: the row
    decides by the same word as elsewhere, `--deliver`, `final`, or
    `deliver` after the fact; an upstream merge without it is a slice.
    Criterion 13's guest fixture ships two slices.
- **2026-09-05** — Planning review, round thirty-five of forty: one
  blocking finding, addressed.
  - C-66, requirement 3: `Authored-with:` named a registry entry, and the
    independence rule resolved its vendor through the registry at review
    time, so an entry repointed to another vendor's model or removed
    after the commit misidentified an older branch's author, permitting
    a self-review or blocking the review until re-attribution.
    Addressed: the trailer carries `<name>/<vendor>`, the vendor the
    registry gave at commit time, `Attributes:` the same, an unknown
    entry is refused at commit, and the rule reads the author's vendor
    from the trailer and the candidate's from the registry. Criterion 7
    repoints and removes the entry after the commits.
- **2026-09-05** — Planning review, round thirty-six of forty: one
  blocking finding, addressed.
  - C-67, landing order: requirement 5 read as if the migration imported
    and removed the lines in one step in B's first slice, before this
    item's reader, trailer-writing ship path and `PR_BODY` setting
    landed, so a pack installed between slices read a migrated item as
    `unknown` and the migration lacked its completion handoff. Addressed
    by saying what B's requirement 2 already ordered: the import is
    additive and retires nothing, this item's slice lands a reader that
    reads the row where the database is and the line where it still is,
    and the retire step runs after that in a pull request of its own,
    refusing under a pack whose `sd_lib` has no `delivered`. Criterion 13
    tests each installed version, not only the completed stack.
- **2026-09-05** — Planning review, round thirty-seven of forty: two
  blocking findings, addressed.
  - C-68, requirement 5: between B's rehearsal import and the retire
    sitting the old pack still wrote the line, and a reader that
    preferred the row reopened an item completed in the interval and
    let the retire delete its newer status with no `Closes:`. Addressed:
    until the retire the line is the record, the rows are a rehearsal,
    and the reader reads the line where there is one and the row where
    there is none; the retire is B's one sitting, freeze, final import,
    verify by content, snapshot, remove, and lifts the freeze with
    nothing removed when the verify differs. Criterion 13 changes a
    line between the slices and asserts each installed version and the
    sitting's final import.
  - C-69, design: the page still wrote `Attributes: <sha> <name>` after
    round thirty-five moved the trailers to `<name>/<vendor>`.
    Addressed on the page; criterion 7 asserts the page's trailer forms
    equal the library's, enumerated from the source.
- **2026-09-05** — Planning review, round thirty-eight of forty: one
  blocking finding, addressed.
  - C-70, requirement 5: a line's presence was the marker of the
    migration's state, and a branch or linked worktree kept across the
    retire keeps its lines, so the reader there read a stale
    `in_progress` over the row and picked finished work. Addressed: the
    repository's row carries `status_source`, `file` until the sitting
    sets `row`; under `row` the reader ignores a line anywhere, reports
    it as stale with the integration update as the repair, and the old
    writers refuse; with no database no line is read at all. Criterion
    13 keeps a worktree across the retire and changes a status after.
- **2026-09-05** — Planning review, round thirty-nine of forty: two
  blocking findings, addressed.
  - C-71, requirement 5: `delivered` answered `no` from a whole history
    that was not a current one, so a clone retained while another
    machine delivered or cancelled the item let planning pick finished
    work. Addressed: the function fetches the default branch from the
    remote before it answers, answers `unknown` naming the remote and
    the fetch when the fetch fails, and answers from its own history
    only where there is no remote. Criterion 13 retains a whole clone
    across a delivery from a second clone.
  - C-72, requirement 5: the recovery contract assumed GitHub's
    acceptance and the row's write were one step, so a kill between
    them left delivered work open to database-backed pickers.
    Addressed: the row names its pull request from the moment it is
    opened, and every restart reconciles first, asking GitHub for the
    pull request's state and `merge_commit_sha` and applying what the
    row does not yet carry, idempotently. Criterion 13 kills between
    the API double's acceptance and the row's write, on a delivering
    merge and on a slice.
- **2026-09-05** — Planning review, round forty of forty, the last
  automatic round: one blocking finding, addressed.
  - C-73, requirement 5: `delivered` fetched the default branch alone,
    and the mark for a branch-only cancel or a guest delivery lives on
    the item's branch, so a clone retained on that branch fetched,
    found nothing, and answered `no` for cancelled work. Addressed: the
    function fetches the default branch and the checkout's branch from
    its upstream, and reads from both as fetched. Criterion 13 retains a
    clone on the item's branch across a cancel from a second clone, and
    a guest clone across a guest delivery.
- **2026-09-05** — Planning review, round forty-one, one confirmation
  round granted by the operator past the cap: two blocking findings,
  addressed, and one cross-item change from B's round forty-nine.
  - C-74, requirement 5: round forty made `delivered` need both fetches
    to succeed, and requirement 2's `delete_branch_on_merge` removes the
    item's branch at its merge, so a retained worktree on that branch
    answered `unknown` for ever with the trailer on the default branch.
    Addressed: the default branch is fetched first and answers `yes`
    alone; the branch is fetched only otherwise; a ref the remote no
    longer has is nothing to be behind; an unreachable remote stays
    `unknown`. Criterion 13 retains a worktree across the deletion.
  - C-75, requirement 5: between this item's reader and the retire, a
    database-free clone read no line and asked git alone, and the
    historical `done` items' `Closes:` arrive only with the retire
    step's pull request, so it picked delivered work. Addressed: the
    retire commit adds a tracked marker, `docs/work/.status-source`;
    without it a database-free reader reads the line as well, with it
    git alone; a checkout with a database asks the row and never the
    marker. Criterion 13 tests a database-free clone at each slice;
    the design page's sentence dates itself to the retire.
  - B's C-81: `status_source` gains `retiring`, the sitting's own value
    and its freeze; every status writer reads it in the transaction that
    writes and refuses under it. Requirement 5, criterion 13.
- **2026-09-05** — Item C created, cross-item: the two places that said
  "item C" name it, `2026-09-05-the-writing-pipeline-runs-on-the-row` in
  `sd-writing-pack`. Requirement 13 and What leaves this item.
- **2026-09-05** — C's round five, cross-item: the retire sitting removed
  the lines and then set `row`, so a run that died between the two left
  the repository frozen with nothing to import. `row` is set before the
  removal, every step idempotent, the same command reruns. Requirement
  5, criterion 13.
- **2026-09-05** — Planning review, round forty-two of forty-six: one
  blocking finding, addressed.
  - C-76, requirement 3: the author set was built from the branch since
    its merge base, and a branch continued after a squash merge keeps
    the earlier slice's commits there for its life, so a Claude slice
    followed by a Codex slice excluded both vendors from reviewing the
    second. Addressed: the range's base is the slice base, the branch
    head the row records as `slice_base` when it records a slice's
    squash commit, the merge base where there is none. Criterion 13
    runs the two-vendor, two-slice case.
- **2026-09-05** — Planning review, round forty-three of forty-six: one
  blocking finding, addressed.
  - C-77, requirement 3: `slice_base..HEAD` still held the first
    slice's squash commit once the default was merged back, since the
    squash is no ancestor of the head it squashed, so the scan refused
    it as untagged or counted the first vendor again; a fresh branch
    from the default had the same. Addressed: the set is what `HEAD`
    reaches and neither the default nor `slice_base` does, `git
    rev-list HEAD --not <default> <slice_base>`. Criterion 13 merges the
    default back before the second slice and runs the fresh-branch
    case.
- **2026-09-05** — Planning review, round forty-four of forty-six: one
  blocking finding, addressed, and one cross-item change from C's
  round eight.
  - C-78, requirement 3: a session that edits and exits without
    committing leaves its work to the next session's commit, whose
    trailer names the committer alone, so Claude's edits shipped by
    Codex let Claude review them. Addressed: every session the runner
    or the wrapper starts on the branch adds its vendor to the row's
    `authors` for the slice, cleared with `slice_base`, and the
    reviewer's set joins the trailers with it. Criterion 13 runs the
    uncommitted handoff.
  - C's C-16: the retire sitting reads `HEAD`'s tree and refuses on a
    dirty `docs/work`, so the marker commit's parent is what the verify
    saw. Requirement 5, criterion 13.
- **2026-09-05** — Planning review, round forty-five of forty-six: one
  blocking finding, addressed.
  - C-79, requirement 3: clearing `authors` at the squash erased the
    entry of a session that had started the second slice before the
    first merged and left its edits uncommitted, so Codex's commit of
    them let Claude review. Addressed: the squash clears only entries
    whose session ended with a clean tree, recorded by the wrapper and
    the supervisor at exit; a dirty or running entry survives it and
    clears at the squash after a later clean end. Criterion 13 runs the
    combination.
- **2026-09-05** — Planning review, round forty-six of forty-six: one
  blocking finding, addressed, and one cross-item change from B's
  round fifty-four.
  - C-80, requirement 3: a clean exit did not prove the edits belonged
    to the slice being merged; Codex committing Claude's second-slice
    edits and exiting clean let the first slice's squash clear Claude.
    Addressed: an entry that ended dirty stays until the first commit
    after its recorded head is an ancestor of `slice_base`, the commit
    carrying its edits in a recorded slice; a clean exit clears at once,
    its trailers standing. Criterion 13 runs the sequence.
  - B's C-86: the retire sitting reads every branch of the remote and
    refuses naming an item whose branches disagree. Requirement 5.

- **2026-09-05** — Adversarial planning review of `implement.md`, one lane,
  ten findings: four blocking, five material, one minor, and six candidate
  findings refuted before recording. The lane read the `prd.md` as the
  authority and checked every citation on the filesystem. Its two category
  verdicts came back clean: every value appearing in both documents agrees,
  and every path, line citation and symbol in `implement.md` resolves. The
  findings are addressed in `implement.md`; the two that reach this file are
  recorded here.
  - **C-88, requirement 11 called both repositories the operator's own.** It
    read "Two are open across repositories the operator owns
    (`sd-ai-command-pack` 1, `mezmo_benchmark` 1)". `mezmo_benchmark`'s
    remote is `git@github.com:answerbook/mezmo_benchmark.git`: the employer's
    repository, eight contributors, of which the operator is the main one but
    not the owner. Corrected in place, and the distinction now stated rather
    than assumed. Severity: material. It mattered because the sentence
    licensed the next one.
  - **C-89, the two issues are shadowed, not imported and closed.** The
    operator's decision of 2026-09-05, and the ownership correction is why:
    closing an issue in a repository eight people read, with a pointer to a
    database only the operator can reach, takes information away from every
    other reader and gives them nothing back. Both issues stay open,
    `sd shadow sync` keeps their state, and criterion 28's clause is rewritten
    to assert the rows and a recording fixture that saw no close call.
    Requirement 11's premise changes with it: internal issues stop being where
    work is filed, they do not stop existing. Severity: blocking, since the
    old criterion asserted a close that must not happen.
  - **The governed tree names a directory that is not there.** Criterion 4's
    definition lists `templates/`; the pack has no top-level `templates/`, and
    the templates live under `skills/*/templates/`. Recorded, not corrected
    here: the fix belongs with criterion 18's scope, which `implement.md`
    carries. Severity: material, and it survived forty review rounds because
    every check for it searched for the string rather than listing the tree.
  - **C-90, criterion 6 was filed onto a documentation pull request.** The
    closure table gave it to PR 1, whose scope was `WORKFLOW.md`,
    `skills/sd-help/`, `bin/sd_install.py` and `.claude/rules/`. Criterion 6
    is requirement 3's whole runtime — roughly a hundred and thirty lines
    covering `sd attribute`, the trailers, `SD_AUTHOR`, `bin/sd-review`
    losing its provider table, the `--provider` flag's refusals, bill caps,
    `meter` rows, fallthrough and the installer's consent line. Only
    `bin/sd_install.py` overlapped. Requirement 3 is the largest requirement
    in the item and reached the plan through this one criterion, so filing
    it wrong scheduled the requirement nowhere. Severity: blocking.
    Addressed: criterion 6 is PR 6's, with the registry reader.
  - **C-91, criterion 11 was in two places and the table had the wrong
    one.** PR 6's prose claimed it; the table gave it to PR 1 and omitted it
    from PR 6. The table is what an implementer works from, so criterion 11
    would have closed on its last sentence — all three modes appear in
    `README.md` — while the merge-time consent re-check went unverified.
    That check is the thing that stops an unattended merge into a
    repository that gained a collaborator since the row was set. Severity:
    blocking. Addressed.
  - **C-92, "PRs 1 through 5 need no database" was false four times.**
    Criterion 24 reads active trial rows and asserts the installer never
    renders from `contrib/` without one; criterion 25's printed date is the
    row's expiry, so there is no install half observable without the row,
    and both are asserted against a temporary database in the criterion's
    own words; criteria 6 and 11 need rows and B's fixture harness.
    Severity: blocking. Addressed: PR 5 moves into slice 2 and takes
    criteria 24 and 25 whole, and the page now says four pull requests need
    no database rather than five.
  - **C-93, criterion 18's scope covered one file of nineteen.** PR 4's
    Touches named the routing block, `.claude/rules/`, the global settings,
    `CONTRIBUTING.md`, the system guide and the pull-request template. A
    grep of the governed tree for `Trellis`, `.trellis` and `task.py`
    returns nineteen files, including two test files and seven `docs/spec/`
    pages — and neither the routing block nor `.claude/rules/` is among
    them, while `bin/sd`, `bin/sd-status` and `bin/sd_setup_github.py` are.
    Severity: blocking. Addressed: the nineteen are enumerated in the page.
    The scope had been written from a summary of where Trellis was thought
    to be, rather than from the grep the criterion specifies.
  - **C-94, the governed tree names a directory that is not there.**
    Criterion 4's definition lists `templates/`; there is no top-level
    `templates/` in this repository and the templates live under
    `skills/*/templates/`. The grep skips a missing path without error, so
    every absence assertion built on that definition passes today partly for
    the wrong reason. Severity: material. **Not addressed here**, because
    the definition is a criteria-list edit; recorded so it travels with the
    next one.
  - **C-95, four smaller misassignments.** Criterion 21's "no sweep or park
    code path remains" clause was given to PR 7, which touches no code;
    it belongs with PR 2's cut set. Criterion 12 was claimed by a pull
    request whose Touches excluded `README.md`, and criterion 9 by one
    excluding `WORKFLOW.md`. Criterion 8's two real sites are
    `.claude/sd-ai-command-pack/planning-adversarial-review.md` and
    `skills/sd-receive-review/SKILL.md`, neither of which was in scope.
    Criteria 4 and 5 need edits across `skills/`, and PR 1 scoped `skills/`
    to `sd-help/`. PR 8's Touches omitted the Codex nightly parse,
    `skills/paths.json`, `dashboard/` and `skills/sd-propose-skills/`, each
    named by a criterion it claimed. Severity: material each. All addressed.
  - **C-96, criterion 28 asserts against a file this repository does not
    have.** It enumerates `commands.yaml` to prove `sd suggest publish` is
    no palette entry; `git ls-files` finds no `commands.yaml` here, because
    it is item B's. The assertion is sound but cross-item, and the plan
    scheduled the criterion without noting it. Severity: material.
    Addressed: flagged in the page and sequenced behind B's slice 4.
  - **C-97, both line citations in "Two things about the criteria list
    itself" were wrong.** It read 1580 and 1590; the criteria are at 1592
    and 1602. Both cited lines fall mid-body of a different criterion, so a
    reader following the citation to fix the transposition would have edited
    the wrong place. Severity: minor. Addressed. The substantive point — a
    reader hits 32 where they expect 31 — was correct.
  - **The lane also refuted six candidate findings before reporting**,
    including one where a cited line range was imprecise rather than wrong,
    and confirmed that every value appearing in both this file and
    `implement.md` agrees and that every path, line citation and symbol in
    `implement.md` resolves on disk. Recorded because a review that reports
    only what it found, and not what it cleared, cannot be weighed.
- **2026-09-05** — Adversarial re-review, round two, of the rewritten
  `implement.md`. Twenty-one findings: six blocking, nine material, six
  minor — the largest of the four items. Round one's C-90, C-91, C-92,
  C-93, C-94, C-96 and C-97 hold. **C-95 does not**, and its failure names
  the shape of the whole round: the rewrite re-derived the
  criterion-to-pull-request mapping and did not re-derive the Touches lists
  under it, so five of eight pull requests claimed a criterion their
  declared file set could not reach. Two Touches entries — "and the rest of
  the line-by-line list", "the handoff path" — were not file sets at all.
  - C-98, blocking: criterion 13, the item's largest, was filed on PR 7,
    whose Touches was the retire step and the `prd.md` files. None of
    `bin/sd_lib.py`, `bin/sd-status`, `bin/sd-docs-lint`,
    `bin/sd_install.py`, `skills/sd-ship/` or `dashboard/` was in it, and
    the criterion asserts all six. The page's own prose said the reader
    ships in PR 6. Addressed: the row names both, and PR 7's Touches carries
    the files.
  - C-99, blocking: PR 2 claimed criterion 31 — roughly a hundred files
    across six trees — behind a five-item list naming no `bin/`, `agents/`,
    `tests/`, `.github/` or `docs/spec/` path, and then said in prose that
    it deletes `bin/sd_sweep.py`. Addressed: the list is enumerated from
    criterion 31's own symbol list with `git grep -l`.
  - C-100, blocking: PR 6 took criterion 6 from PR 1 under C-90 and did not
    take its scope. `bin/sd-review` (the provider table at `:200-266`),
    `.github/sd-review.json` (`tiers` at `:4`), `bin/sd_install.py` (the
    block at `:766-772`) and `bin/sd` (for `sd attribute`) were all outside
    it, as were `bin/sd-docs-lint` and `bin/sd_setup_github.py` for
    criterion 10's rule 5. Addressed.
  - C-101, blocking: C-95's own subject. Criterion 12 was still claimed by
    PR 4, whose Touches still excluded `README.md`, and its second half —
    `README.md` listing the skills that write tracked files — was scheduled
    by no pull request at all. The rewrite documented the split instead of
    closing it. Addressed, with `README.md` in PR 4.
  - C-102, blocking: criterion 9's first clause, that no pack surface
    requests a Copilot review, needs `skills/sd-ship/SKILL.md:55`,
    `skills/sd-handoff/SKILL.md:109`, `bin/sd-review:239` and
    `bin/sd-status:921,940`. PR 4 claimed the criterion and touched none of
    them, so the grep would have failed at its merge and the criterion would
    have closed on its documentation clause alone. Addressed.
  - C-103, blocking: PR 1 justified criterion 4's scope by "deleting that
    lane's skill and agent files". The lane has neither. It is
    `docs/planning-adversarial-review-codex.md`, referenced from
    `AGENTS.md:11-18`, `docs/spec/backend/manifest-and-filesystem.md:1519`
    and `skills/sd-research-repo/references/conventions.md:176` — and
    `AGENTS.md` is a file criterion 4 names outright. The same three files
    carry criterion 20's fourth statement of the rule, and
    `tests/test_doc_citations.py` breaks when the page goes. The criterion
    turns on a grep that would have come back dirty. Addressed.
  - C-104, material: PR 1 described a four-key `CLAUDE.local.md` block —
    "the keys the pack already reads and no others". Criterion 1 requires
    five, `reviewers` among them, and `grep -n reviewers bin/sd_lib.py`
    returns nothing, so "already reads" excluded it by construction and the
    test could not pass. Addressed: five keys, with the value written by
    PR 6's consent prompt and the test reading the key set.
  - C-105, material: PR 3 claimed criteria 15 and 17 without `.coveragerc`
    (where `fail_under` lives), `.github/scripts/` (which is not
    `.github/workflows/` and holds the two gates `make test` runs) or
    `tests/test_loc_caps.py` (which holds the four ceilings and the
    fail-the-suite assertion, so it and not the `Makefile` turns a failing
    cap into a warning). Addressed.
  - C-106, material: criterion 10's substantive half is rule 5's behaviour
    in `bin/sd-docs-lint`, in no pull request. Addressed with C-100.
  - C-107, material: `README.md`'s writes-nothing claim was cited at line
    21. Line 21 is about rendered copies; the claim is line 34, "What it
    writes in a repository: nothing, ever", which is what `prd.md:870`
    quotes. An implementer would have edited the wrong paragraph. Addressed.
  - C-108, material: criterion 5's vendor grep returns
    `skills/_shared/references/subagent-dispatch.md`,
    `skills/sd-handoff/SKILL.md` and `skills/sd-skill-adopt/SKILL.md`, which
    run no review and so fell outside PR 1's "every skill that runs a
    review". Addressed.
  - C-109, material: criterion 23's writing-repository style override and
    criterion 28's writing manifest and `sd shadow sync` surface were in no
    Touches list. Addressed.
  - C-110, material: criterion 11 was whole in the table on PR 6 and split
    in the prose, its `README.md` clause in PR 1, with the ordering section
    allowing PR 1 to land at any time. PR 6 first would have closed the
    criterion with that clause unlanded. Addressed: PR 1 before PR 6, stated
    in both places.
  - C-111, material: PR 7 said criterion 13 is recorded as waiting "before
    this slice, which the landing order says in those words".
    `prd.md:1194-1195` says before the **second** slice; PR 7 is the third.
    Criterion 32 is in the same sentence and was mentioned by neither PR 6
    nor PR 7. Addressed.
  - C-112, material: `tests/` appeared in one Touches list, as a file to
    delete, while at least seventeen criteria mandate a test and the cuts
    break six existing test files. Criterion 30 makes `make check` a
    precondition of every merge, so a pull request deleting a symbol whose
    test still asserts it cannot merge. Addressed with a section stating
    where tests land.
  - C-113, minor: the nineteen-file list for criterion 18 reproduces only
    under an unescaped dot or a case-insensitive grep; under the criterion's
    literal strings it is eighteen, `bin/sd_setup_github.py` being a
    lower-case hyphenated comment hit at `:52`. Recorded rather than
    silently recounted.
  - C-114, minor: "237 `prd.md` files" reads as a present count and is 238
    today, this item's own having been added. Addressed.
  - C-115, minor: `_local_block_entrypoints` runs to `bin/sd_lib.py:414`,
    not `:412`, in both pages. Corrected.
  - C-116, minor: `design.md`'s mode rule omitted the no-git case criterion
    11 asserts by name. Addressed.
  - C-117, minor: `design.md` ships `exo` disabled, faithful to
    `prd.md:448-451`, while criterion 6's test adds an `exo` entry and
    resolves it — and a disabled entry never resolves. Noted in the registry
    block: the test writes its own enabled entry into a fixture.
  - C-118, minor: `plugins/sd` is a directory, not one of "the three residue
    files"; PR 2 and PR 5 both marked `contrib/` new; PR 8's hooks list
    named two of the five requirement 12 requires. All three addressed in
    the Touches rebuild.
  - **Not reached in this round:** item B's `prd.md` is in the `system`
    repository, outside this checkout, so `implement.md`'s "item B's
    criterion 13" and B's slice numbering are unverified against B's text.
- **2026-09-05** — Adversarial re-review, round three. Twenty findings: six
  blocking, eight material, six minor. The named failure mode recurred a
  third time, one layer down each round. Round one left the Touches lists
  stale under a rebuilt criterion mapping. Round two rebuilt the Touches
  lists and left the **ordering section** and the **cross-item attributions**
  stale under them: four of the six blocking findings are contradictions
  round two's own edits created, and the other two are criteria whose
  operative subject the rebuilt file sets still could not reach.
  - C-119, blocking: C-103 scoped criterion 4 from the *filename*
    `planning-adversarial-review-codex.md` and never from what the criterion
    greps for. `git grep -niE 'second-model lane|codex (review )?lane'` over
    the governed tree returns `AGENTS.md:14`, `skills/sd-plan/SKILL.md:40`
    ("routes them to the codex second-model lane") and
    `skills/sd-receive-review/SKILL.md:3`. The middle one — the payload's own
    statement of the lane, in the skill that invokes it — was in PR 2's and
    PR 4's Touches, neither of which claims criterion 4, so the grep came
    back dirty at PR 1's merge. Addressed.
  - C-120, blocking: criterion 6's *first* clause is that the provider
    registry format "is documented in `WORKFLOW.md`" (`prd.md:1232-1234`).
    C-100's rebuild derived PR 6's Touches from the criterion's runtime
    clauses and skipped the documentation obligation, and PR 6 claims
    criterion 6 whole. Addressed, and PR 1 is ordered before PR 6 for it.
  - C-121, blocking: criteria 24 and 25 both have "**the installer** renders"
    as their operative verb, and PR 5's three-file Touches — the data file,
    the trial directory and the `sd skill try` subcommand — held none of the
    code they assert. `bin/sd_install.py:224-229` is the enumeration the
    paths file replaces. This is round two's headline defect verbatim, on the
    one pull request round two changed the character of. Addressed.
  - C-122, blocking: C-110 ordered PR 1 before PR 6 for `WORKFLOW.md` and, in
    the same edit batch, added `WORKFLOW.md` to PR 4's Touches without
    ordering PR 4. The file does not exist. PR 4 merging first would edit a
    missing file or create a second one, and criterion 5's "exactly two
    places" test would pass against a page PR 1 then overwrites. Addressed.
  - C-123, blocking: C-118 added `skills/paths.json` to PR 8's Touches for
    criterion 27 and did not order PR 8 after PR 5, which creates the file.
    Both were constrained only to be after B's slice 1, so PR 8 could merge
    first and criterion 27's branch-content test would have nothing to assert
    against. Addressed.
  - C-124, blocking: the `sd_db` installer step was filed on two pull
    requests at once — PR 6's Verification and the ordering section, and
    PR 7's Touches and the closure table — and called "item B's criterion
    13", which is a dashboard criterion in B's slice 4
    (`B/prd.md:1420-1430`) with nothing to do with an installer. The clause
    is **this item's criterion 13** at `prd.md:1523-1529`, carried by B's
    settled open question 3. Addressed: PR 7 alone, under its own number.
  - C-125, material: C-118 resolved PR 2's and PR 5's duplicate claim on
    `contrib/` by declaring PR 5 the creator, which made PR 2 depend on a
    slice-2 pull request while leaving PR 2 in the "any order" group. The
    directory does not exist. Addressed by the ordering, which is the half
    that gives.
  - C-126, material: C-108 named three files as the ones criterion 5's vendor
    grep returns beyond "every skill that runs a review". The criterion's own
    four-name grep over `skills/` returns **twelve**, including
    `sd-research-repo/SKILL.md:84` and the rendered
    `sd-research-repo/templates/CLAUDE.md:82,87`, which carry more `codex`
    invocations than the reference file beside them that was named. The
    enumeration came from the sentence that reported the gap. Addressed.
  - C-127, material: C-100's new citation said `bin/sd-review`'s provider
    table is at `:200-266` with `tiers` at `:265`. `BACKENDS` is `:193-248`;
    `:200` is inside the *second* entry, so the range omits the `codex` row
    criterion 6 names most often, and `:266` is eighteen lines past the table
    inside `DEFAULT_POLICY`, whose `tiers` dict is at `:262`. Deleting the
    cited range would leave the table's head and remove the tier lists —
    inverting both halves of criterion 6. Addressed.
  - C-128, material: `.coveragerc` has two `include` keys. C-105's citation
    gave `[run] include` the range `:11-24`, which spans into `[report]`, and
    placed `fail_under = 100` inside the `[run]` list. `[run] include` is
    `:11-13`; `[report] include` is `:21-22` and already names
    `bin/sd_install.py` alone, which is what criterion 15 asks for. The file
    that changes is `[run]`'s `:13`. Addressed.
  - C-129, material: the section C-112 added opens "`tests/` appeared in
    exactly one Touches list above — as a file to delete", which its own next
    sentence refutes three times over, and claims Touches coverage for
    `tests/test_sd_docs_lint.py`, which was named only in PR 6's prose — a
    pull request that removes none of the symbols breaking it. Addressed, and
    the file is in PR 2's Touches, whose `none - ` cut breaks it.
  - C-130, material: PR 8's hooks list was justified as "all five requirement
    12 names (`prd.md:993-995`)". Requirement 12 names three — `PreCompact`,
    `SessionEnd`, `SessionStart`. `PreToolUse` and `UserPromptSubmit` are
    criterion 26's (`prd.md:1571-1573`). Both criteria are PR 8's, so the
    file set was right and the count, the source and the citation were not.
    Addressed.
  - C-131, material: PR 4 edits `bin/sd-review`'s copilot rows at `:238-248`,
    which are inside the `BACKENDS` table PR 6 deletes, and the two were
    unordered. Criterion 9's grep also returns a fifth payload surface,
    `skills/sd-review/SKILL.md:80`, that C-102's four-surface enumeration
    missed. Addressed: PR 6 before PR 4, and the fifth surface is in PR 4.
  - C-132, material: C-109 added the global settings, the system
    repository's guide and the writing repository's style override to PR 4's
    Touches without reconciling them with the page's own framing that each
    numbered unit is one pull request carrying `Item:`. Three of PR 4's
    obligations cannot appear in a diff against this repository — criterion
    19's subject is `~/.claude/settings.json`, in no repository at all.
    Addressed: PR 4 is one pull request here plus three landings that are
    recorded separately. PR 8 carries a smaller version of the same shape.
  - C-133, minor: "the forty files carrying `R10-D`" is thirty-nine. Forty is
    reached only by counting `docs/fleet/README.md`, which is outside the six
    trees named and outside the governed tree criterion 31 greps. An
    off-by-one introduced by C-99's own `git grep -l` rebuild. Addressed.
  - C-134, minor: C-114 prepended "238 today," and left "237 `prd.md` files
    under `docs/work/` have the line" attached to the verb, so the sentence
    carried both numbers with the false one doing the work. 238 is correct.
    Addressed.
  - C-135, minor: "the four files stating the planning review rule" was never
    enumerated, and the neighbouring "the same three files" double-counted
    `AGENTS.md`. Criterion 20 closes on the count. Enumerated: six statements
    today plus a seventh in `skills/sd-plan/SKILL.md:38-41` that states it as
    a numbered step. Addressed.
  - C-136, minor: `tests.yml:101` is the `bash32` job header, not the
    invocation, and `tests/test_loc_caps.py:193-217` is `assert_cap` plus the
    first method calling it — the fail-the-suite line is `:195-202`. Both
    were inside round two's claim that "every path, line citation and symbol
    in `implement.md` resolves on disk". Addressed.
  - C-137, minor: `README.md` is in four Touches lists with one ordering
    among them, and criterion 11's `README.md` clause was claimed by both
    PR 1 and PR 6. The closure table already puts it in PR 1. Addressed by
    saying so in the ordering section.
  - C-138, minor: `sd shadow sync` was listed as an existing surface. It does
    not exist — this file introduces it at `prd.md:955`, criterion 28 says
    only "after a sync", and no `shadow sync` string appears in the pack.
    Addressed: marked new, like `WORKFLOW.md` and `skills/paths.json`.
  - Verified sound and recorded as such: the nineteen-file Trellis list is
    exact and its subcounts hold; C-113's eighteen literal-string hits;
    criterion 8's two places are exactly two; the fifty-six
    `argument-vocabulary` files, the five `agents/*.md` and seven
    `skills/*/SKILL.md` carrying `Active item:`, and the three `none - `
    files; 495 `prd.md` files and 8 active items; B's slice numbering,
    criterion 23 and open question 3 quoted correctly; and C-115's
    `bin/sd_lib.py:391-414` correction.

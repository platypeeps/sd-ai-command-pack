---
name: sd-status
description: Read-only derived status for the repository you are standing in — is anything wrong, what is pending, what is next — with branch-protection enforcement gaps named.
disable-model-invocation: true
---

# sd-status

`bin/sd-status` answers "where does this repository actually stand" without
writing anything — not the repo, not the state directory, not a cache. Every
section derives its answer at run time from the filesystem, git, GitHub, or the shared database.

**There is no repo-path argument and no fleet walk (R10-D6).** The repository
is the one enclosing cwd, full stop. The old fleet-walking sd-status is
dropped; the dashboard provides the cross-repo view of repositories. The one
line here that is not scoped to the checkout is the `jira` section: a Jira
ticket belongs to no repository, so it is read from the shared database whole.

The report leads with the judgement. `abnormalities`, `pending` and `next`
answer "is anything wrong", "what is waiting" and "what do I do now" before a
single inventory section appears, because those are the questions a reader
came with; the eight older sections keep their order underneath them so
nobody's muscle memory breaks.

## The fourteen sections, in output order

Above them all sits the banner — two lines, `sd-status: <repo path>` and the
`pack:` line naming the checkout these tools came from with its branch and
head. It is a header rather than a section: it names where the report ran and
what ran it, and nothing under it is a finding. Count it and the report
opens with fifteen top-level lines; the fourteen below are the sections.

| Section | What it shows |
|---|---|
| `abnormalities` | every abnormal class in the ranking table, whether or not it fired: `clear`, `n findings`, or `unchecked: <reason>`. At most three findings print per class, and the elision says how many were held back |
| `pending` | at most ten actionable rows by rank, with the line above them stating the denominator — `10 of 123, by rank`. A class with a cap shows at most that many rows, and a line under the list says how many of its rows the list does not show |
| `next` | one row: the top-ranked id and its `suggest`. Not a menu, not three options |
| `open threads` | a count per `source`, then the exclusions named in full, so the counts are never read as a total of everything that exists |
| `work items` | derived item status from `docs/work`, counted, with the parked ones counted and not listed |
| `contributions (this repo, shared database order)` | upstream activity, local evidence, and dependency readiness from the shared contribution projection |
| `open pull requests` | open pull requests, via the same code path as `sd-pr-state` |
| `detected setup` | mode (`full`/`minimal`/`guest`) and the detected check entrypoints |
| `issues (this repo, from the index)` | indexed issues for this repository, split into the ones the index says need you and the rest |
| `jira (shared database, all repositories)` | the operator's Jira involvement from the shared database, across every repository: one line per ticket, key and state, open rows first, then rows closed within seven days. Not scoped to the checkout |
| `protection` | branch-protection **enforcement**, gap by gap, plus the two merge-settings flags |
| `resumable handoffs` | the pending local packet for this directory (**read, never consumed**) |
| `backends` | which review backends are installed — names only |
| `legacy residue` | legacy leftovers, each with the exact command that removes it |

The contribution section filters the shared projection by the current checkout path and its GitHub repository name.
Its order is newly unblocked, awaiting you, awaiting them, merged, then closed.
`closed` is terminal and holds any row whose last observation reads closed: an upstream issue, or a pull request closed without merging; an unacknowledged event keeps either in awaiting you until it is acknowledged.
The dashboard uses the same projection and order across repositories.
A row is a pull request, an upstream issue, or local work that is neither filed yet.
An issue row carries `issue_url`; an issue you have written up but not filed carries `target_repo`, `draft_title`, `draft_path` and `draft_verified` instead, and filing it keeps the item ID.
Read event IDs and their revision with `sd task contribution show KEY --json`.
Use `sd task contribution ack KEY --event EVENT --if-revision REVISION` to acknowledge an event explicitly.
Acknowledgement records attention separately from notification delivery and local task completion.

**A class that could not be asked prints `unchecked` and is not counted
clear.** The summary line is assembled so the word `clear` cannot appear while
any class is blind, because a banner that says clear over a class it never read
asserts health it did not establish.

## One table enumerates the checks

`CLASSES` in `bin/sd-status` is the single answer to "which checks exist". The
renderer iterates it, the ranking reads `rank` off it, the banner reads
`abnormal` off it, and `open threads` reads `source` off it. **Adding a check
means adding a row there and a producer — never editing a renderer, a sort, or
a list.** That is how those drift apart.

Rows are ordered `(rank, -age_days, id)`: the class first, the oldest of a
class next, the id last so the order is total and reproducible. One class,
`merged-pr-review-unacknowledged`, orders its rows newest first instead, and
`pending` shows at most three of them. A reader can predict `pending` from
this table before running the command.

| Rank | Check | Id prefix | In the banner | Source | What it means |
|---|---|---|---|---|---|
| 10 | `branch-already-merged` | `w` | yes | `work item + git` | a non-done item whose branch already landed in the default branch |
| 10 | `in-progress-without-branch` | `w` | yes | `work item` | status: in_progress with no branch: field to work on |
| 10 | `branch-unresolvable` | `w` | yes | `work item + git` | a branch: field naming a ref no local or remote head carries |
| 10 | `status-unreadable` | `w` | yes | `work item` | an item whose prd.md will not yield a status |
| 20 | `unresolved-concern` | `c` | yes | `## Review ledger` | a review concern left open by its own ledger row |
| 20 | `unreadable-concern-row` | `c` | yes | `ledger row nothing can classify` | a C- row whose disposition this reader does not recognise |
| 30 | `pr-check-failing` | `p` | yes | `open pull requests` | an open pull request with a failing check |
| 30 | `pr-check-missing` | `p` | yes | `open PRs + protection` | an open pull request reporting no check the branch requires |
| 30 | `dirty-tree-with-open-pr` | `p` | yes | `git + open PRs` | uncommitted work on a branch that already has a pull request |
| 35 | `pr-review-unacknowledged` | `p` | yes | `review findings + local acknowledgements` | an open pull request carrying a review finding nobody has answered |
| 40 | `protection-gap` | `g` | yes | `protection` | an enforcement leg missing on the default branch |
| 45 | `accepted-gap-standing` | `g` | no | `.github/sd-status.json accepted_gaps[]` | a written acceptance whose until condition nothing re-reads |
| 50 | `issue-needs-you` | `i` | no | `dashboard index` | an indexed issue the index says is waiting on you |
| 60 | `pr-needs-action` | `p` | no | `open pull requests` | an open pull request waiting on a review or a merge |
| 65 | `merged-pr-review-unacknowledged` | `p` | no | `merged PRs (14 days) + local acknowledgements` | a pull request merged in the last 14 days with a review finding nobody answered |
| 70 | `open-step` | `s` | no | `- [ ] in item docs` | an unchecked box on an item nobody has closed |
| 80 | `unmerged-branch` | `b` | no | `origin heads` | a branch on origin with no open pull request carrying it |
| 90 | `parked-concern` | `c` | no | `## Review ledger` | a concern parked behind a trigger nobody is watching |
| 100 | `idle-planning` | `w` | yes | `item activity + idle threshold` | an item idle in planning past the 45-day threshold |
| 100 | `undated-planning` | `w` | yes | `work item` | a planning item with no date to age it by |
| 110 | `issue-open` | `i` | no | `dashboard index` | an indexed issue open against this repository |
| 120 | `source-marker` | `t` | no | `marker scan over the index` | a marker left in tracked source |
| 125 | `undisclosed-tool` | `k` | no | `skill claims bin/<tool>` | a skill disclosing a tool that is not built |

The `idle-planning` row is rule R10-D1, a registry row. `bin/sd-status` cites
R10-D1 in the comments beside the `CLASSES` row and the reason text, never
inside either string, so no string in the tool is a second copy of the
registry.

### `pr-review-unacknowledged`, and why it sits at 35

A review that runs and is never read produces exactly the signal a review that
found nothing produces. Twelve pull requests merged on green CI in one session
with an automated review on each; the reviews were opened afterwards and held
real defects, three of which reached the default branch under threads that all
read as answered. Nothing in this report told the two apart.

The rank is deliberate. Below the three rank-30 `p` classes, because a red
check is a machine-verified fact and a review finding still needs a human to
judge it. Above `protection-gap` at 40, because a gap in branch protection is a
standing configuration question while an unanswered finding is attached to a
pull request that is about to merge, and the merge is the last point where
answering it can keep a defect off the default branch. Abnormal, so it reaches
the banner: the whole failure was that this was invisible where the operator
already looked.

A finding is answered when `bin/sd-review-ack` says so — acknowledged as fixed
by a commit that actually reached the landing ref, or dismissed with a reason.
Reached it directly, or through a squash: the commit is in the head of a pull
request GitHub merged and the commit it merged as is on the ref, both facts
local `git` settles. A fix the reviewer had already read when it stated the
finding again is `fix-restated`, not answered, and the row stays up.
`sd-status` holds no second opinion about any of this; it counts what that
tool reports unanswered.

Most of those acknowledgements are written by `bin/sd-ship`, not typed. A row
whose store nothing ever fills is a row that is always on, and a report that is
always red is a report nobody reads, so the push records `fixed <commit>` for
each finding it can show an answer for: a commit that did not exist when the
reviewer read the file, that changes the file the finding names, and that is
reachable from the head being pushed. Those are facts `git` settles, and a
finding on a file the push never touched stays unanswered — which is the half
that makes the other half worth anything. `dismissed <reason>` is never
written by a machine: a finding the reviewer got wrong is answered by a
sentence a person writes, and there is no bulk form of either disposition.

Findings are read from inline comments **and** from review bodies, where an
automated reviewer states the ones no comment count sees. The bodies arrive in
the `gh pr list` call this report already makes; the inline comments cost one
`gh api` call per pull request, the same per-pull-request price `behind_by`
already pays. A pull request whose comments cannot be read marks the class
`unchecked` rather than reporting the body findings as the total — a partial
count presented as a count is the failure this class is about. That pull
request gets no row; every other pull request whose findings were read keeps
its row, so one failed read does not empty `pending` of the rest. The reason
names every pull request whose comments could not be read, sorted by number:
the lowest five named, the rest as a count. An acknowledgement store
that cannot be read also marks the class `unchecked`, but it hides no row: the
store then reads as empty, so every finding is unanswered and every pull
request with one keeps its row. Those rows say to repair or move the store
first, because `sd-review-ack --ack` stops with an error on a store it could
not read rather than replace the acknowledgements still in it.

The count is sometimes a floor. A reviewer that writes `Moderate findings
(3 votes each)` has stated more than one finding under one marker and has not
said where they split; `sd-review-ack` keeps the whole text, marks the row
indeterminate, and the detail then reads `at least 2 of at least 2` rather
than `2 of 2`. Splitting that text on "and" would be guessing how many, and
counting it flat as one would understate — an undercount on a gate reads as
progress. Rows with no such marker keep an exact count.

### `merged-pr-review-unacknowledged`, and why it sits at 65

The open class loses its row when the pull request merges, answered or not.
PR #896 merged with seven of seven findings unread, its fixes pushed without
`bin/sd-ship`, and the report showed it nowhere. This class keeps such a pull
request on the report for 14 days after the merge: merged fourteen days ago is
in, fifteen is out. Past that it is no longer a row, and `open threads` names
the exclusion.

The days are counted from the UTC calendar day GitHub records the merge on to
the local date `sd-status` runs on. So the edge can move by the local offset
from UTC: in California a pull request merged in the evening falls on the next
UTC day, so it stays in the window one local day longer. The query to GitHub reaches
one day further back than the window, so no pull request inside the window
goes unread because of that difference.

Sorted after the open class at 35, and not abnormal, both by the owner's
decision (sd:631). Not
abnormal, so it never reaches the banner and never changes its count.
Automatic acknowledgement stays with `bin/sd-ship`; a push or a merge made
another way records nothing, which is the case this row exists to show.

It sat at 36 at first, and review of #925 showed why that cannot hold here.
Lanes in this repository push with plain `git` instead of `bin/sd-ship`, so
nothing records their answers, and about 278 pull requests merged in the
fifteen days to 2026-09-13. Ten of them with one unanswered inline comment
would fill all ten `pending` slots at 36, and `next` would point at the
oldest. So three rules apply now:

- **Rank 65**, below `pr-needs-action` at 60 and above `open-step` at 70. An
  open pull request waiting on a review or a merge can still change; a merged
  one cannot, so the open one comes first.
- **Newest merge first** within the class (`newest_first` in `CLASSES`), the
  reverse of every other class. A finding from yesterday's merge is still
  fresh in someone's head; one from two weeks ago is the least likely to be
  acted on.
- **At most three of its rows in `pending`** (`pending_cap`). The rows it holds
  back leave their slots to the classes below, and a line under the list says
  how many of its rows the list does not show. When higher classes fill all ten
  slots, that is every row of the class, not just the rows past the cap — so
  the line splits the count by cause (`_held_back_line`): rows "past its cap of
  3", rows "ranked below the first 10", or both with a number each. A class
  crowded out while under its cap names rank alone, never the cap.
  `--actions` and `--json` still carry every row.

It asks the same question through the same code as the open class. A finding
is answered when `bin/sd-review-ack` says so, and the merged pull request's
head and merge commit go with the question, so a fix that landed through a
squash reads answered. The rule for unreadable data is the open class's too. A
merged pull request whose comments could not be read gets no row and marks
the class `unchecked`, and every other pull request keeps its row. A pull
request with no merge date does the same, and so does a merged list that
stopped at its limit.

The read runs two `gh` commands, however many pull requests merged: `gh pr list
--state merged` for the window, and one `gh api --paginate` over the
repository's review comments. That call's `since` is the oldest merged pull
request's creation time, since no review comment predates its pull request. It
is still as many HTTP pages as there are comments since then, and one
long-lived pull request that merges widens it. If it runs past `sd-pr-state`'s
60-second limit on each `gh` call, every merged pull request reads unreadable
and the class is `unchecked`.
The data arrives in `--json` as `merged_pull_requests`. The text report has no section for it;
its rows print in `pending`.

## Ids: `<letter><4 hex digits, 8 on collision>`, from the data alone

Every actionable row carries an id like `w0a35` — short enough to type, and a
pure function of the data, so "do `w0a35`" in a later session still names the
same row. Nothing reads a clock, a sequence number or a ledger, and **no id
ledger is written anywhere**; the same data yields the same ids every run.

**The hash is over `(check name, natural key)`, never over the class letter.**
Two checks in one class routinely fire on one object — a pull request that is
both `pr-check-failing` and `dirty-tree-with-open-pr`, an item that is both
`branch-already-merged` and `idle-planning`. Keyed on the letter, each such
pair hashes identically at four digits *and* at eight, so widening could never
separate them and one id would name two actions. The letter is a display
prefix; identity is `(check, key)`.

**Colliding ids widen to eight hex digits, both of them, and record that they
did.** The widened rows carry `"widened": true` in `--json`; the text report
shows the wider id and names the widened ids in a line under the rows, so
the change is visible rather than silent. So a consumer matching ids wants
`^[a-z][0-9a-f]{4,}$` — `{4}` is wrong, and this checkout already
carries two eight-digit ids that a fixed-width pattern misses.

## Picking a row through `AskUserQuestion`

The harness component allows **at most four options per question and at most
four questions**. Ten pending rows do not fit, and spreading them over three
questions abuses a control meant for distinct dimensions — the user would
answer three questions to express one choice.

**The resolution: ids are the primary interface and the component is a
shortcut.** Render exactly **one** question, `multiSelect: true`, whose four
options are pending rows 1 to 4, each labelled by its id. Rows 5 to 10 are
addressable by typing the id, which the component's own free-text answer
already supports, and `--actions` lists every row, the ones `pending` leaves
out included. Take the options from the text report's `pending`, not from
`actions` in `--json`: `pending` is the first ten after each class's
`pending_cap` (`pending_rows`), so a class past its cap can make rows 1 to 10
of `actions` differ from it.

Three rules on that question:

- **Never renumber the options.** The label is the id the report printed.
- **Never substitute your own ordering.** The order is `pending`'s, which is
  the ranking table's, which the user can predict.
- **Never invent an option that is not an inventory row.** An option the report
  did not produce has no id, and nothing acts on it.

## The protection section is the one that matters

The doctrine is that merge authority is GitHub branch protection *wherever
protection is actually enforcing*. Protection that exempts admins is prose, not
authority: it stops collaborators and leaves the one account that does the
merging entirely ungated. So this section reports enforcement state, and each
missing leg prints as a named gap:

- `enforce_admins` off — every rule below it stops at the admin who merges
- no required status checks — a red PR still merges
- `strict` off — a green check run against a base that moved still merges
- `required_not_produced` — required contexts no workflow here produces; each
  blocks every PR until an external app reports it
- `produced_not_required` — checks this repo runs but does not require; they
  can go red without blocking a merge
- `reviews` — no PR review required, or zero required approvals
- the two r7 merge-settings flags: squash title/message source (a `wip:`
  subject reaching main) and whether rebase-merge is allowed

**A finding is a report, not a failure.** The command exits 0 whether or not it
found gaps or abnormalities. Exit 2 is reserved for an invocation or
configuration fault, printed as a sentence, never a traceback.

## Accepted states are not silenced states

A repository can record, in tracked `.github/sd-status.json`, a protection
state it has looked at and decided to keep. Those findings print as
`ok  [id] accepted <date>: <reason>` with the ending condition on the line
below, and move from `protection.gaps` to `protection.accepted` in `--json` —
so a consumer counting gaps counts open ones only, and never mistakes an
accepted finding for an absent one.

What makes it an acknowledgement rather than a suppression:

- **Keyed on the observed protection state, never on the gap id.** `reviews`
  is emitted for two opposite states — the review object being absent, so no
  pull request is required at all, and the object existing while asking for
  zero approvals. An entry pins the facts it was accepted under, and stops
  applying the moment any of them changes; the gap then prints as a gap,
  carrying a line saying an acknowledgement exists and no longer matches.
- **`because` and `until` are both required, and both print every run.**
  `until` is the deletion criterion: when it comes true the entry is deleted
  and the gap returns on its own.
- **A malformed file accepts nothing and says so** — each fault prints as its
  own gap. It fails closed and loudly, never silently.

An acceptance nobody re-reads is itself a row: `accepted-gap-standing` at rank
45 surfaces a written acceptance whose `until` condition nothing is watching.

## Flags

`--json` (one machine-readable object) · `--actions` (every actionable row,
uncapped, one per line, count first) · `--parked` (list only the items that
carry a `parked:` frontmatter line, read from the item, not from a ledger) ·
`--limit N` (most PRs to list).

**`--json` wins when both `--json` and `--actions` are given.** `pending` caps
at ten because a report is read whole; `--actions` is the list a caller pipes,
so capping it would make the cap the interface.

The `--json` schema is version **3**. Beyond the section keys it carries
`merged_pull_requests` (the pull requests merged inside the review window, with
the findings each carries), `inventory` (`rows` plus the `unchecked` map),
`abnormalities`, `actions` — the uncapped inventory, of which `pending` is the
first ten after each class's `pending_cap` (`pending_rows`) — and `next`. It
has no top-level `pending` key, and the two nested ones are something else
again: `handoff.packet.pending` is a boolean about the handoff packet, and
`pull_requests.pull_requests[].checks.pending` an integer count of that pull
request's checks that have not finished. `_BUCKETS` in `bin/sd-pr-state` folds
six states into it: `PENDING`, `QUEUED`, `IN_PROGRESS`, `WAITING`, `REQUESTED`
and `EXPECTED`. `QUEUED`, `IN_PROGRESS`, `WAITING` and `REQUESTED` are a check
run's `status`, which `_outcome` reads only while the run has no `conclusion`;
`EXPECTED` is a commit status GitHub expects and has not received; `PENDING`
is either. `rollup_buckets` writes only the buckets it saw, so with no such
check the key is absent, not 0. Neither is this list.
**`next` is an object with `id`, `check` and `suggest`, not a bare string**,
because a caller acting on the suggestion needs the id it belongs to in the
same breath.

## Never

- **Never present the absence of gaps you did not read as safety.** If the
  protection section could not be fetched, say the enforcement state is
  unknown; do not say the repo is protected.
- **Never call a class clear when it printed `unchecked`.** A class that could
  not be asked was not looked at, and the two words are not interchangeable.
- **Never report an accepted finding as an absent one.** "No open gaps" is a
  different sentence from "protection is fully enforcing", and only the second
  is a claim about the branch. Read `protection.accepted` before saying either.
- **Never claim a guarantee the config does not provide.** In a repo with no
  protection, the honest statement is that nothing enforces merge authority
  there.
- **Never read `pending` as the whole list.** It is capped at ten and says so;
  the total is on its own heading line, and `--actions` and `--json` carry the
  rest.
- **Never invent an id, and never renumber one.** Ids come from the run you are
  looking at; an id you composed names nothing.
- **Never consume the handoff packet from here.** The `resumable handoffs`
  section reads it; only `sd-handoff-restore` or `sd-handoff --show` consumes
  it. Reading status must never eat a pending packet.
- **Never write, anywhere.** No cache, no index row, no state file, no id
  ledger. If you want a fact recorded, that is a different command.
- **Never point it at another repository**, and never loop it over checkouts to
  rebuild the fleet view that was deliberately removed.

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
dropped; the dashboard provides the cross-repo view.

The report leads with the judgement. `abnormalities`, `pending` and `next`
answer "is anything wrong", "what is waiting" and "what do I do now" before a
single inventory section appears, because those are the questions a reader
came with; the eight older sections keep their order underneath them so
nobody's muscle memory breaks.

## The thirteen sections, in output order

Above them all sits the banner — two lines, `sd-status: <repo path>` and the
`pack:` line naming the checkout these tools came from with its branch and
head. It is a header rather than a section: it names where the report ran and
what ran it, and nothing under it is a finding. Count it and the report
opens with fourteen top-level lines; the thirteen below are the sections.

| Section | What it shows |
|---|---|
| `abnormalities` | every abnormal class in the ranking table, whether or not it fired: `clear`, `n findings`, or `unchecked: <reason>`. At most three findings print per class, and the elision says how many were held back |
| `pending` | at most ten actionable rows by rank, with the line above them stating the denominator — `10 of 123, by rank` |
| `next` | one row: the top-ranked id and its `suggest`. Not a menu, not three options |
| `open threads` | a count per `source`, then the exclusions named in full, so the counts are never read as a total of everything that exists |
| `work items` | derived item status from `docs/work`, counted, with the parked ones counted and not listed |
| `contributions (this repo, shared database order)` | upstream activity, local evidence, and dependency readiness from the shared contribution projection |
| `open pull requests` | open pull requests, via the same code path as `sd-pr-state` |
| `detected setup` | mode (`full`/`minimal`/`guest`) and the detected check entrypoints |
| `issues (this repo, from the index)` | indexed issues for this repository, split into the ones the index says need you and the rest |
| `protection` | branch-protection **enforcement**, gap by gap, plus the two merge-settings flags |
| `resumable handoffs` | the pending local packet for this directory (**read, never consumed**) and Lane B carrier branches on origin |
| `backends` | which review backends are installed — names only |
| `legacy residue` | legacy leftovers, each with the exact command that removes it |

The contribution section filters the shared projection by the current checkout path and its GitHub repository name.
Its order is newly unblocked, awaiting you, awaiting them, then merged.
The dashboard uses the same projection and order across repositories.
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
class next, the id last so the order is total and reproducible. A reader can
predict `pending` from this table before running the command.

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
| 40 | `protection-gap` | `g` | yes | `protection` | an enforcement leg missing on the default branch |
| 45 | `accepted-gap-standing` | `g` | no | `.github/sd-status.json accepted_gaps[]` | a written acceptance whose until condition nothing re-reads |
| 50 | `issue-needs-you` | `i` | no | `dashboard index` | an indexed issue the index says is waiting on you |
| 60 | `pr-needs-action` | `p` | no | `open pull requests` | an open pull request waiting on a review or a merge |
| 70 | `open-step` | `s` | no | `- [ ] in item docs` | an unchecked box on an item nobody has closed |
| 80 | `unmerged-branch` | `b` | no | `origin heads` | a branch on origin with no open pull request carrying it |
| 90 | `parked-concern` | `c` | no | `## Review ledger` | a concern parked behind a trigger nobody is watching |
| 100 | `idle-planning` | `w` | yes | `item activity + R10-D1` | an item idle in planning past the 45-day threshold |
| 100 | `undated-planning` | `w` | yes | `work item` | a planning item with no date to age it by |
| 110 | `issue-open` | `i` | no | `dashboard index` | an indexed issue open against this repository |
| 120 | `source-marker` | `t` | no | `marker scan over the index` | a marker left in tracked source |
| 125 | `undisclosed-tool` | `k` | no | `skill claims bin/<tool>` | a skill disclosing a tool that is not built |

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
already supports, and `--actions` lists every row beyond the tenth.

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
uncapped, one per line, count first) · `--parked` (list only the items the age
sweep parked, read from their own `parked:` frontmatter, not from a ledger) ·
`--limit N` (most PRs to list).

**`--json` wins when both `--json` and `--actions` are given.** `pending` caps
at ten because a report is read whole; `--actions` is the list a caller pipes,
so capping it would make the cap the interface.

The `--json` schema is version **3**. Beyond the section keys it carries
`inventory` (`rows` plus the `unchecked` map), `abnormalities`, `actions` — the
uncapped inventory, of which `pending` is a view of the first ten — and `next`.
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

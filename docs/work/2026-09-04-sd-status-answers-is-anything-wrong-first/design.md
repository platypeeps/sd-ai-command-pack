# Design — sd-status answers "is anything wrong" first

## Approach

### One inventory, three renderings

The naive shape is three independent features: a banner, a pending list, and an
"unaddressed things" report. That was rejected in review (C-3) because the same
fact lands in all three — a work item whose branch already merged is an
abnormality, the top pending item, and an unaddressed followup — and three
independent producers give it three ids and three wordings.

So there is exactly one producer. `actionable_inventory(...)` returns a list of
rows; every row carries `id`, `check` (its class), `title`, `detail`, `rank`,
`age_days`, `abnormal`, and `suggest`. The three sections are three views of
that one list:

- `abnormalities` renders the rows where `abnormal` is true, grouped by class.
- `pending` renders the whole list sorted by rank, capped at 10.
- `next` renders `suggest` from the first row of `pending`.
- `open threads` renders per-source counts over the same list, plus the
  exclusions, so the cap of 10 has a stated denominator.

One row, one id, four renderings. A reader who sees `w7a3c` in the banner and
`w7a3c` in `pending` is looking at the same object, not two objects that agree.

### The class table is the enumeration

`CLASSES` is a module-level tuple of `Class(check, letter, rank, abnormal,
source, what)`. It is the answer to "which checks exist", and it is the only
answer: the renderer iterates it, the ranking reads `rank` off it, the banner
reads `abnormal` off it, and `open threads` reads `source` off it. Adding a
check means adding a row and a producer; it does not mean editing the renderer,
the sort, or the skill's prose in three places.

| check | letter | abnormal | rank | source |
|---|---|---|---|---|
| `branch-already-merged` | w | yes | 10 | work item + git |
| `in-progress-without-branch` | w | yes | 10 | work item |
| `branch-unresolvable` | w | yes | 10 | work item + git |
| `status-unreadable` | w | yes | 10 | work item |
| `unresolved-concern` | c | yes | 20 | `## Review` ledger |
| `pr-check-failing` | p | yes | 30 | open pull requests |
| `pr-check-missing` | p | yes | 30 | open PRs + protection |
| `dirty-tree-with-open-pr` | p | yes | 30 | git + open PRs |
| `protection-gap` | g | yes | 40 | protection |
| `issue-needs-you` | i | no | 50 | dashboard index |
| `pr-needs-action` | p | no | 60 | open pull requests |
| `open-step` | s | no | 70 | `- [ ]` in item docs |
| `unmerged-branch` | b | no | 80 | git refs |
| `parked-concern` | c | no | 90 | `## Review` ledger |
| `idle-planning` | w | yes | 100 | work item + R10-D1 |
| `undated-planning` | w | yes | 100 | work item |
| `issue-open` | i | no | 110 | dashboard index |
| `source-marker` | t | no | 120 | `git grep` TODO/FIXME |
| `unreadable-concern-row` | c | yes | 20 | ledger row nothing can classify |
| `accepted-gap-standing` | g | no | 45 | `.github/sd-status.json` `accepted_gaps[]` |
| `undisclosed-tool` | k | no | 125 | skill claims `bin/<tool>`, `test -e` fails |

Ranking is `(rank, -age_days, id)`. Stated in the output as one line and in the
skill as this table. A reader can predict the order without running it, which is
requirement 4.

### Detecting a merged branch when the repository squash-merges

The rejected alternative is `git merge-base --is-ancestor <branch> <default>`.
It is the obvious test and it is wrong here: this repository squash-merges every
pull request, so a landed branch is never an ancestor of `main`. Shipping it
would have produced a check that finds nothing in the repository it was written
for (C-1).

The test that works, in two `git diff --name-only` calls:

```
touched   = git diff --no-renames --name-only merge-base(default, branch) branch
divergent = git diff --no-renames --name-only default branch
merged    = touched and not (touched & divergent)
```

`--no-renames` on **both** calls, and it is load-bearing (C-12). With rename
detection on — which is the default and is confirmed active in this repository
against `c85fcf0c` — `git diff --name-only` reports a rename as the destination
path alone. A branch that renames `A` to `B` while the default branch happens to
contain both `A` and an identical `B` puts `B` in `touched` and `A` in
`divergent`; they do not intersect, and the detector says the work landed when
`A`'s removal never did. `--no-renames` makes both sides report both endpoints,
so the removal is visible on both sides of the comparison.

Read plainly: *every path the branch touched now holds, in the default branch,
exactly what the branch holds.* That is what "the work landed" means
operationally, and it is true after a squash merge, a rebase merge, and an
ordinary merge alike. The ancestor test runs first as a cheap short-circuit.

**Its limit is measured, not estimated.** Run against all five surviving
`origin` branches, every one of which was squash-merged:

| branch | ancestry test | path-equality test | truth |
|---|---|---|---|
| `skill/sd-grill` | not-ancestor | **landed** | merged (#740) |
| `docs/close-host-parsing-open-sweep-resolution` | not-ancestor | **landed** | merged (#739) |
| `test/pin-scope-providers-over-a-skip-tier` | not-ancestor | **landed** | merged (#736) |
| `fix/host-parsing-refuses-what-it-cannot-parse` | not-ancestor | not-landed | merged (#738) |
| `cap/r11-d30-dashboard-ceiling` | not-ancestor | not-landed | merged (#737) |

Ancestry: 0 of 5. Path equality: 3 of 5. The two it misses are exactly the
predicted failure — `main` has since edited paths those branches touched, so the
intersection is non-empty (3 paths and 1 path respectively). Better than the
obvious test by a wide margin, and still a 40% false-negative rate on today's
data. Not good enough to stand alone under a banner that asserts health.

### So the merge check is two-tier, and has a third answer

- **Tier 1, offline.** The path-equality test above. It only ever produces
  positive evidence; a negative from it is not an answer.
- **Tier 2, GitHub.** Match the item's `branch:` to a pull request by
  `headRefName`, and accept it only when **all three** hold: `mergedAt` is
  non-null, `baseRefName` equals the repository's default branch, and
  `headRefOid` equals the branch's current tip. Measured on this repository:
  `gh pr list --state all --json number,headRefName,headRefOid,baseRefName,mergedAt`
  returns a real timestamp for all five branches above, so this tier resolves
  the two tier 1 misses.

  The two extra conditions are C-19 and neither is theoretical. Matching on
  `headRefName` alone says "a pull request with this branch name was merged
  once", which is not the question. A branch **reused or extended** after an
  earlier merge still matches that old PR's `mergedAt` while carrying unlanded
  commits — tier 1 would correctly say not-landed and tier 2 would overrule it
  with a stale fact, putting a false `branch-already-merged` at the very top of
  the banner and suggesting the user close finished work that is not finished.
  A pull request merged into **some other base** likewise says nothing about the
  default branch. `headRefOid` pins the claim to the revision in front of us and
  `baseRefName` pins it to the branch we are asking about; when either fails to
  match, tier 2 abstains and the class reports `unknown` rather than guessing in
  either direction.
- **Tier 3, no answer.** When `gh` is absent, unauthenticated, or the call
  fails, and tier 1 did not fire, the class prints
  `unchecked: <reason>` — **never** "clear".

That third state is the design decision that matters most here. A banner whose
job is to answer "is anything wrong" must distinguish *nothing is wrong* from
*I could not look*. Folding an unchecked class into the clean count would make
`sd-status` assert health it never established, which is the same failure mode
the `protection` section already refuses (`Never present the absence of gaps you
did not read as safety`). So the banner has three per-class states — `clear`,
`n finding(s)`, `unchecked: reason` — and the summary line counts unchecked
classes separately from clear ones.

**Rejected alternatives, with the evidence, because the next person will reach
for these first.**

- `git branch -r --merged origin/main` prints only `origin/main` itself in this
  repository. Zero of five. A squash merge writes a new commit with no ancestry
  link to the branch, so nothing ancestry-based can see it.
- `git merge-base --is-ancestor` — the table above, 0 of 5.
- `git cherry origin/main <branch>` reports `+` for all three commits of
  `skill/sd-grill`: patch-equivalence does not survive squashing several commits
  into one.
- **The REST `merged` boolean.** Reported to me as reading `false` while
  `merged_at` carried a timestamp. I did not reproduce that:
  `gh api repos/<slug>/pulls/740` returns `"merged": true` alongside
  `"merged_at": "2026-09-04T22:11:09Z"`. The claim is recorded as unreproduced
  rather than repeated as fact — but tier 2 reads `mergedAt` regardless, because
  the GraphQL field `gh pr list` exposes is `mergedAt` and there is no `merged`
  field to read even if one wanted it (`gh pr list --json merged` errors with
  `Unknown JSON field`).

**Why single-repo scoping saves this check.** `sd_sweep.sweep()` resolves items
across many roots from the project allowlist, so a branch name there must be
resolved against the item's own repository or it answers on a naming
coincidence. That trap does not reach here: R10-D6 makes `sd-status` the
enclosing repository and nothing else, there is no fleet walk, and every
`branch:` this reads belongs to the checkout it is resolved in. Stated because
the absence of the bug is a consequence of a decision, not luck.

**Where this check may not live.** Not in CI. `.github/workflows/tests.yml` sets
no `fetch-depth`, so the CI checkout is depth 1 with no other branches present,
and any branch-resolving check would answer "absent" for everything. This is a
report a human runs, and the tests for it build their own fixture repositories.

### Scope: this item reports, `sd_sweep` still gets its own fix

`docs/work/2026-09-04-the-sweep-trusts-a-branch-field-it-never-resolves` is
`status: planning` and unowned, and its subject overlaps requirement 2 directly:
`sd_sweep` excludes any item carrying a `branch:` field without ever resolving
it, so the presence of the string is the whole test.

**This item does not touch `bin/sd_sweep.py`.** It reads and reports; the sweep
keeps its own fix and stays landable. What this item does supply is an answer to
that item's open question 2 — "does a stale `branch:` mean sweep it, or report
it differently?" — namely that a `branch:` resolving to nothing is a third
state, `branch-unresolvable`, which is reported and not swept. That item's
criterion 5 (both remote and local refs count, because a branch pushed but not
checked out locally is live work) is adopted here verbatim for
`branch-unresolvable`, and its criterion 4 — "git cannot answer" is distinct
from "the branch is absent" — is the tier-3 `unchecked` state above.

### The id scheme

`<class letter><4 lowercase hex>` — `w7a3c`, `c1f04`, `s9b21`. Five characters,
typable, and the leading letter tells the reader what kind of thing it is before
they look it up.

The hex is `sha1(check + "\0" + natural key)[:4]` — the **check name**, not the
class letter. That distinction is the whole of C-11 and it is not cosmetic: two
checks in the same class routinely fire on the same object. A pull request can
be `pr-check-failing` and `dirty-tree-with-open-pr` at once; a work item can be
`branch-already-merged` and `idle-planning` at once. Keyed on the letter, both
rows in each pair hash identically at four digits and at eight, so widening
cannot separate them and the id the user picks names two different actions. The
letter is a display prefix and nothing else; identity is `(check, natural key)`.

The natural key per class, chosen so that it does not move when unrelated items
resolve — always hashed together with the check name above:

| letter | natural key | why it is stable |
|---|---|---|
| w | the item directory name | the date prefix and slug are the item's identity; `sd-plan` renames neither |
| c | `<item dir>#<C-id>` | `C-*` ids are stable by the planning contract's own section 3 |
| s | `<item dir>/<file>#<nearest preceding heading>#<checkbox text, whitespace-collapsed>#<ordinal>` | line numbers move when text is inserted above; the heading and the text do not |
| i | `<owner/repo>#<number>` | issue numbers are permanent |
| p | `<owner/repo>!<number>` | pull-request numbers are permanent |
| b | `origin/<branch>` | the ref name is the branch |
| g | `<default branch>#<gap id>` | the gap ids are a fixed vocabulary in `_protection_gaps` |
| t | `<path>#<marker text, whitespace-collapsed>#<ordinal>` | line numbers move; the marker text does not |

**The `#<ordinal>` on the two text-keyed classes is C-13.** Checkbox text is not
unique inside a file — `- [ ] Run make check` can legitimately appear under two
implementation steps, and repeated `TODO` text has the same property. Those
occurrences are different tasks, so keying on text alone gives them one id and
picking it authorises an ambiguous action; widening does not help, because the
inputs are identical rather than merely close. The ordinal counts occurrences of
that exact `(heading, text)` pair within that file, in file order, starting at 0.
It is the weakest key component here and it is stated as such: inserting a new
duplicate *above* an existing one shifts the existing one's ordinal. The
alternative keys are worse — a line number moves on every edit above it, and a
sequence number moves whenever any sibling resolves — and a duplicate pair is
rare where a line-number shift is routine.

**Rejected: a sequence number** (`A1`..`A10`). It renumbers when an item
resolves, which requirement 7 forbids outright (C-2).

**Rejected: the natural key itself** (`w:2026-09-04-the-plan-interview-is-one-sentence`).
Perfectly stable and nobody will type it.

**Rejected: a written ledger** mapping short ids to keys. `sd-status` writes
nothing; that is requirement 9 and it is not negotiable for a convenience.

**Two findings on one object are two rows, deliberately.** Each carries its own
`suggest`, and they can have different ranks; aggregating them into one
selectable row would mean the suggestion is a list, which requirement 5 forbids.
Because the check name is in the key, the two rows have different ids and
picking one authorises one action.

**Collisions.** Four hex digits is 65,536 values. With the ~40 rows the whole
inventory carries here the birthday probability is under 1.3%, and it is handled
rather than hoped: when two rows collide, both widen to eight hex digits and the
report prints a note saying so. Deterministic within a run. This is now a
genuine accident of hashing rather than a structural certainty — that was C-11,
and widening was no answer to it.

The residual instability is stated under `## Risks` rather than argued away.

### `accepted_gaps[]` is the best source in the repository, and it was nearly missed

`.github/sd-status.json` is already read by `load_acknowledgements`, but only to
**subtract** findings from `protection.gaps`. That is a loss: it is the one
artifact in this repository *designed* to be machine-read as an open commitment.
It is schema-backed by `.github/sd-status.schema.json`, and every entry carries
an `until` written as an observable condition — this repository's own reads "a
second account with merge rights on this repository exists, or `enforce_admins`
is turned off".

An accepted gap is not a closed one. It is a standing commitment with a written
expiry that nothing currently re-reads, which is exactly the population
requirement 6 asks for. So `accepted-gap-standing` puts each entry in the
inventory with its `since` and its `until`, at rank 45 and **not** abnormal —
accepting it was a decision, and re-flagging a decision as a defect is how a
banner becomes noise. `sd-status` already prints these under `protection`; what
is new is that they become addressable rows with ids, so `until` can be acted on
by picking one.

### Sources that are checked but must not become recurring alerts

Three sources are exact but low-yield, and the design's rule for them is that
they are **counted, not enumerated**, unless non-zero and new:

- **Skills disclosing an unbuilt tool** — 8 skills, 9 disclosures, 7 sharing the
  stem "There is no `bin/<tool>` yet", each cross-checkable against
  `test -e bin/<tool>`. Exact, but it is a known roadmap that would emit the
  same lines every run. Rank 125, bottom of the list, and the `open threads`
  line states the count rather than the names.
- **Source markers** — the true answer here is **zero**. Method matters and is
  recorded: `grep -rE` returns 4 by reaching into untracked worktrees, while a
  scan over `git ls-files` returns 0. The zero is printed; it does not get a
  section.
- **Open GitHub issues and pull requests** — currently **0 and 0**. That is
  itself the finding worth printing: GitHub carries none of this repository's
  backlog, so a status tool that looked only there would report an empty world
  and be wrong about everything. The `open threads` section prints the zero
  beside the non-zero local counts precisely so the contrast is visible.

### Sources deliberately left unparsed, named in the output

`Trigger:`/`Owner:` lines (29 of them, one string carrying two unrelated
meanings, not separable by pattern) and `docs/review-learnings.md` (93 lines,
**no disposition field**, so nothing in it can ever be marked handled) are read
by nobody here. The second is the sharper case: a tool can honestly say "N
findings, M days stale", but saying "N open" every run is a false-alarm
generator, because the format has no way to ever say "handled". Both are listed
in `EXCLUDED` and printed, so the section never implies it swept them.

### The one assumption the checkbox scanner makes, stated out loud

Scoping `- [ ]` to items that are not `done`, not archived and not parked takes
1,747 boxes down to 24. That filter **asserts a repository convention** rather
than observing one — it assumes a checkbox on a `done` item is history and not a
missed step. It is a good assumption and it is still an assumption, so the
`open threads` line says so in words: `24 open steps (1,747 total; boxes on
done, archived and parked items are read as history)`. A reader who disagrees
with the convention can see the number they would rather have.

### The concern ledger is detected by row shape, never by heading

The brief that started this item said concern ledgers sit under a `## Review`
heading with four dispositions. Measured, that is false in both directions, and
the measurement is what the design is built on:

```
grep -rhoiE "^## [^#]*(review|concern)[^#]*$" docs/work --include=*.md \
  | sort | uniq -c | sort -rn
```

returns **75 distinct headings**. Two of them are `## Review`. Forty-nine are
`## Review gates` and thirty-two `## Review Notes`, neither of which is a ledger
at all. The genuine ledgers hide under at least `## Review`, `## Adversarial
review ledger`, `## Planning review ledger`, `## Concern ledger`, `## Concern
ledger — round N`, `## Planning adversarial review — <date>`, `## D8. Review
ledger` and `## Round-3 concerns, resolved after the round budget`. A
heading-matched parser over-matches on 81 non-ledgers and under-matches on the
ledgers whose heading nobody anticipated.

So **headings are not read**. A row is recognised by its own shape:

- the scan is one `git grep` over the index. Note for whoever writes it:
  `[[:space:]]` inside the alternation makes `git grep -E` match **nothing**
  here; ` *` works. Found by the pattern returning 0 rows against a corpus with
  286.
- a **candidate row** is a line whose first meaningful token is a `C-<n>` id —
  `^\s*(\|\s*|[-*]\s*)?(\*\*)?C-\d+\b`. The `\s*` **after** the table pipe is
  load-bearing and was missing in the first draft (C-18): a markdown ledger row
  is written `| C-7 | host | 1 | low | no | parked |`, with a space after the
  pipe, so the anchor without it matched none of them. Measured on
  `docs/work/2026-09-04-the-plan-interview-is-one-sentence/prd.md`: 15 matches
  before the fix, 28 after — the 13 rows of that item's ledger table, which is
  its entire merged concern list. That single anchor removes the false
  positives a bare `\bC-\d+\b` grep produces, which are prose cross-references
  mid-sentence ("the parent item's C-22, C-25, C-30 and C-33 were …") and
  outnumber real rows roughly two to one.
- its **disposition** is the first token from `DISPOSITIONS` the line contains,
  case-insensitively. The vocabulary is enumerated from the corpus, not from the
  contract, because the corpus has five vocabularies and the contract has one:
  closing — `addressed`, `rebutted`, `fixed`, `resolved`, `n/a`; open — `parked`,
  `accepted`, `deferred`, `unresolved`, `does not pass`. `unresolved` appears
  zero times as a disposition anywhere in the repository; it is kept in the
  vocabulary because the contract names it, not because anything uses it.
- when a row carries **both** an open and a closing token —
  `ACCEPTED and parked` is the common form — the open one wins. Under-reporting
  an open concern is the worst failure this feature can have.
- a candidate row with **no recognised disposition is itself a finding**, class
  `unreadable-concern-row`, reported by file and `C-` id. It is never dropped.
  That is what stops a future sixth vocabulary from silently emptying this
  section.

The whole scan is one subprocess — `git grep -n -E <anchor> -- docs/work` — over
the index rather than 1,479 file reads, which is also why it can afford to cover
**archived** items. That coverage is a deliberate exception to the archive
exclusion below, and the case that forces it is real: `archive/2026-08/
2026-08-26-codex-local-review-adapter` carries `C-19 (high, ACCEPTED and
parked)` — `codex exec --sandbox read-only` does not confine reads to the
checkout, verified empirically, re-raised in a later pass with no new
disposition. A parked security acceptance whose trigger nobody is watching
outlives the item it was written in; excluding it because its directory moved
would be the exact silent under-report this section exists to prevent.

### The recommendation not to build this, and why it is overruled

A read-only inventory of the corpus recommended **not automating** the concern
ledger at all — five vocabularies, dispositions wrapping across lines, the same
`C-n` appearing as a table row *and* a prose paragraph *and* a cross-reference,
one entry deliberately carrying no disposition. Its conclusion was that a regex
tuned to one of the four formats mis-parses the other three, and that requirement
5 is better served by reporting the limits than by parsing.

That recommendation is taken seriously and **overruled on measurement**, because
every failure it names is real and each one turned out to have a specific
counter, found by prototyping the parser against all 494 items rather than
reasoning about it. The prototype's final numbers, over `docs/work`:

```
245 distinct concerns   206 closed   23 open   16 unclassifiable
```

Four rules, each earned by a defect the prototype actually produced:

1. **Dedupe by `(full item path, C-id)`.** 286 candidate rows collapse to 245
   concerns. This *is* the answer to "the same `C-n` appears in three places":
   they are three rows about one concern, and one concern is what gets an id.
2. **Absorb continuation lines** to the next blank line or next candidate row.
   Dispositions wrapping across lines took unclassifiable rows from 18 to 1
   within the active items. This was the single largest defect and it is four
   lines of code.
3. **Shape precedence: table beats bold beats prose.** Without it, "any open
   token wins" reads a *cross-reference* as a disposition — this item's own C-4
   is `rebutted` in its table and was classified `open` because a line in the
   `## Log` beginning `C-4, C-8, C-10 and C-16 were rebutted…; C-6 parked.`
   mentions another concern's parking. The ledger of record is the most
   structured row present; prose about a concern is not its disposition.
4. **Key on the full item path**, never a truncated one. A prototype keying on
   `path.split("/")[2]` collapsed all 487 archived items into one bucket named
   `archive` and made `C-19` vanish entirely — the one row that most had to
   survive.

With those four, the must-surface case passes:
`C-19 parked [prose] archive/2026-08/2026-08-26-codex-local-review-adapter`.

**What is accepted, and it is not nothing.** 16 concerns of 245 (6.5%) remain
unclassifiable. They are of two kinds, both visible in the prototype output: a
**sixth vocabulary** the enumeration does not carry (`**Confirmed, design
changed.**`, `**Confirmed, annotated.**`, `**Confirmed, corrected.**` in
`archive/2026-08/2026-08-11-thin-undeclared-codex-marker/design.md`), and prose
sentences that merely begin with a `C-n` token (`C-3 is an argument-construction
defect and only argv proves it.`) and are not ledger rows at all. Both print as
`unreadable-concern-row` findings, named by file and line. That is noise in the
honest direction — it says "look at this, I could not read it" — and it is the
reason the class exists. Adding `confirmed` to the closing vocabulary would
retire about six of them and is deliberately **not** done here: the vocabulary
should grow when a row is read and understood, not when a count is being tuned.

**The one thing that must never happen** is the failure the recommendation was
protecting against, and it is designed out rather than promised against: parsing
one format, finding nothing in the other three, and printing a clean banner. A
row this reader cannot classify is a finding, so an unrecognised format inflates
the abnormality count instead of emptying it.

**Normalising these formats is not this item's job.** It is a change to 493
documents with its own blast radius and its own review; this item reports what
exists and names what it cannot read. Recorded as a decision below.

### Sources scanned, and what is deliberately excluded

Requirement 6 says the exclusions must reach the output. They are a constant,
`EXCLUDED`, printed under `open threads`, so a reader learns what the counts do
not contain without reading this file:

- **archived work items** (`docs/work/archive/**`) — 487 of the 494 — for
  *status, checkboxes and branches*. Closed by where they live; the move is the
  record. Their **concern ledgers are still read**, for the reason given above.
- **parked work items** — parked is a disposition, not an open thread.
  `sd-status --parked` lists them and nothing else should.
- **concerns disposed `addressed` or `rebutted`** — two of the contract's four
  dispositions are closures. Only `unresolved` and `parked` survive into the
  inventory.
- **checkboxes on `done`, archived or parked items** — 490 items carry historic
  checkboxes; sweeping them in produces thousands of rows and hides everything
  real behind the cap (C-5).
- **Jira rows in the dashboard index** — no committed fact ties a Jira project
  key to a checkout. This is the same exclusion `issues_section` already makes,
  for the same reason, and it is restated rather than newly invented.
- **`CHANGELOG.md` and `docs/review-learnings.md`** — narrative history. A
  scanner reading them would report every past decision as a pending one.
- **`TODO`/`FIXME` in prose** — the marker is scanned only in tracked files
  under `bin/`, `dashboard/`, `tests/` and `.github/scripts/`. In `skills/` and
  `docs/` the word is documentation of the convention, not an instance of it.

What the scan found in this repository on `8cf99431` is recorded in
`implement.md`'s verification step, not here, so the two documents do not both
assert a count.

### The fixed skeleton

Twelve headings, always printed, in this order. An empty section prints one
indented sentence.

```
sd-status: <repo>        (+ the pack line)
abnormalities
pending
next
open threads
work items
open pull requests
detected setup
issues (this repo, from the index)
protection
resumable handoffs
backends
legacy residue
```

The three new sections go first because the report is read top-down and the
judgement is what the reader came for; the eight existing sections keep their
existing order underneath, so nobody's muscle memory breaks.

### `AskUserQuestion`, and the 10-into-4 problem

The component allows at most four options per question and at most four
questions, with an optional `multiSelect`. Ten pending items do not fit, and
spreading them over three questions abuses a control meant for distinct
dimensions — the user would be asked three separate questions to express one
choice.

**The resolution: ids are the primary interface; the component is a shortcut.**
The skill instructs the calling agent to render exactly one question, with
`multiSelect: true`, whose four options are pending rows 1..4 labelled by their
id. Rows 5..10 are addressable by typing the id, which the component's own
free-text answer already supports. The skill states that the agent must not
renumber the options, must not substitute its own ordering, and must not invent
an option that is not an inventory row.

## Decisions

- **2026-09-04, host: one inventory rather than three producers.** Reversed if a
  future section needs a row shape the inventory cannot carry — at which point
  the row grows a field rather than the section growing a producer.
- **2026-09-04, host: hash-derived ids over sequence numbers.** Reversed only by
  requirement 7 being dropped.
- **2026-09-04, host: path-equality merge detection over `--is-ancestor`.**
  Reversed if this repository stops squash-merging, which would make the cheap
  ancestor test sufficient on its own.
- **2026-09-04, host: `--actions` added as a fourth flag.** Parked concern C-6
  records the objection. Reversed by a decision that `sd-*` commands have a flag
  budget.

## Risks

- **Id collisions are handled, not eliminated.** Two rows colliding widen to
  eight hex digits; if one of them later resolves, the survivor reverts to four,
  so its id changed. Accepted: the alternative is a written ledger, which
  requirement 9 forbids, or eight digits everywhere, which costs typability for
  a case under 1% likely. The note printed on collision is what makes the change
  visible rather than silent.
- **The merge detector under-reports.** Named above. Accepted because the other
  direction — claiming a branch merged when it did not — would put a false
  abnormality at the top of the report, which is worse than a missing one in a
  section that also lists the branch as unmerged.
- **`git grep` over the whole index on every run.** One subprocess, bounded by
  four pathspecs. Accepted; the run time is checked in `implement.md`'s
  verification rather than assumed.
- **The concern parser reads prose.** `## Review` sections are written by hand
  and their shape varies — this repository has one as a markdown table and one
  as a `- **C-1 — ... `addressed`.**` list. The parser takes the union of both
  shapes and, for a `C-*` id it can find with no disposition it recognises,
  reports it as `unresolved` rather than dropping it. Failing toward "you should
  look at this" is the correct direction for a section whose whole job is to
  surface what was forgotten.
- **The banner could become the section people skim**, which is what
  `.github/sd-status.json` was built to prevent for protection gaps. The
  mitigation is that every abnormality class here is derived from a
  contradiction that has an action ending it, not from a standing condition; a
  finding that cannot be resolved does not belong in this table. No suppression
  file is added, and adding one later would need its own decision.

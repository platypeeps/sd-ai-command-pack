# Design — the plan interview is one sentence

## Approach

### The item's own Log said no design was needed, and it was right on the day

The Log reads: "No `design.md`: the approach was settled before the item
existed — a standalone skill rather than a `--grill` flag on `sd-plan`, chosen
by the user, and a design restating that is a design nobody needed."

That still holds for the approach it was written about, and this page does not
reopen it. `sd-grill` is a standalone skill; it is not a flag on `sd-plan`; the
user chose that and nothing here revisits it. What the Log could not know is
that the skill would ship two days later and then be moved out from under six
of the nine acceptance criteria by a ruling made the day after it shipped. The
approach that needs writing down is not the skill's. It is what the item's
remaining work now is, given that its subject has already been built and has
already been relocated.

### What is already delivered, and how that is known

`8cf99431` (2026-09-04, #740) added `skills/sd-grill/SKILL.md`. `cec8721e`
(2026-09-04, #741) added the question-form rule under its `## Lineage`.
`05eb8ddf` (2026-09-06) moved the directory to `contrib/sd-grill/`, a pure
rename — `git show --stat` prints
`{skills => contrib}/sd-grill/SKILL.md | 0`, no content change.

Every content criterion in `prd.md` passes today against that file. Run on
`origin/main` at `405a9106`, with `contrib/sd-grill/SKILL.md` substituted for
the path the criterion names:

| criterion | expects | measured |
|---|---|---|
| `disable-model-invocation` | `0` | `0` |
| `^# sd-grill$` | `1` | `1` |
| the `sd-plan` sentence, `grep -cF` | `1` | `1` — this one names `skills/sd-plan/SKILL.md` and needed no substitution |
| `obra/superpowers`, licence and revision on the line | `1` | `1`, and the line reads `github.com/obra/superpowers` (MIT, revision `b36e082`) |
| the seven `**class**` declarations | seven lines each ending `1` | seven lines each ending `1` |
| `## Safety rules`, read-only first rule | present | present |
| `This holds at every classification` under `## The gate` | `1` | `1`, and `## The gate` is the heading above it |

Two criteria are not content checks and are handled separately below: the
`make check` baseline, and the `bin/`/`dashboard/` diff.

The item is nevertheless `planning` — read from the row, which is where
`docs/work/.status-source` says to read it. `.venv/bin/python bin/sd-status`
prints `planning the-plan-interview-is-one-sentence`. The system `python3`
cannot import `sd_db`, falls back to git and prints `in_progress` for the same
item with a warning saying so; that disagreement is a property of the
interpreter, not of the item, and every status claim on this page is the row's.

That the row is still open is not an oversight anybody has to
guess at — #740's own body says why, in as many words: "**The work item is
therefore still `status: planning`, not `ready`.**" C-11 was unresolved and
blocking when the pull request merged, so the merge carried no `Delivers:`
trailer, and `skills/sd-ship/SKILL.md` closes an item on that trailer and on
nothing else. The user then ruled C-11 non-blocking on 2026-09-04 and the
`## Review` section was updated to say so; the row was never moved, and no
later merge has carried `Delivers:` for this item.

This is visible from outside the item, too. `docs/work/2026-09-04-sd-status-answers-is-anything-wrong-first/implement.md`
names it as that item's verification 4: a `branch-already-merged` finding whose
subject is `the-plan-interview-is-one-sentence`. The row still records
`branch: skill/sd-grill`, and listing every local and remote-tracking head
matching `*grill*` in this checkout returns nothing.

### Two different things are called promote, and reading the wrong one inverts this item

`prd.md`'s `## Review` ends "**Promotion is unblocked.**" There are two
promotions in this repository and they point in opposite directions.

- `skills/sd-plan/SKILL.md` step 4: "**Promote.** `planning → ready` only when
  acceptance criteria are present." A status transition on the item's row.
- `sd skill promote <name> --path <path>` in `bin/sd_skill.py`: move a
  directory from `contrib/` to `skills/` and name it on a path, in a pull
  request.

The `## Review` sentence is the first. It sits at the end of a section about
the planning adversarial review, whose whole subject is whether the item may
leave planning, and it was written on 2026-09-04, two days before `contrib/`
existed at all. Reading it as the second turns a sentence saying "this item may
now proceed" into a mandate to undo a ruling made the following day. The
mistake is easy and this design made it for the first twenty minutes of the
work; it is written down so the next reader does not have to make it too.

### Where the file lives is settled, and this item is not who settles it

`docs/work/2026-09-05-the-pack-runs-a-team-process-for-one-person/prd.md`, under
`### Requirement 13 — the review's confirmed cuts and bugs land`:

> Step 1's delegation to `sd-grill` (:23) goes: attended, `sd-plan` asks its
> three to five questions itself; unattended, none. `sd-grill` moves to
> `contrib/` and a trial decides whether it stays, by the operator's decision on
> 2026-09-05.

The same item's Log records it as one of "The three questions from the flow
review, settled by the operator", dated 2026-09-05. That item is `in_progress`
on `feat/solo-first-workflow-policy`. Half of the ruling has executed —
`05eb8ddf` did the move. The other half, removing `sd-plan`'s delegation, has
not.

So a design here that promoted `sd-grill` back to `skills/` would be
overturning an operator ruling from inside the item the ruling was about, one
day after it was made, on the strength of a sentence that means something else.
The direction of the work is the opposite one: the criteria follow the file.

### The criteria are re-pointed; the file is not moved

Six criteria name `skills/sd-grill/SKILL.md`. They become
`contrib/sd-grill/SKILL.md`. Nothing else about them changes: the same
commands, the same expected results, the same fixed-string quoting that C-4 and
C-9 earned. A criterion whose path names nothing in the checkout checks
nothing, and six of the nine are in that state today.

**This is not the bar moving.** The substance each criterion asserts —
frontmatter, title, lineage with licence and revision, the seven declared
classes, the safety section, the gate sentence — is unchanged and still
verified. Only the directory changes, and it changes because a later ruling
moved the file. The distinction matters because amending acceptance criteria
after the fact to match what shipped is the standard way an item marks its own
homework, and this item has to be able to say why it is not doing that. The
answer is that no criterion is being weakened, deleted for being unmet, or
replaced with a check that passes more easily; one path token is being
corrected to the location an operator ruling put the file, and the ruling is
quoted at the criteria so a reader can disagree with the ruling rather than
with this document.

### Requirement 7 and its criterion are retired, not deleted, and this item does not execute the retirement

Requirement 7 — "`sd-plan`'s interview step names the skill" — and its
criterion are met today. This exact command prints `1` on `405a9106`, and it is
fenced rather than inline because the pattern contains backticks and an inline
span holding one is not the command it looks like:

```
grep -cF -- '`sd-grill` is that interrogation written down' skills/sd-plan/SKILL.md
```

The 2026-09-05 ruling removes the sentence it counts.

Three things follow, and the third is the one that is easy to get wrong.

1. The criterion is recorded as met, with the commit it was met at, and marked
   superseded. It is not re-run after the owning item lands, because it will
   correctly fail then.
2. Requirement 7 gains one sentence naming the ruling and the item that owns
   the removal. The requirement is not struck: it was a real requirement, it
   was met, and a later ruling retired it. Striking it would erase the fact
   that the relationship was once asserted in both directions and that
   something decided to stop asserting it.
3. **This item does not touch `skills/sd-plan/SKILL.md`.** The deletion belongs
   to `docs/work/2026-09-05-the-pack-runs-a-team-process-for-one-person`'s
   requirement 13, which enumerates it as one of seven cuts to that file — step
   6's archive and park, the `sd-status --parked` line, the sweep sentence in
   `skills/sd-plan/templates/work-README.md`, the flags table for a `bin/sd-plan`
   that does not exist, `--from-suggestion`/`--from-proposal`, the work-item
   threshold, and this delegation — that must land together. Two items editing one file to execute half a
   ruling each is how the other half gets forgotten, and the enumeration is
   already written down in exactly one place.

### Criterion 1's baseline is stale in the way a budget was stale, and gets the same repair

The criterion reads: "`make check` reports 40 `OK` and 0 `FAILED` — unchanged
from `6b1ea46e`". Measured on this worktree at `405a9106`,
`grep -cE '^OK' unittest-output.log` prints `56` and `grep -c FAILED` prints
`0`. `tests/` tracks 56 modules. The `40` was true on 2026-09-04 and has been
overtaken by sixteen modules that have nothing to do with this item.

The repair is not a new number. It is the form
`docs/work/2026-09-04-sd-status-answers-is-anything-wrong-first/implement.md`
already reached, in its verification 2: the `OK` count is one per test module,
"a pinned figure ages into a false check rather than a failing one", and what
the criterion asserts is that the count is unchanged across this item's own
change and that `FAILED` is `0`. That form cannot rot, and it fails for the
right reason — a module that stopped reporting `OK`.

Pinning `56` instead of `40` would be the same defect with a fresher date on
it. The criterion is being repaired, not re-measured.

### Closure is a merge trailer, not a file edit

`skills/sd-ship/SKILL.md` is explicit: the item closes on a merge carrying
`Delivers: <item>` "and on no other", nothing is written into a file for it,
and its directory stays. Where the merge that delivered went out without the
trailer, "the next merge message `sd-ship` writes in this repository … carries
`Closes: <item>` for it". That is exactly this item's case: #740 delivered and
carried no trailer.

So the last step is a trailer on the merge that lands the amendments, and a row
transition through `sd_db`. No `status:` line is written into `prd.md` —
`docs/work/.status-source` says `row`, and `bin/sd-docs-lint` rule 1 fails an
active item whose `prd.md` carries one.

**The row goes `planning → done` and skips `ready` and `in_progress`.** That
looks like a gate being jumped and is not one. `skills/sd-plan/SKILL.md` step 4
promotes `planning → ready` "only when acceptance criteria are present and **no
open `BLOCKING` line remains**", and step 5 branches — both are gates in front
of work that has already happened here, on a branch that has already merged.
`sd_lib.ROW_STATUSES` admits all six words and `sd-ship` writes `done` on the
delivering merge without consulting the prior state, so nothing refuses the
transition. What would be wrong is closing the item without the amendments, and
D6 is what prevents that; the intermediate states would record a sequence that
did not happen.

### What this breaks in the existing suite

**Nothing.** The change is confined to
`docs/work/2026-09-04-the-plan-interview-is-one-sentence/`, and the checks that
read that directory — `bin/sd-docs-lint` rules 1, 2, 6 and 7 — pass over the
amended shapes: the frontmatter keeps `title`, `created` and `branch` and gains
no `status:`; `## Acceptance criteria` stays a heading rule 2 can match; the
citation manifest stays empty because no criterion cites a `docs/work` markdown
line number; and every `docs/work/` path the amended text names resolves.

That is a claim worth stating as its negation, because the approach that was
rejected does break something. Promoting `sd-grill` to `skills/` without
editing `skills/paths.json` in the same commit fails
`tests/test_sd_install.py::…::test_the_real_checkout_has_three_paths_covering_every_directory`,
which asserts `sd_install.unnamed_directories(REPO_ROOT) == []` against this
repository rather than a fixture. The rejected approach is therefore not merely
against a ruling; it is a red build unless a second file moves with it. That
the correct approach breaks no test and the rejected one breaks a named test is
the sharpest evidence available here that the direction is right.

The one test that changes meaning without changing text is criterion 4's
`grep`, and it changes meaning in a later item's pull request, not in this one.
It is a criterion, not a test module; nothing in `tests/` reads it.

## Validation

Criteria 1 and 5 are the two that are not content checks, and neither is
satisfied by the approach above on its own.

**The `make check` criterion has to be able to fail.** Under the repaired form
it asserts two things: `grep -c FAILED unittest-output.log` prints `0`, and the
`^OK` count is the same before and after this item's change. The second is a
real check only if the before-figure is recorded rather than remembered, so the
baseline is measured on `origin/main` in the same worktree and written into
`## Verification results` before the first amendment, and the after-figure is
measured on the amended tree. A run that recorded only the after-figure would
be asserting a count against nothing.

What could make it fail, correctly: an amendment that added a file under
`docs/work/` with a name rule 1 refuses, which drops
`tests/test_sd_docs_lint.py` out of the `OK` column. What could not make it fail, and is the
reason `56` is not pinned: another item landing a test module while this one is
open.

**The `bin/`/`dashboard/` criterion is evaluated on the pushed branch, and C-8
already established why.** Before the branch has commits,
`git diff --stat origin/main...HEAD -- bin/ dashboard/` prints nothing whatever
the tree holds, so running it early verifies nothing. It runs after the
amendment commits exist. Under this approach it is expected to print nothing
for the honest reason — no line under either directory is touched — rather than
vacuously.

**The re-pointed criteria are re-run verbatim, not adapted.** C-9 on this item
was a criterion verified by running a different command from the one written
down. The guard against repeating it is mechanical: each amended criterion is
executed by copying the text out of the amended `prd.md`, not by typing an
equivalent. The seven-class loop in particular is a multi-line shell block, and
it is the one C-9 was about.

**The ruling quote is checked against its source, not against this page.** The
sentence attributed to
`docs/work/2026-09-05-the-pack-runs-a-team-process-for-one-person/prd.md` is
verified by `grep -F` against that file at the commit the amendment lands on. It
is quoted here without a line number on purpose: that document is `in_progress`
and over five thousand lines, and a line-numbered citation into a living
document is the drift `bin/sd-docs-lint` rule 6 exists to catch. A heading name
and a quoted sentence survive insertions above them; a line number does not —
that sentence sat at line 1023 of 5,030 when this design was written, and every
insertion above it moves the number.

**Mutations, and where each one dies.**

| mutation | what fails |
|---|---|
| a criterion re-pointed to `skills/sd-grill/SKILL.md` after all | the criterion itself, run verbatim: the path names nothing in the checkout, and `grep` prints its own error |
| criterion 4 quietly deleted rather than retired | nothing automated — which is why the retirement note names the commit it was met at and the item that owns its removal, and why this row is in the table |
| the `56` pinned in place of the `40` | nothing today, and the criterion again next week; the repair is the form, and the review is what catches a number sneaking back in |
| the item closed without a `Delivers:` or `Closes:` trailer | `sd-status` keeps listing it as an active `planning` item, which is how the current state was found. Not `branch-already-merged`: `grep -n 'branch-already-merged' bin/sd-status` returns nothing, that check being unbuilt work in another item that is itself still `planning` |

The third row is honest about a gap: the anti-pinning repair has no mechanical
guard, and a future editor may re-pin the count. Stating that is better than a
check that does not exist.

## Decisions

**D1 — the file is not moved back to `skills/`.** Considered:
`sd skill promote sd-grill --path development`, on the argument that
`skills/sd-plan/SKILL.md` installs and names a skill that no longer installs, so
the development path is broken without it — which is the test
`skills/paths.json`'s own comment states. Rejected on evidence, not on taste:
the operator ruled on 2026-09-05 that `sd-grill` moves to `contrib/` and a trial
decides, and ruled in the same breath that `sd-plan`'s delegation goes, which
removes the broken reference by the other end. The argument for promotion is
built on a sentence that the same ruling deletes. `sd skill try sd-grill` is the
route the ruling names, and it is the operator's to take.

**D2 — the criteria move to `contrib/`, and not to a root-independent form.**
Considered: a criterion that finds the file wherever it lives, since `sd skill
list` reads both roots and a trial may move it back. Rejected. A criterion that
cannot notice where the file lives cannot notice a move nobody ruled on, and a
path changing under this document without the document saying so is the entire
reason these criteria are stale. An explicit path that breaks loudly is the
feature. If a trial promotes `sd-grill`, that promotion is a change someone
records, and moving one token in six criteria is the cheapest possible price for
making them say where the file is.

**D3 — criterion 4 is retired with its commit, not struck.** Considered:
deleting requirement 7 and its criterion outright, since the ruling removes what
they check. Rejected. A struck requirement leaves no trace that the two-way
relationship was ever asserted, and the next reader of `skills/sd-plan/SKILL.md`
finds a missing sentence with no record of what removed it. Retiring it names
the ruling, the date, and the owning item, which is what a reader needs.

**D4 — this item does not edit `skills/sd-plan/SKILL.md`.** The deletion is one
line of requirement 13's enumeration of cuts to that file, and the enumeration
exists so the cuts land together. Executing one of them here would leave the
enumeration asserting work already done, which is the cross-artifact drift
shape the review contract's sweep is written about.

**D5 — criterion 1 loses its pinned number rather than gaining a fresh one.**
The precedent is in this repository and is cited rather than re-argued:
`docs/work/2026-09-04-sd-status-answers-is-anything-wrong-first/implement.md`
verification 2. A pinned module count is a check that ages into falsehood; the
invariant — unchanged across this item's own change, `FAILED` zero — is the
thing the criterion was always trying to say.

**D6 — the amendments and the closure ride one pull request, and it carries
both trailers.** `Delivers:` because the work shipped, and it shipped in #740
without a trailer; `sd-ship`'s rule is that the next merge in this repository
carries `Closes:` for such an item. Splitting the amendment and the closure
across two pull requests would leave a window in which the criteria name
`contrib/` and the row still says `planning`, which is a state nobody needs to
exist.

**D7 — this round's review ledger lives in `design.md`, not in `prd.md`.**
The item's `## Review` in `prd.md` is the record of the three rounds that ran
over the PRD in 2026-09-04, including a user ruling and a disclosure attached to
it. This round reviewed a different artifact set — `design.md` and
`implement.md`, which did not exist then — and appending to a section whose
lane statuses and round counts describe the earlier set would make those
statements wrong. The numbering continues from `C-13` so the two ledgers read as
one sequence for the item.

**D8 — `prd.md` is not edited by the change that adds these two pages.** The
amendments are the item's remaining work and are what `implement.md` plans; a
planning commit that also performed them would make the plan a record of
something already done. The corrections are named here with their evidence, and
they land in the implementation commit alongside the closure.

## Risks

**The item can be read as already finished, and closed without the
amendments.** Everything material shipped; a reader who checks the skill's
content and stops will call the item delivered and close the row. What is left
undone in that case is not visible: six criteria naming a path that does not
exist, a baseline that has been wrong since 2026-09-05, and a requirement the
operator retired with nothing in the item saying so. The mitigation is that
closure and amendment are one pull request (D6), so the trailer cannot land
without the corrections beside it.

**The ruling this design rests on lives in another item's `prd.md`, and that
item is `in_progress`.** The quoted sentence could be revised while this item is
open. It is quoted rather than paraphrased and verified by `grep -F` at
implementation time (Validation), so a revision surfaces as a failed check
instead of as a design resting on something that no longer says it. What the
check cannot do is notice a *reversal* recorded somewhere else in a five
thousand line document; that would need a reader, and the reader is the review.

**A trial may put `sd-grill` back under `skills/`, and then six criteria are
wrong again in the other direction.** This is real and is accepted rather than
engineered around, per D2. The cost is one token in six lines, and the benefit
is that the move is visible. What makes it acceptable is that the trial is a
deliberate act with a pull request behind it — `sd skill promote` opens one —
so there is a change for the correction to ride on.

**No line-count ceiling constrains this item, and that is a smaller comfort
than it sounds.** `bin/` measures 17,216 against `BIN_CAP` 18,000 and
`dashboard/` is untouched, but neither number binds because the change adds no
line under either directory; `docs/` has no ceiling in
`tests/test_loc_caps.py` at all. So nothing mechanical would stop this item
growing a five hundred line amendment. The budget in `implement.md` is derived
against measured analogues rather than waved through for that reason, and
criterion 5 is what keeps the claim honest about `bin/` and `dashboard/`.


## Review

Planning adversarial review, 2026-09-07. Trigger:
`.claude/rules/sd-planning-adversarial-review.md`, point **Development / prd and
design**, cap **5**, read from that table and not invented here. Baseline
recorded before the first planning write: `prd.md` present and unmodified,
`design.md` absent, `implement.md` absent. Two of the three are new, so the
trigger applies. Three rounds ran of the five permitted.

**Path sensitivity, and what it switches off.** The changed artifact set is this
item's `design.md` and `implement.md`. `.github/sd-review.json`'s `sensitive`
list is `.github/workflows/**`, `.github/sd-review.json`,
`.github/sd-status.json`, `bin/sd_install.py` and `bin/sd-review`. Neither
artifact is on it, so by section 3 of the contract this review carries no
stable-id ledger obligation and no per-round cross-artifact sweep obligation.
Both were kept anyway, and the contract's instruction is to say which it is: the
numbering continues the item's existing `C-*` sequence because the item already
has one and two half-ledgers read worse than one, and the sweep ran because the
two pages share a dozen measured values. Kept by choice, not owed.

**Lanes, and the second one is unavailable rather than skipped.**

- Host: completed, three rounds. It is the lane that wrote the artifacts, which
  is the same conflict of interest `prd.md`'s C-11 disclosure named, and it
  applies again here.
- The repository's reviewer chain: **resolves to nobody.**
  `bin/sd-review --scope planning --item 2026-09-04-the-plan-interview-is-one-sentence --explain`
  runs nothing and reports `route tier skip category docs`, `providers (none)`,
  and, of the five registry entries, "this repository has no 'reviewers' line in
  CLAUDE.local.md, so no entry may receive its diff and no reviewer resolves."
  There is no `CLAUDE.local.md` in this worktree or in the main checkout. So the
  Codex lane that `prd.md`'s 2026-09-04 ledger records is not available today,
  and reporting it as "skipped" would claim a choice nobody made. Per section 2,
  the host lane held itself to the standard two lanes would have met; that it
  needed three rounds to reach C-19 and C-28 says how far short of two lanes one
  lane is.
- Two independent readers were spawned to stand in for the missing lane and
  **neither reported inside its budget**. Nothing in this ledger comes from
  them. Recorded because a reader who sees three host rounds should know a
  second opinion was attempted and did not arrive, rather than assume none was
  tried.

| ID | Round | Severity | Blocking | Disposition |
|---|---|---|---|---|
| C-14 | 1 | high | yes | addressed |
| C-15 | 1 | high | yes | addressed |
| C-16 | 1 | medium | yes | addressed |
| C-17 | 1 | medium | yes | addressed |
| C-18 | 1 | low | no | addressed |
| C-19 | 2 | high | yes | addressed |
| C-20 | 2 | medium | yes | addressed |
| C-21 | 2 | medium | yes | addressed |
| C-22 | 2 | medium | no | addressed |
| C-23 | 2 | low | no | addressed |
| C-24 | 2 | low | no | addressed |
| C-25 | 2 | low | no | addressed |
| C-26 | 2 | low | no | addressed |
| C-27 | 2 | low | no | addressed |
| C-28 | 3 | high | yes | addressed |
| C-29 | 3 | medium | yes | addressed |
| C-30 | 3 | low | no | parked |

**C-14 — the design's first approach was a promotion the operator had already
ruled against.** Round 1 read `prd.md`'s closing "**Promotion is unblocked.**"
as `sd skill promote`, found `contrib/sd-grill/` and `skills/paths.json`, and
built an approach around moving the directory back onto the `development` path.
The ruling that forbids it is in another item's `prd.md` under
`### Requirement 13 — the review's confirmed cuts and bugs land`, dated
2026-09-05, and was reached only by grepping that 5,030-line document for
`sd-grill`. Addressed: the approach is inverted — the criteria follow the file —
D1 records the rejected alternative with the evidence that rejects it, and the
misreading has its own subsection, because the sentence is genuinely ambiguous
and the next reader will meet it too.

**C-15 — the design asserted the acceptance criteria pass without having run
them.** The first pass wrote that the skill satisfies its criteria as it stands.
That is this item's own C-9 in new clothes: a claim about a command's result
made without the command. Addressed: all seven content criteria were executed
against `contrib/sd-grill/SKILL.md` at `405a9106` and the measured results are
tabulated, including the lineage line's actual text.

**C-16 — re-pointing acceptance criteria to match what shipped had no defence
written down.** Six criteria change to name the location the file turned out to
be in, which is the same shape as an item lowering its own bar after the fact.
Addressed: the "This is not the bar moving" paragraph states the distinction and
what would falsify it — no criterion weakened, deleted for being unmet, or given
an easier check.

**C-17 — the design proposed executing the retirement it had just discovered.**
The first pass deleted `sd-plan`'s sd-grill sentence here. That would have taken
one line out of an enumeration of seven cuts to the same file that requirement
13 exists to land together. Addressed: D4, and this item touches no file under
`skills/`, which verification 5 checks by path rather than by reading the diff.

**C-18 — the item's own Log said no design was needed and the design ignored
it.** Producing a design for an item whose Log calls a design unnecessary,
without addressing that, is the shape the Log warns about. Addressed: the
opening subsection agrees with the Log about the approach it was written about
and names what changed after it.

**C-19 — `implement.md` verified the closure with a check that does not
exist.** Verification 7 counted `branch-already-merged` findings from
`bin/sd-status`. `grep -n 'branch-already-merged' bin/sd-status` returns
nothing: that check is unbuilt work in
`docs/work/2026-09-04-sd-status-answers-is-anything-wrong-first`, which is
itself still `planning`. A verification naming a check that cannot run is a
verification that cannot fail. Found by running the grep rather than by reading
the sentence. Addressed: verification 7 is now `.venv/bin/python bin/sd-status`
reporting the item `done`, with the false start recorded beside it; the same
phrase in the Validation mutation table was corrected in the same pass, which is
where it would otherwise have survived.

**C-20 — two commands were printed as inline spans containing backticks, and
are not the commands they look like.** The requirement 7 `grep -cF` in
`design.md` and step 2's ruling check in `implement.md` both embed a backticked
`sd-grill` inside a single-backtick span, so the span terminates early and what
is printed is not runnable. This is precisely C-9's failure on this item,
reproduced by the pages describing it. Addressed: both are fenced blocks, and
each says why it is fenced.

**C-21 — the status claim named no interpreter, and the two disagree.**
The design said the item is `planning`. Run with the system `python3`,
`bin/sd-status` cannot import `sd_db`, falls back to git and prints
`in_progress` for this item with a warning; run with `.venv/bin/python` it reads
the row and prints `planning`. Asserting one word without saying which reader
produced it is how the wrong one gets quoted. Addressed: the claim names the
interpreter and the disagreement, and verification 7 names it too.

**C-22 — the row transition skips two states and the design had not said so.**
`planning → done` passes over `ready` and `in_progress`, which are `sd-plan`
steps 4 and 5. Addressed: the subsection states it, names why nothing refuses it
(`ROW_STATUSES` admits all six and `sd-ship` writes `done` without consulting
the prior state), and says what would actually be wrong — closing without the
amendments, which D6 prevents.

**C-23 — a test module was named that does not exist.** Validation cited
`tests/test_docs_lint`; `ls tests/` shows `test_sd_docs_lint.py`. Addressed.

**C-24 — "a dozen other cuts" was a count nobody had made.** Requirement 13's
`sd-plan` bullet enumerates seven. Addressed: the seven are listed, so the claim
is checkable rather than atmospheric.

**C-25 — a line-number citation was written in the one form the lint records.**
Validation ended with a backticked `prd.md:1023` as an example of what not to
write. `bin/sd-docs-lint`'s `CITATION_RE` matches exactly that shape, and
`resolve_citation` looks beside the citing page first, where `prd.md` is this
item's own 291-line file. It fails nothing today — this item's `.citations.tsv`
is empty and `write_citation_manifest` drops an out-of-range start — but an
example of a bad citation written in the citation syntax is a trap left for
`--record-citations`. Addressed: the number is prose now.

**C-26 — an unbounded claim from one checkout's refs.** "No head anywhere has
that name" was read off a branch listing in this worktree. Addressed: the
sentence says what was listed and where.

**C-27 — a table row sat under a premise that was false for it.** The criteria
table is headed "with `contrib/sd-grill/SKILL.md` substituted"; the `sd-plan`
sentence row names a different file and needed no substitution. Addressed: the
row says so.

**C-28 — the `## Review` section was written before the review ran.** The first
saved `design.md` carried a ledger of eleven concerns with dispositions, a
cross-artifact sweep paragraph and a lane status, none of which had happened at
the time they were written; four rounds were claimed and none had been held.
Some entries described real corrections made while drafting and some did not,
and nothing in the section said which was which. **This is the exact failure the
item exists to prevent — assistant-supplied content presented as a record the
user can rely on — reproduced inside the design for the skill that forbids it,
and by the mechanism `contrib/sd-grill/SKILL.md` step 7 names: a plausible thing
written into a silence.** Addressed: the section was deleted and rewritten from
the rounds that actually ran, every entry now names the command or the file that
produced it, and this entry is the record that it happened rather than a quiet
repair. It is kept at the top of round 3 rather than folded away, because a
ledger that omits its own worst entry is the thing it is describing.

**C-29 — the lane statement claimed a choice that was not made.** The
pre-written section said the repository lane was "not run" because this run was
instructed not to post anywhere. `bin/sd-review --explain` shows it resolves to
no reviewer at all: no `reviewers` line exists in any `CLAUDE.local.md`, so no
entry may receive a diff, and the route is `tier skip` besides. "Skipped"
attributes to a decision what is actually an absent consent line. Addressed: the
Lanes paragraph quotes the tool.

**C-30 — the anti-pinning repair to criterion 1 has no mechanical guard.**
Nothing stops a later editor pinning `56` where `40` used to be, and the
criterion would rot again on the same schedule. Parked, not blocking. The guard
would be a lint on the wording of one acceptance criterion, which is a mechanism
invented to enforce one sentence. Trigger: a second criterion in this repository
found rotted for the same reason. Owner: the user. It is in Validation's
mutation table as an admitted gap rather than left implicit.

**Cross-artifact sweep, run each round.** The values that appear on more than
one page, each measured once and then searched for rather than read in
sequence: `contrib/sd-grill/SKILL.md` and its 289 lines; `17,216` and `18,000`,
both from `tests/test_loc_caps.py`'s own `line_count(tracked("bin"))` and
`BIN_CAP` at `405a9106`; `56` and `0` from `unittest-output.log`; the commits
`8cf99431`, `cec8721e`, `05eb8ddf` and `405a9106`; and the analogue sizes 6, 4,
13, 4, 0.975 and 13, each measured in `prd.md` and quoted in `implement.md`'s
budget table. All agree across the two pages after round 3. Round 2's sweep is
what found C-19's second copy — the same non-existent check named in
`implement.md`'s verification and again in `design.md`'s mutation table, which
is the "corrected in one artifact, left standing in the other" shape the
contract's sweep is written about, and the reason fixing the sentence you were
reading is not enough.

**Every concern is addressed or parked, and no parked concern blocks.** C-30 is
the only parked one and is non-blocking by its own terms. Implementation is
unblocked. Two limits on that sentence, both real: one lane ran, and it is the
lane that wrote the artifacts; and C-28 was a defect that survived two full
rounds of that same lane before the third caught it.

# Implement — sd-status answers "is anything wrong" first

## Budget

The whole change lands in `bin/sd-status`, `skills/sd-status/SKILL.md` and
`tests/test_sd_status.py`. `dashboard/` is not touched at all, so neither
`DASHBOARD_CAP` nor `DASHBOARD_CODE_CAP` moves.

**Re-derived 2026-09-07 as R11-D46, because the first figure here had gone ten
times stale.** This section originally read 12,416 lines on `8cf99431` against
a 14,000 ceiling, 1,584 of headroom, and claimed at most 600 of them. Every one
of those numbers is now wrong in the same direction. `bin/` measures **17,189**
on `main` at `6f9b96ad` — `line_count` over the files `tracked("bin")`
enumerates with `migrate-*` filtered out, which is exactly what
`test_bin_stays_under_its_ceiling` does — against the 17,250 R11-D45 left.
The headroom is **61 lines**, not 1,584. A claim of 600 against 61 is not a
budget; it is a sentence that stopped being checked. The clause at the top
of `tests/test_loc_caps.py` is why that mattered: a cap is never raised in the pull request that busts it, so
discovering this while implementing would have cost a re-derivation and a
second pull request before a line of the item could land.

The derivation is in `tests/test_loc_caps.py` at R11-D46 and is not repeated
here — one copy, in the file the test reads. Its result: **801** reserved,
`BIN_CAP` moved 17,250 to **18,000**, and the item is funded whole rather than
sliced. 524 of that is body, priced span by span at named built analogues in
`bin/sd-status` itself; 89 is glue at that file's own measured 5.21 lines per
definition boundary rather than at its class mean; 0 is seam, because both
boundaries that look new — `git grep` over the ledger corpus and
`git diff --no-renames` — go through the built `sd_lib.git_output` and have had
their discovery made already, in step 3's prototype run and step 2's
five-branch verification below; 159 is body variance at the 26% R11-D45 sized
to the worst overrun yet seen; 29 is post-report discovery at 5.5%.

**801 is a real increase on the 600 this section used to claim, and the reason
is not scope creep.** 600 was never derived — it was a round number chosen when
1,584 lines of headroom made the choice free. 613 of body and glue against 600
guessed is the estimate landing almost exactly where the guess did; the other
188 is the two contingency lines the method did not have in September's first
week and earned across PR 8's four slices.

The ceiling is what checks this, not this paragraph.

## Step checklist

- [x] **1. The inventory producer.** Landed 2026-09-07, `333d1eec`. Add
      `CLASSES`, `EXCLUDED`, `action_id()` and `actionable_inventory()` to
      `bin/sd-status`, plus the per-class
      producers. Landable and green on its own: nothing renders it yet, and
      `python3 -m unittest tests.test_sd_status` still passes.
- [x] **2. The merged-branch derivation, two-tier.** Landed 2026-09-07. `branch_landed(root,
      branch, default, pulls)` — ancestor test, then the `--no-renames`
      path-equality test, then a pull request matched by `headRefName` whose
      `mergedAt` is set, whose `baseRefName` is the default branch, and whose
      `headRefOid` equals the branch tip. Returns `landed` / `not landed` /
      `unknown`, never a bare boolean. Regression cases, both from C-19: a
      branch extended after its PR merged must not report landed, and a PR
      merged into a non-default base must not count.
      ~~Verified against this checkout's five squash-merged branches:
      tier 1 resolves three, tier 2 resolves the remaining two, ancestry
      resolves none.~~ **That verification cannot be run and was not run.**
      `git ls-remote --heads origin` returns `main` and nothing else: all five
      were deleted at their own merges, three of them by this session's
      `--delete-branch`. The design's table was measured on 2026-09-04 against
      a corpus that no longer exists, which is this item's own recurring defect
      class -- a check written while the evidence stood, cited later as though
      it still ran. It is struck rather than quietly restated.

      **Substituted, and stronger in the way that matters:** each row of that
      table is reconstructed as a git fixture, so the shapes are tested
      deterministically instead of being sampled from whatever `origin`
      happens to hold. Twelve tests in `BranchLandedTests`, against real git
      and not a mock, because the claim under test is *which git commands
      answer correctly in a repository that squash-merges*.
- [x] **2b. The three-state banner.** Landed 2026-09-07. `clear` /
      `n finding(s)` / `unchecked: reason` per class, with unchecked counted
      separately from clear in the summary line. `banner(inventory)` builds one
      row per abnormal class in `CLASSES` whether or not it fired, so the
      reader learns what was looked at and not only what was found.

      **The summary is assembled so the word `clear` cannot be printed while
      any class is unchecked**, which is `prd.md:134`'s substring test written
      as a construction rather than as a wording convention: with something
      unread the tail reads `n of 11 checks could not run`, and only with
      nothing unread does it read `all 11 checks clear`.

      Two things this step needed that the checklist line did not say. First,
      the third state has no source until a producer can report *I could not
      look*, so `branch-already-merged` is wired here -- `merged_pulls` fetches
      tier 2's corpus once per run and `_work_rows` turns `branch_landed`'s
      three answers into a finding, nothing, or an entry in `unchecked`.
      Second, `actionable_inventory` now returns `Inventory(rows, unchecked)`:
      a class cannot be kept out of a count it was never separated from, and
      the rows alone carry no channel for a check that produced nothing
      *because it never ran*.

      **`branch-already-merged` is asked only of a branch that resolves** --
      an `elif` after `branch-unresolvable`, not a second `if`. A `branch:`
      naming no ref answers `unknown` for a reason that has nothing to do with
      GitHub, so one stale field would otherwise mark the class unchecked on
      every run and `unchecked` would decay into a second way of saying
      "something is wrong over there". Both that guard and the never-fold-into-
      clear rule were falsified before being claimed: turning the `elif` into
      an `if` produces `{} != {'branch-already-merged': 'gh is not installed'}`,
      and folding unchecked into clear produces `'unchecked' != 'clear'`.

      `merged_pulls` fetches once per run whether or not tier 1 already
      answered. Deferring it until a tier 1 miss would save a call on a clean
      checkout and cost the report its determinism: whether GitHub gets asked
      would depend on which items happen to be open, so two runs a minute apart
      could say `clear` and `unchecked` with nothing having changed.

      Cost: `bin/` 17,887 to **18,035**, 148 lines against the 750 R11-D47
      reserved for steps 2 through 7; 515 of that reservation is left for steps
      3, 3b, 4, 5 and 7. Nothing renders the banner yet, so the report is
      byte-identical again; the acceptance criterion that runs it through
      `--json` with `gh` off `PATH` becomes runnable at step 5, and until then
      its two assertions are made against the structure in
      `BannerTests.test_a_check_that_could_not_run_is_unchecked_and_the_word_clear_is_gone`.

      Review on #791 found two, both real and both fixed there. The banner's
      docstring opened `""""Is anything wrong"` -- legal Python and unreadable.
      And `GH_MERGED_QUERY`, the sentence an `unknown` hands the reader as its
      repair, was typed beside the argument vector rather than derived from it,
      so it named a call without the `--limit 200` the code actually sends. A
      repair is a command the reader is being told to run; one that was never
      the command that failed is the defect this file already fixed once, in
      `delivered`'s repairs. The vector is now the single source and the
      sentence is joined from it, with a test that records the argv
      `merged_pulls` passes and asserts every token of it appears in the
      sentence. Falsified: restoring the old string produces
      `'--limit' not found in 'gh pr list --state all --json ...'`.

      This step shifted `_render_work` a **third** time, 1772 to 1920, and the
      citation in `2026-09-05-the-pack-runs-a-team-process-for-one-person`
      was re-pointed again. Three corrections in three pull requests is now
      recorded on that item's own bullet, with the option of dropping the
      line anchor left to it.
- [ ] **3. The concern-ledger scanner, by row shape.** One
      `git grep -n -E '^\s*(\|\s*|[-*]\s*)?(\*\*)?C-[0-9]+\b' -- docs/work` over
      the index, archived items included. Classify each row against the
      five-vocabulary `DISPOSITIONS` table; an open token beats a closing one on
      the same row; a row with no recognised token becomes an
      `unreadable-concern-row` finding rather than being dropped. Headings are
      not read at all — 75 distinct `##` headings match /review|concern/ and
      only a handful are ledgers. Four rules the prototype earned, all four
      required: dedupe by `(full item path, C-id)`; absorb continuation lines to
      the next blank or next candidate; shape precedence table > bold > prose;
      and never truncate the item path (keying on `split("/")[2]` collapses 487
      archived items into one bucket and loses `C-19` entirely). Expected on
      today's corpus: 245 concerns, 206 closed, 23 open, 16 unclassifiable.
      Note: `[[:space:]]` in the `git grep -E` pattern matches nothing; use ` *`.

      **Two corrections measured 2026-09-07, before step 3 starts.** First,
      `\b` in the pattern above matches nothing either, for the same reason
      `[[:space:]]` does not: `git grep -E` is POSIX ERE here, and `\b` is a
      GNU extension. The counts are decisive --

      ```
      with \b:    0
      without \b: 624
      with -P:    624
      ```

      -- so the scanner uses `([^0-9]|$)` as the right edge, or `-P`. `-P`
      is not portable to a `git` built without PCRE, and this runs on
      whatever a reader has, so the ERE form is the one to build.

      Second, **the expected corpus figures are stale.** `245 concerns, 206
      closed, 23 open, 16 unclassifiable` was measured on an older tree.
      Deduping today's 624 matching rows by `(file, C-id)` gives **530**
      across 22 item directories. That count is a rough shape and not the
      scanner's -- it takes the first `C-` id on each line and does not
      absorb continuation lines -- so 530 is not the number to write into a
      test. What it does establish is that 245 is no longer a measurement of
      anything, and the step must re-derive its own figures against the
      corpus standing when it lands rather than assert these. Which is this
      item's recurring defect class, caught before the assertion this time.
- [ ] **3b. `accepted-gap-standing`.** Each `.github/sd-status.json`
      `accepted_gaps[]` entry becomes an inventory row carrying `since` and
      `until`, rank 45, not abnormal.
- [ ] **4. The three new sections and the fixed skeleton.** `_render_banner`,
      `_render_pending`, `_render_next`, `_render_threads`, and an empty-state
      sentence for each of the eight existing sections that could vanish.
- [ ] **5. `--actions`, and the `--json` keys.** `abnormalities`, `actions` and
      `next` added to `collect()`; `SCHEMA_VERSION` bumped to 3, because
      consumers gain keys and the report gains a section order they may depend
      on.
- [ ] **6. `skills/sd-status/SKILL.md`.** The twelve-section order, the ranking
      table, the id scheme, and the `AskUserQuestion` contract with its
      4-option/4-question limit and the resolution.
- [ ] **7. Tests.** Every new behaviour in `tests/test_sd_status.py` — no new
      module, so `make check`'s `OK` count does not change. Named cases, in order of
      what they protect: **(a)** two checks firing on one pull request produce
      two rows with two different ids — C-11's regression, which fails under the
      rejected letter-keyed formula; **(b)** a squash-merged branch is detected
      as landed and an unmerged one is not; **(c)** the `## Review` scanner
      reads both ledger shapes and defaults an unrecognised disposition to
      `unreadable-concern-row`; **(c2)** a class whose data could not be fetched
      prints `unchecked` and is not counted clear; **(c3)** an item that is
      `in_progress` *and* `parked:` *and* under `archive/` at once — the real
      case is `archive/2026-09/2026-08-21-port-integration-only-profile` —
      resolves to exactly one row per firing check and no crash; **(d)** the
      section skeleton is identical for a repository
      with content and one with none; **(e)** the pending cap prints at most 10
      rows and states the suppressed count.

## Verification

Named before the work, and each names its own result.

1. `python3 -m unittest tests.test_sd_status -v` → `OK`, 0 failures, 0 errors.
2. `make -C <worktree> VENV=<shared venv> check` → the tail prints no `FAILED`
   and `grep -c FAILED unittest-output.log` prints `0`. The `OK` count is one
   per test module and is **not** pinned to a number here: the baseline measured
   on `8cf99431` was 40 modules and `tests/` now tracks 56, so a pinned figure
   ages into a false check rather than a failing one. The count before and after
   this item's own change must match, and step 7 adds no module.
3. `python3 -m unittest tests.test_loc_caps` → `OK`. This is the check that
   enforces the budget above; the budget is not separately asserted. R11-D46
   moved `BIN_CAP` to 18,000 in its own pull request touching nothing under
   `bin/`, so this test is green before the item's first line of code and stays
   the only thing standing between the item and its reservation.
4. `./bin/sd-status --json | python3 -c "..."` counting
   `check == 'branch-already-merged'` findings → `1`, naming
   `the-plan-interview-is-one-sentence`. This is the criterion that would have
   failed under the rejected `--is-ancestor` derivation, so it is the one that
   proves C-1 was actually fixed rather than described.
5. Id stability: `./bin/sd-status --json` run twice, the `id` fields diffed →
   no output.
6. Read-only: `python3 -m unittest tests.test_sd_status.ReadOnlyTests` → `OK`.
   The existing digest test brackets a full run; if any new code path writes,
   this is what says so.
7. Run time: `time ./bin/sd-status >/dev/null` → recorded here after the fact,
   as the evidence rebutting C-4. A wall time over 5 seconds means the concern
   was right and the scanners need narrowing.

**Not verifiable here.** That the report *reads* as a report — that a person
opening it sees the abnormality before anything else — is the user's eyes on the
first real run. And that a calling agent renders four `multiSelect` options from
the pending list is a property of the agent; the skill states the contract and no
test in this repository can assert conformance to it.

## Verification results

Filled in as each check runs, so a claim here is a transcript and not a plan.

- 2026-09-04 baseline, before any code change: `make check` →
  `grep -cE '^OK' unittest-output.log` = `40`, `grep -c FAILED` = `0`.
- 2026-09-07, step 1: `make check` (shared venv) → `grep -c FAILED` = `0`,
  `grep -cE '^OK'` = `56`, unchanged, step 1 adding no module.
  `tests.test_sd_status` → `Ran 99 tests ... OK`, 69 before.
  `tests.test_loc_caps` → `Ran 8 tests ... OK`. `ReadOnlyTests` → `OK`.
  Check 4 is **not** run yet and cannot be: `branch-already-merged` is step 2,
  and step 1 ships its `CLASSES` row with no producer behind it.
  Id stability held on this checkout: 45 rows, two runs, identical ids, all
  unique.
- 2026-09-07, step 1 measured `bin/` at **17,800** against `BIN_CAP` 18,000.

## Budget, amended after step 1

Step 1 cost **584** lines, measured at `d3166845~1` and `d3166845` by the two
functions `test_bin_stays_under_its_ceiling` calls. R11-D46 priced the same
spans at about **328** — 260 of body plus roughly 68 of glue at the file's 5.21
rate. The gap is 256, and it is in the derivation rather than in the scope:
nothing was built that the design did not ask for.

Two causes, both nameable:

- **The four adapters were priced at 24 and cost 121.** R11-D46 called each
  "a six-line row shaper". A row carries `title`, `detail` and `suggest` prose
  and a docstring, and six lines cannot hold them. This is the first span in
  the series priced by its shape rather than at a named built analogue, and it
  is the one that missed.
- **Four helpers were never priced at all and cost 77**: `_row` 18,
  `_widen_collisions` 17 — the collision handling the design requires —
  `_age_days` 18, `_branch_names` 24. Seven one-line module constants were
  unpriced too, for a further 7, so 84 of the 584 answered to no price at all.

**The remaining steps do not fit.** R11-D46 still prices about 264 of body for
steps 2 through 5, plus glue, against **200** of headroom. That is recorded
here and not acted on: a cap is never raised in the pull request that busts
it, and step 1 does not bust it — 17,800 is under 18,000 with the tests green.
The next step to touch `bin/` needs a re-derivation first, and that
re-derivation has step 1's own span-by-span measurement to price adapters and
helpers against, rather than a shape guess.

**And that re-derivation raises the ceiling; it does not cut the steps.** The
operator's ruling of 2026-09-07, in their words: *"whatever does not reduce
existing functionality. We gotta get out of the proposal to remove
functionality to maintain a cap. I will never agree to that. If functionality
requires more code, then it requires more code."* So the shortfall above is a
statement about the ceiling, not about steps 2 through 5. None of them is
dropped, deferred or trimmed to fit 18,000. The cap exists to make growth
deliberate and measured, which is why a raise is derived and recorded rather
than waved through — and why it is never raised in the pull request that busts
it. It does not exist to decide what the tool does.

**R11-D47 is that re-derivation, and it is done.**

**And step 2 is the first test of R11-D47's method, which held.** `branch_landed`
was priced at 41, funded at 62 by the 1.5x that R11-D47 charges a span priced at
a built same-file analogue. It came in at **55**, or 1.34x -- inside the charge
and inside the 1.29-1.73 band the four producers set. The two other predictions
came in as well: unenumerated spans cost **7** (`_changed` at 6 and the
`LANDED`/`NOT_LANDED` line) against the 13 the 32% surcharge reserved, and glue
was **10** on a 62-line measured span, or **16.1%**, against the 16.3% charged.
Step 2 spent 72 of the 739 and `bin/` stands at 17,872 with 678 of headroom.

One observation is not a validated model, and the two spans still to come --
the ledger scanner at 96 and the renderers at 79 -- are the larger half. But the
failure mode R11-D46 hit was a span priced by shape missing by five, and this
span was priced at an analogue and missed by a third of its contingency.

**Step 2's 72 lines shifted a citation in another item, and the gate caught it.**
`2026-09-05-the-pack-runs-a-team-process-for-one-person` cites `_render_work` as
an analogue for a 38-line reservation. Re-pointing it turned up two wrong
measurements that predate this change: `residue_section` starts at 990 and was
cited at 986, and `_render_work` is 24 lines and was cited as 19. Both are
corrected in place; the 38 they feed is 43 by its own arithmetic, and that is
reported on that page rather than re-derived here, because the reservation is
that item's to move.

Worth naming because of *how* it surfaced. The stale end line sat there through
every prior run: `test_every_anchored_citation_names_its_symbol_at_the_cited_line`
compares the symbol at the **start** line and never reads the end, so a range
whose end is five lines short passes. It only became visible when an unrelated
edit moved the start. That is the gap
`2026-09-04-the-citation-gate-skips-what-it-cannot-match` exists to close,
arriving here from a direction its own measurement did not count. `BIN_CAP` moves 18,000 →
**18,550** on a base of 17,800 measured on `main` at `5c23df19`, funding steps
2 through 7 at **739**: 488 of body, 80 of glue, 0 of seam, 148 of variance and
23 of post-report discovery. Three things it learned from step 1 rather than
guessing again — a span priced at a built same-file analogue lands within about
1.5x of it, a span priced by its *shape* missed by five, and 32% of what step 1
delivered answered to no price at all. The full derivation is in
`tests/test_loc_caps.py`, which is the only place a ceiling is allowed to be
argued. Steps 2 through 7 are funded whole; none was trimmed to fit.

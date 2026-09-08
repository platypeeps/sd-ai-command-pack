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
      any class is unchecked**, which is `prd.md:143`'s substring test written
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
- [x] **3. The concern-ledger scanner, by row shape.** Landed 2026-09-07. One
      `git grep -n -E '^ *(\| *|[-*] *)?(\*\*)?C-[0-9]+([^0-9]|$)' -- docs/work`
      over the index, archived items included. That is the POSIX ERE form and
      it is the one to run; `\s` and `\b` are the two corrections recorded
      below, and both match nothing here. Classify each row against the
      five-vocabulary `DISPOSITIONS` table; an open token beats a closing one on
      the same row; a row with no recognised token becomes an
      `unreadable-concern-row` finding rather than being dropped. Headings are
      not read at all — 75 distinct `##` headings match /review|concern/ and
      only a handful are ledgers. Four rules the prototype earned, all four
      required: dedupe by `(full item path, C-id)`; absorb continuation lines to
      the next blank or next candidate; shape precedence table > bold > prose;
      and never truncate the item path (keying on `split("/")[2]` collapses 487
      archived items into one bucket and loses `C-19` entirely).

      **The pattern and the counts were both re-measured 2026-09-07, before
      this step starts.** Two corrections, and the checklist line above already
      carries the first one.

      `\b` matches nothing here, for the same reason the previously noted
      `[[:space:]]` does not: `git grep -E` is POSIX ERE and `\b` is a GNU
      extension. `\s` in the original anchor fails the same way. Decisive --

      ```
      with \b:    0
      without \b: 624
      with -P:    624
      ```

      -- so the right edge is `([^0-9]|$)`. `-P` answers identically and is not
      portable to a `git` built without PCRE, and this runs on whatever a
      reader has, so the ERE form is the one built.

      **The corpus figures this step used to assert are retired.** `245
      concerns, 206 closed, 23 open, 16 unclassifiable` was measured on an
      older tree and is no longer a measurement of anything. A prototype of
      the full scanner -- all four rules, continuation absorption included --
      run against the corpus on 2026-09-07 returns:

      ```
      624 candidate rows   530 distinct concerns
      430 closed   24 open   18 parked   58 unclassifiable
      ```

      and `C-19` surfaces as `parked` from
      `archive/2026-08/2026-08-26-codex-local-review-adapter/prd.md:61`, which
      is the must-survive case. These are recorded as the shape to expect, not
      as numbers to pin a test to: the step re-derives against the corpus
      standing when it lands, because a count asserted from a run three days
      old is this item's own recurring defect class.

      **One of those numbers is a decision this step has to make, not a
      measurement it can report.** The design accepted 16 unclassifiable of 245
      (6.5%) as honest noise in the correct direction. Today it is 58 of 530
      (10.9%), and `unreadable-concern-row` is an *abnormal* class, so all 58
      land in the banner whose whole job is to be readable at a glance. **37 of
      the 58 come from one file**, `2026-09-05-the-pack-runs-a-team-process-for-
      one-person/prd.md`, whose ledger is written `- C-113, minor: ...` with the
      disposition in a later `## Log` paragraph rather than on the row. Three
      ways out, none of them free: carry the 58; teach the scanner that item's
      shape; or make the class non-abnormal so it reports without asserting.
      **Resolved on Sven's word: teach the scanner the shape.** Read, the 58
      turned out not to be a shape problem at all but the sixth vocabulary
      `design.md` named and declined to add -- `Corrected.`, `Recorded rather
      than silently recounted.`, `Noted in the registry block`, `superseded
      here`, `**Confirmed, design changed.**`. The design's reason for
      declining was that a vocabulary should grow when a row is read and
      understood rather than when a count is being tuned. The rows were read,
      one by one, and those five words are dispositions written by hand in
      ledgers older than this scanner.

      Adding them is safe by construction and not by hope. Closing words are
      checked **last**, after parked and after open, so a closing word can only
      ever reclassify a row nothing could read -- never an open one. Measured
      across every candidate combination, `open` and `parked` moved by exactly
      zero:

      ```
      base       parked 18  open 24  closed 430  unreadable 58
      all five   parked 18  open 24  closed 453  unreadable 35
      ```

      35 of 530 is 6.6%, which is the 6.5% the design accepted at 16 of 245.
      `test_the_sixth_vocabulary_closes_rows_and_moves_nothing_else` asserts
      both halves: the five close, and a row also carrying an open token stays
      open.

      **What the step actually landed, and what each rule cost.** All four of
      the design's rules are in, and all four were falsified rather than
      asserted -- each one broken deliberately to watch the predicted test
      fail:

      | rule broken | test that failed |
      |---|---|
      | ` *` dropped after the table pipe | the whole table ledger vanishes, C-2 lost |
      | closing words checked before open | `['...#C-2'] != None` |
      | shape precedence removed | a `## Log` line parks C-4, `[] != [parked-concern]` |
      | continuation absorption removed | the wrapped row's `Corrected.` is unread |
      | keyed on `split("/")[2]` | `'docs/work/...#C-6' != '2026-08-01-wrapped#C-6'` |

      The shape-precedence test **did not fail on the first attempt**, and that
      is worth recording: rows of equal shape keep the one seen first, so with
      the table written above the `## Log` the broken scanner kept the right
      row by accident and the test passed against it. The fixture now puts the
      Log first. A test that cannot fail is not evidence, and this one was not
      until it was made to.

      **Review on #792 found a fourth tier the design's rule did not have.**
      `design.md` says table > bold > prose, and a `- C-113, minor: ...` row is
      none of the first two, so bulleted ledger rows shared a tier with prose
      sentences that merely open with a `C-` id. Sharing a tier, which of the
      two decides a concern is settled by whichever line `git grep` returns
      first. Measured before changing anything, the three-tier and four-tier
      rules agree on every one of 530 concerns -- 453 closed, 24 open, 18
      parked, 35 unreadable either way, zero verdicts changing -- so this is a
      latent defect removed and not a live misclassification corrected. It is
      still worth removing: the largest ledger in the corpus, 37 rows, is
      written in exactly the bullet form that was sharing a tier with prose,
      and its correctness today is an accident of file order. Precedence is now
      table > bold > bullet > prose, with a test whose fixture puts the prose
      above the row, and which fails when the tier is collapsed back.

      **The verification review found the one disposition word that is also
      ordinary English.** `accepted` sat in `OPEN_WORDS`, and Copilot's second
      pass said an accepted concern is a decision, not a defect. Measured
      before changing anything, the finding was wider than the report: ten rows
      classified `unresolved-concern` on that word alone, and on **eight** of
      them `accepted` is prose -- "validation accepted a codex provider it
      should have refused" -- standing in front of an `addressed` the row
      already carried. Opening words are read before closing ones, so the prose
      won and eight closed rows reported as open defects.

      The fix is a fourth tier rather than a move between the first three. As
      an opening word it opens eight rows that are shut; as a parking word it
      would park them without reading their real disposition; removed
      altogether it leaves the two rows where it *is* the verdict unreadable.
      `STANDING_WORDS` is read **after** the closing words, so it reaches only a
      row nothing else could read, which is the same safety the closing tier
      has and is measured the same way:

      ```
      before   parked 18  open 24  unreadable 35   (77 rows)
      after    parked 20  open 14  unreadable 35   (69 rows)
      ```

      Eight rows leave as closed, two move to parked, and **no row that was
      parked changed at all**. `parked` is where the file side already puts
      this state: `accepted-gap-standing` is rank 45 and not abnormal, so the
      ledger scanner and the `accepted_gaps[]` scanner now agree on what an
      acceptance is. Two tests, both falsified by putting the word back in
      `OPEN_WORDS`: the prose row must not open
      (`[] != [{'check': 'unresolved-concern'...}]`) and the bare `ACCEPTED`
      row must park (`{'parked-concern': [...]} != {'unresolved-concern': [...]}`).

      Verified against the live corpus, which is the point of the whole
      section: **20 parked, 14 open, 35 unreadable**, and `C-19` surfaces as
      parked from
      `docs/work/archive/2026-08/2026-08-26-codex-local-review-adapter/prd.md:61`
      -- the must-survive case, from an archived item, through a `## Review`
      heading no heading-matcher anticipated. The one `git grep` runs in
      **0.043s** real over the whole corpus, which is the run-time this item
      said it would check rather than assume.
- [x] **3b. `accepted-gap-standing`.** Landed 2026-09-07 with step 3. Each
      `.github/sd-status.json` `accepted_gaps[]` entry becomes an inventory row
      carrying `since` and `until`, rank 45, not abnormal -- an acceptance is a
      decision, and re-flagging a decision as a defect is how a banner becomes
      noise. It is listed at all because `until` is prose nothing re-evaluates:
      the entry stays true only for as long as somebody looks, and this is the
      looking. Read from `protection["accepted"]`, which
      `load_acknowledgements` already validates, so no second reader of that
      file is added.
- [x] **4. The three new sections and the fixed skeleton.** Landed 2026-09-07.
      `_render_banner`, `_render_pending`, `_render_next`, `_render_threads`,
      wired into `render()` ahead of the eight that were already there. Twelve
      headings print in `design.md`'s order in a repository with nothing in it
      and in this one.

      **The empty-state sentence for each of the eight is zero of eight.**
      This step was priced for eight sections that "could vanish", and the
      number was checked rather than carried: `sd-status` run in a bare `git
      init` prints all twelve headings, because every one of the eight already
      writes its own empty line -- `none found`, `no open pull requests`,
      `none open`, and so on. Nothing was added and nothing was needed, which
      is budget the step did not spend.

      **Two defects that passed every structural test became visible the
      moment the structure was rendered.** Both are step 2b's, and neither
      could have been seen before there was text to read:

      - *`all 12 checks clear` printed beside `52 findings`.* The tail had two
        branches, blind and not-blind, so a run with findings and nothing
        unchecked asserted every class was clear in the same sentence that
        counted three that were not. The head and the tail describe the same
        twelve classes and contradicted each other; the tail is the half a
        skimmer reads. Three branches now: `N of M could not run` when any
        class is blind, `the other N checks clear` when some fired, `all N
        checks clear` only when none did. The never-say-clear rule outranks
        the new middle branch -- with a blind class the word is still absent
        entirely, because `the other N clear` would count the blind class
        among the clear ones.
      - *The banner printed all 52 findings.* One class carried 35 and pushed
        the other eleven sections off the screen, which is the failure
        `design.md` names under rejected alternatives: the banner becoming the
        section people skim. `BANNER_LIMIT` is 3 per class with the elision
        stated (`... 32 more, ranked in pending`), and the class line already
        carries the true count, so nothing is lost that `pending` does not
        rank.

      **Column widths are measured off `CLASSES`, not typed.** The first draft
      padded to 24 and `in-progress-without-branch` is 26, so that one row
      overflowed and every aligned line below it read as ragged.
      `CHECK_WIDTH` and `SOURCE_WIDTH` are `max(len(...))` over the tuple, so
      a check added to it widens the column on the next run.

      **`collect()` gains `inventory` and `abnormalities`, and
      `SCHEMA_VERSION` goes to 3 here rather than in step 5.** The renderer
      needs the rows and `render()` takes a dict, so the first new `--json`
      key appears at this step. Step 5 adds `actions` and `next` under the
      same version; nothing consumes 3 in between, and bumping twice before
      anything shipped would describe a version that never existed.

      **Every rule falsified, and one test that could not fail.** Six
      deliberate breakages:

      | rule broken | test that failed |
      |---|---|
      | `next` rendered before `pending` | three order assertions |
      | the summary's middle branch removed | `all 12 checks clear` beside a finding |
      | `BANNER_LIMIT` slice removed | the elision line is absent |
      | `CHECK_WIDTH` hardcoded to 24 | the column no longer fits the longest name |
      | one source dropped from the thread counts | the counts stop summing to the inventory |
      | `next` reads `rows[1]` | **passed** -- see below |

      The C-3 test -- the id in `next` is the id at the top of `pending`, one
      row and not a fourth judgement -- **passed against a renderer taking the
      wrong row**, because its fixture built a single item and `rows[1]` fell
      back to `rows[0]`. This is the same failure the shape-precedence test
      had on #792: a fixture whose only row is the right row cannot tell a
      correct renderer from a broken one. Three items now, `assertEqual` on
      the id rather than `assertIn`, and every other row asserted absent from
      the section. It then failed as predicted: `'w0a35' != 'w94b9'`.

      **`test_nothing_renders_it_yet` is retired, inverted rather than
      loosened.** Steps 1 to 3b built producers wired to nothing and that test
      is what said each was landable alone. Step 4 is the step that falsifies
      it, so it now asserts the four sections *are* in the executable's output.
      `actions` stays absent: that key is step 5's.

      **One rule the suite enforces that this step tripped.**
      `test_suite_shape` refuses any class defined after a module's
      `if __name__ == "__main__":` guard, and appending to the file put
      `ReportSectionTests` there. Moved above the guard; the rule is right and
      the append was the mistake.

      Cost: `bin/` 18,262 to **18,367**, 105 lines against 79 priced -- inside
      the 1.34x this item has been running at, and **183 of headroom** left
      under `BIN_CAP` 18,550 for step 5.
- [x] **5. `--actions`, and the `--json` keys.** `abnormalities`, `actions` and
      `next` added to `collect()`; `SCHEMA_VERSION` bumped to 3, because
      consumers gain keys and the report gains a section order they may depend
      on.

      **`SCHEMA_VERSION` was already 3 from step 4, and stays 3.** Step 4
      needed `inventory` under the same version and said so there. Two bumps
      before anything consumed either would describe a version that never
      shipped.

      **`--actions` is uncapped and `pending` is a view of its first ten.**
      `pending` caps because a report is read whole; this is the list a caller
      pipes, so capping it would make the cap the interface. The count leads
      the output so a reader knows the length before the lines scroll.

      **`next` is an object, not a sentence.** A caller acting on the
      suggestion needs the row it came from in the same breath. A bare string
      would send it back to look the id up and it could pick a different row
      than the one the report named.

      **`--json` wins when both flags are given.** It carries `actions` in
      full, so a caller passing both loses nothing; the reverse would drop
      every other key.

      **Four rules falsified, and the second one passed when it should not
      have.**

      | rule broken | test that failed |
      |---|---|
      | `--actions` sliced to `PENDING_LIMIT` | the count no longer equals the rows |
      | the `actions` key sliced to `PENDING_LIMIT` | **passed** -- see below |
      | `next` returned a bare string | the object assertion |
      | `--actions` dropped the leading id | three, including the widened-id one |

      `ActionsFlagTests.result()` builds the `actions` key by hand to exercise
      the renderer, so nothing in that class can see a slice applied inside
      `collect()`. `ActionsCliTests` had the key but asserted only truthiness
      against a one-item fixture, where `rows[:10]` is a no-op. This is the C-3
      fixture defect of step 4 wearing a different hat: a fixture holding one
      row cannot tell an uncapped list from a capped one. A test through
      `collect()` with `PENDING_LIMIT + 4` items now asserts
      `payload["actions"] == payload["inventory"]["rows"]`, and the slice
      fails it.

      **Two acceptance criteria were wrong and were corrected, not worked
      around.** One named a `threads` JSON key with an `unreadable_rows` list;
      no step builds it and no design names it. The guarantee behind it -- a
      row the scanner cannot classify is listed rather than dropped -- is
      already implemented, as `unreadable-concern-row` inventory rows, so the
      criterion had the wrong shape rather than a missing feature and now
      reads the count from `actions`. The other pinned a prototype split of
      245/206/23/16 with `C-19` "among the open ones"; the corpus measures
      531/462/14 open/20 parked/35 unclassifiable and `C-19` is parked, which
      is what #792's `accepted` fix made it. Both now carry the date they were
      measured.

      Cost: `bin/` 18,367 to **18,402**, 35 lines, and **148 of headroom** left
      under `BIN_CAP` 18,550 for steps 6 and 7. Neither of those touches
      `bin/`.
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

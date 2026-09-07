# Implement — a gate that skips silently is a gate that passes

## Budget

**The reservation is zero, and that is the derivation's result rather than its
premise.** Every line of this item lands in `tests/test_doc_citations.py` and in
`docs/`. `assert_cap` is called three times in `tests/test_loc_caps.py` — for
`bin/`, for `bin/migrate-*` and for `dashboard/` — and `tests/` is not among
them, so nothing here is claimed against a ceiling. `BIN_CAP` stays at 18,000
against a `bin/` measuring **17,216** by `line_count` over the files `tracked("bin")`
enumerates with `migrate-*` filtered out, which is what
`test_bin_stays_under_its_ceiling` does. The **784** lines of headroom are
untouched and this item does not so much as read them.

The size is derived anyway, because "it lands in `tests/`" is a reason not to
reserve and not a reason not to know. Same method as R11-D46: body priced span
by span against named built analogues, glue at the measured per-boundary rate
for a module this size, seam at what the crossing actually costs, then variance
and post-report discovery.

**Body is 213**, against analogues measured on this worktree rather than
recalled:

| span | lines | analogue |
|---|---|---|
| `Citation` record and the closed `REASONS` vocabulary | 16 | the four status tuples at `bin/sd-docs-lint:57`, one line each, plus a six-field record and the comment that says why the eight-name vocabulary is closed |
| `classify()` | 32 | `check_work_references` (`bin/sd-docs-lint:465`) is 41 for walk-a-corpus, skip-with-a-named-reason, count, report; this is the same job without its git call and without `METAVARIABLE_RE`'s branch |
| `anchored_citations()` as a thin filter over it | 5 | it is 23 today and becomes a comprehension the existing assertion calls |
| `census()` | 10 | the accumulate-and-note half of `check_citations` (`bin/sd-docs-lint:404`), which is about 10 of its 52 |
| the conservation test | 20 | `test_the_scan_reaches_the_documents` (`tests/test_doc_citations.py:117`) is 15, most of it the docstring saying why it is not a count; this one needs the same paragraph and one more assertion |
| `is_under_repo` split and the missing-target failure | 18 | `is_inside_repo` (`tests/test_doc_citations.py:70`) is 8 and becomes 6; the new assertion is shaped like `test_every_anchored_citation_names_its_symbol_at_the_cited_line`, which is 10 |
| the marker regexes and `marker_after()` | 17 | `anchor_line` (`bin/sd-docs-lint:369`) is 15 for a small positional read whose docstring carries the reason |
| the two marker tests | 26 | `test_a_citation_cannot_send_this_test_outside_the_checkout` (`tests/test_doc_citations.py:133`) is 12 for four fixture assertions; these are seven across two tests |
| `PAREN_PAIR` and its fixtures | 20 | `test_prose_between_a_symbol_and_a_citation_breaks_the_anchor` (`tests/test_doc_citations.py:146`) is 10 for two; five assertions plus the pattern and the comment that says why it needs a parenthesis on both ends |
| the module docstring | 40 | it is 41 today and lists four deliberate skips; it must list five silencers, two markers and three named-and-counted shapes |
| the three counted-not-resolved reasons | 9 | three vocabulary entries and the branches that assign them |

**Glue is 8.** The module has four top-level definitions today and eight after —
`is_symbol`, `is_under_repo`, `marker_after`, `Citation`, `classify`,
`anchored_citations`, `census`, `DocCitationTests`. Four new boundaries, far
under fifteen, so R11-D43's **2.10** for a module this size applies rather than
the 3.70 of the eleven larger ones. 4 x 2.10 = 8.

**Seam is 0.** Nothing crosses a boundary that is not already crossed. The
module reads the filesystem through `pathlib` and `REPO_ROOT.glob` today; it
shells out to nothing, imports nothing new, and the one thing that looks new —
reading `[absent: <reason>]` — is a regex over text already in hand. R11-D44's
correction applies: a seam charge buys the discovery behind an unrepaired
boundary, and there is no boundary here.

**Body variance is 26%**, R11-D45's largest overrun yet observed, kept by
R11-D46 rather than averaged down. 26% of 213 is 55.

**Post-report discovery is 5.5%**, R11-D46's mean of six observations. 5.5% of
213 is 12.

213 + 8 + 0 + 55 + 12 = **288 lines**, taking `tests/test_doc_citations.py`
from 159 to roughly 447. Nothing consumes it, because `tests/` answers to no
ceiling.

The counterfactual is worth stating once, because it is the number a reviewer
would otherwise have to compute to check D6. Had the design put this rule in
`bin/sd-docs-lint` as a rule 8, the same 288 would land against 784 lines of
headroom — 37% of it, affordable without a re-derivation and still the wrong
home, for the reason D6 gives.

## Step checklist

Ordered so that every step is green on its own. Steps 1 to 3 cannot make
anything fail that does not fail today; step 4 is the first that can, and it is
green only because step 3 landed.

- [ ] **1. The classification.** Replace the filter chain in
      `anchored_citations` with `classify()`, returning one `Citation` row per
      `path:line` token found in the corpus, each carrying a reason from
      `REASONS`. `anchored_citations()` becomes the `compared` filter over it,
      so `test_every_anchored_citation_names_its_symbol_at_the_cited_line` is
      untouched and still compares the same 44. Landable and green alone:
      nothing reads the new reasons yet.
- [ ] **2. The census and conservation.** `census()` returns the bucket counts.
      `test_the_scan_reaches_the_documents` keeps both non-emptiness assertions
      and its docstring's reasoning, and gains two more: the buckets sum to the
      number of tokens found, and no row carries a reason outside `REASONS`.
      Print one census line; `.github/scripts/run-tests.sh` does not pass `-b`,
      so it lands in `unittest-output.log`.
- [ ] **3. The marker vocabulary, read-only.** `marker_after()` implements
      0.71.34's grammar exactly: the reason is required, the marker follows the
      citation on the same line with nothing non-blank between them, and it
      covers one citation. `[quoted: <reason>]` yields the `quoted` reason;
      `[absent: <reason>]` is read but does not yet change any verdict. Five
      grammar fixtures, all negative cases from the specification.
- [ ] **4. The split, and the first thing that can go red.** `is_inside_repo`
      becomes `is_under_repo` plus a `target.is_file()` at the call site.
      `escapes-checkout` stays silent; `target-missing` fails **unless** the
      citation carries `[absent: ...]`; an `[absent: ...]` whose target exists
      fails. `test_a_citation_cannot_send_this_test_outside_the_checkout` keeps
      its three outside-the-checkout assertions against `is_under_repo` and
      loses its fourth, which asserted the conflation; the missing-target case
      moves to its own test. Expected on today's tree: exactly one citation in
      the `target-missing` class, already marked, so `make check` stays green.
- [ ] **5. `PAREN_PAIR`.** Added beside `PAIR`, not merged into it, so
      `test_prose_between_a_symbol_and_a_citation_breaks_the_anchor` keeps
      meaning what it means. Five fixtures: parenthesised comma matches,
      parenthesised semicolon matches, bare comma does not, bare semicolon does
      not, and the two shapes taken verbatim from the real list constructions
      the design's table names.
- [ ] **6. The docstring.** Five silencers, each with the reason it exists and
      the count it drops today; the two markers and their grammar; and the
      three shapes named-and-counted rather than resolved, with their numbers.
      Every number re-measured at this step, not copied from `design.md`.
- [ ] **7. This item's own pages.** `prd.md`, `design.md` and this file each
      carry illustrative citation shapes written with a metavariable line
      number because no inert form existed when they were written. Rewrite them
      to use `[quoted: <reason>]`. This is the acceptance test for question 3
      that no fixture can be: if the pages still cannot show the shape they
      discuss, the marker did not solve the problem it was designed for.
- [ ] **8. Criterion 2.** Verify that
      `docs/spec/backend/manifest-and-filesystem.md`'s `prepare-release.py`
      citation is resolved by step 3's marker read rather than by an edit — it
      already carries `[absent: removed with the release train in 0.72.0]`, so
      the mechanism generalising is the whole of the criterion. Confirm the
      other 21 markers in that file are all still true, which under step 4 is a
      test rather than a reading.
- [ ] **9. Criterion 3.** Re-measure every count in `prd.md` and `design.md`
      from the filesystem, and correct both. The PRD's table is a snapshot from
      2026-09-04 and this plan's numbers are a snapshot from 2026-09-07; both
      will have moved. The corrections already known are listed under
      "What the PRD got wrong the second time" in `design.md`.

## Verification

Named before the work, each naming its own result. A partial pass is not a
pass.

1. `.venv/bin/python -m unittest tests.test_doc_citations -v` -> `OK`, 0
   failures, 0 errors, and the test count rises from **4 to 8**. The four are
   enumerated so the number is checkable rather than round: step 3's marker
   grammar, step 4's missing-target failure, step 4's absent-marker falsifier,
   step 5's `PAREN_PAIR` fixtures. Step 2 adds assertions to
   `test_the_scan_reaches_the_documents` rather than a test, which is why it is
   not five.
2. `make VENV=<shared venv> check` -> exit 0; `grep -c FAILED
   unittest-output.log` prints `0`. The `OK` count is one per test module and
   is **not** pinned to a number: it measured 56 on `405a9106` before this item
   and must measure 56 after, because no step adds a module. A pinned figure
   ages into a false check; the before-and-after equality does not.
3. `.venv/bin/python bin/sd-docs-lint` -> `sd-docs-lint: clean`. This item edits
   nothing under `bin/`, so its notes must move only by what this item's own
   pages add. Measured on `405a9106` before these two pages existed:
   `rules 1-2 work items: checked 497 item(s)`, `rule 6 citations: checked 25
   citation(s) across 5 recorded item(s)`, `rule 7 work references: read 54
   reference(s) across 135 file(s)`. Measured with `design.md` and
   `implement.md` staged: **497**, **25**, and `read 55 reference(s) across
   137 file(s)` — two more files because rule 7 reads the git index, and one
   more reference because `design.md` names a sibling item. Any movement
   beyond that is a defect in this item rather than a change in the tree.
4. `.venv/bin/python -m unittest tests.test_loc_caps` -> `OK`. Included not
   because this item claims capacity but because it claims **none**: if this
   test's `bin/` figure has moved at all, a step touched a file it was not
   supposed to touch.
5. **The census, printed and read once.** `grep 'citations:' unittest-output.log`
   -> one line partitioning the corpus. The proposed classification was run
   against this worktree to produce these, and they are to be re-measured at
   step 6 rather than asserted:

   | reason | on `405a9106` | with this item's two pages staged |
   |---|---|---|
   | `compared` | 44 | 65 |
   | `declared-absent` | 1 | 1 |
   | `target-missing` | 0 | 0 |
   | `escapes-checkout` | 0 | 0 |
   | `anchor-not-a-symbol` | 7 | 7 |
   | `separator-not-adjacent` | 33 | 33 |
   | `no-adjacent-anchor` | 273 | 277 |
   | `quoted` | 0 | 0 |
   | **sum** | **358** | **383** |

   The sum equals the `path:line` tokens in the live documents — 358 in 24,
   383 in 26 — which is the conservation property, and it held on both runs.
   162 of the 273, and 166 of the 277, are the elided-path shape. This is the
   check that answers criterion 6, and it is a reading rather than an assertion
   for the reason `test_the_scan_reaches_the_documents`'s docstring gives.

   The second column is the more useful one and is why the table has two: this
   item's own planning pages add 21 compared citations and four more elided
   paths. A plan about a citation gate is a substantial fraction of what the
   gate then checks, and a figure taken before the plan existed would be wrong
   by the time anyone implemented it.
6. **Conservation survives a hostile corpus.** A fixture document containing
   one citation of each declined shape, run through `classify()` -> every row
   carries a reason and the buckets sum to the tokens. This is the check that
   would have caught all four of the PRD's silencers on the day each was
   introduced, so it is the one that proves the item did its job rather than
   described it.
7. **The marker is falsifiable.** A fixture citation marked `[absent: x]` whose
   target exists -> the test fails, with the target named. If this passes, the
   marker is a mute button and D4 was not implemented.
8. **The widening's blast radius, re-measured on the tree of the day.** A
   throwaway script counting `PAREN_PAIR` matches that `PAIR` misses, split by
   verdict -> on `405a9106` this is 1 newly compared, 1 pass, 0 failures. If it
   is not, the corpus moved between planning and implementation and step 5's
   fixtures still hold, because they are literals; what moves is the sentence
   in the docstring, and step 6 re-measures it.

**Not verifiable here.** Whether the census line is *read* by anyone is a
property of the people running `make check`, not of this repository; the
conservation assertion is what stands in for it and is the reason the design
does not rely on the printing. Whether `[quoted: <reason>]` is used honestly —
to mark an example rather than to silence a claim someone could not be bothered
to fix — cannot be tested at all. The census makes its population visible,
which is the most a gate can do about a marker whose whole purpose is to be
unfalsifiable.

## Verification results

Filled in as each check runs, so a claim here is a transcript and not a plan.

- 2026-09-07 baseline, before any code change, on `405a9106`:
  `make VENV=<shared venv> check` -> exit 0, `grep -cE '^OK' unittest-output.log`
  = `56`, `grep -c FAILED` = `0`. `.venv/bin/python bin/sd-docs-lint` ->
  `sd-docs-lint: clean`. `.venv/bin/python -m unittest tests.test_doc_citations`
  -> `Ran 4 tests`, `OK`. `bin/` = 17,216 against `BIN_CAP` 18,000.

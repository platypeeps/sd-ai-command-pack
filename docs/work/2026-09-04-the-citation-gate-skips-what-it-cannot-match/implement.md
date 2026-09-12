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

**Body is 219**, against analogues measured on this worktree rather than
recalled:

| span | lines | analogue |
|---|---|---|
| `Citation` record and the closed `REASONS` vocabulary | 16 | `ITEM_STATUSES` (`bin/sd-docs-lint:57`) and the three tuples under it are one line each, plus a six-field record, `TOKEN` and `SEPARATED_PAIR` written out, and the comment that says why the nine-name vocabulary is closed |
| `classify()` | 32 | `check_work_references` (`source:bin/sd-docs-lint::check_work_references`) is 41 for walk-a-corpus, skip-with-a-named-reason, count, report; this is the same job without its git call and without `METAVARIABLE_RE`'s branch |
| `anchored_citations()` as a thin filter over it | 5 | it is 23 today and becomes a comprehension the existing assertion calls |
| `census()` | 10 | the accumulate-and-note half of `check_citations` (`source:bin/sd-docs-lint::check_citations`), which is about 10 of its 52 |
| the conservation test | 20 | `test_the_scan_reaches_the_documents` (`source:tests/test_doc_citations.py::test_the_scan_reaches_the_documents`) is 15, most of it the docstring saying why it is not a count; this one needs the same paragraph and one more assertion |
| `is_under_repo` split and the missing-target failure | 18 | `is_inside_repo` was 8 and becomes `is_under_repo` (`source:tests/test_doc_citations.py::is_under_repo`) at 6; the new assertion is shaped like `test_every_anchored_citation_names_its_symbol_at_the_cited_line`, which is 10 |
| the marker regexes and `marker_after()` | 17 | `anchor_line` (`source:bin/sd-docs-lint::anchor_line`) is 15 for a small positional read whose docstring carries the reason |
| the two marker tests | 26 | `test_a_citation_cannot_send_this_test_outside_the_checkout` (`source:tests/test_doc_citations.py::test_a_citation_cannot_send_this_test_outside_the_checkout`) is 12 for four fixture assertions; these are seven across two tests |
| `PAREN_PAIR` and its fixtures | 20 | `test_prose_between_a_symbol_and_a_citation_breaks_the_anchor` (`source:tests/test_doc_citations.py::test_prose_between_a_symbol_and_a_citation_breaks_the_anchor`) is 10 for two; five assertions plus the pattern and the comment that says why it needs a parenthesis on both ends |
| the module docstring | 40 | it is 41 today and lists four deliberate skips; it must list five silencers, two markers and three named-and-counted shapes |
| the three counted-not-resolved reasons | 9 | three vocabulary entries and the branches that assign them |
| the token partition rule and its comment | 6 | one loop keyed on token offset rather than on anchor-citation pairs, plus the four-line comment recording that 4 of 7 live `PAREN_PAIR` matches contain two tokens |

**Glue is 8.** The module has four top-level definitions today and eight after —
`is_symbol`, `is_under_repo`, `marker_after`, `Citation`, `classify`,
`anchored_citations`, `census`, `DocCitationTests`. Four new boundaries, far
under fifteen, so R11-D43's **2.10** for a module this size applies rather than
the 3.70 of the eleven larger ones. 4 x 2.10 = 8.

**Seam was 0, and the operator's answer to question 2 made it real.** The
figure below is superseded and kept so the correction is legible.

*As derived:* nothing crosses a boundary that is not already crossed. The
module reads the filesystem through `pathlib` and `REPO_ROOT.glob` today; it
shells out to nothing, imports nothing new, and the one thing that looks new —
reading `[absent: <reason>]` — is a regex over text already in hand. R11-D44's
correction applies: a seam charge buys the discovery behind an unrepaired
boundary, and there was no boundary here.

*As decided:* question 2 was answered "widen the corpus", and a widened corpus
must be asked of **git** rather than walked from the filesystem — a filesystem
walk outside `docs/` picks up untracked files, a `.venv`, and anything a
vendored tree contains, while the index does not. `design.md` said this in
advance and priced it as the one place the answer is not free. So the module
gains a subprocess where it has none today.

**The seam charge is still 0, and now for the R11-D44 reason rather than for
lack of a boundary.** The transport is `sd_lib.git_output`, built and in use at
30 call sites, and the discovery behind the boundary is already written down —
`bin/sd-docs-lint:465` does exactly this for rule 7 and is the model the widened
corpus copies. A seam charge buys discovery that has not happened yet. This one
has.

What does change is body: one call, its error path, and the comment naming the
exclusion. Priced against `check_work_references`'s own git call, that is **6
lines**, carried in the body total below rather than as a seam.

Recording it this way rather than leaving `0` unexplained is the point. The
number is the same; the reason is not, and a later reader finding a subprocess
in a module whose budget said "no boundary here" would be right to distrust the
whole derivation.

**Body variance is 26%**, R11-D45's largest overrun yet observed, kept by
R11-D46 rather than averaged down. 26% of 219 is 57. The 6 lines question 2
added are inside the body's variance rather than outside it; at 225 the same
26% is 58, and the difference is not worth a second figure.

**Post-report discovery is 5.5%**, R11-D46's mean of six observations. 5.5% of
219 is 12.

219 + 6 + 8 + 0 + 57 + 12 = **302 lines**, taking `tests/test_doc_citations.py`
from 159 to roughly 455. Nothing consumes it, because `tests/` answers to no
ceiling.

The counterfactual is worth stating once, because it is the number a reviewer
would otherwise have to compute to check D6. Had the design put this rule in
`bin/sd-docs-lint` as a rule 8, the same 296 would land against 784 lines of
headroom — 38% of it, affordable without a re-derivation and still the wrong
home, for the reason D6 gives.

## Step checklist

Ordered so that every step is green on its own. Steps 1 to 3 cannot make
anything fail that does not fail today; step 4 is the first that can, and it is
green only because step 3 landed.

**Step 0 is taken. The operator answered both questions on 2026-09-07.**

- **Question 1 — narrow it.** Archived citations are compared and a stale one
  is *reported*, not failed: one new reason, `archived-stale`, and one census
  line. Nothing goes red.
- **Question 2 — widen the corpus and exclude `CHANGELOG.md` by name**, with
  rule 7's reason written where a reader finds it.

Both follow one principle from the ruling that decided them: take the coverage,
and do not buy it by editing the historical record. Keeping either exclusion
would have left the gate unable to see something it could see; dropping either
would have paid for sight by rewriting archived documents or historical
changelog entries. `design.md`'s "The two calls that are not mine" carries the
evidence, the options and the reasoning under each.

**Step 9 can therefore close and criterion 5 can be claimed**, because what
step 6 writes into the docstring is the reason, and there is now a reason to
write. What follows is the original note, kept because it states what the
questions gated and why an implementer should not have invented the argument.

**Step 0 was not this agent's to take.** Criterion 5 asks for the archive and
corpus-glob exclusions to be *decided*, and the decision was the PRD's open
questions 1 and 2, which belonged to the operator. `design.md`'s "The two calls
that are not mine" carries the evidence and the options for both, and the
design holds under every answer — what changes is one glob, one `continue`, and
one line of the census. Steps 1 to 8 can be built and landed before either
question is answered. **Step 9 cannot close, and criterion 5 cannot be claimed,
until they are**, because what step 6 writes into the docstring is the reason,
and there is no reason to write until somebody chooses one. An implementer who
reaches step 9 with the questions still open should stop there and say so
rather than invent the argument.

- [x] **1. The classification.** Replace the filter chain in
      `anchored_citations` with `classify(docs=None)`, returning one `Citation`
      row per `path:line` token found in the corpus, each carrying a reason
      from `REASONS`. The parameter defaults to the live glob and is not a
      convenience: `escapes-checkout` has no live instance and `quoted` has
      none until step 7, so without it those branches are unreachable in a test
      and checks 6 and 7 below cannot be written. `anchored_citations()` becomes
      the `compared` filter over it, so
      `test_every_anchored_citation_names_its_symbol_at_the_cited_line` is
      untouched and still compares the same 44. Landable and green alone:
      nothing reads the new reasons yet.
- [x] **2. The census and conservation.** `census()` returns the bucket counts.
      `test_the_scan_reaches_the_documents` keeps both non-emptiness assertions
      and its docstring's reasoning, and gains two more: the buckets sum to the
      number of tokens found, and no row carries a reason outside `REASONS`.
      Print one census line; `.github/scripts/run-tests.sh` runs each module as
      `python -m unittest <module> > <shard>.log 2>&1` and concatenates the
      shards, with no `-b` anywhere, so a `print()` from a test lands in
      `unittest-output.log`. This step also collapses the corpus rule's second
      copy: the control currently rebuilds the glob-and-archive filter inline to
      compute `live`, and after step 1 there is a function that already knows
      what the corpus is.
- [x] **3. The marker vocabulary, read-only.** `marker_after()` implements
      0.71.34's grammar exactly: the reason is required, the marker follows the
      citation on the same line with nothing non-blank between them, and it
      covers one citation. `[quoted: <reason>]` yields the `quoted` reason;
      `[absent: <reason>]` is read but does not yet change any verdict. Five
      grammar cases from the specification, four of them negative: a marker
      with a reason exempts; `[absent:]` and `[absent: ]` do not; anything
      non-blank between the citation and the marker does not; a marker on the
      next line does not; and a marker exempts only the citation it follows, so
      a second citation of the same path is still classified on its own. The
      next-line case is testable because the flatten is offset-preserving:
      `marker_after()` matches on the flattened text and then asserts no `\n`
      in the *unflattened* slice between citation and marker. `[quoted: ]`
      took free text and the gate did not read it, so the exemption was
      counted and not falsifiable. D4a made the reason a `path:line` the gate
      opens; delivered as sd:568, after this step.
- [x] **4. The split.** `is_inside_repo` becomes `is_under_repo` plus a
      `target.is_file()` at the call site. `is_under_repo` **keeps the
      `resolve()`**: `Path.is_relative_to` is lexical, and
      `(REPO_ROOT / ".." / ".." / "etc" / "passwd").is_relative_to(REPO_ROOT)`
      is `True` without it and `False` with it, so dropping it while reading
      the predicate's name as "containment" would turn the security refusal
      into an invitation. The first draft of `design.md` said "containment
      only" and did not say this; a reviewer found it by reading the phrase
      literally, which is how it would have been implemented.
      `escapes-checkout` stays silent; `target-missing` fails **unless** the
      citation carries `[absent: ...]`; an `[absent: ...]` whose target exists
      fails. This is not the first step that can go red — step 2's conservation
      assertion, step 5's widening and step 7's rewrite each can too, and the
      first draft's heading claimed otherwise. It is the first step whose red
      would be a *stale citation* rather than a defect in this item's own work.
      `test_a_citation_cannot_send_this_test_outside_the_checkout` keeps
      its three outside-the-checkout assertions against `is_under_repo` and
      loses its fourth, which asserted the conflation; the missing-target case
      moves to its own test. Expected on today's tree: `target-missing` is
      **empty** and `declared-absent` holds exactly one — the
      `prepare-release.py` citation, which already carries its marker — so
      `make check` stays green. Landing step 4 before step 3 would put that one
      citation in `target-missing` and break the build between two commits of
      the same item, which is the whole reason for the ordering.
- [x] **5. `PAREN_PAIR`.** Added beside `PAIR`, not merged into it, so
      `test_prose_between_a_symbol_and_a_citation_breaks_the_anchor` keeps
      meaning what it means. Six fixtures: parenthesised comma matches,
      parenthesised semicolon matches, bare comma does not, bare semicolon does
      not, and the two shapes taken verbatim from the real list constructions
      the design's table names do not either. The last two are the point — a
      synthetic negative proves the regex is narrow, and only the real ones
      prove it is narrow enough for this corpus.
- [x] **6. The docstring.** Five silencers, each with the reason it exists and
      the count it drops today; the two markers and their grammar; and the
      three shapes named-and-counted rather than resolved, with their numbers.
      Every number re-measured at this step, not copied from `design.md`.
- [x] **7. This item's own pages.** `prd.md`, `design.md` and this file each
      carry illustrative citation shapes written with a metavariable line
      number because no inert form existed when they were written. Rewrite them
      to use `[quoted: <path:line>]`, naming a line of *another* file that
      really carries the quoted citation -- free text stopped being a marker
      at D4a, and a page cannot be its own source. This is the acceptance
      test for question 3
      that no fixture can be: if the pages still cannot show the shape they
      discuss, the marker did not solve the problem it was designed for.
- [x] **8. Criterion 2.** Verify that
      `docs/spec/backend/manifest-and-filesystem.md`'s `prepare-release.py`
      citation is resolved by step 3's marker read rather than by an edit — it
      already carries `[absent: removed with the release train in 0.72.0]`, so
      the mechanism generalising is the whole of the criterion. **Do not** try
      to confirm the other 21 markers in that file by this mechanism, as the
      first draft of this step said to: of the 22 markers there, exactly two
      sit on a `path:line` token and only one of those reaches the marker read,
      so for 21 of them the gate has no opinion and never will. They sit on
      bare path references, which is rule 6's and rule 7's subject in
      `bin/sd-docs-lint`, not this gate's. Saying so is the honest scope of
      criterion 2 and it is smaller than the first draft claimed.
- [x] **9. Criterion 3.** Re-measure every count in `prd.md` and `design.md`
      from the filesystem, and correct both. The PRD's table is a snapshot from
      2026-09-04 and this plan's numbers are a snapshot from 2026-09-07; both
      will have moved. The corrections already known are listed under
      "What the PRD got wrong the second time" in `design.md`. The four
      off-by-one citations listed there are **already applied**, in `d3c26286`;
      the entry is a record, not an outstanding edit, and re-applying it would
      damage correct text. Everything else in that section still needs
      re-measuring, and the re-measurement is the step — not the numbers this
      page happens to carry.

## Verification

Named before the work, each naming its own result. A partial pass is not a
pass.

1. `.venv/bin/python -m unittest tests.test_doc_citations -v` -> `OK`, 0
   failures, 0 errors, and the test count rises from **4 to 9**. The five are
   enumerated so the number is checkable rather than round: step 3's marker
   grammar, step 4's missing-target failure, step 4's absent-marker falsifier,
   step 5's `PAREN_PAIR` fixtures, and D4a's quoted-source falsifier — a
   `[quoted: <path:line>]` whose named line does not carry the quoted text must
   fail. Step 2 adds assertions to `test_the_scan_reaches_the_documents` rather
   than a test, which is why it is not six.
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
5. **The census, derived at run time, with no number to match.** `grep
   'citations:' unittest-output.log` -> one line partitioning the corpus. The
   check is that the line **exists, sums, and carries only names from
   `REASONS`** — the two assertions step 2 adds. It is deliberately not a
   comparison against a table, and the first draft of this page made it one,
   twice: it pinned a column measured before these two pages existed, then
   re-measured and pinned the new column, which went stale again on the next
   edit. These pages are inside the corpus they count. `git ls-files -- '*.md'`
   returns 1,091 in this worktree and returned 1,089 at `405a9106`, and the two
   extra files are `design.md` and `implement.md`. A count written into a
   document that the count includes cannot be kept true by re-measuring it; it
   can only be pinned to a commit, or derived.

   So the figures below are pinned and labelled as history, and **nothing
   asserts them**. Both columns are the classification `design.md` specifies —
   nine reasons, `TOKEN` with an optional path, `SEPARATED_PAIR`, one row per
   token — run over the live corpus, the left one with this item's two pages
   excluded to reconstruct `405a9106`:

   | reason | at `405a9106` | at `2694c4a5` |
   |---|---|---|
   | `compared` | 45 | 69 |
   | `declared-absent` | 1 | 1 |
   | `target-missing` | 0 | 0 |
   | `escapes-checkout` | 0 | 0 |
   | `anchor-not-a-symbol` | 12 | 12 |
   | `elided-path` | 162 | 166 |
   | `separator-not-adjacent` | 20 | 20 |
   | `no-adjacent-anchor` | 280 | 283 |
   | `quoted` | 0 | 0 |
   | **sum** | **520** | **551** |
   | live documents | 24 | 26 |

   Conservation held on both runs and the vocabulary was closed on both. Read
   the columns as a measurement taken on two named commits, not as the current
   state of anything.

   Four of these differ from the numbers the first draft of this page carried,
   and each difference is a defect a reviewer found rather than a change in the
   tree. `compared` is 45 rather than 44 because the left column is the
   *proposed* gate, `PAREN_PAIR` included; today's gate compares 44, and that
   figure belongs to `design.md`'s headline and not to this table.
   `anchor-not-a-symbol` is 12 rather than 7 because the anchors inside
   `PAREN_PAIR` matches that are themselves paths now get rows.
   `separator-not-adjacent` is 20 rather than 33 because 33 came from a
   nearest-backticked-token rule with no distance bound, which no written
   definition on either page described; `SEPARATED_PAIR` is the definition and
   20 is what it finds. And the sum is 520 rather than 358 because the elided
   path is now enumerated, which is the whole point: the first draft called it
   "45% of the corpus" while excluding it from the corpus it was 45% of.

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
does not rely on the printing. Whether `[quoted: <path:line>]` is used honestly —
to mark an example rather than to silence a claim someone could not be bothered
to fix — cannot be tested at all, and that limit is the only one left. D4a
closed the rest: the reason names a line, the gate opens it, and a reason that
does not carry the citation lands in `quoted-not-there` and fails. What a gate
cannot check is the intent behind an honest-looking reason; the census makes
the population visible, which is the most it can do about that.

## Verification results

Filled in as each check runs, so a claim here is a transcript and not a plan.

- 2026-09-07 baseline, before any code change, on `405a9106`:
  `make VENV=<shared venv> check` -> exit 0, `grep -cE '^OK' unittest-output.log`
  = `56`, `grep -c FAILED` = `0`. `.venv/bin/python bin/sd-docs-lint` ->
  `sd-docs-lint: clean`. `.venv/bin/python -m unittest tests.test_doc_citations`
  -> `Ran 4 tests`, `OK`. `bin/` = 17,216 against `BIN_CAP` 18,000.

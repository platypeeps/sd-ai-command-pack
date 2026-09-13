# Implement — every rule is a row and a checker

## Step checklist

- [ ] **1. The empty registry and its own tests.** Add the registry table with
      zero rows, and the test asserting every row's checker resolves to a
      declaration that exists. Zero rows passes. This step is independently
      landable and independently green, and it fixes the shape before any rule
      argues about content. It also carries requirement 1's check: a rule id
      appearing as a literal in tracked code outside the registry module is a
      failure.
      Verify: the new tests pass; mutation — add a row naming a checker that
      does not exist, confirm `test_every_live_rule_names_a_checker_that_exists`
      reddens; separately, paste a rule id literal into a consumer and confirm
      the second-list test reddens. Remove both and `diff -q` reports the tree
      identical. (As delivered, the checker was the function object and the
      first mutation failed at *import*. Since 2026-09-13 it is a
      `path::symbol` string, so the same mutation fails in the test named
      above — the check moved, the mutation did not.)

- [ ] **2. Meta-check legs a and b, with the baseline.** Leg a: every registry
      row is cited by at least one skill. Leg b: every tool-behaviour claim in
      a skill cites a rule id the registry carries.
      **The baseline is `UNCITED_SKILL_CLAIMS`, a projection of `claims_in`
      and not its return value.** `claims_in` finds every claim, cited or not;
      `uncited_skill_claims()` keeps the ones citing no id and counts them per
      document. It counts *violations* within leg b's scope —
      the claims in `skills/` citing no rule id — and never the *population*.
      A ratchet over the whole live-prose population would be wrong twice: it
      counts claims leg b never examines, and adding a new, correctly cited
      claim would redden it.
      Verify: each leg reddens under its own mutation; the baseline test
      reddens when a document's uncited count RISES; adding a correctly cited
      claim does NOT redden it, which is the control that separates a
      violation count from a census.
      Do not verify against a 263→264 mutation. That instruction stood here
      until 2026-09-12 and cannot be run: 263 was never reproducible, so there
      is no such transition to induce. The correction below has the history.

      > **Correction, 2026-09-12 (sd:622).** 263 could not be reproduced, and
      > the three readings offered in its place could not be reproduced either:
      > an independent reconstruction of the same three shapes gave different
      > figures again, because each reconstruction had to invent the counting
      > rule the original never recorded. The shape of the requirement is
      > unchanged — violations, not population, downward only. The number is
      > now `UNCITED_SKILL_CLAIMS`: the per-document count `uncited_skill_claims()`
      > projects from `claims_in`, and the three properties of that predicate that
      > were load-bearing and unstated are pinned by `TheClaimPredicate`.
      > `design.md` carries the correction in full.

- [ ] **3. Meta-check leg c, over the R-id corpus.** Every rule id cited in live
      prose is defined in the registry. On the first run this reports 4
      failures — `R11-D1`, `R11-D30`, `R11-D46`, `R5-D1` — and a baseline of 26
      archive-only definitions. Verify: the run names exactly those 4 ids.

- [ ] **4. The R-id backfill.** Move live rule definitions out of archived
      planning documents into registry rows, one at a time, deciding for each
      whether it is a live rule or a historical decision. This is the expensive
      step. It lands in slices; each slice reduces the leg c baseline and the
      baseline test proves it fell.

      **Slice 1, 2026-09-12. `STRANDED_RULE_IDS` 26 → 25.** `R10-D5` is a
      row. It was already taught by a skill section that cites the id, and its
      checker is a plain function in `bin/` — `sd_setup_github.setup_github` —
      that is runtime code carrying its own refusal. Registering it turned the
      second-list check red on the refusal message in `bin/sd_setup_github.py`,
      which carried the id inside a string; the citation moved to the comment
      above it, which is the rephrasing that check's own failure text
      prescribes.

      `R10-D6` was a row for one review round, was pulled, and came back in
      slice 2. The first row named `sd_lib.repo_root` as its checker, and
      `repo_root(start=None)` accepts a path: it is the resolver the rule
      constrains, not a guard, so the row named the mechanism by which the rule
      would be broken as its enforcement. The meta-check passed it because the
      checker test asserts the checker EXISTS and never that it ENFORCES. Slice
      2 is that fix, and `R10-D6` is its first beneficiary rather than its
      casualty.

      **Slice 2, 2026-09-13. `STRANDED_RULE_IDS` 25 → 24, and the hole that
      admitted the bad row is closed.** Three changes, in the order they depend
      on each other:

      1. `Rule.checker` is a `path::symbol` string, resolved by
         `source:tests/test_doc_citations.py::source_declaration_error` — the
         resolver the pack's documentation citations already use. The callable
         form made `bin/sd_rules.py` import every checker's module at load time,
         and it could not name an extensionless entrypoint or a test at all.
      2. `Rule.proof` is new and required beside a checker: the mutation that
         makes that checker redden, in one sentence a reader can execute.
      3. Leg d runs it. For every live row with a checker it copies the tree,
         runs the named test clean, applies the mutation, requires the test to
         go red, restores the text and proves the copy identical again. It runs
         in a copy because `.github/scripts/run-tests.sh` shards the suite by
         module across workers, so editing `bin/` in the live tree would be
         editing it while another shard imports it.
         The leg carries its own control: a sentinel edit to a docstring in the
         same file, run through the same machinery, must leave the same test
         green. Without it, any failure to start a child would read as every
         checker enforcing.

      `R10-D6` is a row on that basis. Its checker is
      `tests/test_verb_inventory.py::test_no_command_accepts_a_repository_path`,
      and its proof renames `--belongs-to` in `bin/sd_work.py` to the banned
      spelling, which that test's `iterdir()` scan of `bin/` finds.

      **Two obstacles decide the rest of the backfill, and neither is the
      judgement the step was sized for.** Twenty of the twenty-four remaining
      ids are taught by no skill section at all, so leg a cannot pass for them:
      registering one means writing the teaching section first, which is step 8
      and not this step. The other four are taught, and each is held up by
      something specific:

      | Id | Taught in | Why it is not a row yet |
      |---|---|---|
      | `R10-D1` | `skills/sd-status/SKILL.md` | `bin/sd-status` carries the id in two strings, one of them the `CLASSES` row whose text the skill's table mirrors. The second-list check wants it out of the string; leg a reads the skill table it would have to change. The two checks pull opposite ways and that needs a decision, not an edit. |
      | `R10-D2` | `skills/sd-handoff/SKILL.md` | The section that teaches it says Lane B is *not implemented*. A live row with a checker would assert an enforcement that does not exist, which is the defect this item is about. |
      | `R10-D3` | `skills/sd-handoff/SKILL.md` | Its enforcement lives in `bin/sd-handoff-restore`, which has no `.py` suffix. **The import obstacle recorded here is gone** — a `path::symbol` location needs no import and the path needs no suffix. What is left is leg d: the row needs a mutation that reddens a named test, and finding one for a restore path is the work. |
      | `R10-D4` | `skills/sd-review/SKILL.md` | `codex_preflight` lives in the suffixless `bin/sd-review`, and that obstacle is gone with `R10-D3`'s. This is the best-taught rule in the corpus — the heading cites the id — and it is the first candidate for slice 3, needing only a proof that reddens a named test. |

      **A finding about leg c's four dangling ids, measured on `239ff624`.**
      They are not undefined. Three of them carry a definition in a form
      `DEFINITION` cannot see, because that pattern requires a bold run
      *opening* with the id: `R5-D1` is written `**Obsidian vault stays
      system-of-record** (R5-D1)`, `R11-D1` sits in a table cell with no bold at
      all, and `R11-D30` is a heading. The fourth, `R11-D46`, is defined in no
      document in any form — its derivation was recorded as a comment in
      `tests/test_loc_caps.py`. Widening the grammar would move ids between two
      baselines at once and is a change to the measurement, so it is left for
      its own slice rather than folded into this one.

- [ ] **5. Code rules, citing sd:430's checkers.** `tests/test_code_health.py`
      already enforces complexity, length, depth and clone floor. These become
      registry rows pointing at the existing checkers — no new enforcement, only
      registration. Verify: the ceilings in `tests/test_code_health.py` are
      unchanged by this step; `git diff` touches no ceiling constant.

- [ ] **6. Prose rules, in their narrowed forms.** Rule 2 as filed. Rules 1 and
      3 as narrowed in `design.md`, each with its baseline. Verify: each rule
      reddens under mutation; no rule's first run reddens the existing corpus.

- [ ] **7. The pre-commit tier.** The code checkers run whole — measured at
      1.71 s over the tree, so there is no second scope to drift from the CI
      scope. Only `bin/sd-docs-lint`, at 19.87 s, is diff-scoped, and its cost
      is attributed to a stage first. **No threshold is set here on purpose.**
      The two whole-tree passes are already 1.71 s + 0.84 s = 2.55 s before the
      diff-scoped docs lint and any hook overhead, so the "under two seconds"
      this step first demanded was unreachable from its own measurements. Verify:
      time the assembled hook on a one-file diff, record the number, and set the
      budget from that result in the same pull request. Re-run the whole-tree
      timings there too, because the decision to skip diff-scoping rests on
      numbers that will age.

- [ ] **8. The authoring tier.** Skills consult the registry and name the rule
      ids in scope. Last, because it depends on the registry carrying rules.

Steps 1 to 3 are the deliverable. Steps 4 to 8 are payload and may be batched
into fewer pull requests to reduce CI churn.

## Verification

**Named before the work starts.**

- Every meta-check leg is proved by mutation, not by passing: remove the guard,
  confirm a *named* test goes red, restore, and `diff -q` must report the tree
  identical. A mutation script asserts its own edit applied — `assert
  t.count(old) == 1` — because a script whose pattern matches nothing reports a
  false pass. That has happened twice on this repository in one week.
- **Leg d is that protocol executed by the suite rather than by a person**, once
  per live row with a checker, and it is held to the same bar it applies: the
  edit-landed count, the green control run, the red mutated run, and the
  restoration are four separate assertions, and a sentinel edit that violates
  nothing must leave the same test green. A leg that reports red for a child it
  could not start would otherwise read as every checker enforcing.
- A fixture must be checked for vacuity. A test that exercises a guard through
  several layers can fail earlier, for the wrong reason, and still pass. Where a
  guard can be called directly, call it directly, and include a control
  asserting the case that *should* succeed.
- Baselines: `pytest` the baseline test with the number raised by one; it must
  go red. A baseline that does not redden when raised is not a ratchet.
- Leg c's first run must name exactly `R11-D1`, `R11-D30`, `R11-D46` and
  `R5-D1`. More or fewer means the live-prose scope is wrong.
- Full suite through the repository's own runner: `make test`, which runs
  `.github/scripts/run-tests.sh` and shards `python -m unittest` across workers.
  That is the authoritative suite and the one CI gates on. A focused run is
  `python -m unittest tests.test_<module> -v`.
  `pytest` is a convenience here, not the contract: under `pytest tests/` this
  tree reports 19 collection errors from a missing `sd_db` module, pre-existing
  on `origin/main`, which is a fact about `pytest` rather than a baseline for
  this project.
- `bin/sd-docs-lint` exits 0.

**What cannot be verified here.** Whether an R-id in an archived design document
is a live rule or a historical decision is a judgement, not a check. Step 4
records the decision per id in the registry row; nothing can test that the
judgement was right.

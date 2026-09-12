# Implement — every rule is a row and a checker

## Step checklist

- [ ] **1. The empty registry and its own tests.** Add the registry table with
      zero rows, and the test asserting every row's checker is a callable that
      exists. Zero rows passes. This step is independently landable and
      independently green, and it fixes the shape before any rule argues about
      content. It also carries requirement 1's check: a rule id appearing as a
      literal in tracked code outside the registry module is a failure.
      Verify: the new tests pass; mutation — add a row naming a checker that
      does not exist, confirm import fails; separately, paste a rule id literal
      into a consumer and confirm the second-list test reddens. Remove both and
      `diff -q` reports the tree identical.

- [ ] **2. Meta-check legs a and b, with the baseline.** Leg a: every registry
      row is cited by at least one skill. Leg b: every tool-behaviour claim in
      a skill cites a rule id the registry carries.
      **The baseline is 263, not 681.** 681 is the whole live-prose population,
      of which 264 are in `skills/` — leg b's scope — and 263 of those cite no
      rule id. A downward-only ratchet on 681 would be wrong twice: it counts
      claims leg b never examines, and it counts the *population* rather than
      the *violations*, so adding a new, correctly cited claim would redden it.
      Verify: each leg reddens under its own mutation; the baseline test reddens
      when 263 is raised to 264; adding a correctly cited claim does NOT redden
      it, which is the control that separates a violation count from a census.

- [ ] **3. Meta-check leg c, over the R-id corpus.** Every rule id cited in live
      prose is defined in the registry. On the first run this reports 4
      failures — `R11-D1`, `R11-D30`, `R11-D46`, `R5-D1` — and a baseline of 26
      archive-only definitions. Verify: the run names exactly those 4 ids.

- [ ] **4. The R-id backfill.** Move live rule definitions out of archived
      planning documents into registry rows, one at a time, deciding for each
      whether it is a live rule or a historical decision. This is the expensive
      step. It lands in slices; each slice reduces the leg c baseline and the
      baseline test proves it fell.

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

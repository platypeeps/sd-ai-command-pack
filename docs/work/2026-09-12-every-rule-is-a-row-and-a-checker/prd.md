---
title: every quality rule is a registry row and a checker, and the skills cite it
created: 2026-09-12
branch: main
---

# PRD — the rules live in prose, and prose does not run

## Problem

This pack states quality rules in skills, in `WORKFLOW.md`, and in planning
documents. A rule stated only in prose is advisory. Advisory rules are the ones
that silently stop being true, because nothing fails when the sentence and the
machinery disagree.

The pack has already been bitten by exactly this. `WORKFLOW.md` claimed for
weeks that every writing skill refuses the upstream tree, while nothing
refused. That claim did not decay; it was never true, and no check existed that
could have said so.

### The pack already runs a rule registry, informally, and it is broken

The sharpest evidence is not the missing system. It is the half-built one.

The pack uses decision ids of the form `R<n>-D<n>`. Measured on `e6c2cb20`
across all tracked files:

| Fact | Count |
|---|---|
| Distinct R-ids cited in live prose, outside `docs/work/archive` | 47 |
| Distinct R-ids defined anywhere | 50 |
| Definitions that live inside `docs/work/archive` | 33 |
| Live citations whose only definition is an archived page | 26 |
| Live citations that resolve to no definition at all | 4 |

The four that resolve nowhere are `R11-D1`, `R11-D30`, `R11-D46` and `R5-D1`.

There is no registry file. A definition is a run of bold text inside a planning
document, so "which rules exist" is answered by a grep whose pattern nobody
wrote down. More than half the rule ids in live prose point only into the
archive — into pages the pack's own citation gate treats as historical records
rather than as current statements. The pack cites rules the way it would cite a
source it had stopped maintaining, because that is what it is doing.

### Enforcement claims do not cite anything

A machinery claim is an enforcement verb — refuses, never, always, cannot — on
a line that also names a pack tool or a test. Measured on `e6c2cb20`, over
tracked markdown outside `docs/work/archive`:

| Fact | Count |
|---|---|
| Machinery claims in live prose | 681 |
| Of those, inside `skills/` | 264 |
| Of those, citing any rule id | 1 |

One in 681. Every other enforcement claim in this pack is a sentence asserting
a behaviour with nothing linking it to the code that performs it.

### What the pack has already got right, and is the model

`CLASSES` in `bin/sd-status` is this pattern done correctly, in production, in
this repository. One table answers "which checks exist". The renderer iterates
it. The ranking reads `rank` off it. Adding a check means adding a row and a
producer — never editing a renderer, a sort, or a list. The `sd-status` skill
states the reason in one sentence: *"That is how those drift apart."*

This item asks for the same shape, applied to quality rules rather than to
status checks.

## Requirements

1. **One registry is the single answer to "which rules exist."** It is a table
   in code, iterated by every consumer. No consumer carries a second list.
2. **Every registry row names its checker.** A row whose checker does not exist
   is a failure of the registry's own test, not a comment.
3. **A registry row records: id, what it checks, its checker, its scope
   (`code`, `prose`, or `both`), and the skill section that teaches it.**
4. **A skill teaching a rule cites the rule id.** Restating the rule is how the
   two copies drift, so a skill should not — but *"does not restate"* has no
   mechanical check, and this item does not claim one. Citation is enforced;
   non-restatement stays a review habit, and `design.md` records it as an
   accepted gap rather than as a rule nothing performs. Asserting an enforcement
   that does not exist is the defect this whole item is about, and it would be
   absurd to commit it in the requirements list.
5. **The meta-check has three legs, and each fails independently:**
   - a. every registry rule is cited by at least one skill;
   - b. every enforcement claim in a skill cites a rule id that the registry
     carries;
   - c. every rule id cited in live prose is defined in the registry.
6. **Leg b and leg c carry a frozen baseline, not a flag day.** The uncited
   claims in `skills/` — held per document in `UNCITED_SKILL_CLAIMS`, the
   count `uncited_skill_claims()` projects from what `claims_in` finds — and
   the archive-only R-ids cannot be fixed in
   the pull request that introduces the check. A baseline counts *violations*, never a
   population: it may fall and may not rise, in the shape
   `tests/test_loc_caps.py` already uses, and adding a correctly cited claim
   must not move it.

   > **Correction, 2026-09-12 (sd:622).** The figure 263 in this requirement,
   > and every other count of claims in this document, came from a predicate
   > that was never recorded. It cannot be reproduced, and neither can the
   > replacements proposed for it. The requirement stands as written — a frozen
   > baseline of violations, not a flag day — but the *number* is now whatever
   > `source:tests/test_rule_registry.py::claims_in` returns, recorded per
   > document in `UNCITED_SKILL_CLAIMS`. `design.md` carries the correction and
   > the three properties of the predicate that are now pinned by tests.
   >
   > The 26 archive-only R-ids in this requirement were reproducible and are
   > not affected by that correction; the backfill has since moved them to 24,
   > which `STRANDED_RULE_IDS` records and the Log dates.
7. **The pre-commit tier is scoped by measurement, not by assumption.** A
   checker runs over the whole repository when a whole-repository run is fast,
   and is diff-scoped only where it is not. The backbone item asserts the
   opposite of what the clock says; `design.md` carries the timings.
8. **Rescoping is expected and must be recorded.** Two of the three prose rules
   proposed in the backbone item do not survive measurement unchanged. See
   `design.md`.

## Acceptance criteria

- [ ] A registry exists as a single code table, and a test asserts every row's
      checker resolves to a callable that exists. Zero rows must pass, so the
      table can land before any rule does.
- [ ] A test asserts no consumer carries a second list: a rule id appearing as a
      literal anywhere in tracked code outside the registry module is a failure.
      This is requirement 1's only mechanical check, and it is the one that
      would have caught the drift `CLASSES` was built to prevent.
- [ ] Meta-check leg a fails when a registry row is added with no citing skill.
      Demonstrated by mutation: add a row, see one named test go red, remove it,
      `diff -q` reports the tree identical.
- [ ] Meta-check leg b fails when a skill asserts an enforcement naming a rule
      id the registry does not carry, **and equally when it names no rule id at
      all.** Both mutations are required. The unknown-id case alone would be
      satisfied by a checker that only validates ids it finds, which would pass
      over the uncited shape — and the uncited shape is the large majority of
      the claims in `skills/` today, so a leg b that missed it would miss
      essentially everything it exists to catch. The exact figure is
      `UNCITED_SKILL_CLAIMS`; no single number is quoted here, because the one
      that used to be could not be reproduced.
- [x] ~~The leg b baseline is 263~~ — **superseded 2026-09-12 by sd:622: 263
      cannot be reproduced and neither can its proposed replacements.** The
      baseline is what `claims_in` returns, held per document in
      `UNCITED_SKILL_CLAIMS`, and a test asserts it may fall and may not rise.
      The control asserting that a *correctly cited* claim does not redden it
      stands unchanged and is met.
- [ ] Meta-check leg c reports the 4 currently dangling R-ids — `R11-D1`,
      `R11-D30`, `R11-D46`, `R5-D1` — as failures on the first run over live
      prose, and reports zero once they are resolved or registered.
- [ ] The baselines for legs b and c are recorded with the measured numbers
      above, and a test asserts a baseline may fall and may not rise.
- [ ] `make test` — the repository's own runner, sharding `python -m unittest`
      — passes with 0 new failures.
- [ ] `bin/sd-docs-lint` exits 0.

## References

- Backbone item sd:431. Depends on sd:430, which is `done` and delivered
  `tests/test_code_health.py` with the code ceilings this item's code rules
  cite.
- `bin/sd-status` and its `CLASSES` table: the pattern this item copies.
- sd:525, filed 2026-09-12: line-anchored citations shape code layout and
  create cross-lane conflicts. It bears directly on this item's first prose
  rule.
- sd:568 and sd:569, in flight on pull request #870: the `[quoted: path:line]`
  marker, which requires a line number by construction.

## Log

- 2026-09-12 created
- 2026-09-12 steps 1 to 3 delivered (#882); the registry, the three legs, zero
  rows
- 2026-09-12 sd:622 closed out against this document: leg b's predicate has one
  recorded definition, and the counts in this document are marked as
  unreproducible rather than replaced with a fourth number
- 2026-09-12 step 4 first slice: `R10-D5` registered, the stranded baseline
  falls 26 → 25, and the twenty-five that did not move each carry a recorded
  reason in `implement.md`. `R10-D6` was registered in the first round and
  unregistered in review: its named checker, `sd_lib.repo_root`, accepts a
  path and enforces nothing

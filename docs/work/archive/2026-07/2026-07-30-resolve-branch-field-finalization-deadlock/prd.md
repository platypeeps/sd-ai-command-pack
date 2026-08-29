---
title: Resolve the branch-field deadlock between the pre-archive and completion bundle gates
status: done
created: 2026-07-30
branch: fix/resolve-branch-field-finalization-deadlock
---
# Resolve the branch-field deadlock between the pre-archive and completion bundle gates

## Goal

Stop a task that reaches `sd-finish-work` with `"branch": null` from being
unfinalizable. Two gates in the same flow impose contradictory requirements on
that one field, and satisfying the first at the point the flow tells you to
satisfy it guarantees the second fails.

## Evidence

Hit live on 2026-07-30 finishing `07-28-pin-bookkeeping-ci-classifier-trust`
(the A-038 P0, merged as PR #279).

1. `final-bundle --mode completion` was run per `sd-finish-work` step 7 and
   returned:

   ```json
   { "status": "invalid",
     "reasonCodes": ["completion_archive_identity_changed"],
     "findings": [{ "path": ".trellis/tasks/archive/2026-07/07-28-pin-bookkeeping-ci-classifier-trust/task.json",
                    "message": "archive move changed fields other than status and completedAt" }] }
   ```

2. The only field that differed beyond the two allowed was `branch`
   (`null` → `fix/pin-bookkeeping-ci-classifier-trust`). Every other field was
   byte-identical.

3. That field was set only because the **pre-archive** gate had already refused
   the task with `task_branch_invalid` — "completion-ready task must have a
   non-empty feature branch".

4. Recovery required a hand-authored commit (`2b24c33a`) restoring the archived
   `branch` to `null`, after which the same command returned
   `status: valid` / `completion_bundle_valid`.

This is the third distinct branch-field finalization failure on record. See
`07-29-scope-final-bundle-validator-to-delta/prd.md:66-70`: commit `f92221e5`
cleared a stale `branch` field and produced `planning_lifecycle_mutation` plus
`planning_baseline_invalid`. The field is repeatedly load-bearing in ways the
flow does not account for.

## Root cause

**Every task is born in the failing state, and nothing in the normal lifecycle
leaves it.**

- `.trellis/scripts/common/task_store.py:324` seeds new tasks with
  `"branch": None`.
- `:296-298` reads the current git branch and records it as **`base_branch`**,
  the PR target — not as `branch`.
- No code path in `task.py start` writes `branch`. The only writer is the
  explicit `cmd_set_branch` at `:728`.

So `branch` stays null unless an operator remembers to run `set-branch` by hand.

The two gates then collide:

| Gate | Location | Demands |
|---|---|---|
| pre-archive | `scripts/sd-ai-command-pack-review-preflight.mjs:700`, reached only via `completionReady: true` set at `:569` | `branch` must be a non-empty string |
| completion bundle | `:1496-1503` | archive move may change **only** `status` and `completedAt` |

The bundle gate reads the source record at `baseOid` (`:1484`) and the archived
record at head (`:1485-1488` — note no `completionReady`, so `:700` never
applies to the archived copy), strips exactly `status` and `completedAt`
(`:1496-1501`), and compares. A `branch` set after the finalization base was
captured is inside the archive commit and therefore inside the compared delta.

`sd-finish-work` step 4 instructs the operator to capture the finalization base
**before** running the pre-archive gate, and then says "do not attempt a repair
by mutating the task". `set-branch` is the documented repair, it is a mutation,
and performing it at that point is what breaks step 7. Step 7 in turn forbids
amending, resetting, dropping, or pushing the archive and journal commits, so
the only exit is a manual correction commit against the archived artifact.

Nothing in either skill states the ordering that avoids this: record the branch
and commit it as a work commit *before* capturing the finalization base.

## Scope boundary

`task_store.py` is Trellis-owned and out of pack scope, consistent with
`07-28-analyze-recurring-trellis-workflow-instability/prd.md:192-196`. "Make
`task.py start` record the branch" is therefore an **upstream** fix, not this
task's deliverable, though it may be worth a parked upstream task.

The pack-side surface is the validator and the two skills.

## Requirements

- A completion bundle whose archive move changes `branch` in addition to
  `status` and `completedAt` must not be rejected on that basis alone. Decide
  and state in `design.md` whether `branch` joins the stripped-lifecycle set at
  `:1496-1501` unconditionally, or only for a null-to-non-empty transition.
  The asymmetry matters: `null` → `"feature/x"` is a late record of a fact;
  `"feature/x"` → `"feature/y"` is a rewrite and should stay blocked.
- Do not weaken the identity check for any other field. The gate exists so a
  reviewer can trust that archiving smuggled in no content change, and every
  other field must still compare equal. Note the comparison is *structural*,
  not bytewise: `stableJson` (`:2016-2021`) sorts object keys, so key-order and
  formatting differences are deliberately ignored on both sides. "Byte-for-byte"
  would misstate the invariant.
- Resolve the pre-archive requirement against the default state. Either
  `task_branch_invalid` stops firing when the branch is inferable from the
  current checkout, or `sd-finish-work` step 4 gains an explicit instruction to
  record and commit the branch before capturing the finalization base.
  `design.md` must pick one and say why — these are different contracts, not
  two phrasings of one.
- `branch: null` must remain a valid archived state. `:2545` already permits it
  and `07-29-exempt-planning-scaffold-preflight` shipped that way (`e4839c69`).
  A fix that forces a non-null archived branch would invalidate existing records.
- Edit under `templates/` as the source and regenerate the root mirror for every
  mirrored file touched. `design.md` resolved this to two pairs:
  `templates/scripts/sd-ai-command-pack-review-preflight.mjs` and
  `templates/.agents/skills/sd-finish-work/SKILL.md`. Both are byte-identical
  to their root mirrors today and must stay so.
- Cover the defect with a focused regression in
  `tests/test_bookkeeping_validator.py`, which is where `final-bundle` coverage
  lives. The test must fail against the current validator.

## Acceptance Criteria

- [x] A completion bundle whose archive move changes `branch` from `null` to a
      non-empty string, and is otherwise a pure move, reaches `status: valid`
      with `completion_bundle_valid`, asserted by a regression test that fails
      against the current validator.
      Evidence: `test_completion_bundle_allows_branch_recorded_during_archive`
      failed against the unmodified validator with
      `completion_archive_identity_changed`, and passes after the fix.
- [x] An archive move that changes any other field — or that rewrites a
      non-null `branch` to a different non-null value, if `design.md` chose the
      asymmetric rule — still fails with
      `completion_archive_identity_changed`, asserted by a regression test.
      Evidence: four guard tests — rewrite, erasure, unrelated `title` change,
      and addition to a record whose `branch` key is absent — all reject, both
      before and after the fix.
- [x] A task whose `branch` is null at the moment `sd-finish-work` runs reaches
      a valid receipt without a hand-authored correction commit against an
      archived artifact. State in the test or the skill which of the two
      resolutions above delivers this.
      Evidence: the **skill** delivers it. `sd-finish-work` step 4 now records
      the branch before capturing the finalization base, so the pre-archive
      gate is never reached with a null branch. Note the limit honestly: this
      task's own branch was recorded by hand at planning time, before the
      instruction existed, so its finalization run demonstrates the outcome
      rather than the instruction's automation. The first task to exercise the
      instruction end to end will be the next one finalized.
- [x] `branch: null` still validates as an archived state.
      Evidence: `test_completion_bundle_allows_null_branch_through_archive`
      passes; `:2545` is unchanged.
- [x] `templates/` and the root mirror remain byte-identical after `make sync`
      for every file touched.
      Evidence: `diff -q` is silent for both pairs —
      `sd-ai-command-pack-review-preflight.mjs` and
      `sd-finish-work/SKILL.md`.
- [x] `make check` passes.
      Evidence: `make release-prep` exits 0, ending in `make check`. Both edited
      files are shipped payload, so the change carries the `0.56.4` bump, its
      CHANGELOG entry, and a candidate ledger refreshed across the eight fleet
      consumers to payload digest
      `sha256:771821351df0cc70946bd7abdec5828a85988a7cda5e5a10399f7773783c252c`.
      One warning remains and is a PR-body requirement, not a check failure: the
      branch changes generated files, so the body must carry a
      `Tooling/generated scope:` section.

## Notes

- Sibling, not child: `07-29-scope-final-bundle-validator-to-delta` covers the
  *planning*-mode whole-directory scoping defect and the missing
  repo-maintenance mode. It explicitly classifies `task_branch_invalid` as
  group 3 (completion-only) and places groups 2, 3, and 4 outside its
  acceptance criteria (`prd.md:114-116`, `:182-183`). This defect is therefore
  uncovered there by that task's own design, which is why it is tracked
  separately rather than folded in. Both touch
  `scripts/sd-ai-command-pack-review-preflight.mjs`, so sequencing should be
  agreed before either starts.
- The next instance is already queued:
  `07-28-roll-out-stabilized-pack-release-to-fleet` is `in_progress` with
  `"branch": null` and will hit this on completion.
- Most archived tasks do carry a branch (7 of 8 sampled), so operators have been
  running `set-branch` early enough to land it in a work commit. That is luck of
  ordering, not a contract.
- A clean archive commit for comparison: `524d50d0` changed only `status` and
  `completedAt`.
- `make sync` is required before full-check after task edits
  (`CONTRIBUTING.md:108-111`).

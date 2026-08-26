# Implement — reachable bookkeeping successor under an absent router

Branch `fix/bookkeeping-absent-router`, cut from `origin/main` at `b17764ed`.

## 0. Baseline

- [x] `.venv/bin/python -m unittest tests.test_review_controller` green.
      Record the count; 55 tests are defined today.
- [x] Confirm the defect from the existing test rather than by assertion:
      `test_run_composes_non_pr_local_and_optional_absence` (`:1265`) already
      pins it at `:1277-1287` -- absent capability, `local_status="skipped"`,
      expects `code 3`, `status "indeterminate"`, `"clean local review"` in the
      diagnostic. **That test encodes the defect and must change.** It is the
      one place the current behaviour is asserted on purpose, so changing it is
      the deliberate act, not collateral.

## 1. Tests first (red)

In `tests/test_review_controller.py`. The harness already carries what these
need: `run_with_mocks(..., local_status=, capability=, local_receipt_extra=)`
at `:1167`, and `local_report` at `:72`, whose default receipt has a `plan`
with **no** `providers` key -- so a test must add one explicitly to describe a
zero selection.

- [x] `test_absent_router_accepts_a_pr_whose_plan_asked_no_provider` --
      scope `pr`, capability `absent`, `local_status="skipped"`,
      `local_receipt_extra` setting `plan["providers"] = []`,
      `plan["policyId"] = "bookkeeping-successor"`, `attempts = []`. Assert
      `code == 0`, `status == "ready"`, and that `limitations` contains all
      three of `router-not-configured`, `zero-remote-confidence`, and
      `local-skipped:bookkeeping-successor`. Asserting the outcome and the
      attribution, per criterion 3 -- not merely that the call succeeded.
- [x] `test_absent_router_still_refuses_a_pr_whose_providers_declined` --
      same, but `plan["providers"] = [{"id": "argv"}]` and one attempt with
      `status: "skipped"`. Assert `code == 3` and `status == "indeterminate"`.
      This is case (b) and is the hole PRD option 1 would have opened.
- [x] `test_the_skip_limitation_names_the_policy_verbatim` -- as the first
      test but `plan["policyId"] = "trivial-skip"`. Assert the limitation is
      `local-skipped:trivial-skip`, not `local-skipped:not-requested`. This is
      the check that the verbatim decision in `design.md` actually holds; the
      `_router_local_summary` mapping would fail it.
- [x] `test_pr_and_non_pr_branches_accept_the_same_local_silence` -- drive
      both scopes over the same four receipts (clean; zero-selected skipped;
      providers-declined skipped; and a clean receipt with a malformed
      non-list `plan["providers"]`) and assert the accept/reject decision
      matches across the two scopes for each. Criterion 4. It must compare the
      two branches, not restate one branch's expected table twice.
- [x] `test_non_pr_no_longer_accepts_a_declined_provider_run` -- the
      tightening, asserted on purpose so it cannot be mistaken for a
      regression later. `code == 3`, limitations carry `local-skipped`.
- [x] `test_bookkeeping_reentry_reaches_ready_on_a_pr_under_an_absent_router`
      -- criterion 1 and criterion 5 together. Model it on
      `test_bookkeeping_reentry_has_its_own_bounded_round_budget` (`:2734`),
      which does this at `scope=branch`; this one uses `--scope pr`
      `--attempt 6` `--successor bookkeeping --bookkeeping-evidence <file>`,
      an `absent` capability, a zero-selected local report, and **no**
      `--remote none`. Assert `(0, "ready")`. Then assert the other half in
      the same test: without `--bookkeeping-evidence` the same attempt raises
      `ReviewError` matching `roundLimit`. Both halves in one test, because
      either alone hides the deadlock.
- [x] Update `test_run_composes_non_pr_local_and_optional_absence` so its
      absent-router assertion describes a providers-declined receipt, which is
      still `indeterminate`. Adjust the diagnostic substring it greps for.
- [x] Run; confirm the new tests fail and that
      `test_run_composes_non_pr_local_and_optional_absence` is the only
      existing test that needed changing. If any other existing test goes red,
      stop -- it is evidence the tightening reaches further than `design.md`
      claims, and the design is what should change first.

## 2. Implement

All edits in `templates/scripts/sd-ai-command-pack-review.py`. **Not
`scripts/`** -- that copy is generated, and editing it changes nothing the
tests read.

- [x] Add `_local_selected_nothing(local)` next to `_local_outcome` (`:854`),
      returning `True` only when `receipt["plan"]["providers"]` is a list and
      empty; `False` for every malformed shape.
- [x] Add `_local_silence_is_accounted(local, outcome)` beside it.
- [x] Non-PR branch `:2119`: replace
      `if local_status in {"clean", "skipped"}:` with the helper.
- [x] Absent-router PR branch `:2145`: replace `if local_status != "clean":`
      with `if not _local_silence_is_accounted(local, local_status):`, and
      reword the diagnostic -- it no longer requires `clean`.
- [x] Absent-router success return `:2153-2157`: append
      `f"local-skipped:{policy_id}"` to `limitations` when the outcome is
      `skipped`, where `policy_id` is `str(plan.get("policyId") or "unknown")`
      -- verbatim, not run through the `skipReason` mapping, and never
      rendering as `None`.
- [x] Leave `_router_local_summary` and its `skipReason` mapping untouched.
- [x] Leave `sd-ai-command-pack-review-local.py`, `OUTCOMES`, and every
      receipt field untouched.

## 3. Validate

- [x] `.venv/bin/python -m unittest tests.test_review_controller` -- green.
- [x] `.github/scripts/run-tests.sh` -- full suite, 0 failures. **Not
      optional: the targeted suite missed a shipped-shell drift rule two tasks
      ago, and a stale command-catalog mirror one task ago.**
- [x] `PYTHON_BIN=".venv/bin/python" make test` -- carries the
      `--fail-under=100` installer coverage gate.

## 4. Docs

- [x] `templates/docs/SD_AI_COMMAND_PACK.md`, the paragraph at `:1037`. It
      currently states the absent-router rule as "only a local receipt whose
      `remoteGate.state` is `eligible` may complete" and enumerates four
      qualifying receipts. Both directions of this change have to land there,
      or the doc and the code diverge:
      - the zero-selected `skipped` receipt qualifies. It is **not** a fifth
        gate reason: its `remoteGate.reason` is `local-stage-terminal`, the
        same reason a clean receipt carries. What the enumeration omits is that
        `local-stage-terminal` covers two receipt shapes -- nothing was found,
        and nothing was asked. Say that; do not change "Four receipts qualify"
        to "Five", which would be wrong.
      - a `skipped` receipt whose providers were asked and declined does **not**
        qualify, which makes the code stricter than the rule as worded. Say so,
        and say why -- the gate cannot tell the two apart.
      Also state explicitly that `skipped` was **not** split into a new outcome,
      and that the deciding fact is `plan["providers"]`. Criterion 2.
      Edit `templates/`; `docs/SD_AI_COMMAND_PACK.md` is generated.
- [x] `.trellis/spec/tooling/review-attempt-state.md` was checked and is not
      the home for this rule -- it scopes memoization of review stages, not the
      router's local-acceptance predicate. Recorded so the Trellis spec step is
      seen to have been considered rather than skipped.
- [x] CHANGELOG under the new version: the fix, and separately the non-PR
      tightening, which is a behaviour change and not a bug fix.

## 5. Ship

- [x] Re-read `main`'s manifest version immediately before bumping. #555 holds
      0.71.55 and #556 holds 0.71.56, both open; take the next free one.
- [x] `make sync` -> `make generate` -> `fleet-candidate-check.py` ->
      `make generate`. The second `generate` is load-bearing.
- [x] After the version bump, expect `make generate` to fail on the two
      `command-catalog.md` mirrors -- the installer preserves them. `cp` from
      `templates/`, then a second `make sync` to refresh provenance, or
      `make check` reports them as drifted installed targets.
- [x] Confirm all four copies of `sd-ai-command-pack-review.py` are
      hash-identical.
- [x] `make check` exit 0.
- [x] PR. No admin override.

## Rollback

Revert the commit. Both helpers are additive and both call sites are
single-expression swaps; no state file, receipt, or digest changes shape.

## Verification record

Branch `fix/bookkeeping-absent-router`, pack 0.71.57.

- Baseline: `Ran 55 tests ... OK`.
- Red-first, six tests added and one existing test updated:
  `Ran 61 tests ... FAILED (failures=5)`. The five were the four new tests that
  assert new behaviour plus
  `test_run_composes_non_pr_local_and_optional_absence`, whose diagnostic
  substring changed.
  `test_absent_router_still_refuses_a_pr_whose_providers_declined` passed
  throughout, as a regression guard should.
- `test_pr_and_non_pr_branches_accept_the_same_local_silence` needed a fix
  before it meant anything: driven against one repository it passed
  immediately, in 0.394s, because the controller persists attempt state under
  the artifact root and the second run answered from the first run's stored
  decision instead of re-deciding. With a fresh repository per run it failed on
  three of four cases -- `AssertionError: False != True : malformed-plan: pr=3
  branch=0` -- which is the divergence the task exists to close. A comparison
  test that shares mutable state between the two things being compared is not
  a comparison.
- After the implementation: `Ran 61 tests in 10.034s ... OK`.
- Full suite, first run: **exit 1, four modules failing** --
  `test_generate_plugin`, `test_full_check`, `test_surface_closure`,
  `test_pack_drift`. The targeted suite was green at that moment. These are the
  release gates refusing a changed shipped payload with no version bump, so
  they were expected here, but the pattern is now three tasks old and the
  warning in step 3 stands.
- Full suite after the bump and regeneration: exit 0, 83 modules, no `FAILED`
  or `ERROR` line. `PYTHON_BIN=".venv/bin/python" make test` exit 0.
- `make generate` exit 0, `shipped-surface closure: clean`; four copies of
  `sd-ai-command-pack-review.py` at
  `sha256:7ab348b55de7758ffaf0a095c38abebbb5474a89e4d0c927d1b143e76c2b5fb1`.
  `make check` exit 0.

Build-order note, sharper than the one recorded on the previous task. Running
`fleet-candidate-check.py` before `make generate` fails -- `plugin build and
drift check failed with exit 1 ... plugins/sd drifts from the surface partition
and templates` -- because the ledger validates the generated tree and the tree
had not been regenerated for the new version yet. The order that converges is
`make sync` -> `make generate` (exits 2 on the stale ledger, having written
`plugins/sd`) -> `fleet-candidate-check.py` -> `make generate`. Separately, the
two `command-catalog.md` mirrors must be `cp`-ed from `templates/` **after**
the last `make generate` that touches the version string, and then `make sync`
run once more to refresh provenance; copying them earlier is wasted, because a
later `sync` restores them from a payload that still carries the old version.

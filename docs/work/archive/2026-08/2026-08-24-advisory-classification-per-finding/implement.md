# Implement — record the advisory classification on the finding

Branch `fix/advisory-classification-per-finding`, cut from `origin/main` at
`b17764ed`.

## 0. Baseline

- [ ] `.venv/bin/python -m unittest tests.test_review_stage` green. Record the
      count.
- [ ] Confirm the gap rather than assuming it: run the stage with a ceiling
      configured and a releasable finding, and show that `disposition.advisory`
      is non-zero while every `findings[]` record still reads
      `disposition: "outstanding"` with nothing distinguishing them.

## 1. The existing test that must change

`test_advisory_ceiling_reaches_the_plan_and_changes_the_policy_digest`
(`tests/test_review_stage.py:2022`) asserts the ceiling is the **only** added
plan key:

```python
self.assertEqual(
    set(ceiling_plan) ^ set(strict_plan), {"localAdvisorySeverityCeiling"}
)
```

- [ ] Update it to expect both keys, and extend its docstring to say why the
      version marker rides the same condition. Do not weaken the assertion to
      a subset check: its whole value is that it fails when an unintended key
      reaches the plan, and that value is worth more than the one-line edit it
      costs here. This is the only existing test expected to change; if others
      go red, the change is wider than `design.md` claims.

## 2. Tests first (red)

In `tests/test_review_stage.py`. The fixtures already carry everything these
need: `write_config(root, modes=..., ceiling=...)`, and the `mixed-severity`
provider mode (`tests/fixtures/review_stage_provider.py:125`) which emits
exactly two findings, one `low` and one `high`. Under `ceiling="medium"` that
is one released and one blocking in a single receipt -- the shape the existing
tests at `:2270` and `:2286` already use.

- [ ] Add a helper `assert_counts_match_records(receipt)` that recomputes all
      four counts from `findings[]` -- reading only `disposition` and
      `advisory`, never severity -- and asserts they equal the `disposition`
      block. Call it from every new test below. Acceptance criterion 2. This is the
      form that makes the requirement checkable: one predicate applied to
      several receipts, rather than one test that tries to build a receipt
      with all four buckets non-zero, which `mixed-severity`'s two findings
      cannot produce anyway.
- [ ] `test_a_released_finding_says_so_on_its_own_record` --
      `modes=("mixed-severity", "clean")`, `ceiling="medium"`. Assert the
      `low` finding carries `advisory: true` and the `high` one
      `advisory: false`, both still `disposition: "outstanding"`, reading no
      severity logic of the test's own. Acceptance criterion 1.
- [ ] `test_a_rebutted_finding_does_not_keep_its_advisory_flag` -- follow the
      two-run idiom at `:2286`: same repo, same scope name, so the second run
      takes the reuse path and `_redispose_receipt` is what recomputes. Rebut
      the **low** finding, not the high one -- the high one was never advisory,
      so rebutting it would pass with the pop unimplemented. Assert the stored
      record no longer carries `advisory`. Without this the fix re-creates its
      own defect one disposition later.
- [ ] `test_no_ceiling_leaves_every_finding_record_unchanged` -- no ceiling,
      no `advisory` key on any finding, and no `localAdvisoryRecordVersion` on
      the plan. Acceptance criterion 3 (no ceiling, nothing changes).
- [ ] `test_adopting_the_record_changes_the_receipt_identity` -- acceptance
      criterion 4 (the field is in the identity digest).
      Assert `localAdvisoryRecordVersion` is on the ceiling-configured plan and
      that its `policyDigest` differs from the strict repository's. The point
      is that a cached pre-change receipt cannot be reused, so assert against
      the digest, not merely that the field exists.
- [ ] The rank-0 edge stays where it is already pinned:
      `test_advisory_predicate_keeps_a_floor_a_wider_vocabulary_cannot_lower`
      (`:2087`) calls `_is_advisory` directly. No fixture mode emits an
      `unspecified` severity, and adding one to reach that edge end-to-end
      would buy coverage the predicate test already has.
- [ ] Run; confirm the new tests fail and that only the test named in step 1
      changed.

## 3. Implement

In `templates/scripts/sd-ai-command-pack-review-local.py` -- **not**
`scripts/`, which is generated.

- [ ] `build_plan` (`:1341`, ceiling read at `:1468`): emit
      `plan["localAdvisoryRecordVersion"] = 1` inside the existing
      `if ceiling is not None:` block, before `plan["policyDigest"] = _digest(plan)`.
- [ ] Rename `_disposition_counts` (`:2419`) to `_classify_findings`, update
      both call sites (`:2367`, `:2642`), and change the parameter type to
      `Sequence[MutableMapping[str, Any]]` -- the same annotation
      `_apply_local_dispositions` (`:2300`) already uses for the same list.
      No test references the old name.
- [ ] In its loop: `item.pop("advisory", None)` unconditionally, then
      `item["advisory"] = _is_advisory(item, ceiling)` only when the finding is
      outstanding **and** `ceiling is not None`. Pop first, on every pass, so
      `advisory` is present exactly where the current plan's ceiling classified
      it. Popping an absent key is a no-op, and today's code never writes the
      key, so no existing receipt is touched.
- [ ] Leave `_is_advisory` untouched, and leave which findings the ceiling
      releases untouched.
- [ ] Update the docstring: it describes counting, and the function now
      records. Say that the single traversal is the point, not an
      optimisation.

## 4. Validate

- [ ] `.venv/bin/python -m unittest tests.test_review_stage` green.
- [ ] `PYTHON_BIN=".venv/bin/python" bash .github/scripts/run-tests.sh` -- full
      suite, 0 failures. **Not optional.** It has caught something the targeted
      suite missed on each of the last three tasks; a receipt-shape change is
      exactly the kind of thing a downstream fixture asserts on.
- [ ] `PYTHON_BIN=".venv/bin/python" make test` -- coverage gate.

## 5. Docs

- [ ] `templates/docs/SD_AI_COMMAND_PACK.md` -- the advisory ceiling is
      documented there. State that a released finding is now marked on its own
      record, that the mark appears only where a ceiling is configured, and
      that adopting it changes the receipt identity, which supersedes a
      cached receipt rather than invalidating it -- the identity names a
      different file, so nothing errors.
- [ ] CHANGELOG under the new version.

## 6. Ship

- [ ] Re-read `main`'s manifest version immediately before bumping. #555
      through #558 hold 0.71.55 to 0.71.58 and are all open.
- [ ] `make sync` -> `make generate` (exits 2 on the stale ledger, having
      written `plugins/sd`) -> `fleet-candidate-check.py` -> `make generate`.
      Running the ledger check before the first `generate` fails with
      `plugins/sd drifts from the surface partition`.
- [ ] `cp` the two `command-catalog.md` mirrors from `templates/` **after** the
      last version-touching `generate`, then `make sync` once more for
      provenance.
- [ ] Confirm all four copies of the changed script are hash-identical.
- [ ] `make check` exit 0.
- [ ] PR. No admin override.

## Rollback

Revert the commit. Receipts written under this version carry an extra finding
field and a plan key, so after the revert their identity no longer matches what
the reverted code computes. They are orphaned, not misread: the next run writes
a fresh receipt at the old identity, and no run fails because one is lying
around.

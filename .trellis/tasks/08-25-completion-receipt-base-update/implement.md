# Implement — a completion receipt that survives a base update

Branch `fix/completion-receipt-base-update`, cut from `origin/main`.

## 0. Baseline

- [x] `.venv/bin/python -m unittest tests.test_bookkeeping_validator` green.
      Record the count; 103 tests are defined today.
- [x] Reproduce the deadlock in a scratch repository rather than trusting the
      PRD's transcript: archive commit, base moves, `git merge --no-ff` the
      base into the branch, then run `final-bundle --mode completion`. Expect
      `completion_successor_history_non_linear` and
      `completion_successor_scope_invalid` naming a path from the base.

## 1. Tests first (red)

In `tests/test_bookkeeping_validator.py`. The harness already has what these
need: `make_post_archive_successor_repo()` (`:1336`) builds a real repository
with a real archive commit, and `run_validator(..., extra_env=)` (`:182`)
takes `SD_AI_COMMAND_PACK_DEFAULT_BRANCH`, which is how a test gets a
resolvable base tip in a repository that has no `origin`.

Every one of these builds a **real merge**. Criterion 2 rules out a
synthesized linear range, and the whole point is that the merge's parent
structure is what the validator reads.

- [x] `test_completion_successor_accepts_a_clean_base_update` -- the deadlock
      itself, and criterion 1. Archive commit, base branch moves with a
      `.trellis/tasks/` path belonging to someone else, `merge --no-ff` the
      base in, no force push anywhere. Assert `returncode == 0` and
      `reasonCodes == ["completion_bundle_valid"]`.
- [x] `test_a_base_update_contributes_no_paths_to_the_successor_scope` --
      criterion 2, asserted directly rather than inferred from the receipt
      being valid: the other task's path must not appear in the evidence's
      changed-path list, and no `completion_successor_scope_invalid` finding
      may name it. `evaluateCompletionSuccessorRange` returns the list as
      `changedPaths`; confirm the key the *payload* surfaces before writing
      the assertion rather than assuming the internal name survives to the
      JSON.
- [x] `test_completion_successor_rejects_a_conflicted_base_update` -- the same
      shape but with both sides editing one file, resolved in the merge.
      Assert the new `completion_successor_base_update_conflicted` and that
      the conflicted path is named.
- [x] `test_a_merge_already_on_the_base_branch_is_still_non_linear` --
      condition 3. This is the shape of the existing
      `test_completion_successor_rejects_merge_commit` (`:2005`), but run
      **with** `SD_AI_COMMAND_PACK_DEFAULT_BRANCH` set, so the first two
      conditions both hold and only condition 3 refuses it. Without this test
      the relaxation silently swallows the existing one.
- [x] `test_an_unresolvable_base_tip_keeps_rejecting_the_merge` -- no
      `origin`, no environment variable. Assert
      `completion_successor_history_non_linear`, i.e. the pre-change verdict.
- [x] `test_active_task_successor_accepts_a_clean_base_update` -- the same fix
      in `evaluateActiveTaskSuccessorRange`. Its existing merge test is
      `test_active_task_successor_rejects_merge_commit_in_range` (`:2527`).
- [x] `test_finish_work_stale_names_the_mismatched_half` -- in
      `tests/` alongside the other `pr-eligibility` tests. Three cases: head
      differs, branch differs, both differ. Assert the message names the
      right half each time. Criterion 4. The PRD hit the confusing case:
      `matchesCurrentHead: true` reported beside "does not match the current
      branch and exact head".
- [x] Run; confirm the new tests fail and that
      `test_completion_successor_rejects_merge_commit` and
      `test_active_task_successor_rejects_merge_commit_in_range` still pass
      untouched. If either goes red, the relaxation is too wide and the
      predicate is what should change -- not the test.

## 2. Implement

All in `templates/scripts/` -- **not** `scripts/`, which is generated.

- [x] `sd-ai-command-pack-review-preflight.mjs`: one helper,
      `classifyFirstParentMerge(oid, fields)`, returning
      `linear` / `base-update` / `conflicted-base-update` / `non-linear`,
      applying the three conditions from `design.md` in order. Resolve the
      base tip with `trellisRootDefaultBranchName()` (`:5560`), preferring
      `origin/<name>` and falling back to `<name>`.
- [x] `evaluateActiveTaskSuccessorRange` (`:1824`), parent test at `:1856`:
      accept `base-update`, contributing no entries, and thread `parent = oid`
      so the chain continues. Reject the other two.
- [x] `evaluateCompletionSuccessorRange` (`:2158`), parent test at `:2189`:
      the same acceptance, plus the scope change below.
- [x] `evaluateCompletionSuccessorRange` scope: replace the single
      `bookkeepingChangedEntries(anchorOid, headOid, ...)` with a union of
      `bookkeepingChangedEntries(parent, oid, ...)` across the first-parent
      chain, skipping accepted base-update merges. This is the shape
      `evaluateActiveTaskSuccessorRange` already uses; the completion variant
      is the one that diverged.
- [x] Derive the returned `entries` from the same union, so paths the base
      contributed are not mode-validated either -- otherwise a base carrying an
      executable file fails the receipt under `bundle_unsupported_file_mode`
      for a file the branch never touched.
- [x] Add `completion_successor_base_update_conflicted` wherever reason codes
      are enumerated. **Enumerate the registries rather than trusting this
      list** -- grep the repository for an existing completion reason code and
      add the new one everywhere that one appears.
- [x] `sd-ai-command-pack-pr-eligibility.py:356`: split the message so it
      names whichever of branch or head differs, and both when both do.

## 3. Docs

- [x] `sd-ship` Stage 4's moved-head rule -- criterion 3. It prescribes
      `--base <head> --head <head>`, which the PRD measured as failing after a
      base update. State that a clean base update is now walked through, and
      that a conflicted one is not.
- [x] `sd-finish-work`'s "a merge commit anywhere in the range still fails
      closed and is not a bug" -- still true for feature merges, no longer
      true unqualified. Find it by grep; it is quoted in `prd.md` and is the
      sentence a caller will read when this fails.
- [x] CHANGELOG under the new version.

## 4. Validate

- [x] `.venv/bin/python -m unittest tests.test_bookkeeping_validator` green.
- [x] `.github/scripts/run-tests.sh` -- full suite, 0 failures. **Not
      optional.** Three tasks running: it has caught something the targeted
      suite missed every time.
- [x] `PYTHON_BIN=".venv/bin/python" make test` -- coverage gate.

## 5. Ship

- [x] Re-read `main`'s manifest version immediately before bumping. #555,
      #556, and #557 hold 0.71.55 through 0.71.57 and are all open.
- [x] `make sync` -> `make generate` (exits 2 on the stale ledger, having
      written `plugins/sd`) -> `fleet-candidate-check.py` -> `make generate`.
      Running the ledger check *before* the first `generate` fails with
      `plugins/sd drifts from the surface partition`; the tree must be
      regenerated for the new version first.
- [x] `cp` the two `command-catalog.md` mirrors from `templates/` **after**
      the last version-touching `generate`, then `make sync` once more for
      provenance. Copying earlier is wasted: a later `sync` restores them from
      a payload still carrying the old version.
- [x] Confirm all four copies of the changed scripts are hash-identical.
- [x] `make check` exit 0.
- [x] PR. No admin override.

## Rollback

Revert the commit. No receipt field changes shape. A receipt produced for a
base-updated branch stops validating on revert, which is the pre-change
behaviour.

## Verification record

Branch `fix/completion-receipt-base-update`, pack 0.71.58.

- Baseline: `Ran 103 tests ... OK` (`tests.test_bookkeeping_validator`),
  `Ran 42 tests ... OK` (`tests.test_pr_eligibility`).
- The fixture reproduces the reported failure exactly. Before the
  implementation, `test_completion_successor_accepts_a_clean_base_update`
  returned:

  ```
  [ "completion_successor_history_non_linear",
    "completion_successor_scope_invalid" ]
  ```

  which is the same pair the PRD measured on PR #551. The deadlock is
  reproduced from a real merge in a real repository, not asserted from the
  transcript.
- Red-first: `Ran 108 tests ... FAILED (failures=3)`. The two condition-3 and
  unresolvable-base tests passed from the start, correctly -- they assert
  today's verdict, and a relaxation that broke them would be too wide.
- After: `Ran 109 tests ... OK`, with
  `test_completion_successor_rejects_merge_commit` and
  `test_active_task_successor_rejects_merge_commit_in_range` untouched and
  still green. `tests.test_pr_eligibility`: `Ran 42 tests ... OK`.
- Full suite caught one thing the targeted suites did not, for the third task
  running: `tests.test_housekeeping.test_housekeeping_rejects_stale_finish_work_receipt_before_auto_merge`
  asserted the old `finish-work receipt does not match` wording. Updated to
  assert the new message names the head and does **not** blame the branch,
  since that fixture's receipt carries only a wrong head. A downstream
  assertion on an exact diagnostic string is precisely what changing a
  diagnostic breaks, and only the full suite holds it.
- Final: `run-tests.sh` exit 0, 83 modules, no `FAILED`/`ERROR`.
  `make check` exit 0. `make generate` exit 0,
  `shipped-surface closure: clean`. Both changed scripts hash-identical across
  all four copies.

One test needed correcting before it proved anything:
`test_finish_work_stale_names_the_mismatched_half` first asserted that the
branch-only case does not contain the word "head" anywhere in the diagnostic.
It does -- the call site appends "rerun sd-finish-work for the current head
before housekeeping". The assertion now reads only the leading clause the
message owns.

# Implementation plan — direction-aware completion-successor validation

Target: `scripts/sd-ai-command-pack-review-preflight.mjs` and its byte-identical
twin `templates/scripts/sd-ai-command-pack-review-preflight.mjs`.
Tests: `tests/test_bookkeeping_validator.py`.

> **Rebased onto origin/main (post-#302).** See `design.md` §"Rebased onto
> origin/main" for the authoritative structure and line anchors — they supersede the
> older `:NNNN` in the steps below. Net effect on this checklist:
> - C4/C6 land in `attemptArchiveAnchorRecovery` (`:1205`), at the
>   `successor.status !== 'valid'` block (`:1260`); the block already returns
>   `{ status: 'invalid', shapedTailCount, findings, evidence: {} }` (not a bare
>   `return`) — prepend the revert `add(...)` before the `successor.findings` loop and
>   keep that return.
> - Regex consts go at top-of-file (`:52`), not beside the helpers (CLI dispatch at
>   `:462` runs before the helper region → TDZ crash otherwise).
> - T3 now asserts `completion_successor_active_task_anchor_missing` (the pure
>   un-archive falls through to #302's active-task path), not `anchor_missing`.
> - Status: implemented and green on the new base (85 tests pass); the steps below are
>   the record of what was applied.

## Baseline first

- [ ] B1. Capture the pre-change failure shape. Build a fixture reproducing the
      verified `c59db841` shape — an archive tail, then a commit that renames the
      whole task directory back from `.trellis/tasks/archive/<ym>/<name>/` to
      `.trellis/tasks/<name>/` — and confirm it currently returns
      `completion_successor_scope_invalid`. This is the regression witness; write it
      before touching the validator so the "before" assertion is real and not
      reconstructed afterward. This step is what closes `prd.md` AC4.
      The un-archive commit must also **restore the original active `task.json`
      content** (status back to its pre-archive value, `completedAt` cleared), so
      the restored file differs from the archived copy — a *modified* rename, as the
      real revert was. A plain rename of the unchanged archived file would be `R100`;
      the real revert is `R093` because content changed. The similarity index itself
      (`R100` vs `R09x`) does **not** affect the code path — both are `R…` — so the
      exact number is fidelity, not a functional gate; but the content restoration is
      what makes the witness match `prd.md` AC4.
      Reference shape (do not depend on repo history at test time — the fixture must
      be self-contained): `git show --stat c59db841`.
- [ ] B2. Record the current full-suite baseline (repo-local venv — bare `python3`
      lacks `yaml` and dies before any test runs):
      `.venv/bin/python -m unittest tests.test_bookkeeping_validator -v 2>&1 | tail -5`
      Note pass/fail counts so C-step regressions are attributable.

## Change steps

- [ ] C1. Shared path helpers. Add `archiveTaskName(path)` and `activeTaskName(path)`
      wrapping the two existing regexes
      (`^\.trellis/tasks/archive/\d{4}-\d{2}/(\d{2}-\d{2}-[^/]+)/task\.json$` and
      `^\.trellis/tasks/(\d{2}-\d{2}-[^/]+)/task\.json$`). No behavior change.
- [ ] C2. Rewrite `isAdjacentArchiveCommit` (:1279) as the move assertion from
      `design.md` C1: `archivedNames` from non-`D` destinations, `vacatedNames` from
      `R…` rename sources and `D` paths, qualify on intersection. Keep the
      all-paths-under-`.trellis/tasks/` guard. Note: `bookkeepingChangedEntries` runs
      `--find-renames` with no `--find-copies` (:1435), so `C…` is not emitted here;
      the rename-only rule needs no copy branch. Expose a helper that returns the
      `archivedNames ∩ vacatedNames` move-set (not just a boolean) so C4 can reuse
      the exact set this predicate qualified on.
- [ ] C2b. Extend `evaluateCompletionSuccessorRange` (:1319) to return the parsed
      `entries` (already read at :1375) alongside `status`/`evidence`/`findings`. No
      behavior change — additive field only. This is what lets C3 avoid a second
      diff read (design C3 "one authoritative diff read").
- [ ] C3. Add `completionAnchorRevertedNames(anchorMoveSet, successorEntries)`
      returning the archived names genuinely un-archived in the successor range.
      **Both halves required for the same name** (design C3): the archived
      `task.json` leaves (`R…` rename `oldPath`, or a `D` entry's `path`) **and** the
      active `task.json` arrives (non-`D` destination). Intersect the two sets; do not
      union them. `anchorMoveSet` is the C1 intersection from C2's helper, so an
      unrelated archive copy in the same anchor commit is never a candidate.
- [ ] C4. In `validateCompletionSuccessorRecovery` (:1176-1218): compute the anchor
      move-set from `archiveEntries` via C2's helper (the `archivedNames ∩
      vacatedNames` intersection, **not** raw archive destinations). Pass it and
      `successor.entries` (from C2b — **no** second `bookkeepingChangedEntries` call)
      to `completionAnchorRevertedNames`. A failed range read is already handled by
      `evaluateCompletionSuccessorRange` returning `indeterminate` (:1383); since C3
      runs only on `status === 'invalid'` (C6), it never sees a `null`-derived range,
      and no independent second read exists to suppress the scope findings.
- [ ] C5. **No-op — withdrawn.** The `return` at :1209 stays. Do not convert it to
      `continue`; `successor.status !== 'valid'` covers `indeterminate`, and
      continuing would both fail open on git-inspection errors and let a wider
      two-endpoint diff cancel a bookkeeping mutation against its own reversal
      (design D2). Step retained as a numbered no-op so later references hold.
- [ ] C6. In the `successor.status !== 'valid'` branch (:1205-1210), run C3 **after**
      `evaluateCompletionSuccessorRange` **only when `successor.status === 'invalid'`**.
      Never run it on `indeterminate` — an inspection failure is not a diagnosis and
      must not be dressed up as a revert (design C4). When C3 returns a non-empty set
      emit `completion_successor_anchor_reverted` with the design C3 message *before*
      the existing loop that emits `successor.findings`. Emit every existing finding
      unchanged — no filtering, no downgrading. Respect `MAX_BOOKKEEPING_FINDINGS`
      (100): only at that cap does the prepend truncate the last scope path, which is
      the already-documented bounded-output behavior, not new loss.
- [ ] C7. Amend `.trellis/spec/backend/quality-guidelines.md` Validation & Error
      Matrix (:1233-1250) per `design.md` "Spec amendment": add the
      `completion_successor_anchor_reverted` row. Leave `:1246` and `:1235` as
      written — C4 is additive and C5 is withdrawn, so neither mapping changes
      meaning and no existing row becomes unreachable. Required deliverable, not
      follow-up.
- [ ] C8. Mirror every hunk into `templates/scripts/…`. Verify with
      `diff -q scripts/sd-ai-command-pack-review-preflight.mjs templates/scripts/sd-ai-command-pack-review-preflight.mjs`
      — must print nothing.

## Tests

- [ ] T1. Extend the `make_post_archive_successor_repo` fixture with an
      `unarchive_after: bool` option producing the PR #301 shape — rename the task
      directory back **and** restore the original active `task.json` content (per B1),
      so the un-archive is a modified rename, not an identical-content `R100`.
- [ ] T2. B1's witness now asserts `completion_successor_anchor_reverted` is present
      **and** that `completion_successor_scope_invalid` is still present. Asserting
      its absence would be asserting the regression Codex caught.
- [ ] T3. Pure-un-archive commit is not accepted as an archive anchor (C1 / R1).
      On the post-#302 base this means it falls through to the active-task recovery
      path and reports exactly `completion_successor_active_task_anchor_missing`
      (**not** the old `anchor_missing`), and never
      `completion_successor_anchor_reverted`.
- [ ] T4. Fail-closed, replacing the withdrawn poisoned-candidate test (R2):
      a candidate whose successor range is `indeterminate` terminates the scan with
      `completion_successor_history_unavailable` and does not fall through to an
      older anchor. Drive it by making a successor-range git inspection fail. Also
      assert `completion_successor_anchor_reverted` is **absent** — an indeterminate
      range must never be classified as a revert (C6 / design C4).
- [ ] T5. Guard-intact regressions: `:1136` and `:1162` still yield
      `completion_successor_scope_invalid`; `:1086` and `:1221` still yield their
      exact single-code arrays.
- [ ] T6. Half-an-un-archive is not one (C3 / R3): (a) archived `task.json` deleted
      (`D`) with no active restoration, and (b) an active `task.json` added (`A`) while
      the archive path stays untouched — each yields
      `completion_successor_scope_invalid` **without**
      `completion_successor_anchor_reverted`. This is the direct regression test for
      the `or`-vs-`and` defect. Note these are the real reachable shapes under
      `--find-renames`: case (b) is an `A` add, not a `C…` copy. Git cannot emit `C…`
      on this path (no `--find-copies`), so the copy-source exclusion is defensive-only
      and has no naturally reachable test; do not fabricate one by hand-injecting a raw
      `C` entry — assert the reachable `A`/`D` halves instead, which is what R5 covers.
- [ ] T7. Mixed failure (C6 / R3 / R6): a successor that un-archives the anchored
      task *and* writes `.trellis/.runtime/` reports both
      `completion_successor_anchor_reverted` and `completion_successor_scope_invalid`.
      Proves the new code cannot mask an independent violation.

## Validation gates

Run in order; stop on first failure. Use the repo-local venv — a bare `python3`
lacks `yaml` and dies in `install_test_support` before any test runs.

```bash
.venv/bin/python -m unittest tests.test_bookkeeping_validator 2>&1 | tail -5
```

```bash
node --check scripts/sd-ai-command-pack-review-preflight.mjs && node --check templates/scripts/sd-ai-command-pack-review-preflight.mjs && diff -q scripts/sd-ai-command-pack-review-preflight.mjs templates/scripts/sd-ai-command-pack-review-preflight.mjs && echo MIRROR-OK
```

```bash
make check
```

## Review gates

- After C2 — confirm the move assertion does not reject a real `task.py archive`
  commit. Replay a genuine archive commit from repo history through the predicate
  rather than trusting the fixture alone.
- After C6 — grep for `continue` inside `attemptArchiveAnchorRecovery` (post-#302
  home of the recovery loop). The only one is the pre-existing unshaped-candidate
  skip at :1254. A second `continue` means C5's withdrawal was reintroduced by
  accident, which is the fail-open regression this plan exists to avoid.
- After C6 — confirm no existing `add(...)` call in the
  `successor.status !== 'valid'` branch (:1260) was removed, reordered away, or made
  conditional. C4 is additive; the diff should show insertion only.
- After C6/C7 — confirm this task's shipped matrix row and its code agree in both
  directions: `completion_successor_anchor_reverted` has a matrix row (C7) and is
  reachable (T2/T7), and C7 introduces no unreachable row. Scope this gate to the
  code this task introduces; #302's `completion_successor_active_task_anchor_missing`
  and `..._active_task_ambiguous` are reachable but undocumented in the matrix — a
  pre-existing #302 gap flagged as follow-up in `design.md`, not closed here.

## Rollback points

- After C8, before tests:
  `git checkout -- scripts templates/scripts .trellis/spec/backend/quality-guidelines.md`
  restores the validator, its mirror, and the spec with no other state to unwind.
- Whole task: revert the branch commit; no schema, receipt, or persisted-state
  changes are introduced.

## Out of scope

- Any override/force/bypass flag.
- Changing `.github/scripts/bookkeeping_ci_scope.py` (settled by `b3d0cb25`).
- Unifying the Python and `.mjs` classifiers — the duplication is the deeper root
  risk and is noted in `prd.md` as a follow-up, not taken up here.

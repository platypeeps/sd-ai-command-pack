# Scope the finalization bundle validator to the change delta

## Goal

Stop the `final-bundle` validator from failing a bundle on pre-existing debt in
task directories a branch did not change, and give repo-maintenance branches a
valid mode, so `sd-finish-work` stops failing closed on work that is genuinely
complete.

## Evidence

Both PRs merged on 2026-07-29 were merged by hand because no finish-work receipt
was obtainable. Neither failure was about the change under review.

**PR #273** (`plan/audit-2026-07-28-followup-artifacts`, merged `5fc11c2f`) —
`final-bundle --mode planning` returned `status=invalid` with 27 findings:

| Count | Reason code | Pre-existing? |
|-------|-------------|---------------|
| 2 | `bundle_scope_invalid` | No — `.trellis/audit/**` in the delta |
| 20 | `task_context_seed` | Yes — `_example` scaffold rows, untouched by the PR |
| 5 | `task_metadata_invalid` | Yes — empty `task.json` descriptions, untouched by the PR |

25 of 27 findings were in files the PR never modified. They surfaced only because
the PR edited a *sibling* file in the same task directory.

**PR #274** (`improve/review-workflow-hygiene`, merged `16b6ebe2`) — rejected in
both available modes: `--mode completion` gave `completion_archive_move_missing`
(the branch archives no task) and `--mode planning` gave
`planning_recovery_commit_scope_invalid` (its commits touch paths outside any
active task directory). A skills-and-release branch fits neither mode, so there
is no valid mode for it to be finalized in.

## Root causes

**1. Whole-directory validation.** `validatePlanningBundle`
(`scripts/sd-ai-command-pack-review-preflight.mjs:1505`) derives `taskDirs` from
the delta (`:1513-1517`), then calls `validateBookkeepingTaskDirectory` per
*directory* (`:1532-1535`). That function validates the directory's entire
current content — `task.json` metadata (`:694`), `prd.md` (`:706-709`), and
`_example` scaffold rows in the context manifests (`:733`) — regardless of which
files the delta actually contains. Touching one `prd.md` therefore inherits every
stale artifact its neighbours accumulated.

**2. Only two modes exist.** `:523` restricts `--mode` to `completion` and
`planning`. `completion` requires archiving an active task (`:1462`); `planning`
requires at least one active task artifact change (`:1525`). A branch that
changes skills, scripts, specs, or cuts a release satisfies neither.

## Requirements

- Scope the fix to the whole `validateBookkeepingTaskDirectory` family, not to the
  two codes #273 happened to surface. That function emits 14 reason codes
  (`:644-760`) plus the three `task_context_*` kinds (`:731-738`), and every one
  of them fires on untouched neighbour files by the same mechanism. Fixing only
  `task_context_seed` and `task_metadata_invalid` leaves the next branch to fail
  on `task_prd_empty` or `task_context_malformed` for identical reasons.
- Report a per-file finding only when that file is present in the base..head
  delta. A finding in an untouched file must not invalidate the bundle.
- Preserve the existing whole-directory checks as non-blocking signal rather than
  discarding them, so accumulated debt stays visible without gating unrelated
  work. The typed result already carries the mechanism: `add()` (`:547`) takes a
  `disposition` argument defaulting to `'invalid'`, and bundle validity is
  computed as `findings.some((finding) => finding.disposition === 'invalid')`
  (`:586`). A non-`'invalid'` disposition is therefore already emitted and
  already non-blocking; this work needs to use it, not invent it.
- Give a branch that changes neither an archived task nor an active task artifact
  a mode in which it can produce a valid receipt, without weakening the delta
  scope rules that `completion` and `planning` already enforce.
- Keep `bundle_scope_invalid` blocking. Its two PR #273 findings were correct:
  `.trellis/audit/**` genuinely does not belong in a finalization delta, and the
  rule shipped in v0.56.1 exists to prevent that mix.
- Change `templates/scripts/sd-ai-command-pack-review-preflight.mjs` as the
  source and regenerate the root mirror; the two files are currently identical
  and must stay so.
- Cover each defect with a focused regression in
  `tests/test_bookkeeping_validator.py` that fails against the current validator.
  That is where `final-bundle` coverage lives — it invokes the command 37 times
  and already asserts `planning_recovery_commit_scope_invalid` (`:1417`, `:1520`).
  `tests/test_review_preflight.py` does not reference `final-bundle` at all and is
  the wrong file for this work.

## Acceptance Criteria

- [ ] A bundle whose delta touches one file in a task directory containing a
      stale `_example` scaffold row or an empty `task.json` description
      validates successfully, and a regression test asserts it.
- [ ] A bundle whose delta itself contains such a defect still fails, and a
      regression test asserts it — the fix narrows scope without removing the
      check.
- [ ] A branch that changes only skills, scripts, specs, or release payload
      produces a valid receipt, and a regression test asserts it.
- [ ] `bundle_scope_invalid` still fails a delta containing `.trellis/audit/**`.
- [ ] Replaying the PR #273 delta (`49b43afd..7fde6218`, 154 files: 152 under
      `.trellis/tasks/` and 2 under `.trellis/audit/`) under the fixed validator
      leaves exactly the 2 `bundle_scope_invalid` findings and no other blocking
      finding. It must not reach `status=valid` — the audit-path findings are
      correct and this delta is permanently unfinalizable. Requires
      `git checkout 7fde6218` first; `final-bundle` returns
      `bundle_head_not_checked_out` otherwise.
- [ ] `templates/` and root copies of the validator remain byte-identical after
      `make sync`.

## Open questions

- How a repo-maintenance branch gets a valid receipt. Three options, not two: a
  new named mode, a relaxation of `planning`, or **a new subtype**. The subtype
  route has a working precedent — `:1779` sets
  `evidence.planningSubtype = 'journal-only-recovery'` and admits a narrower
  bundle inside `planning` mode with its own scope rule
  (`planning_recovery_bundle_scope_invalid`, `:1785`). Prefer evaluating that
  first: it keeps `--mode` at two values, and the plumbing already exists.
  Note the contract cost either way — `sd-ai-command-pack-pr-eligibility.py:259-279`
  reads both subtypes off the receipt and enforces that each is null in the other
  mode, so any new subtype or mode must be reflected there.
- Which `disposition` value non-blocking directory findings should carry. The
  field itself is settled (see the requirement above); only the vocabulary is
  open, and it must not collide with the existing `invalid` and `indeterminate`
  values.

## Notes

- This task is **not** a licence to weaken finalization. Every gate that fired on
  a path the branch actually changed fired correctly.
- Recorded as residue in
  `.trellis/tasks/07-28-analyze-recurring-trellis-workflow-instability/prd.md`
  (Post-Completion Residue — 2026-07-29); that task's own criteria are met and it
  is not reopened by this work.
- Complex enough to need `design.md` and `implement.md` before `task.py start` —
  the mode question is a contract change reaching `sd-finish-work`,
  `sd-housekeeping`, and `sd-ai-command-pack-pr-eligibility.py`, which
  independently recomputes the receipt before merge.

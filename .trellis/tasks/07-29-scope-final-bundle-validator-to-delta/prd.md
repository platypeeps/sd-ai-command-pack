# Scope the finalization bundle validator to the change delta

## Goal

Stop the `final-bundle` validator from failing a bundle on pre-existing debt in
task directories a branch did not change, and give repo-maintenance branches a
valid mode, so `sd-finish-work` stops failing closed on work that is genuinely
complete.

## Evidence

Both PRs merged on 2026-07-29 were merged by hand because no finish-work receipt
was obtainable. The two cases are not symmetric, and it would be wrong to record
them as if they were.

For **#274** the validator was wholly at fault — the branch had no mode to be
finalized in. For **#273** it was not: 2 of its 27 findings were correct findings
about its own delta, and those alone made the bundle unfinalizable. Even a perfect
validator would have refused it. What the whole-directory defect added there was
25 spurious findings on files the PR never touched — it buried a real, small
failure under noise rather than causing the failure.

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

**3. `journal-only-recovery` cannot prove a session that repaired the journal.**
Observed directly on this branch on 2026-07-29. The CI bookkeeping fast lane
re-validates *each push increment* rather than the branch, using the previous
head as its base. A push that carries only a journal entry and its sibling index
therefore lands in `validateJournalOnlyPlanningRecovery` (`:1763`), which proves
every commit the session's `Git Commits` table references. That proof admits
task-only commits: `:1876-1888` rejects any path outside
`.trellis/tasks/<dd-dd-name>/`, and `:1866-1874` rejects deletes, renames, and
copies. Recording session 251 failed because that session's own work included
two journal-repair commits (`acc836dc`, `d21afe83`, both touching
`.trellis/workspace/`) and one that cleared a stale `branch` field
(`f92221e5`, yielding `planning_lifecycle_mutation` and
`planning_baseline_invalid` against the task as it stood at that commit's
parent). The same range validates cleanly as an ordinary planning bundle
against the branch's merge-base, so the defect is the per-increment framing plus
the task-only commit filter, not the session content.

The consequence is structural, not cosmetic: any session that repairs
bookkeeping — exactly the sessions this pack most wants recorded — cannot be
journaled in its own isolated push. A fix must either let the recovery subtype
admit workspace paths for commits the session itself declares, or stop
validating push increments as standalone bundles.

**Scope decision (2026-07-30, adversarial planning review):** root cause 3 is
split out to the follow-up task
`.trellis/tasks/07-30-recover-bookkeeping-repair-sessions/`. Two review rounds
failed to produce a sound no-re-audit justification for admitting
`.trellis/workspace/**` paths in cited commits — an initial pull-request push
receives no per-increment bookkeeping validation
(`.github/scripts/bookkeeping_ci_scope.py` classifies non-`synchronize`
pull-request events as full CI, and the `Validate bookkeeping head` step is
gated on `mode == 'bookkeeping'`), so cited workspace mutations could go
entirely unaudited. The session-251 shape additionally needs a
direction-of-repair rule for commits like `f92221e5` whose parent lifecycle
state was already dirty. This task therefore fixes root causes 1 and 2 only:
the recovery subtype's cited-commit scope widens to repo-maintenance paths,
while `.trellis/workspace/**` cited commits and dirty-parent task repairs
remain rejected until the follow-up lands.

Two adjacent sharp edges surfaced while diagnosing this and belong in the same
review:

- The `Status` heading is a machine-read marker, not prose. `:4248` requires a
  line matching `**Completed**` exactly, and `:1678` silently skips any session
  without it — a session with an accurate but non-matching status is dropped
  with no diagnostic naming the marker.
- `:1653` requires the sibling `index.md` in the same delta as any journal
  change, so a journal-only correction cannot be pushed alone.

## Requirements

- Scope the fix to the whole `validateBookkeepingTaskDirectory` family, not to the
  two codes #273 happened to surface. That function (`:644-719`) emits 12 reason
  codes directly and calls three more validators at `:715-717`
  (`validateBookkeepingTextWhitespace`, `validateBookkeepingTaskContexts`,
  `validateBookkeepingTopology`). Fixing only `task_context_seed` and
  `task_metadata_invalid` leaves the next branch to fail on `task_prd_empty` or
  `task_context_malformed` for identical reasons.
- Classify the family before changing it. **The codes are not homogeneous, and
  "delta-scope everything" is the wrong instruction.** `design.md` must place
  every code in one of these four groups and state the rule for each:
  1. **Per-file** — attributable to one named file in the directory:
     `task_json_invalid`, `task_metadata_invalid`, `task_prd_empty`,
     `task_prd_invalid`, `task_artifact_invalid`, `task_context_invalid`, the
     three `task_context_${kind}` variants (`:737` — `seed`, `malformed`,
     `reference`), and the whitespace findings. **These are the ones to
     delta-scope.**
  2. **Directory-level** — about the directory itself, raised before any file is
     read, with an early `return`: `task_layout_invalid` and
     `task_path_outside_repository` (`:649` onward), `task_directory_unreadable`,
     `task_directory_unsafe`. No file to test against the delta; scoping these by
     file is meaningless and they should stay as they are.
  3. **Completion-only** — gated on `completionReady` (`:697`):
     `task_lifecycle_not_completion_ready`, `task_branch_invalid`. These never
     fire in `planning` mode and were never part of the #273 failure.
  4. **Relationship** — `validateBookkeepingTopology` (`:743`) emits six codes,
     not the one this PRD previously named: `task_topology_base_invalid`,
     `task_topology_not_reciprocal`, `task_topology_prd_missing_child`,
     `task_topology_unverifiable`, `task_topology_missing`,
     `task_topology_ambiguous`. These span two task directories, so "is the
     file in the delta" has more than one answer. `design.md` must say which end
     of the link governs.
- Report a **group 1** finding only when that file is present in the base..head
  delta. A per-file finding in an untouched file must not invalidate the bundle.
- Preserve the existing whole-directory checks as non-blocking signal rather than
  discarding them, so accumulated debt stays visible without gating unrelated
  work. **The `disposition` field is not sufficient for this and must not be
  mistaken for it.** `add()` (`:547`) does take a `disposition` defaulting to
  `'invalid'`, but status is derived at `:586-591` as:

  ```js
  const invalid = findings.some((finding) => finding.disposition === 'invalid');
  const status = invalid ? 'invalid' : findings.length > 0 ? 'indeterminate' : 'valid';
  ```

  A non-`'invalid'` finding still yields `indeterminate`, never `valid`. The
  merge consumer is stricter still — `sd-ai-command-pack-pr-eligibility.py:250-252`
  rejects the receipt unless `findings == []`. So *any* entry in `findings`
  blocks a receipt through two independent mechanisms. Carrying non-blocking
  signal therefore requires either a separate field in the typed result, or
  coordinated changes to both `:586-591` and the eligibility consumer. Whichever
  route is chosen must be stated in `design.md` before implementation.
- Give a branch that changes neither an archived task nor an active task artifact
  a mode in which it can produce a valid receipt, without weakening the delta
  scope rules that `completion` and `planning` already enforce.
- Land that change across every consumer in the same commit, not in the validator
  alone. `sd-ai-command-pack-pr-eligibility.py` independently rejects a receipt
  whose `mode` is outside `{"completion", "planning"}` (`:238`) and whose
  `reasonCodes` are not exactly `[f"{mode}_bundle_valid"]` (`:246`), and
  `templates/.agents/skills/sd-finish-work/SKILL.md:122` hard-codes
  `--mode <completion|planning>` in the command it tells the operator to run. A
  validator-only change plus a validator-only test can pass while the merge gate
  still refuses the receipt — which is exactly the failure this task exists to
  remove.
- Keep `bundle_scope_invalid` blocking. Its two PR #273 findings were correct:
  `.trellis/audit/**` genuinely does not belong in a finalization delta, and the
  rule shipped in v0.56.1 exists to prevent that mix.
- Edit under `templates/` as the source and regenerate the root mirror for every
  mirrored file this change touches — at minimum
  `templates/scripts/sd-ai-command-pack-review-preflight.mjs` and, if the mode
  question lands, `templates/.agents/skills/sd-finish-work/SKILL.md`. Both pairs
  are currently byte-identical and must stay so.
- Cover each defect with a focused regression in
  `tests/test_bookkeeping_validator.py` that fails against the current validator.
  That is where `final-bundle` coverage lives — it invokes the command 37 times
  and already asserts `planning_recovery_commit_scope_invalid` (`:1417`, `:1520`).
  `tests/test_review_preflight.py` does not reference `final-bundle` at all and is
  the wrong file for this work.

## Acceptance Criteria

- [ ] A bundle whose delta touches **only a clean sibling file** in a task
      directory that separately contains a stale `_example` scaffold row or an
      empty `task.json` description validates successfully, and a regression test
      asserts it. The defective file must be absent from the delta — a delta that
      includes it is the next-but-one criterion, not this one.
- [ ] The same holds across group 1 as a whole, not a sampled pair. A regression
      asserts at least one code from each distinct producer:
      `validateBookkeepingTaskDirectory` itself (`task_prd_empty`),
      `validateBookkeepingTaskContexts` (`task_context_malformed`), and
      `validateBookkeepingTextWhitespace`. A three-code special case must not be
      able to pass. Groups 2, 3, and 4 are explicitly outside this criterion —
      `design.md` states their rule instead.
- [ ] A bundle whose delta itself contains such a defect still fails, and a
      regression test asserts it — the fix narrows scope without removing the
      check.
- [ ] The untouched-file finding is still **reported**, not silently dropped. A
      regression asserts it appears in whichever non-blocking channel `design.md`
      chose, on a bundle that simultaneously reaches `status=valid` and is
      accepted by `sd-ai-command-pack-pr-eligibility.py`. An implementation that
      merely stops scanning untouched files satisfies every other criterion here
      while violating the signal-preservation requirement; this criterion is what
      separates the two.
- [ ] A repo-maintenance branch produces a valid receipt, and a regression test
      asserts it. `design.md` must first fix the exact allowlist of paths such a
      branch may touch, and must state whether the range still has to carry the
      journal-plus-index pair: `validateBookkeepingJournalBundle` (`:1622`) adds
      `journal_session_missing` (`:1645-1646`) whenever the delta contains no
      `.trellis/workspace/` journal file, so "changes only skills, scripts,
      specs, or release payload" is not by itself a finalizable delta today.
- [ ] That receipt is accepted end to end, not just by the validator: it passes
      `sd-ai-command-pack-pr-eligibility.py` without raising
      `EligibilityInputError`, and `sd-finish-work/SKILL.md` documents the mode
      the operator must actually pass. Asserting `status=valid` alone does not
      satisfy this criterion.
- [ ] `bundle_scope_invalid` still fails a delta containing `.trellis/audit/**`.
- [ ] Replaying the PR #273 delta (`49b43afd..7fde6218`, 154 files: 152 under
      `.trellis/tasks/` and 2 under `.trellis/audit/`) under the fixed validator
      drops all 25 whole-directory findings and keeps the 2 `bundle_scope_invalid`
      findings. It must **not** reach `status=valid`, and the residue is not the
      audit pair alone: that range carries no `.trellis/workspace/` journal file,
      so `journal_session_missing` (`:1645-1646`) fires as well. The delta is
      permanently unfinalizable, so the criterion is the **drop of the 25**, not
      a clean run. `final-bundle` returns `bundle_head_not_checked_out` unless
      `7fde6218` is checked out — but checking it out also restores the *pre-fix*
      validator, so run the fixed validator from a separate worktree or fixture
      rather than from inside that checkout.
- [ ] `templates/` and root copies remain byte-identical after `make sync` for
      every file this change touches, not the validator alone —
      `sd-finish-work/SKILL.md` is mirrored the same way and hard-codes the mode
      list at `:122` in both copies.

## Open questions

- How a repo-maintenance branch gets a valid receipt. Three options, not two: a
  new named mode, a relaxation of `planning`, or **a new subtype**. The subtype
  route has a working precedent — `:1779` sets
  `evidence.planningSubtype = 'journal-only-recovery'` and admits a narrower
  bundle inside `planning` mode with its own scope rule
  (`planning_recovery_bundle_scope_invalid`, `:1785`). Prefer evaluating that
  first: it keeps `--mode` at two values, and the plumbing already exists.
  The costs are sharply asymmetric, and an earlier draft of this PRD overstated
  the subtype cost. A **new subtype** keeps `mode="planning"`, so `:238`, `:246`,
  and `sd-finish-work/SKILL.md:122` all hold unchanged — and
  `sd-ai-command-pack-pr-eligibility.py:259-279` needs no change either: it only
  type-checks the subtype string and enforces that each subtype is null in the
  opposite mode. It does **not** whitelist subtype names. A **third named mode**
  breaks `:238`, `:246`, and `SKILL.md:122` at once. Either way, eligibility
  re-invokes the validator with the receipt's own mode (`:354`) and compares the
  recomputed document, so the receipt must still reproduce exactly.
- Where non-blocking directory signal lives. Neither route is free, and an
  earlier draft of this PRD was wrong to say a separate field leaves the
  eligibility contract untouched.
  - A **separate typed-result field** keeps `findings` and the `findings == []`
    rule intact — but only if it is additive at schema version 1. If the schema
    version increments, `sd-ai-command-pack-pr-eligibility.py:224` rejects the
    receipt on an exact `schemaVersion` mismatch, and
    `sd-finish-work/SKILL.md:127` ("Require schema version 1") goes stale. Both
    consumers and their tests would then have to change too. `design.md` must
    state which it is: schema-1-additive, or a coordinated version bump.
  - **Reusing `findings` with a new `disposition`** requires relaxing both
    `:586-591` and `sd-ai-command-pack-pr-eligibility.py:250-252`, widening what
    a valid receipt may contain — a merge-gate change, not a reporting change.

  Prefer the schema-1-additive field unless `design.md` argues otherwise.

## Notes

- This task is **not** a licence to weaken finalization. Every gate that fired on
  a path the branch actually changed fired correctly.
- Recorded as residue in
  `.trellis/tasks/archive/2026-07/07-28-analyze-recurring-trellis-workflow-instability/prd.md`
  (Post-Completion Residue — 2026-07-29); that task's own criteria are met and it
  is not reopened by this work.
- Complex enough to need `design.md` and `implement.md` before `task.py start` —
  the mode question is a contract change reaching `sd-finish-work`,
  `sd-housekeeping`, and `sd-ai-command-pack-pr-eligibility.py`, which
  independently recomputes the receipt before merge.

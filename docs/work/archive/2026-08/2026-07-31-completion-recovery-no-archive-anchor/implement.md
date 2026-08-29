# Implementation — active-task completion recovery

One coordinated change, one commit (per `design.md`'s "Shape of the change").
Ordered so each step is independently reviewable and the refactor is
separated from new capability.

**Revision note:** this plan follows `design.md` through two rounds of
review-driven correction. Step 4 in particular has changed mechanism twice —
first from an isolated anchor-commit proof to one unified range, then from an
unqualified "oldest touch" to a "oldest touch whose parent already qualifies"
search (round 2 found the unqualified version would select `task.py create`/
`task.py start` itself for most real tasks). Do not implement against an
older copy of `design.md` or from memory of an earlier summary of this file.

## Order

1. **Extract `validateTaskLifecycleIdentity`** from the archive-move path's
   existing inline block (`:1544-1574`) into a shared function taking
   `(source, current, sourcePath, currentPath, add, options)` — two separate
   path parameters, not one (the archive-move caller reports the
   source-status finding at the active path but the identity finding at the
   archive path; a single shared path can't reproduce that split) —
   parameterized by `{sourceStatuses, checkCurrentStatus, currentStatuses,
   requireStatusEqual, checkSourceCompletedAtNull, checkCompletedAt,
   currentCompletedAtRule, tolerateBranchNewlyRecorded, sourceCode,
   identityCode}` (see `design.md`'s Change A shared-helper section for the
   exact shape and the two option constants,
   `ARCHIVE_MOVE_IDENTITY_OPTIONS`/`IN_PLACE_IDENTITY_OPTIONS`). Call it back
   from the archive-move path with `ARCHIVE_MOVE_IDENTITY_OPTIONS` and the
   two genuinely different paths (`${mapping.sourceDir}/task.json`,
   `${mapping.archiveDir}/task.json`) — note `checkCurrentStatus: false`,
   `checkSourceCompletedAtNull: false`, and `checkCompletedAt: false` there:
   the archived record's status/completedAt are already independently
   enforced elsewhere (`task_lifecycle_incomplete`, `task_metadata_invalid`),
   so this caller must reproduce only the original source-status check plus
   the field-identity diff, nothing more.

   **Gate:** behavior-preserving only — no new caller yet. Run the existing
   archive-move fixtures in `tests/test_bookkeeping_validator.py` and confirm
   **byte-identical reason-code sets**, not just "still passes" — this is the
   exact step where the first design draft's blocking defect lived (an
   unparameterized helper that would have rejected every archived record),
   and where a second, subtler defect lived even after that fix (a version
   that checked `current.status`/`current.completedAt` unconditionally would
   have added a new, previously-absent reason code to a malformed-archive
   fixture without causing a false failure — easy to miss with a pass/fail
   check alone). Do not combine this step's diff with step 2 in review.

2. **Change A** — add `detectInPlaceTaskTouch` / `validateInPlaceTaskTouch` to
   `validateCompletionBundle`'s `uniqueMappings.length === 0` branch, calling
   the extracted helper from step 1 with `IN_PLACE_IDENTITY_OPTIONS`
   (`requireStatusEqual: true`, `tolerateBranchNewlyRecorded: false` —
   Decision 4: no transition tolerance for this shape).

   **Gate:** AC1 (in-place touch validates directly) and AC10 (a status
   transition or newly-recorded branch on this shape still blocks) both
   pass. Existing archive-move and `completion_archive_move_missing`
   fixtures stay green.

3. **Refactor `validateCompletionSuccessorRecovery`** into
   `attemptArchiveAnchorRecovery` (local-findings extraction of the current
   body, **now also returning `shapedTailCount`** — the existing local
   variable at `:1214`/`:1243` in the current tree, already computed, just
   needs exposing in the return value) plus the orchestration:

   ```
   const archiveResult = attemptArchiveAnchorRecovery(headOid);
   if (archiveResult.status === 'valid') { commit archiveResult; return; }
   const activeTaskResult = attemptActiveTaskAnchorRecovery(headOid);
   if (activeTaskResult.status === 'valid') { commit activeTaskResult; return; }
   const findingsToCommit = (archiveResult.shapedTailCount > 0 || archiveResult.status === 'indeterminate')
     ? archiveResult.findings
     : activeTaskResult.findings;
   for (const f of findingsToCommit) add(f.reasonCode, f.path, f.message, f.disposition);
   ```

   **This is the corrected (now third revision) orchestration — implement
   exactly this, not an earlier description you may have seen, including
   your own prior progress.** Two empirically-found defects, both traced to
   specific lines rather than guessed (see `design.md`'s Control Flow "Round
   3 note" for the full history): (1) unconditionally preferring
   `activeTaskResult` on double failure silently replaced every existing
   archive-failure fixture's specific reason code with a generic
   `completion_successor_active_task_ambiguous`, since every such fixture
   archives its task and has zero active tasks at head; (2) `shapedTailCount`
   alone still missed two fixtures where Git itself fails mid-search (before
   the shape check that increments it) — a materially different,
   `'indeterminate'`-disposition situation that also shouldn't be routed to
   the active-task diagnosis.

   **Gate:** stub `attemptActiveTaskAnchorRecovery` to always return
   `{status: 'invalid', shapedTailCount: 0, findings: [...]}` for this step
   (step 4 implements it for real), then run the full existing
   `completion_successor_*` suite. **Ten of the eleven existing fixtures must
   stay byte-identical.** The eleventh,
   `test_completion_successor_requires_a_canonical_anchor` (a one-commit repo
   with no task and no archive ever created — `shapedTailCount` is
   structurally always `0` there, definitively, no Git errors), pins
   genuinely-superseded behavior: update its assertion to expect
   `completion_successor_active_task_ambiguous` instead of
   `completion_successor_anchor_missing`, as an intentional, documented
   improvement — not a regression to chase, and not a reason to touch the
   discriminator further. If any *other* existing fixture changes, the
   orchestration is wrong — stop and re-check against `design.md`'s current
   text, do not patch around it locally.

4. **Change B** — implement `attemptActiveTaskAnchorRecovery` per
   `design.md`'s corrected mechanism. This step went through two rounds of
   review-driven correction — implement against the *current* `design.md`
   text, not from memory of an earlier summary of it:

   a. `discoverActiveTrellisTaskDirectory()` — enumerate `.trellis/tasks/*`
      excluding `archive`, load each `task.json`. Any load failure
      (unreadable/unsafe/oversized) counts toward ambiguity, not toward "not
      a candidate." Exactly one `in_progress`/`review` record → proceed; else
      `completion_successor_active_task_ambiguous`.
   b. Walk the already-fetched bounded `commits` array, indices
      `commits.length - 2` down to `0` only, to find the **oldest
      qualifying** touch: a commit whose diff against its own parent touches
      the active task's directory, **and** whose parent's `task.json`
      (probed via `loadBookkeepingJsonAtRef` with a no-op `add` — a shape
      probe, not a validation, same pattern `isAdjacentJournalCommit` already
      uses) already has status in `{in_progress, review}`. **This
      qualification check is load-bearing, not optional**: `task.py create`
      writes `status: 'planning'` and `task.py start` flips
      `planning → in_progress` (`.trellis/scripts/common/task_store.py:310-315`,
      `.trellis/scripts/task.py:111-131`), both touching the task's own
      directory — without requiring the parent to already qualify, the
      search would select one of *those* commits as the starting point for
      any task whose whole lifecycle fits in the window, which is the
      ordinary case for a young task, not an edge case. Skip
      non-qualifying candidates and keep walking toward more recent commits.
      If the only qualifying candidate is at the window's edge
      (`i = commits.length - 2`) and the fetch hit its count cap
      (`commits.length > MAX_BOOKKEEPING_ANCHOR_SEARCH_COMMITS`) →
      `completion_successor_history_oversized`. No qualifying candidate at
      all → `completion_successor_active_task_anchor_missing`. Otherwise,
      that commit's parent is `startingPoint`.
   c. Bound + per-commit linearity check across `startingPoint..headOid`
      (same call shape as the existing `evaluateCompletionSuccessorRange`,
      `:1325` — reuse the style, do not duplicate the archive case's own
      function).
   d. **Two separate scope checks — do not conflate them:**
      (i) aggregate net-unique-path count across `startingPoint..headOid`
      against the existing `MAX_BOOKKEEPING_CHANGED_PATHS` cap, reusing the
      exact dedup pattern `evaluateCompletionSuccessorRange` already uses
      (`:1385-1394`); (ii) a *separate* per-commit category check (walk each
      commit's own diff against its own parent, inspect every changed path
      in that commit): allowed categories are non-`.trellis` paths, the
      active task's own directory, and `.trellis/workspace/**` journal/index
      files; anything else → `completion_successor_scope_invalid`. (i) is
      not a substitute for (ii): (i) bounds total scope the way the archive
      case already does; (ii) is what catches a mutate-then-revert or a
      single commit touching both an allowed and forbidden path, which a net
      diff would miss.
   e. `validateTaskLifecycleIdentity(source, current, taskFile, taskFile, add, IN_PLACE_IDENTITY_OPTIONS)`
      — same path passed twice (unlike the archive-move caller in step 1,
      this shape never moves the file) — where
      `source = loadBookkeepingJsonAtRef(startingPoint, taskFile, add)` (may
      reuse step (b)'s probed value rather than reading it twice) and
      `current` is the **live** current record for the active task
      directory.
   f. `validateBookkeepingJournalBundle` called once across
      `startingPoint..headOid` (existing, unmodified function) — confirms a
      well-formed session (or sessions) is present.
   g. One fresh `validateBookkeepingTaskDirectory(taskDir, {archived: false, ...})`
      sweep at live head (the same full per-file check Change A's direct path
      runs) — exactly once, not once per historical checkpoint.
   h. `evidence.taskDirectories = [taskDir]` (mirrors the archive-move path's
      own assignment — a first draft of Change A omitted the equivalent for
      the direct path; don't repeat that here),
      `evidence.completionSubtype = 'active-task-review-successor'`.

   **Do not** implement a step that calls `validateBookkeepingTaskDirectory`
   or any live-filesystem-reading loader against anything other than true
   live head. Every read against `startingPoint` or earlier must go through
   `loadBookkeepingJsonAtRef` / `bookkeepingChangedEntries` (git-backed).

   **Gate:** AC2 (recovers via the new subtype, starting point resolves to
   before the single touch), AC3 (starting point resolves to before the
   *older* of two touches, both journal sessions confirmed present), **AC3b
   — task created and started inside the search window still recovers**
   (starting point resolves to after `task.py start`, never to the creation
   or start commit; this was round-2 review's most serious finding — treat a
   green result here as load-bearing, not a formality), AC5 (all three
   ambiguous-active-task fixtures, including the unreadable-sibling case,
   fail closed immediately with no history walk), AC6 (no anchor within
   bound fails closed with the direct diagnostic) all pass.

5. **Safety regression sweep (AC4).** Add the fixtures: range touching a
   second active task, range touching the archive, merge commit inside the
   range, and (new in this draft) a forbidden-path mutation followed by a
   later commit in the same range that reverts it — confirm the last one
   still blocks, proving step 4d's scope check is genuinely per-commit and
   not evadable by a net-zero diff.

6. **Change C** — update `.agents/skills/sd-finish-work/SKILL.md` and its
   template mirror: new paragraph under Step 7's completion-mode section
   documenting `active-task-review-successor`, its precondition (exactly one
   `in_progress`/`review` task, no archive this session), and its limits (one
   bounded range; a merge commit anywhere in it, or bookkeeping history older
   than the search bound, still fails by design).

   **Gate:** `make sync` then `git diff --exit-code` on both
   `templates/scripts/sd-ai-command-pack-review-preflight.mjs` /
   `scripts/sd-ai-command-pack-review-preflight.mjs` and the SKILL.md pair.

7. **Eligibility regression (AC8).** Add a `tests/test_pr_eligibility.py` case
   feeding a receipt with `evidence.completionSubtype:
   "active-task-review-successor"` through `validate_finish_work_receipt`,
   asserting acceptance with **no code change** to
   `sd-ai-command-pack-pr-eligibility.py`. If this test requires touching
   that file to pass, stop — that means R4 was wrong and `design.md` needs to
   be revisited before continuing, not patched around inline.

## Validation

Syntax and targeted tests, in order:

```bash
node --check scripts/sd-ai-command-pack-review-preflight.mjs
python3 -m pytest tests/test_bookkeeping_validator.py -q
python3 -m pytest tests/test_pr_eligibility.py -q
```

Mirror parity:

```bash
make sync && git diff --exit-code
```

Full gate before finishing:

```bash
make check
```

Manual sanity check against this repo's own real history (informational, not
a CI test — mirrors 07-29's PR #273 replay): run the fixed validator against
this task's own branch once it has a real `in_progress`-task-touch + journal
commit, `--base == --head`, and confirm `evidence.completionSubtype:
"active-task-review-successor"` — a live demonstration that the shape this
task exists to unblock now works, distinct from the synthetic fixtures.

## Review gates

- Steps 1 and 3 (extractions/refactors) must show zero behavioral change on
  their own — review them before steps 2 and 4 land new capability on top.
- No new `--mode` value and no `sd-ai-command-pack-pr-eligibility.py` code
  change (R4) — either appearing in the diff is scope creep to flag.
- Reason-code *names* and the exact subtype string
  `"active-task-review-successor"` may be adjusted during implementation, but
  **`design.md` must be updated in the same change to match** — prd.md states
  these names are finalized in `design.md`, so implementation silently
  drifting from what `design.md` says would itself be a cross-artifact defect
  of the same kind this task's review process kept finding. The *invariants*
  the codes check (R1/Decision 4:
  status and branch byte-identical, `completedAt` stays null, field identity
  otherwise; R2: one unified range from the oldest qualifying touch within
  bound, per-commit scope check, active task discovered from head content
  only, no CLI contract change; R6: no merge commits, no unaudited workspace
  admission, scope check survives a mutate-then-revert) must not change
  without returning to `design.md`.
- **Reviewer checklist specific to this design's known failure modes** (each
  maps to a fixed review defect — confirm the fix, don't just confirm tests
  pass): (a) does the archive-move path's identity check still use
  `ARCHIVE_MOVE_IDENTITY_OPTIONS` with the two genuinely different paths,
  unchanged from `:1547-1574`'s original logic and locations? (b) does any
  code path call a filesystem-reading function
  (`validateBookkeepingTaskDirectory`, `loadTrellisTaskMetadataFile`,
  `safeJournalFiles`, etc.) with anything other than true live head as the
  implicit "current" state? (c) does step 4d still run *both* the aggregate
  path-count check and the per-commit category check, or did one of them get
  dropped, or did the per-commit check regress to a net
  `startingPoint..headOid` diff? (d) does the orchestration in step 3 still
  branch on an `attempted` flag, or was that removed as designed? (e) does
  step 4b's search actually probe the *parent's* status before accepting a
  candidate, or does it accept the first directory-touching commit
  unconditionally (the most serious round-2 finding — a fixture where the
  task was created/started inside the search window is the one that catches
  a regression here)?
- AC4's mutate-then-revert fixture and AC5's unreadable-sibling fixture are
  the load-bearing proof that this task does not weaken existing safety
  properties in ways review specifically found — do not let review proceed
  past a green test run without these two specifically present.

## Rollback

Single revert of the one commit restores today's validator and docs.
Receipts are ephemeral (deleted after housekeeping consumes them, per
SKILL.md Step 7) — no stored artifact depends on the new shape or subtype
surviving a rollback.

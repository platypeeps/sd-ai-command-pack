# Implement — branch-field finalization deadlock

## Sequencing against T-47

`07-29-scope-final-bundle-validator-to-delta` edits the same file. The two
changes do not overlap in region — T-47 rewrites the per-file finding scope for
planning mode, this task edits the completion-mode identity comparison at
`:1496-1504` — but they will conflict textually if branched from the same base
and merged independently.

**This task goes first.** It is smaller, fully specified, and unblocks a
finalization path that is failing today (`07-28-roll-out-stabilized-pack-release-to-fleet`
is `in_progress` with `branch: null` and will hit it). T-47 rebases on the
result. Confirm with the user before starting either.

## Order of work

Write the tests first — the design's central claim is that the current
validator rejects a legitimate bundle, and that claim is only worth anything if
a test demonstrates it before the fix exists.

- [x] **1. Red test: the deadlock case.**
      In `tests/test_bookkeeping_validator.py`, add
      `test_completion_bundle_allows_branch_recorded_during_archive`, modelled
      on `test_valid_completion_archive_and_journal_bundle` (`:613-662`).
      Differences from that template: build the active record with
      `branch=None` (`task_record` already types it `str | None`, `:45`), and
      in the archive step set `record["branch"] = "codex/completion-fixture"`
      alongside `status` and `completedAt`.
      Assert `returncode == 0`, `status == "valid"`,
      `reasonCodes == ["completion_bundle_valid"]`.
- [x] **2. Confirm it fails for the stated reason.**
      Run it against the unmodified validator. It must fail with
      `completion_archive_identity_changed`, not with a fixture error. A test
      that fails because the fixture is malformed proves nothing.

      ```bash
      bash scripts/sd-ai-command-pack-toolchain.sh run-python -- -m unittest tests.test_bookkeeping_validator.BookkeepingValidatorTests.test_completion_bundle_allows_branch_recorded_during_archive -v
      ```

- [x] **3. Guard tests: the cases that must stay blocked.**
      Add three more, all asserting `status == "invalid"` and
      `completion_archive_identity_changed` in `reasonCodes`:
      - `test_completion_bundle_rejects_branch_rewritten_during_archive` —
        active `branch="codex/a"`, archived `branch="codex/b"`.
      - `test_completion_bundle_rejects_branch_erased_during_archive` —
        active `branch="codex/a"`, archived `branch=None`.
      - `test_completion_bundle_rejects_unrelated_field_change_during_archive` —
        active and archived `branch="codex/a"`, but the archive step also
        rewrites `record["title"]`. This is AC 2's "any other field" clause,
        which the two branch cases do not cover, and which nothing in the
        suite covers today.

      These three pass against the current validator. They exist to fail if
      step 5 overreaches into an unconditional strip or a broader one, so run
      them before and after.
- [x] **3b. Guard test: the absent-key case stays blocked.**
      `test_completion_bundle_rejects_branch_added_to_keyless_record` — build
      the active record, then `del record["branch"]` before writing it; archive
      with `branch="codex/a"`. Assert `invalid` /
      `completion_archive_identity_changed`.

      This pins the `=== null` versus `== null` distinction. `== null` also
      matches `undefined`, so it is the exact "simplification" a later editor
      would reach for, and nothing else in the suite would catch it.
- [x] **4. Guard test: `branch: null` survives as an archived state (AC 4).**
      `test_completion_bundle_allows_null_branch_through_archive` — active and
      archived both `branch=None`, otherwise a pure move. Assert `valid` /
      `completion_bundle_valid`. The existing `:613` template uses a non-null
      branch on both sides, so the null-to-null path is untested today and AC 4
      would otherwise rest on an unexercised claim.
- [x] **5. Apply the validator fix to the template.**
      Edit `templates/scripts/sd-ai-command-pack-review-preflight.mjs` at
      `:1496-1504` per the shape in `design.md`. `templates/` is source of
      truth — do not touch the root copy by hand. The condition tests
      `sourceRecord.branch === null`, not `== null`: the absent-key case is
      deliberately excluded (Decision 2).
- [x] **5b. Apply the ordering instruction to the skill template.**
      Edit `templates/.agents/skills/sd-finish-work/SKILL.md` step 4
      (`:51-72` in the generated copy). Add the instruction that when the
      selected task's `branch` is null, it is recorded with `task.py set-branch`
      and committed **before** the finalization base is captured.

      Specify the mechanics — `task.py set-branch` (`task_store.py:728-748`)
      only rewrites `task.json`; it neither derives the branch nor commits:
      - **Source of the value:** `git symbolic-ref --quiet --short HEAD`.
      - **Failure behavior:** if that is empty (detached HEAD) or equals
        `base_branch`, stop and report rather than guessing. `:2549-2552`
        rejects `branch == base_branch` anyway, so a guess would only relocate
        the failure.
      - **The commit:** scoped to the task record alone —
        `git add <task-dir>/task.json` then a metadata commit. It must not
        sweep unrelated dirty paths.
      - **Terminology:** do not call it a "work commit". `trellis-finish-work`
        reserves that for Phase 3.4 code commits completed *before* invocation,
        whose hashes feed the journal (`:8`, `:69`). Name it a branch-metadata
        commit and say whether it belongs in the journal's commit list — it is
        part of the finalization, so it should be listed.

      Placement is exact and matters. "Capture the current commit as the
      finalization base" is the **first clause of `:51`**, before the task
      directories are identified and before the gate is invoked — so the new
      instruction must precede that clause, not merely precede the gate
      invocation at `:55-58`. Prepend it to step 4 or append it to step 3.

      Scoping constraints:
      - Condition it on the same trigger as the rest of the paragraph — "when
        an active task is selected for completion" (`:51-52`). It must not
        apply to the no-active-task successor path at `:68-72`, which
        deliberately keeps the base at the current head, nor to the planning
        finalization path at `:65-67`, which skips this boundary entirely.
      - Apply it to **every** task directory the gate is invoked for, not just
        the current one. Step 4 already takes repeated `--task-dir`, so the
        preparation is per-directory, matching the gate's own scope.
      - The stop clause at `:60-64` stays exactly as written. Its "do not
        attempt a repair by mutating the task" rule is what makes prevention
        necessary; weakening it would re-open the hole this task closes.

      **Late-surfaced tasks — state this explicitly.** The wrapper captures the
      base and runs the gate at step 4, but the inner skill discovers more
      archivable tasks afterwards: `trellis-finish-work` Step 1 offers "These N
      tasks look done — archive them too in this round? [y/N]". A task accepted
      at that prompt with `branch: null` was never prepared and never passed the
      gate, and preparing it then would commit a `task.json` change *after* base
      capture — reproducing the exact deadlock this task fixes.

      The instruction must therefore say what happens: a task surfaced after
      base capture whose `branch` is null is **declined for this round**, or the
      finalization is restarted with it in the initial `--task-dir` set. Do not
      leave this to operator improvisation; it is the same trap under a
      different entry point.

      This step is what delivers AC 3. Without it the validator change only
      helps a run that has already deviated from step 4.
- [x] **6. Regenerate the mirror.**

      ```bash
      make sync
      ```

      Then confirm **both** pairs are byte-identical:

      ```bash
      diff -q scripts/sd-ai-command-pack-review-preflight.mjs templates/scripts/sd-ai-command-pack-review-preflight.mjs && diff -q .agents/skills/sd-finish-work/SKILL.md templates/.agents/skills/sd-finish-work/SKILL.md
      ```

      Expected output: nothing (`diff -q` is silent when identical). There is
      no third copy — the skill exists only under `.agents/` and
      `templates/.agents/`; `.claude/skills/sd-finish-work/` does not exist.
- [x] **7. Green the new tests, and check nothing else moved.**

      ```bash
      bash scripts/sd-ai-command-pack-toolchain.sh run-python -- -m unittest tests.test_bookkeeping_validator -v
      ```

      All six new tests pass; the existing 12 completion-mode tests
      (`:613`, `:710`, `:795`, `:821`, `:849`, `:890`, `:931`, `:952`, `:981`,
      `:1007`, `:1036`, `:1066`) stay green.
- [x] **7b. Release payload gate — unplanned, recorded after the fact.**
      Both edited files are under `templates/**`, which
      `CONTRIBUTING.md:98-99` defines as shipped payload, so the change
      requires a same-PR `manifest.json` bump and a matching top `CHANGELOG.md`
      heading. This plan did not anticipate it. Precedent is explicit:
      `archive/2026-07/07-29-recover-retry-exhausted-fleet-lanes/implement.md:168-174`
      records the same discovery on 2026-07-29 after CI failed the gate.

      Bumped to `0.56.4` with a CHANGELOG entry, then `make generate` to refresh
      the version-bearing command surfaces and `make sync` to remirror them.
- [ ] **8. Full check.**

      ```bash
      make check
      ```

      **Currently blocked on one permitted finding, by design.** `make check`
      fails with exactly one failure — `test_live_surface_is_clean_and_json_is_versioned`
      — whose sole finding is `provenance.candidate-stale` on
      `docs/fleet/candidate-validation.json`: the ledger still pins pack
      `0.56.3` and the pre-change payload digest.
      `.trellis/spec/backend/manifest-and-filesystem.md:72-74` permits exactly
      this one finding at this path with relation `requires-release-evidence`,
      and names fleet validation as its resolution.

      The closer is `make release-prep`, which regenerates surfaces, refreshes
      the exact-payload ledger against the eight consumers in
      `docs/fleet/consumers.json` using disposable clones, and then runs
      `make check`. Run it **last**: `CONTRIBUTING.md:96-97` warns that later
      generation or sync changes invalidate the validator's evidence, so it
      belongs immediately before the PR push, and again if review feedback
      changes payload.

      `make sync` in step 6 already satisfies the `CONTRIBUTING.md:108-111`
      ordering requirement; re-run it if any task artifact changed after that
      point.

## Verification

The falsifiable check, named before the work: **step 2 must fail with
`completion_archive_identity_changed`, and step 7 must pass all six new tests
with the four guard cases still rejecting.** Any other combination is a
failure of the design, not a passing variant:

- Step 2 passes against the unmodified validator: the fixture does not
  reproduce the defect; the whole premise is wrong and the design needs
  rework before any code changes.
- Step 7's guard cases fail: the fix stripped `branch` unconditionally, or
  stripped more than `branch`, and Decision 2 was not implemented.
- Step 4's null-to-null case fails: the fix made a non-null archived branch
  mandatory and would invalidate existing archived records.

End-to-end confirmation comes free and unfaked: this task's own
`sd-finish-work` run exercises the fixed path, because the task is being
created with `branch: null` like every other. Under step 5b the run should
record and commit the branch before base capture and never trip `:700` at all.
If it finalizes without a hand-authored correction commit against an archived
artifact, AC 3 is met by observation. Record the receipt in the journal.

Note what that run does *not* prove: taking the prevention path means the
tolerance added in step 5 is never exercised end-to-end. The unit tests are the
only evidence for the recovery half, which is why step 2's red run matters —
it is the sole demonstration that the tolerance addresses a real rejection.

## Rollback

Revert the single commit. No migration, no state, no generated artifact beyond
the two mirrors, which `make sync` reproduces from the reverted templates.

## Out of scope

- `.trellis/scripts/common/task_store.py` — Trellis-owned; the upstream fix
  belongs in a parked task. It would also close the branch-fabrication gap
  parked in `design.md`, since the value would come from the checkout rather
  than from an operator's typing.
- Tying the recorded branch to `evidence.repository.branch` — declined in
  `design.md` because it would make a committed-content comparison depend on
  live git state.
- The pre-archive gate at `:700` itself. It keeps firing; step 5b stops runs
  from reaching it with a null branch.
- Groups 2 and 4 from T-47's classification, and the repo-maintenance mode.

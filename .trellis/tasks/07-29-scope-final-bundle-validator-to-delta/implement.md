# Implementation plan: scope the finalization bundle validator to the delta

Ordered checklist. Every shell command runs through the toolchain wrapper where
required by repo policy (`bash scripts/sd-ai-command-pack-toolchain.sh run -- <tool>`,
Python via `run-python --`); bare read-only `git` is fine. Edit
`templates/scripts/sd-ai-command-pack-review-preflight.mjs` and
`templates/.agents/skills/sd-finish-work/SKILL.md` only — root `scripts/**` and
`.agents/**` are generated mirrors refreshed by `make sync`.

## 0. Branch

- [x] `python3 ./.trellis/scripts/task.py start 07-29-scope-final-bundle-validator-to-delta`
- [x] Create branch `fix/scope-final-bundle-validator-to-delta`; `task.py set-branch`.

## 1. Regression tests first (red)

Add the tests from design.md §"Test plan" to `tests/test_bookkeeping_validator.py`
(and the two eligibility companions to `tests/test_pr_eligibility.py`), then run
them against the **unmodified** validator:

- [x] Behavior-changing tests — must FAIL pre-fix for the expected reason
      (wrong status or reason code, not a fixture error): Test 1 (clean-sibling
      valid + advisories, incl. eligibility companion on the advisories-bearing
      receipt), Test 2 (three group-1 producers), Test 4 (topology anchor rule,
      all three cases), Test 5 (maintenance receipt + eligibility companion),
      Test 10 (advisory cap / 64 KiB boundary).
- [x] Preservation tests — expected GREEN pre-fix and post-fix: Test 3
      (delta-defect blocks), Test 6 (workspace cited commit still blocks —
      descope boundary), Test 7 (recovery blocks archive mutation, task
      deletion, invalid lifecycle, malformed task-namespace path), Test 8
      (`bundle_scope_invalid` on `.trellis/audit/**`). Write them to assert
      `status: invalid` plus the scope-invalid reason code, which holds both
      before and after.
- [x] Validation: `bash scripts/sd-ai-command-pack-toolchain.sh run-python -- -m unittest tests.test_bookkeeping_validator -v 2>&1 | tail -30`
      — behavior-changing tests FAIL, preservation + existing tests pass.
      Quote the failure lines into the session notes.

  Red-run evidence (2026-07-30, `tests.test_bookkeeping_validator` +
  `tests.test_pr_eligibility` together): `Ran 93 tests` → `FAILED (failures=9)`,
  zero errors. The 9 failure entries collapse to exactly the five
  behavior-changing tests (subtests counted separately):
  `test_planning_bundle_scopes_untouched_sibling_defects_to_advisories`
  (`AssertionError: 1 != 0`),
  `test_planning_bundle_group_one_producers_delta_scope` ×3 (`1 != 0`),
  `test_planning_bundle_topology_findings_follow_anchor` — advises scenario
  `1 != 0`, both blocking scenarios `AssertionError: None != []` (advisories
  key absent pre-fix),
  `test_journal_only_recovery_accepts_repo_maintenance_commits` (`1 != 0`),
  `test_planning_bundle_caps_advisories_and_reports_dropped` (`1 != 0`).
  Preservation tests 3/6/7/8, both eligibility companions, and all existing
  tests passed.

## 2. Change A — delta scoping + advisories (green, part 1)

In `templates/scripts/sd-ai-command-pack-review-preflight.mjs`:

- [x] `runBookkeepingValidator`: add `advisories` array to the result document
      (after `findings`), an `addAdvisory(reasonCode, path, message)` sink with
      a new `MAX_BOOKKEEPING_ADVISORIES = 25` cap and the same 300/500
      path/message truncation, and pass both sinks down. Count entries dropped
      over the cap and record `evidence.advisoriesDropped` when the count is
      nonzero — truncation must be visible, not silent.
- [x] `validateBookkeepingTaskDirectory` family: accept `deltaPaths`
      (`Set<string> | null`) via options; introduce
      `addScoped(reasonCode, path, message, anchorPath = path)` used at
      group-1 emission sites (default anchor) and topology emission sites
      (anchor = the validated directory's own file — two sites report the
      neighbor's path, design.md §Group 4). Groups 2–3 keep raw `add`.
- [x] `validatePlanningBundle` and `validateCompletionBundle`: build the
      changed-path set from the bundle entries and pass it as `deltaPaths`.
      `pre-archive` passes `null`.
- [x] `printBookkeepingResult`: print `ADVISORY` lines, advisory count, and
      the dropped-over-cap count when `evidence.advisoriesDropped` is present.
- [x] `make sync` before running any test in this step and the next —
      the tests copy and execute the **root mirror**
      (`tests/test_bookkeeping_validator.py:30` copies
      `scripts/sd-ai-command-pack-review-preflight.mjs`), so a green run
      without sync would exercise the unmodified validator.

## 3. Change B — recovery commit scope (green, part 2)

Still in the template validator, `validateJournalOnlyPlanningRecovery`:

- [x] Replace the per-commit task-only path rule with the five-way partition
      (archive → blocking; active task → current rules incl. per-commit
      lifecycle validation fed **only task-path entries**, D/R/C rejection,
      regular-blob check; malformed `.trellis/tasks/**` → blocking;
      `.trellis/workspace/**` → blocking, unchanged — root cause 3 descoped;
      repo → allowed including D/R/C, no per-path validation).
- [x] Reformulate `planning_recovery_task_change_missing`: fire only when the
      cited commits collectively change zero allowed paths (active-task or
      repo).
- [x] Validation (after `make sync` — see step 2's mirror note): full
      validator suite green —
      `... run-python -- -m unittest tests.test_bookkeeping_validator -v 2>&1 | tail -5`
      expecting `OK`; then `tests.test_pr_eligibility` likewise.

## 4. Change C — SKILL.md documentation

- [x] `templates/.agents/skills/sd-finish-work/SKILL.md`: base = last work
      commit (with the merge-base caveat), maintenance-branch planning flow,
      advisories paragraph (per design.md §Change C). **Rewrite the recovery
      paragraph around `:157`** — its "task-only work commits" / "verifies
      task-only scope" wording becomes false with change B; describe the
      widened scope (active-task + repo paths citable; archive, malformed
      task-namespace, and workspace paths still forbidden).
- [x] `make sync`; confirm `git status --porcelain` shows the two mirrors
      updated and nothing else unexpected.

## 5. PR #273 replay (manual AC 8)

- [x] `git worktree add <scratchpad>/replay-7fde6218 7fde6218`
- [x] Run the **fixed** validator from the working tree:
      `node scripts/sd-ai-command-pack-review-preflight.mjs final-bundle --mode planning --base 49b43afd --head 7fde6218 --repo <scratchpad>/replay-7fde6218 --json`
      (#273 was a planning branch; the original failing run used `--mode planning`)
- [x] Expected: `status: invalid`; `findings` contains the 2
      `bundle_scope_invalid` (`.trellis/audit/**`) and the journal-session
      finding, none of the previous 25 whole-directory codes; those 25 appear
      in `advisories`. Save the JSON to the scratchpad and summarize counts in
      the journal session.

  Replay evidence (2026-07-30): fixed validator returned `status: invalid`
  with exactly 3 findings (2 `bundle_scope_invalid`, 1
  `journal_session_missing`) and 5 advisories (`task_metadata_invalid`, five
  untouched sibling `task.json` files). The historical "25 whole-directory
  codes" figure predates the pristine-scaffold context exemption shipped in an
  interim release: the pre-fix validator embedded at 7fde6218 reports 28
  findings (20 `task_context_seed` + 5 `task_metadata_invalid` + the 3 above),
  while the pre-fix validator at today's origin/main reports 8 (the seed
  findings are exempt). Against that current baseline the fix demotes exactly
  the 5 remaining whole-directory defects to advisories and keeps every
  delta-anchored finding blocking — the designed transformation. JSONs saved
  to scratchpad (`pr273-replay.json`, `pr273-old-validator.json`,
  `pr273-main-validator.json`).
- [x] `git worktree remove <scratchpad>/replay-7fde6218`

## 6. Release prep

- [x] `templates/**` payload changed → bump `manifest.json` version + CHANGELOG
      entry, then `make release-prep` (includes `make check`, mirror parity,
      full test suite). Expect `Full check complete`, exit 0.

  Evidence (2026-07-30): first run failed twice — a stale docs-consistency pin
  (`tests/test_sdlc_commands.py:496` expected the pre-rewrite phrase "without
  retroactively applying"; updated to the new "does not retroactively apply")
  and an empty `description` in the follow-up task
  `07-30-recover-bookkeeping-repair-sessions/task.json` (filled). Re-run ended
  `==> Full check complete`, exit 0.

## 7. Ship

- [ ] Commit work (tests + validator + docs + release artifacts; mirrors via
      sync). Push branch.
- [ ] PR via `--body-file` (scratchpad), with the standing
      "Tooling/generated scope:" section listing every generated-mirror path.
- [ ] Copilot review loop to convergence; CI green.
- [ ] Finish-work: archive task + journal session (use
      `scripts/sd-ai-command-pack-record-session.py` with `--change`/`--test`,
      not bare `add_session.py`); push; receipt via
      `final-bundle --mode completion --base <last work commit> --head <HEAD> --json`;
      validated merge through
      `bash scripts/sd-ai-command-pack-housekeeping.sh --finish-work-receipt <path>`.

## Rollback points

- After step 1: tests are additive; revert the test commit to abandon.
- After steps 2–4: single revert of the validator/docs commit restores current
  behavior; mirrors re-synced by `make sync`.
- The replay worktree is disposable; no repo state depends on it.

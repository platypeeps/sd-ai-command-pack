# Journal - sdelmas (Part 6)

> Continuation from `journal-5.md` (archived at ~2000 lines)
> Started: 2026-07-29

---



## Session 251: Recover the 2026-07-29 finalization residue and plan the validator delta-scoping fix

**Date**: 2026-07-29
**Task**: Recover the 2026-07-29 finalization residue and plan the validator delta-scoping fix
**Branch**: `plan/workflow-instability-evidence`

### Summary

Replayed the two journal sessions lost to the manual merges of PRs #273 and #274, repaired the stale bookkeeping those merges left behind, and planned the validator defect that forced them. Two rounds of planning adversarial review resolved 18 concerns against the new task's PRD.

### Main Changes

- Replayed journal sessions 249 and 250 onto journal-5.md and corrected their index rows, restoring the session record the two manual merges skipped.
- Cleared a dangling branch reference and trimmed a generated root mirror out of relatedFiles on the review-learnings diagnostics task.
- Created 07-29-scope-final-bundle-validator-to-delta with full evidence, a four-group classification of the bookkeeping reason codes, and testable acceptance criteria.
- Recorded the 2026-07-29 finalization residue on the analyze-recurring-trellis-workflow-instability task, framing PR #273 and PR #274 as the asymmetric failures they were.
- Ran the planning adversarial review contract over two rounds across a host lane and the Codex CLI lane, dispositioning 18 concerns.


### Git Commits

| Hash | Message |
|------|---------|
| `35e74c17` | docs: plan bounded review-learnings diagnostics |
| `acc836dc` | chore: replay journal entries for sessions 249 and 250 |
| `f92221e5` | chore: clear the dangling branch reference on the replayed task |
| `1bb1bc92` | plan: scope the finalization bundle validator to the change delta |
| `7a5542a6` | docs: record the 2026-07-29 finalization residue on the analyze task |
| `d21afe83` | fix: match replayed session index rows to their journal entries |
| `5641f0eb` | plan: harden the validator-scoping PRD after adversarial review |
| `3ff2ff5f` | chore: list only the template source in the diagnostics task relatedFiles |

### Testing

- [OK] final-bundle --mode planning --base 5fc11c2f: status=valid, reasonCodes=['planning_bundle_valid'], findings=0
- [OK] CI on PR #275 head 3ff2ff5f: lint, security, CI scope, Release payload gate, and all three unittest matrix jobs green
- [NOTE] unittest (macos-latest, 3.13) failed once on a git-gc/copytree race in tests/install_test_support.py, then passed on rerun at the identical head with no code change

### Status

[OK] **Completed**

No task was archived this session. `07-28-analyze-recurring-trellis-workflow-instability` is still `planning` with one of two acceptance criteria met, and `07-29-scope-final-bundle-validator-to-delta` was created but not started.

### Next Steps

- Write `design.md` and `implement.md` for `07-29-scope-final-bundle-validator-to-delta`; its own notes require both before `task.py start`, and adversarial review round 2 left three questions for design to answer: the four-group reason-code classification, whether the non-blocking signal field is schema-1-additive or needs a coordinated version bump, and the maintenance-branch path allowlist.
- Fix the `git gc`/`copytree` race in `tests/install_test_support.py` that intermittently fails `unittest (macos-latest, 3.13)`; the template repo is copied while a detached post-push `gc --auto` prunes its loose-object fanout dirs.


## Session 252: Exempt untouched planning scaffolds from both review-preflight seed-row lanes (v0.56.2)

**Date**: 2026-07-29
**Task**: Exempt untouched planning scaffolds from both review-preflight seed-row lanes (v0.56.2)
**Branch**: `claude/trusting-turing-d2ec3f`

### Summary

task.py create seeds implement.jsonl/check.jsonl with a generated _example row, and both of the pack's own seed-row enforcement lanes failed on exactly that row, so creating a Trellis task put the repo into a failing gate state. Hit live in rwbp-coordinator during the v0.56.1 fleet rollout. Fixed entirely pack-side: .trellis/scripts/** is vendored Trellis runtime with no manifest.json entry, so the scaffold text is not the pack's to change. Exempted a non-archived planning task's untouched scaffold in checkTrellisTaskContextManifests (diff-scoped review gate) and validateBookkeepingTaskContexts (bookkeeping validator, task_context_seed). The predicate is shape-based, not value-based: a lone row parsing to a plain object whose only key is _example. Deliberately does not pin Trellis's _SEED_EXAMPLE string, which Trellis owns and revises across versions; pinning it would re-break task creation on the next Trellis upgrade with a worse recovery path. Two Codex adversarial-review rounds produced six concerns, all addressed. Round 2 caught that my own affected-population correction was wrong: _has_subagent_platform short-circuits on the first _SUBAGENT_CONFIG_DIRS match, so a .claude repo is seeded regardless of Codex dispatch mode. Spec contract recorded in adapter-guidelines.md with an exempt/fail matrix. Copilot found one real defect the change introduced, a doc claim that symlinked context files are skipped, true only of the diff-scoped gate; the bookkeeping validator reports task_context_invalid. Fixed and thread resolved. PR #276 green, no unresolved threads.

### Main Changes

- Detailed change bullets were not supplied; see the summary above.

### Git Commits

| Hash | Message |
|------|---------|
| `0ff54ffe` | (see git log) |
| `5ef0b8c9` | (see git log) |
| `2013ed46` | (see git log) |

### Testing

- Validation was not recorded for this session.

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 253: Add a fleet-controller recovery transition for retry-exhausted lanes

**Date**: 2026-07-29
**Task**: Add a fleet-controller recovery transition for retry-exhausted lanes
**Branch**: `chore/record-retry-exhausted-recovery-planning`

### Summary

Gave the fleet controller an explicit, evidence-gated recovery transition for terminal retry-exhausted lanes, bumped the campaign state schema to 2 with an automatic load-time migration, and published the change as release 0.56.3.

### Main Changes

- resume --recover-exhausted-consumer NAME --exhausted-action ID --release VERSION grants one operator-authorized attempt at the stage that exhausted, bounded to two recoveries per consumer and stage, validated against the campaign's own target release rather than the current manifest version.
- Campaign state schema bumped to version 2 with a read-only load-time migration: absent 'recoveries' becomes an empty list and untagged rows gain kind 'pack-blocker'. Recovery rows are now a tagged union on 'kind', validated per arm, and both idempotency lookups filter on kind so a pack-blocker recovery can never dereference an exhaustion row.
- Corrected the permanent-park wording in the shipped sd-fleet-refresh skill and its controller-recovery reference, regenerated the .agents and .claude mirrors, and made the repository's own controller contract kind-aware in two places.
- Released 0.56.3: the release payload gate defines shipped payload as all of templates/**, so the source-only skill edits required a same-PR manifest bump, CHANGELOG entry, regenerated version-bearing surfaces, and a refreshed exact-payload candidate ledger.


### Git Commits

| Hash | Message |
|------|---------|
| `c96df89b` | docs(task): record retry-exhausted lane recovery planning |
| `33df6776` | docs(task): resolve C-N-1 with a schema bump and load-time migration |
| `92b2af3d` | docs(task): abandon paused campaign and start recovery task |
| `212a38d9` | feat(fleet): recover retry-exhausted lanes through the controller |
| `4da788c1` | docs(task): mark C-N-1 addressed in the review ledger |
| `50693f5f` | chore(release): prepare 0.56.3 |
| `77a8cb68` | test(fleet): select the exhausted lane and action by consumer |
| `08f3e407` | docs(task): record that the version bump rides in the merge PR |

### Testing

- [OK] tests.test_fleet_controller: Ran 44 tests, OK
- [OK] PR #277 CI on 08f3e407: 8 checks pass, 2 skipping, Release payload gate pass
- [OK] full-fleet candidate validation at 0.56.3: all 8 consumers passed
- [NOTE] local make check reports 2 of 1367 failures, both caused by the untracked stale worktree .claude/worktrees/quizzical-newton-ac691f; both linters run clean on a worktree-free snapshot and CI is unaffected

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 254: A-038 (P0): pin the bookkeeping CI classifier against the PR base

**Date**: 2026-07-30
**Task**: A-038 (P0): pin the bookkeeping CI classifier against the PR base
**Branch**: `fix/pin-bookkeeping-ci-classifier-trust`

### Summary

Closed a branch-protection bypass in the bookkeeping CI fast lane. tests.yml read the classifier blob out of $BEFORE_SHA and executed it; on a pull_request synchronize event that sha is the PR's own previous head, so a PR author could push a tampered classifier, let concurrency cancel that commit's own run, then push a payload commit whose scope was decided by their own code. Added a pull_request-only blob-identity guard that requires the $BEFORE_SHA classifier blob to be identical to the base branch's before the blob is executed, anchored on github.event.pull_request.base.sha (not PROTECTED_REF, which is refs/pull/<n>/merge and therefore author content). Absent, unresolvable, and divergent bases all fail closed to mode: full with distinct reason codes.

### Main Changes

- Added the identity guard at .github/workflows/tests.yml:149-169, immediately before the git show that executes the classifier
- Added BASE_SHA: ${{ github.event.pull_request.base.sha }} at tests.yml:47 as the trusted anchor
- Kept an explicit non-empty check on BASE_SHA: git rev-parse ':path' with an empty prefix is a valid index lookup that exits 0, and unlike BEFORE_SHA there is no upstream 40-hex shape gate for it
- Split requirement 3 (evidenceRunId API resolution) out to 07-29-resolve-evidence-run-id-through-api; it is not on A-038's attack path and was underspecified
- No change to .github/scripts/check-ci-result.sh or bookkeeping_ci_scope.py was needed; requirement 4 is satisfied structurally because an identity failure routes through select_full


### Git Commits

| Hash | Message |
|------|---------|
| `a94957eb` | docs(task): split evidenceRunId validation out of A-038 hardening |
| `d95c23f3` | fix(ci): pin the bookkeeping classifier to the pull request base |
| `8d0f488a` | docs(task): correct the changelog step and drop personal paths |
| `a51abbec` | docs(task): record the AC1 rehearsal evidence |
| `4e4aaf07` | docs(task): close the push-path review gate with a measurement |
| `0b17d702` | docs(task): record the live negative control for the fast lane |
| `c3b6e7f8` | docs(task): tick the acceptance criteria with their evidence |

### Testing

- [OK] AC1 proven live, not by inspection: rehearsal PR #278 run 30515960389 job 90785786135 selected mode: full, reason: prior_classifier_not_base_identical on a synchronize event whose BEFORE_SHA was the tamper commit
- [OK] Live negative control on PR #279 head 4e4aaf07 (run 30535866807, job 90848907337) selected mode: bookkeeping, reason: verified_bookkeeping_successor, so the guard discriminates rather than always selecting full
- [PARTIAL] The push path is not observable before merge. Measured offline instead by executing the extracted guard block under EVENT_NAME=push with two positive controls proving the harness was live; the construction argument is recorded in implement.md step 10 with its scope limits stated
- [OK] make check exit 0 on the final head, re-run after each task-record edit and preceded by make sync per CONTRIBUTING.md:108-111, which regenerated nothing

### Status

[OK] **Completed**

### Next Steps

- After merge, confirm the first bookkeeping-only push to main reports mode: bookkeeping. A full with a prior_classifier_* reason means the guard leaked to the push path and the change must be reverted

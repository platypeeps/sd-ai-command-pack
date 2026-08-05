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


## Session 255: Resolve the branch-field deadlock between the finalization gates

**Date**: 2026-07-30
**Task**: Resolve the branch-field deadlock between the finalization gates
**Branch**: `fix/resolve-branch-field-finalization-deadlock`

### Summary

A completion-ready task whose task.json branch is null had no sanctioned exit from finish-work: the pre-archive gate rejected the null branch, but the documented repair landed inside the archive commit, which the completion-bundle gate then read as a changed field. Fixed both halves — step 4 now records a missing branch before capturing the finalization base, and the completion-bundle archive-identity comparison tolerates a null to non-null branch transition. Specs, acceptance criteria, and a new ordering contract test ship with it as 0.56.4.

### Main Changes

- Moved the branch preparation in sd-finish-work step 4 above the finalization base capture, so task.py set-branch and its scoped branch-metadata commit land before the archive range opens. The preparation is scoped to the completion path only; the planning finalization boundary and the no-active-task successor path skip it, and it stops rather than guessing on a detached HEAD or when the recorded value equals base_branch.
- Relaxed the completion-bundle archive-identity comparison in review-preflight.mjs to accept a null to non-null branch transition, using === null so an absent branch key stays distinct from an explicit null. This is the recovery half: a task that already reached finalization unprepared can still finalize.
- Documented both rules in the specs — the completion-mode archive-identity tolerance in quality-guidelines, and the branch preparation ordering, its detached-HEAD and base_branch stops, and the extended error matrix in the wrapper-preserving lifecycle chaining scenario in adapter-guidelines.
- Added tests/test_finish_work_branch_preparation.py, four assertions against both shipped copies of the skill. The ordering assertion compares string indices rather than presence, so moving the preparation below the base capture fails it; the others pin the stops, the skipped paths, and the refusal to repair a failed gate by mutating the task.
- Ticked all six acceptance criteria with evidence, prepared release 0.56.4 with a matching CHANGELOG heading and an all-pass fleet candidate ledger, and fixed implement.jsonl, which referenced a path outside the allowed roots and blocked make release-prep.


### Git Commits

| Hash | Message |
|------|---------|
| `ae832216` | plan: resolve the branch-field finalization deadlock |
| `d85e48ed` | fix: resolve the branch-field deadlock between the finalization gates |
| `02921b58` | docs(spec): record the branch preparation ordering and archive-identity rule |
| `f9543da3` | docs(task): tick the acceptance criteria with their evidence |
| `9425eb18` | chore(release): prepare 0.56.4 |
| `07952aee` | test(finish-work): pin the branch preparation ordering in both twins |

### Testing

- [OK] make check: EXIT=0, 1378 tests across shards, 0 FAIL, 0 ERROR; review preflight 0 failures, 1 advisory warning
- [OK] sd-check --json: status passed, exitCode 0, stateGuard passed with beforeDigest == afterDigest and changed: []
- [OK] tests/test_finish_work_branch_preparation.py standalone: Ran 4 tests in 0.002s, OK
- [OK] ordering assertion proven sensitive: real order prep<cap True (2651 < 4390); mutated order prep<cap False (4330 > 4277)
- [OK] pre-archive gate: schemaVersion 1, status valid, pre_archive_valid, exit 0
- [OK] PR #280 CI: all 7 executed checks pass including CI Result; Copilot review round 1 of 5 returned no comments and zero review threads

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 256: Silence the scope advisory once the PR body satisfies it

**Date**: 2026-07-30
**Task**: Silence the scope advisory once the PR body satisfies it
**Branch**: `fix/silence-satisfied-scope-advisory`

### Summary

Advisory mode of the tooling/generated PR-body scope check warned on every branch touching a tooling/generated file, returning before the PR body was ever consulted, so a correct PR body could not clear it. Split PR-body resolution into a state-token resolver, mapped enforcing mode over the tokens without behavior change, and gave advisory mode a three-way branch that is silent on a satisfying body. Bounded the preflight's advisory subprocess with a 10s timeout. Copilot review across three rounds surfaced two real defects, both fixed: the documented unknown:resolver_error token was never produced or mapped, and the docs claimed a satisfying body produces no output when the classifier still prints its info lines. Shipped as 0.56.5.

### Main Changes

- Detailed change bullets were not supplied; see the summary above.

### Git Commits

| Hash | Message |
|------|---------|
| `4937be42` | (see git log) |
| `dc92d8b5` | (see git log) |
| `55759506` | (see git log) |
| `d7ee985c` | (see git log) |
| `1f9ccedc` | (see git log) |

### Testing

- Validation was not recorded for this session.

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 257: Close out v0.56.5 delivery and archive the Trellis instability analysis

**Date**: 2026-07-30
**Task**: Close out v0.56.5 delivery and archive the Trellis instability analysis
**Branch**: `chore/archive-analyze-trellis-instability`

### Summary

Merged PR #281 (v0.56.5 scope advisory fix) through sd-housekeeping after recovering the finish-work receipt that was generated out of order. Cleaned two stray Claude worktrees and their branches, which had been contaminating the shipped-surface closure walk; PR #282 landed the durable fix so the walk now skips git-ignored paths. Archived 07-28-analyze-recurring-trellis-workflow-instability, whose six acceptance criteria were long satisfied but whose task.json still read status planning, orphaning its one remaining in-progress child by design.

### Main Changes

- Recovered the finish-work receipt for PR #281 after it was generated out of
  order, then merged through sd-housekeeping with the exact-head gate intact.
- Removed two stray Claude worktrees whose git-ignored trees were adding 113
  false findings to the shipped-surface closure walk.
- Archived 07-28-analyze-recurring-trellis-workflow-instability, which had met
  all six acceptance criteria but still recorded status planning.

### Git Commits

| Hash | Message |
|------|---------|
| `d15f0eb6` | chore(task): archive 07-28-analyze-recurring-trellis-workflow-instability |

### Testing

- `final-bundle --mode completion` reports invalid on this branch; the residual
  reason codes are recorded on PR #283 rather than silently cleared.
- PR #283 CI: unittest across three matrix jobs, lint, security, release payload
  gate, CI scope, and CI Result all pass on the archive commit.

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 258: Backlog grooming: priority raises and fleet rollout archive

**Date**: 2026-07-30
**Task**: Backlog grooming: priority raises and fleet rollout archive
**Branch**: `chore/archive-fleet-rollout-task`

### Summary

Reviewed all 65 unarchived Trellis tasks for priority and applicability. Raised 07-29-scope-final-bundle-validator-to-delta to P1 (three hand-merges bypassed the receipt gate), 07-28-consolidate-ci-fast-lane-trust-stack to P2 (owns the A-038 branch-protection bypass), and 07-24-simplify-review-shipping-composition to P1 (blocked a P1, priority inversion) — merged as PR #284 (e7cdb4fb). Archived 07-28-roll-out-stabilized-pack-release-to-fleet per maintainer direction: fleet rollouts are decided on demand, not tracked as standing work (PR #285). Diagnosed the macOS unittest failure on PR #284 as a shared-fixture shutil copy race in test_housekeeping_auto_merges_green_comment_clean_pr_then_cleans_up; rerun passed.

### Main Changes

- Raised three mispositioned task priorities in `.trellis/tasks/*/task.json` (PR #284, merge `e7cdb4fb`).
- Archived `07-28-roll-out-stabilized-pack-release-to-fleet` to `archive/2026-07/` per maintainer direction (PR #285).
- Left unselected review recommendations (demotes, PARKED markers, sequencing notes) unapplied by explicit choice.

### Git Commits

| Hash | Message |
|------|---------|
| `ae79f89b` | chore(task): raise priorities for three mispositioned backlog tasks |

### Testing

- Diff inspection: PR #284 touched exactly three files, one `"priority"` line each; JSON re-read confirmed P1/P2/P1.
- CI green on both heads after one macOS fixture-race rerun; Copilot reviews on #284 and #285 produced zero threads.

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 259: Allowlist shipped review.json in install audit (T-1, v0.56.6)

**Date**: 2026-07-30
**Task**: Allowlist shipped review.json in install audit (T-1, v0.56.6)
**Branch**: `fix/allowlist-review-json-install-audit`

### Summary

Implemented Trellis task 07-28-allowlist-review-json-install-audit: added .sd-ai-command-pack/review.json to LOCAL_ALLOWED_PACK_FILES in the install audit (template source + synced mirror), locked it with a fixture-backed test verified by mutation, bumped the pack to 0.56.6 with CHANGELOG entry per the release payload gate, and retargeted a stale archived-task reference in 07-29-scope-final-bundle-validator-to-delta/prd.md that blocked full-check repo-wide. Shipped as PR #286: CI fully green, Copilot review clean with zero threads.

### Main Changes

- Added `.sd-ai-command-pack/review.json` to `LOCAL_ALLOWED_PACK_FILES` in `templates/scripts/sd-ai-command-pack-install-audit.py` (source of truth) and synced the `scripts/` mirror via `make sync` (audit finding A-056).
- Added `test_install_audit_allows_repository_owned_review_configuration` in `tests/test_install_audit.py`: installs the pack into a consumer fixture, writes the documented review.json, asserts install-audit exits 0 without flagging the file.
- Bumped `manifest.json` to 0.56.6 with a CHANGELOG entry; `make release-prep` regenerated the command catalogs, dogfood install receipt, and fleet candidate ledger.
- Retargeted the `07-28-analyze-recurring-trellis-workflow-instability` reference in `.trellis/tasks/07-29-scope-final-bundle-validator-to-delta/prd.md` to its archive path — pre-existing debt from PR #283 that failed the repo-wide documentation path check on every full-check run.

### Git Commits

| Hash | Message |
|------|---------|
| `46ee5de8` | fix(audit): allowlist the shipped review.json in the install audit |
| `6750f8de` | chore(task): activate allowlist task and retarget archived prd reference |
| `29cfcbb1` | chore(release): prepare 0.56.6 |

### Testing

- `python -m unittest tests.test_install_audit -k review_configuration -k check_configuration` — Ran 2 tests, OK.
- Mutation check: removed the allowlist entry, new test FAILED (failures=1); restored via `make sync`.
- `make release-prep` — "Full check complete", exit 0.
- PR #286 CI: unittest on ubuntu 3.10/3.13 and macOS 3.13, lint, security, release payload gate — all SUCCESS; Copilot review COMMENTED with zero threads.

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 260: Scope final-bundle validator to the change delta (0.56.7, PR #287)

**Date**: 2026-07-30
**Task**: Scope final-bundle validator to the change delta (0.56.7, PR #287)
**Branch**: `fix/scope-final-bundle-validator-to-delta`

### Summary

Implemented Trellis task 07-29-scope-final-bundle-validator-to-delta: findings anchored to task files outside the bundle delta demote to non-blocking advisories (capped at 25, advisoriesDropped evidence); journal-only planning recovery partitions cited-commit paths five ways with ordinary repository paths allowed as maintenance work; sd-finish-work SKILL.md documents the captured-base rule, maintenance-branch flow, and advisories contract. PR #273 replay: 3 blocking findings + 5 advisories against today's baseline (the historical 25-advisory figure predates the pristine-scaffold exemption). Copilot round 1 found a real early-return bypass (delta-anchored prd/context checks skipped when a demoted sibling task.json fails to load), fixed with regression test; rounds 2-3 clean, CI green. Released 0.56.7.

### Main Changes

- Delta scoping + advisories contract in the bookkeeping validator (templates + root mirror): addScoped routing for group-1/topology sites, advisories array with cap and truncation, printBookkeepingResult advisory output
- Five-way cited-commit path partition in journal-only planning recovery; planning_recovery_task_change_missing fires only when zero allowed paths change
- Closed early-return bypass: prd/task-text/context checks run even when sibling task.json load or parse fails; pristine-scaffold exemption requires a readable planning record
- sd-finish-work SKILL.md: captured-base rule, maintenance-branch planning flow, advisories paragraph; release 0.56.7 with regenerated payload digest


### Git Commits

| Hash | Message |
|------|---------|
| `c24d3e6d` | fix: scope final-bundle validator findings to the change delta |
| `1d93d605` | fix: keep delta-anchored checks blocking when sibling task.json is broken |
| `781c887a` | chore(release): refresh candidate validation digest for updated payload |

### Testing

- [OK] tests.test_bookkeeping_validator + tests.test_pr_eligibility: Ran 93 tests, OK (red-first: 9 expected failures pre-fix)
- [OK] make release-prep: Full check complete, exit 0
- [OK] PR #273 replay 49b43afd..7fde6218: status invalid, 3 findings (2 bundle_scope_invalid, 1 journal_session_missing), 5 advisories
- [OK] PR #287 CI: all checks pass; Copilot review converged round 3 with zero unresolved threads

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 261: Repair follow-up task PRD reference after 07-29 archive

**Date**: 2026-07-30
**Task**: Repair follow-up task PRD reference after 07-29 archive
**Branch**: `fix/scope-final-bundle-validator-to-delta`

### Summary

The archive of 07-29-scope-final-bundle-validator-to-delta moved its prd.md under .trellis/tasks/archive/2026-07/, leaving a dangling path reference in the follow-up task 07-30-recover-bookkeeping-repair-sessions PRD that failed the CI scope reference check on PR #287. Retargeted the reference to the archive path.

### Main Changes

- Pointed the 07-30-recover-bookkeeping-repair-sessions PRD root-cause reference at the archived 07-29 task path


### Git Commits

| Hash | Message |
|------|---------|
| `fca7ef70` | chore(task): point follow-up PRD at archived 07-29 task path |

### Testing

- [OK] repo-wide grep for the old active path: only historical journal prose remains

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 262: Ship composition Phase A: Stage 2 repoint and Stage 2b

**Date**: 2026-07-30
**Task**: Ship composition Phase A: Stage 2 repoint and Stage 2b
**Branch**: `fix/simplify-review-shipping-composition`

### Summary

Repointed sd-ship Stage 2 to the routed sd-review scope=pr loop, added the composite-owned Stage 2b lifecycle step, moved the until=review stop-point, removed defer-finish-work, and drove make release-prep green for 0.56.8.

### Main Changes

- Phase A of simplify-review-shipping-composition: repointed sd-ship Stage 2 from sd-review-pr to the routed sd-review scope=pr loop, added the composite-owned Stage 2b lifecycle step (one PR-scoped review-learnings pass for until=review and until=merge; finish-work bound to the reviewed head for until=review only), moved the until=review stop-point after Stage 2b, and removed the defer-finish-work delegation mode. Updated the authored command source .github/command-sources/sd-ship.md (adapters are generated), sd-ship SKILL, sd-create-pr SKILL, the usage guide's recommended review loop and ship sections, four generated ship adapters, manifest 0.56.8, and CHANGELOG. Restored the guide's explicit remote-reviewer env-var paragraph after a wildcard rewrite broke the shipped-env-vars drift gate.


### Git Commits

(No commits - planning session)

### Testing

- [OK] make release-prep green end to end (prepare-release 0.56.8 validation, full test suite, lint, audit, full-check); targeted reruns of the six previously failing tests (gemini toml shape, two pack-drift gates, reviewer-configurable, round-limit, shipped-env-vars) all pass; grep confirms zero sd-review-pr or defer-finish-work references remain under the sd-ship skill.

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 263: PR 288 review loop converged for ship composition Phase A

**Date**: 2026-07-30
**Task**: PR 288 review loop converged for ship composition Phase A
**Branch**: `fix/simplify-review-shipping-composition`

### Summary

Converged the PR 288 Copilot review loop for the sd-ship Stage 2 repoint and Stage 2b lifecycle step: fixed the router-owned reviewer-request wording the round-1 comment flagged, refreshed the candidate ledger, and verified CI green with a clean round-2 review.

### Main Changes

- Reworded the recommended review loop's reviewer-request rule in the usage guide to say the router issues the configured request (default @copilot alias) and manual reviewer or backend requests stay outside the loop, resolving the Copilot round-1 ambiguity with the configuration paragraph.
- Refreshed docs/fleet/candidate-validation.json after the doc clarification changed the release payload digest.


### Git Commits

| Hash | Message |
|------|---------|
| `e8d10910` | docs: clarify router-owned reviewer requests in recommended loop |
| `b2e8d830` | chore(release): refresh candidate ledger for doc clarification |

### Testing

- [OK] make release-prep green after the clarification (==> Full check complete, exit 0)
- [OK] PR 288 CI green on head b2e8d830 (CI Result, CI scope, Release payload gate, lint, security all pass); Copilot round-2 review returned zero new comments and the round-1 thread is resolved

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 264: Ship Phase B of simplify-review-shipping-composition (0.57.0)

**Date**: 2026-07-30
**Task**: Ship Phase B of simplify-review-shipping-composition (0.57.0)
**Branch**: `fix/simplify-review-shipping-composition`

### Summary

Implemented Phase B of 07-24-simplify-review-shipping-composition: R1 narrowed sd-create-pr to publish-only, R3+R4+R5 replaced the public sd-watch-pr command with sd-ship's internal read-only watch coordinator and swept all references, R2 moved finish-work finalization into Stage 2b for both until= modes with Stage 4 consuming the retained or validator-recomputed receipt, and R6 removed the Stage 1 orchestration context. Prepared release 0.57.0 with CHANGELOG entries and aligned all test pins, including a new coordinator zero-mutation test.

### Main Changes

- sd-create-pr publish-only in every invocation; Step 6 names sd-review scope=pr or sd-ship instead of running review
- sd-watch-pr removed as a public command; Stage 3 runs the internal read-only watch coordinator (20s poll, timeout-minutes x 3 ceiling, four outcomes, only settled-green continues)
- Stage 2b runs the SD finish-work flow exactly once for both until=review and until=merge, retains the exact-head receipt, and re-enters Stage 2 once for a finalization successor head
- Stage 4 runs zero finish-work flow invocations: retained receipt on unchanged head, direct read-only final-bundle validator recomputation on moved head; eligibility recheck stays the double-run guard
- Stage 1 orchestration context (caller/stage/return-after) removed from sd-create-pr and sd-ship; trusted sd-work-backlog and sd-fleet-refresh contexts unchanged
- Release prep 0.57.0: manifest bump, CHANGELOG, catalog regeneration, candidate-ledger refresh


### Git Commits

| Hash | Message |
|------|---------|
| `13661913` | refactor(create-pr): narrow sd-create-pr to publish-or-reuse only (R1) |
| `71d12d1f` | feat(ship): replace sd-watch-pr with internal read-only watch coordinator |
| `190f2585` | feat(ship): move finish-work finalization into Stage 2b for both until modes |
| `1f50f3b9` | refactor(ship): remove the Stage 1 orchestration context |
| `0812a4b0` | chore(release): prepare 0.57.0 |

### Testing

- [OK] make release-prep green (Full check complete, 0 failures)
- [OK] unittest suites test_sdlc_commands, test_generated_parity, test_install_core, test_script_lib, test_retired_targets, test_surface_generation all OK
- [OK] shipped-surface closure: clean; 67 changed path(s), 1092 affected node(s)
- [OK] route grep for sd-review-pr across ship/create-pr/work-backlog/fix-ci/status.py: 0 hits; fleet carve-out grep: 1 hit (parked with owner)

### Status

[OK] **Completed**

### Next Steps

- Open PR for Phase B, run the Copilot review loop, then validated housekeeping merge with the journal-only planning receipt (task stays open pending cutover evidence)


## Session 265: Merge Phase B PR #289 and close simplify-review-shipping-composition

**Date**: 2026-07-30
**Task**: Merge Phase B PR #289 and close simplify-review-shipping-composition
**Branch**: `chore/archive-simplify-review-shipping-composition`

### Summary

Converged the PR #289 review loop (Copilot round 1 returned zero findings, all CI checks green), produced the planning-mode journal-only-recovery receipt for the febd6707 finalization delta, and merged 0.57.0 through the validated housekeeping flow. With both phases shipped, ticked the eight acceptance criteria and archived task 07-24-simplify-review-shipping-composition.

### Main Changes

- Merged PR #289 (sd-create-pr publish-only, sd-watch-pr removal behind the internal watch coordinator, Stage 2b finalization ownership, release 0.57.0) into main via scripts/sd-ai-command-pack-housekeeping.sh with a planning-mode final-bundle receipt
- Marked all eight acceptance criteria complete in the task prd and archived 07-24-simplify-review-shipping-composition to .trellis/tasks/archive/2026-07/


### Git Commits

| Hash | Message |
|------|---------|
| `d6de646d7a7b` | Merge pull request #289 from platypeeps/fix/simplify-review-shipping-composition |

### Testing

- [OK] Planning-mode final-bundle validator returned planning_bundle_valid (journal-only-recovery) for 0812a4b0..febd6707 before the merge
- [OK] PR #289 CI checks lint, security, and all three unittest matrix jobs passed; Copilot reviewed 69/69 files with zero comments

### Status

[OK] **Completed**

### Next Steps

- Survey the backlog and start the next item


## Session 266: Regenerate frozen source-only fleet-refresh adapters

**Date**: 2026-07-31
**Task**: Regenerate frozen source-only fleet-refresh adapters
**Branch**: `fix/regenerate-fleet-refresh-adapters`

### Summary

Fixed audit finding A-044: four dev-tree fleet-refresh adapters frozen at 0.20.0 because source-only commands have no consumer manifest entries, so neither dogfood self-install nor the manifest-driven twin gate ever touched them. Added registry helper source_only_adapter_twins() as single source of truth for the dev-tree footprint, taught the command-surface generator to emit those copies, added a registry-driven parity test plus helper unit tests, and regenerated the four adapters byte-identical to their template twins. Shipped as PR #293 (clean Copilot round 1, CI green).

### Main Changes

- installer/registry.py: added source_only_adapter_twins() anchor-gated helper + __all__ export
- .github/scripts/generate-command-surfaces.py: emit dev-tree adapters for source-only commands via generate_source_only_dev_adapters()
- tests/test_pack_drift.py: registry-driven parity test for source-only dev adapters
- tests/test_help_command.py: unit tests for source_only_adapter_twins() anchor gating and no-pattern rejection
- Regenerated .claude/.gemini/.github/.opencode fleet-refresh adapters to current template content


### Git Commits

| Hash | Message |
|------|---------|
| `bd98b831` | fix: regenerate frozen source-only fleet-refresh adapters |

### Testing

- [OK] make release-prep exit 0 (installer 100% coverage gate incl new helper)
- [OK] generator --check 94/94; twin cmp identical x4; manifest.json byte-unchanged
- [OK] desync bite proof: parity test FAILED on desynced adapter, OK after restore

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 267: Cover sd-check read-only git guard (A-049)

**Date**: 2026-07-31
**Task**: Cover sd-check read-only git guard (A-049)
**Branch**: `fix/test-sd-check-read-only-git-guard`

### Summary

Added invalid-config subtests executing the READ_ONLY_GIT_SUBCOMMANDS guard and inline-eval branches in sd-check; raised check.py coverage floor 70 to 74 with parity test sync; shipped via PR #294.

### Main Changes

- tests/test_check.py: perl-inline, ruby-inline, git-push, git-commit invalid-config entries
- .github/scripts/check-shipped-script-coverage.sh + tests/test_generated_parity.py: check.py floor 70 to 74


### Git Commits

| Hash | Message |
|------|---------|
| `1c8992a9` | test: cover the sd-check read-only git guard |

### Testing

- [OK] make release-prep exit 0; coverage 75% measured

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 268: Preserve the aside lock when work-loop restore fails (A-092)

**Date**: 2026-07-31
**Task**: Preserve the aside lock when work-loop restore fails (A-092)
**Branch**: `fix/work-loop-lock-restore`

### Summary

Fixed _recover_locked_path deleting the only copy of a live foreign lock when the no-clobber restore fails: aside file now survives with its path named in the error, and an O_CREAT|O_EXCL rewrite fallback restores the canonical path where hard links are unavailable. Four new tests; 0.57.1; shipped via PR #295.

### Main Changes

- scripts+templates work-loop.py: A+C restore with preserved aside and fallback-error reporting
- tests/test_work_loop.py: four recovery tests plus errno assertion


### Git Commits

| Hash | Message |
|------|---------|
| `9ef65a56` | fix(work-loop): preserve the aside lock file when restore fails |
| `ef0ec529` | fix(work-loop): report the fallback error when lock restore fails |

### Testing

- [OK] unittest -k recover -k lock: 23 OK; make release-prep exit 0 twice

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 269: Harden KB prune with trailing provenance marker (PR #296)

**Date**: 2026-07-31
**Task**: Harden KB prune with trailing provenance marker (PR #296)
**Branch**: `fix/harden-kb-prune-marker-check`

### Summary

Fixed audit A-070 residual: KB prune deleted any plain file in a managed category folder without ownership proof, endangering user files behind a vault root symlink. Copies now end with a trailing SD-AI-COMMAND-PACK:KB-COPY marker; the prune requires the file to end with that marker (substring quoting is safe), currency checks compare marked payload with a size pre-check, pre-marker copies adopt on next refresh. Round-1 Copilot findings (marker-anywhere too permissive; size pre-check) complied; round 2 clean. 40/40 tests, release-prep green, version 0.57.2.

### Main Changes

- Detailed change bullets were not supplied; see the summary above.

### Git Commits

| Hash | Message |
|------|---------|
| `bc6611b9` | (see git log) |
| `24c3b612` | (see git log) |

### Testing

- Validation was not recorded for this session.

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 270: Document remaining shipped scripts and gate doc coverage (A-115, PR #297)

**Date**: 2026-07-31
**Task**: Document remaining shipped scripts and gate doc coverage (A-115, PR #297)
**Branch**: `fix/document-remaining-shipped-scripts`

### Summary

Classified all 26 shipped script targets (23 public documented, pr-eligibility newly documented, review-local.py and lib allowlisted internal), narrowed CONTRIBUTING stable-surface promise, added colon-anchored doc-coverage gate to make test and CI with allowlist/guide-entry conflict detection, corrected pr-eligibility exit-code docs. Four Copilot rounds converged; round 4 approved.

### Main Changes

- Detailed change bullets were not supplied; see the summary above.

### Git Commits

| Hash | Message |
|------|---------|
| `6efe757c` | (see git log) |
| `14d6c75c` | (see git log) |
| `a595f670` | (see git log) |
| `dfef55df` | (see git log) |

### Testing

- Validation was not recorded for this session.

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 271: Declare and pin build dependency toolchain (A-108/109/110)

**Date**: 2026-07-31
**Task**: Declare and pin build dependency toolchain (A-108/109/110)
**Branch**: `fix/declare-pin-build-dependencies`

### Summary

Single-sourced the Python floor in pyproject.toml [project].requires-python with a guard test, raised and CI-pinned the Node floor to 22.0.0, and compiled both requirements files into hash-pinned closures enforced with --require-hashes at all four install sites. PR #298: two Copilot rounds; round-1 findings (regex TOML parse brittleness, setuptools auto-discovery leak) verified and fixed.

### Main Changes

- pyproject.toml: added [project] with requires-python ">=3.10", [build-system], [tool.setuptools] packages = [] (auto-discovery off), [tool.uv] package = false; dropped hand-written ruff target-version (now inferred); deleted stray uv.lock.
- tests/test_python_floor.py (new): asserts CI matrix floor leg and toolchain probe against the declared floor; parses via tomllib with pinned-tomli fallback on 3.10.
- Review-preflight MIN_NODE_VERSION raised 16.9.0 to 22.0.0 in both script copies; tests.yml ci-scope and lint jobs pin SHA-pinned actions/setup-node at node-version 22.
- requirements-dev.txt / requirements-security.txt recompiled as universal hash-pinned closures; --require-hashes enforced at three CI install sites plus the Makefile setup target; CONTRIBUTING.md documents the bump/recompile workflow.
- Suites realigned: parity expects the --require-hashes install line, bookkeeping workflow-contract tests locate ci-scope steps by id, manifest bumped to 0.59.0 with CHANGELOG entry.

### Git Commits

| Hash | Message |
|------|---------|
| `05ab4f61` | fix: parse floor via tomllib/tomli and disable package auto-discovery |
| `26ae2976` | test: align suites with pinned toolchain and refresh release evidence |
| `bf2e5aae` | feat: install Python dependencies from hash-pinned compiled requirements |
| `49d633af` | feat: raise review-preflight Node floor to 22 and pin CI's Node version |
| `af8f96eb` | feat: declare requires-python and check floor copies against it |

### Testing

- `make release-prep` exit 0 on head `26ae2976` (full battery: coverage-gated tests, ruff, mypy, node checks, bandit, zizmor, full-check).
- Round-1 fix head `05ab4f61`: ruff clean; tests.test_python_floor and tests.test_generated_parity OK.
- Hash tamper check: zeroed hashes rejected ("THESE PACKAGES DO NOT MATCH THE HASHES"); --ignore-installed dry-runs resolve cleanly; recompile fixed point (run 3 = run 2).
- PR #298 CI Result SUCCESS on `05ab4f61`; Copilot round 2 generated no new comments; sd-check attempt it8-pr298-sdcheck2 status passed.

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 272: Align status and housekeeping selector contracts to F/T

**Date**: 2026-07-31
**Task**: Align status and housekeeping selector contracts to F/T
**Branch**: `fix/align-status-selector-contract`

### Summary

Closed review finding 1.1.1: removed retired F/T/R selector wording from sd-status and sd-housekeeping skills, added generic non-F/T selector rejection covering stale-snapshot input, and added an allowlist drift test over the shipped surface. Version 0.59.1. PR #299, 2 Copilot rounds (round-1 comment-clarity finding complied), CI green after one unrelated macOS housekeeping-fixture flake.

### Main Changes

- `templates/.agents/skills/sd-status/SKILL.md:140`: report-local selector wording `F/T/R` → `F/T`, plus a new generic rejection sentence — any selector that is not an `F-*` or `T-*` row of the current snapshot is unresolved input with no action taken (covers both retired-prefix and stale-snapshot requests without naming the removed category).
- `templates/.agents/skills/sd-housekeeping/SKILL.md:118`: delegated-result contract relays `F/T selectors` (was `F/T/R selectors`).
- `tests/test_selector_contract_drift.py` (new): allowlist drift guard over shipped roots (`templates/`, `docs/`, generated adapters and root mirrors, existence-guarded) for retired `F/T/R`, `R-*`, `R-<n>`, and standalone `Roadmap` heading wording; `.trellis/` out of scope by construction. Round-1 Copilot feedback tightened the pattern comment.
- Mirrors regenerated via `make sync`; release bookkeeping for 0.59.1 (`manifest.json`, dogfood manifest, `CHANGELOG.md`, command-catalog restamp, `docs/fleet/candidate-validation.json`).
- No change to `scripts/sd-ai-command-pack-status.py` — `select_items` already emits only `prefix="T"`/`prefix="F"` (AC1 verified, not built).

### Git Commits

| Hash | Message |
|------|---------|
| `b690b9eb` | fix: align status and housekeeping selector contracts to F/T |
| `1ac22f79` | docs: clarify which Roadmap wording the drift guard bans |

### Testing

- `make release-prep` exit 0 on b690b9eb (surface generation, self-sync, payload version gate 0.59.0 → 0.59.1, fleet candidate validation, full check).
- `tests/test_selector_contract_drift.py` 2 tests OK (correctly failed on the stale mirror before `make sync`); `tests/test_status.py` 47 tests OK; ruff clean on 1ac22f79.
- Validation greps: retired wording 0 hits across live surfaces; `.trellis/` history paths unchanged; no diff to `scripts/sd-ai-command-pack-status.py`.
- PR #299 CI SUCCESS on 1ac22f79 (round-1 run had one unrelated macOS housekeeping-fixture copytree flake; passed on retry). Copilot round 2: "reviewed 13 out of 13 changed files … generated no new comments"; 0 unresolved threads. sd-check `check.status` passed (attempt it9-sdcheck-1ac22f79-a).

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 273: Retire transitional review surfaces: removal version and catalog status

**Date**: 2026-07-31
**Task**: Retire transitional review surfaces: removal version and catalog status
**Branch**: `fix/retire-transitional-review-surfaces`

### Summary

Pre-registered removed_version=0.62.0 for sd-full-check, sd-review-local, sd-review-pr; added transitional catalog status to sd-help; PR #300 reviewed and greenlit.

### Main Changes

- Pre-registered RetiredCommandSurface rows with removed_version=0.62.0 for the three remaining transitional surfaces (installer/registry.py)
- Added transitional/superseded-by status to the sd-help command catalog so it stops recommending the legacy commands as live
- Added CHANGELOG deprecation note per CONTRIBUTING.md policy
- Fixed Copilot review finding: renamed shadowed variable in generate-command-surfaces.py


### Git Commits

| Hash | Message |
|------|---------|
| `a1ae4bc5` | chore(task): plan retirement schedule for transitional review surfaces |
| `afdcd54a` | feat: name a removal version for the transitional review surfaces |
| `7cf1cbba` | fix: address review feedback round 1 |

### Testing

- [OK] sd-check gate: 8/8 passed
- [OK] make check: Full check complete, exit 0
- [OK] Copilot remote review: 2 rounds — round 1 found variable shadowing (fixed), round 2 clean with no new comments

### Status

[OK] **Completed**

### Next Steps

- Push finish-work commits and hand off to sd-housekeeping to merge PR #300


## Session 274: PR #291 review loop: ship-receipt validation hardening (rounds 4-9)

**Date**: 2026-07-31
**Task**: PR #291 review loop: ship-receipt validation hardening (rounds 4-9)
**Branch**: `fix/add-ship-result-receipt`

### Summary

Gave sd-ship's merge handoff a schema-v1 receipt the work loop validates independently (recomputing outcome against git/PR instead of trusting the payload), then drove PR #291 through 9 rounds of Copilot review to a clean pass: fixed PR-URL and task compaction-limit mismatches against transition_state's stable-field normalization, a state-mutation-ordering bug, bool coercion accepted as pr_number and schemaVersion, a blank pr_url silently bypassing the evidence contradiction check, and documented the receipt's prUrl canonical-form requirement. Round 9 returned 0 new and 0 suppressed comments.

### Main Changes

- Detailed change bullets were not supplied; see the summary above.

### Git Commits

| Hash | Message |
|------|---------|
| `01ca5adc` | (see git log) |
| `9e65cfb9` | (see git log) |
| `e7ab9c8c` | (see git log) |
| `85260377` | (see git log) |
| `b282daf9` | (see git log) |
| `3c86d72b` | (see git log) |
| `b3a43760` | (see git log) |
| `0cb8f666` | (see git log) |
| `4d656f50` | (see git log) |
| `76bdd98c` | (see git log) |
| `7ebffc75` | (see git log) |
| `04c90f81` | (see git log) |
| `695457f0` | (see git log) |
| `16e94172` | (see git log) |
| `c2075414` | (see git log) |
| `b0cffa1d` | (see git log) |
| `bc3b7c56` | (see git log) |
| `f66c358f` | (see git log) |
| `b752def8` | (see git log) |
| `506297e3` | (see git log) |
| `64d033ae` | (see git log) |
| `8e993984` | (see git log) |
| `ed76ca15` | (see git log) |
| `2ae8c306` | (see git log) |
| `bf700b23` | (see git log) |

### Testing

- Validation was not recorded for this session.

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 275: Measure .github/scripts Python under coverage (lane 1)

**Date**: 2026-07-31
**Task**: Measure .github/scripts Python under coverage (lane 1)
**Branch**: `fix/measure-unmeasured-runtime-surface`

### Summary

Implemented lane 1 of 07-28-measure-unmeasured-runtime-surface: added .github/scripts/*.py to the coverage [run] include list (plus */ variant) so CI automation helpers are measured, updated the CONTRIBUTING.md exemption paragraph (A-033 partial reversal), and shipped the change through PR #292 with a clean Copilot round and green CI. Recorded the 77% measured baseline; no floor introduced. Lanes 2 and 3 stay open.

### Main Changes

- Added .github/scripts/*.py and */.github/scripts/*.py to .coveragerc [run] include; [report] strict installer gate untouched
- Updated CONTRIBUTING.md so .github/scripts/*.py is no longer documented as coverage.py-exempt; floors deferred to a follow-up at or below measured values
- Ticked lane 1 acceptance criterion and recorded the 77% (233-statement) measured baseline in the task PRD


### Git Commits

| Hash | Message |
|------|---------|
| `82cc6a03` | feat: measure .github/scripts Python under coverage |
| `0c73cb0` | chore(task): record lane 1 baseline for 07-28-measure-unmeasured-runtime-surface |

### Testing

- [OK] coverage report --include=".github/scripts/*" shows bookkeeping_ci_scope.py 233 stmts 77% (non-zero measurement gate)
- [OK] grep [report] .coveragerc — include still install.py + installer/*, fail_under=100 unchanged
- [OK] make release-prep exit 0
- [OK] PR #292 CI Result pass (unit matrix, lint, security, release payload gate); Copilot review round 1 zero findings

### Status

[OK] **Completed**

Session complete; task `07-28-measure-unmeasured-runtime-surface` stays `in_progress` — only lane 1 shipped.

### Next Steps

- Lane 2: measure `review-preflight.mjs` via c8/NODE_V8_COVERAGE.
- Lane 3: decide and implement the shell coverage scope.
- Shell lane must report a coverage number in CI before the task's acceptance criteria are met.


## Session 276: Lane 2: measure review-preflight.mjs coverage via c8, PR #301 review loop to clean

**Date**: 2026-07-31
**Task**: Lane 2: measure review-preflight.mjs coverage via c8, PR #301 review loop to clean
**Branch**: `fix/measure-unmeasured-runtime-surface`

### Summary

Implemented lane 2 of 07-28-measure-unmeasured-runtime-surface: added c8-based coverage measurement for scripts/sd-ai-command-pack-review-preflight.mjs to the bookkeeping CI lane, with a shared c8_run wrapper reused across both preflight invocations and a fail-closed jq -e gate against zero measured lines. Shipped through PR #301 and drove its Copilot review loop to a clean round 4: round 1 added missing step ids plus a wiring/gate contract test; round 2 extended it with c8_run wrapper-reuse and temp-directory assertions plus a new negative-case test executing the live jq gate expression against a synthetic zero-coverage fixture; round 3 added the repo's established shutil.which("jq") + skipTest guard to that new test. All 8 sd-check gates and full CI green at 394f3cc0; PR-scoped review-learnings dry run recorded 1 proposed change, 0 applied.

### Main Changes

- Detailed change bullets were not supplied; see the summary above.

### Git Commits

| Hash | Message |
|------|---------|
| `cf2f36fa` | (see git log) |
| `cba06eb3` | (see git log) |
| `a81e548a` | (see git log) |
| `394f3cc0` | (see git log) |

### Testing

- Validation was not recorded for this session.

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 277: Fix completion-mode recovery for open multi-lane tasks

**Date**: 2026-08-01
**Task**: Fix completion-mode recovery for open multi-lane tasks
**Branch**: `claude/vibrant-banach-299a9e`

### Summary

Widened validateCompletionBundle's normal path with an in-place active-task bundle shape and added a new active-task-review-successor recovery subtype for --base == --head, so a legitimately-open (non-archived) task's own bookkeeping touch gets a valid finish-work receipt. Two rounds of host+Codex adversarial review and three implementation-time empirical fixes (found only by running the existing suite) are recorded in the task's design.md; 108/108 tests pass.

### Main Changes

- Widened `validateCompletionBundle`'s normal path (`scripts/sd-ai-command-pack-review-preflight.mjs`) with a second bundle shape: an `in_progress`/`review` task's own-directory touch, status/branch byte-identical, no archive — reusing a parameterized `validateTaskLifecycleIdentity` shared with the existing archive-move path.
- Added a new completion-mode recovery subtype, `active-task-review-successor`, for the `--base == --head` fallback: validates one bounded range from the oldest qualifying prior touch to head (linearity, per-commit scope, net-effect identity, journal presence), tried only after the existing archive-anchor search fails.
- Two rounds of host+Codex adversarial review (read-only, evidence-checked against the real source) found and fixed 10 blocking defects in the design before any code was written; implementing it and running the existing test suite then surfaced 3 further genuine defects (an orchestration discriminator that silently replaced 9 of 11 existing tests' specific reason codes with a generic one; a follow-up gap in that same discriminator; an anchor search that would select `task.py create`/`start` itself for the single most common real-world case). All are fixed and documented in the task's `design.md`.
- Documented the new subtype in `.agents/skills/sd-finish-work/SKILL.md` Step 7.
- Captured two reusable lessons in new spec docs: a top-level `const`-placement gotcha specific to this file's CLI-dispatch structure, and the architectural principle that a "historical proof via a live-reading function" is only sound for content that's provably immutable afterward (`.trellis/spec/tooling/`); a review-methodology lesson (static review vs. running the real suite) in `.trellis/spec/guides/index.md`.

### Git Commits

| Hash | Message |
|------|---------|
| `71e5c877` | fix: recover completion receipts for open multi-lane tasks |

### Testing

- `python3 -m unittest tests.test_bookkeeping_validator tests.test_pr_eligibility` — 108/108 tests pass (79 + 29), independently re-run at each verification checkpoint rather than trusted from a single report.
- `ruff check` and `mypy` — clean on all changed Python.
- `node --check` on both `scripts/` and `templates/scripts/` copies of the validator — pass; `diff` confirms the two mirrors are byte-identical.
- Mirror re-sync (`install.py . --force`) introduces zero additional drift.
- `git diff` on `scripts/sd-ai-command-pack-pr-eligibility.py` — zero lines changed, confirming no eligibility-side code change was needed for the new subtype.

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 278: Direction-aware completion-successor validation (rebased onto #302, shipped 0.62.0)

**Date**: 2026-08-02
**Task**: Direction-aware completion-successor validation (rebased onto #302, shipped 0.62.0)
**Branch**: `fix/direction-aware-completion-successor`

### Summary

Made completion-successor validation direction-aware in review-preflight: isAdjacentArchiveCommit now qualifies an anchor via an archive move-set (name both lands in archive/ and vacates its active location), so a pure un-archive no longer masquerades as an archive commit. Added completion_successor_anchor_reverted, emitted alongside scope findings when a successor un-archives the anchored task, naming the stale receipt and recovery action. Integrated origin/main (PR #302 had rewritten the same subsystem into a dispatcher over attemptArchiveAnchorRecovery + attemptActiveTaskAnchorRecovery); re-planned artifacts and ported the fix verbatim; re-ran the adversarial review (Codex: no impl defect). Bumped pack to 0.62.0 with changelog + regenerated surfaces/manifest/ledger. 6 new tests, suite 85 pass, make check green. Pruned 2 stale agent worktrees.

### Main Changes

- Detailed change bullets were not supplied; see the summary above.

### Git Commits

| Hash | Message |
|------|---------|
| `caaa08de` | (see git log) |

### Testing

- Validation was not recorded for this session.

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 279: Pre-push gate against stale fleet candidate ledger

**Date**: 2026-08-02
**Task**: Pre-push gate against stale fleet candidate ledger
**Branch**: `fix/prevent-stale-candidate-ledger`

### Summary

Added a pre-push ledger digest gate (.githooks/pre-push) that blocks pushes when docs/fleet/candidate-validation.json is stale/invalid for the current payload, skipping outside pack-source checkouts. Documented the branch-protection strict=false merge-skew cause of main reds in FLEET_ROLLOUT.md as a maintainer follow-up. Two Codex adversarial planning rounds; make check green.

### Main Changes

- Detailed change bullets were not supplied; see the summary above.

### Git Commits

| Hash | Message |
|------|---------|
| `ba0bd20b` | (see git log) |

### Testing

- Validation was not recorded for this session.

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 280: Abandon review_preflight in-proc install conversion (hypothesis falsified)

**Date**: 2026-08-02
**Task**: Abandon review_preflight in-proc install conversion (hypothesis falsified)
**Branch**: `main`

### Summary

Planned + adversarially reviewed (2 Codex rounds, cap 3) the run_install->run_install_inproc conversion for test_review_preflight. Implemented all 54 sites, proved isolation (cwd/env/argv unchanged), 66 tests OK. Measured under full CI env: coverage 92.2s->87.5s (-5.1%), plain 79.8s->77.9s (-2.4%). AC4 (>=30%) FAILED: spawn is ~35ms/call; install copytree/git I/O and 44 unconvertible node-preflight spawns dominate. Reverted, nothing shipped. Same falsification pattern as PR #312. Real levers deferred: shared install fixture, fewer node spawns.

### Main Changes

- Detailed change bullets were not supplied; see the summary above.

### Git Commits

(No commits - planning session)

### Testing

- Validation was not recorded for this session.

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 281: Ship sd skills to Claude Code .claude/skills/sd-* (fanout parity)

**Date**: 2026-08-03
**Task**: Ship sd skills to Claude Code .claude/skills/sd-* (fanout parity)
**Branch**: `main`

### Summary

Added claude to SKILL_FANOUT_PLATFORMS so the 21 non-source-only sd skills fan out to .claude/skills/sd-* and ship to consumers via manifest.json, making them resolvable by Claude Code's installed-skill resolver. sd-fleet-refresh stays source-only (intentionally unresolvable). Reconciled install-audit twins (PACK_FILE_PATTERNS + SOURCE_ONLY_ALLOWED_PACK_FILES + Claude rogue-skill test), pinned counts (25->26, RETIRED 100->104), manifest 0.64.0, CHANGELOG, regenerated candidate ledger. Consumer coordination: loadsmith PR #173 (merged) data-drove its review-readiness classifier from installed-targets.txt. Copilot flagged a CHANGELOG overclaim (fixed). CI flaky macOS copytree race re-run green. Merged as #313.

### Main Changes

- Detailed change bullets were not supplied; see the summary above.

### Git Commits

| Hash | Message |
|------|---------|
| `ac1243b9` | (see git log) |

### Testing

- Validation of record: PR #313 merged 2026-08-03 with CI 8 checks SUCCESS / 2 SKIPPED (macOS copytree-race re-run passed green before merge). No additional local validation was captured this session.

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 282: Release sd-ai-command-pack 0.64.1 — vendored pack-source hardening

**Date**: 2026-08-03
**Task**: Release sd-ai-command-pack 0.64.1 — vendored pack-source hardening
**Branch**: `chore/pack-source-hardening-0.64.1`

### Summary

Fixed 0.64.0-refresh lint/robustness findings in four vendored pack scripts (recovery-artifacts, work-loop, update-spec-kb, status) across both scripts/ and templates/scripts/ twins: structural contextlib.suppress for CodeQL py/empty-except, UnicodeError-hardened reads, bounded KB tail-read, status.py schemaVersion fail-closed + symlink-reject import guards. Added unit tests for every new branch. Bumped manifest.json 0.64.0->0.64.1 + CHANGELOG; make sync regenerated command surfaces, dogfood manifest, provenance, and fleet candidate ledger. make release-prep green (test/lint/audit/full-check). No consumer fanout (deferred per PRD).

### Main Changes

- Detailed change bullets were not supplied; see the summary above.

### Git Commits

| Hash | Message |
|------|---------|
| `dcdf0820` | (see git log) |

### Testing

- Validation was not recorded for this session.

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 283: Decouple sd:fleet-refresh command from installed-skill resolution (0.64.2)

**Date**: 2026-08-03
**Task**: Decouple sd:fleet-refresh command from installed-skill resolution (0.64.2)
**Branch**: `feat/decouple-fleet-refresh-command`

### Summary

Rewrote neutral command source to load the source-only fleet-refresh procedure by reading .agents/skills/sd-fleet-refresh/SKILL.md directly instead of resolving it by name (which could never succeed, leaving the command broken). Added per-command injection_anchor override on CommandInfo so the checkout-trust policy anchors on the new step-1 line; the other 21 commands regenerate byte-identical. Bumped to 0.64.2, refreshed version-bearing surfaces, dogfood manifest, changelog, candidate ledger. fleet-refresh remains source-only, 0 manifest consumer entries. Two-lane adversarial review pre-caught 4 blockers (generator anchor coupling was deepest). make release-prep EXIT 0. Committed 74bc984c; task archived. Fanout deferred.

### Main Changes

- Detailed change bullets were not supplied; see the summary above.

### Git Commits

| Hash | Message |
|------|---------|
| `74bc984c` | (see git log) |

### Testing

- Validation was not recorded for this session.

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 284: Ship 0.64.3: harden sibling-helper loaders against TOCTOU

**Date**: 2026-08-03
**Task**: Ship 0.64.3: harden sibling-helper loaders against TOCTOU
**Branch**: `fix/harden-helper-loader-toctou`

### Summary

Corrective release 0.64.3. Replaced islink-precheck-then-exec_module at 4 sibling-loader sites (status work-loop + recovery, surface-check _load_source_module, fleet-controller _wave_planner) with an atomic O_NOFOLLOW|O_NONBLOCK fd read + fstat + compile/exec; advisory lstat preserves classification; metadata/registration/bytecode-suppression behavior-preserved. Added test_helper_loader_safety.py and reworked status loader tests off the importlib seam. 4-round adversarial planning review (user-authorized round 4). make release-prep EXIT=0.

### Main Changes

- Detailed change bullets were not supplied; see the summary above.

### Git Commits

| Hash | Message |
|------|---------|
| `46243a5c` | (see git log) |

### Testing

- Validation was not recorded for this session.

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 285: sd-ai-command-pack 0.64.4 — fleet-rollout hardening

**Date**: 2026-08-04
**Task**: sd-ai-command-pack 0.64.4 — fleet-rollout hardening
**Branch**: `feat/0.64.4-fleet-rollout-hardening`

### Summary

Shipped 0.64.4: six behavior fixes (#2/#5/#6/#7/#11/AC1.c), source-only fleet-publish.py, controller/timing ergonomics; addressed 4 Copilot findings on PR #318 (f1c1dd48).

### Main Changes

- 0.64.4 hardening: pr-eligibility BLOCKED/MERGEABLE classification, review-preflight _example-only advisory gate, review-scope CLOSED-PR guard, housekeeping read-only KB advisory skip, sibling-loader reason codes, fleet-refresh checkout/pr-publication steps
- New source-only fleet-publish.py folds finish-work into the reviewed head under allowlist/transactional-restore/.trellis-only guards
- Copilot review on PR #318 (f1c1dd48): rename moved inside try/finally, --record-session resolved to CWD, ENOTDIR->non_regular + ELOOP->symlink in status/surface-check twins, +2 regression tests


### Git Commits

| Hash | Message |
|------|---------|
| `1561b5119237fe0a63a5cfa764b2109314af745e` | chore(task): record 0.64.4 fleet-rollout hardening task artifacts |

### Testing

- [OK] make release-prep green; install-audit vouched hashes match at 0.64.4 (210 targets); 71 focused unittests OK
- [OK] PR #318 CI all green on fixed head f1c1dd48 (unittest matrix incl.); 4/4 Copilot threads resolved

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 286: 0.64.5 planning — adversarial review round-2 remediation (Option 1)

**Date**: 2026-08-04
**Task**: 0.64.5 planning — adversarial review round-2 remediation (Option 1)
**Branch**: `main`

### Summary

Planning-only, NO code impl started, NO active task, NO campaign (standing constraint: no fleet rollout until user explicitly asks; loadsmith deferred, 6 consumers still on 0.64.3). Parent 08-04-0-64-5-followup-hardening + 3 children (A=08-03-improve-unsafe-sibling-diagnostics, B=08-04-fleet-publish-archive-commit-retry, C=08-04-fleet-publish-pack-self-publish-gate). Adversarial-review status: round-1 closed C-1..C-9; round-2 (Codex) found C-8 residual + N-1, both remediated in commit 2228505e. Option 1 chosen for N-1: task_store._auto_commit_archive retries only final commit on index-lock stderr (real fix); consumer fleet-publish fails LOUDLY (PublishError+recovery), NO rollback (cmd_archive mutates status/children/sessions pre-move, task_store.py:473-506). GATE NOT CLOSED: final Codex pass-3 was interrupted by user before verdict; host pass-3 green on both items. TO RESUME: run one fresh read-only Codex pass-3 (prompt at scratchpad/codex-r3-prompt.txt, or reconstruct) against the 6 .md artifacts; if UNBLOCKED, write completion report (contract section 5) + reconcile C-1..C-9/N-1 ledger, then seek user go-ahead for task.py start and implement 0.64.5 (order C->B->A->R per implement.md). Codex CLI flaky this session (exit 144 hook-startup twice; macOS lacks 'timeout' binary — run codex plain). Impl NOT allowed until gate closes + user go-ahead.

### Main Changes

- Detailed change bullets were not supplied; see the summary above.

### Git Commits

| Hash | Message |
|------|---------|
| `2228505e` | (see git log) |

### Testing

- Validation was not recorded for this session.

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 287: 0.64.5 planning gate CLOSED (Option A) — held before implementation

**Date**: 2026-08-04
**Task**: 0.64.5 planning gate CLOSED (Option A) — held before implementation
**Branch**: `main`

### Summary

HELD at user request; NO code impl, NO campaign (standing constraint: no fleet rollout until user explicitly asks; loadsmith deferred, 6 consumers on 0.64.3). Planning-adversarial-review COMPLETE (3 passes, contract cap): C-1..C-9 (r1) + N-1 (r2) + M-1/M-2/M-3 (r3) all dispositioned; report at .trellis/tasks/08-04-0-64-5-followup-hardening/adversarial-review.md. Gate CLOSED on host review. HONESTY CAVEAT: Option A (M-1 fix) landed after the final review pass -> host-verified only, NOT Codex-approved (pass budget spent); used 3 remediation rounds vs nominal 2. 0.64.5 SHIPS: A (sibling-loader ENOTDIR->missing, both branches/both twins, templates-first, caller verify-only, repo-relative path OK, advisory+authoritative tests) + B-fleet (fleet-publish.py loud abort on non-zero archive: PublishError+recovery, NO rollback) + C (self-publish guard: bookkeeping-CI fingerprint -> PublishError code 3 naming sd-finish-work + consumer-only docs) + R (bump 0.64.5, CHANGELOG, release-prep, check, PR, tag). OUT OF 0.64.5 (M-1): task_store retry handed upstream as standalone task 08-04-trellis-upstream-archive-commit-lock-retry (Trellis-owned file, pack doesn't ship it; carries M-2 preserve 'not source_was_tracked' return contract + M-3 anchor retry on 'index.lock' substring). SIDE EFFECT: task.py create auto-activated the upstream task as session current; on resume, task.py start a 0.64.5 child instead (order C->B->A->R per implement.md, each phase green gate). TO RESUME: task.py start 08-04-fleet-publish-pack-self-publish-gate, implement C->B->A->R. Codex CLI flaky this session (exit 144 hook-startup; macOS has no 'timeout' binary -> run codex plain). Impl NOT allowed until user go-ahead; NO campaign until user explicitly asks.

### Main Changes

- Detailed change bullets were not supplied; see the summary above.

### Git Commits

| Hash | Message |
|------|---------|
| `be12f4d8` | (see git log) |

### Testing

- Validation was not recorded for this session.

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 288: Release 0.64.5 — sibling-loader + fleet-publish hardening (A/B/C)

**Date**: 2026-08-04
**Task**: Release 0.64.5 — sibling-loader + fleet-publish hardening (A/B/C)
**Branch**: `feat/0.64.5-followup-hardening`

### Summary

Implemented + released 0.64.5 (branch feat/0.64.5-followup-hardening). A: sibling-loader ENOTDIR->missing both branches/both twins + authoritative-branch test (loader 10/10). B: fleet-publish loud abort on archive failure, no rollback (fleet 15/15); task_store retry handed upstream (08-04-trellis-upstream-archive-commit-lock-retry). C: self-publish guard code 3 -> sd-finish-work + consumer-only docs. Version 0.64.4->0.64.5 propagated all 6 sites; make release-prep exit 0 (test+lint+mypy+audit+full-check, 0 preflight failures). 3-round adversarial review (host+Codex) complete; report at archive/2026-08/08-04-0-64-5-followup-hardening/adversarial-review.md. 4 tasks archived (3 children + parent). NEXT: push, open PR w/ Tooling/generated scope body, Copilot review, settle CI, merge, tag v0.64.5. NO fleet campaign (standing constraint; 6 consumers on 0.64.3).

### Main Changes

- Detailed change bullets were not supplied; see the summary above.

### Git Commits

| Hash | Message |
|------|---------|
| `386a7e82` | (see git log) |

### Testing

- Validation was not recorded for this session.

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 289: 07-25-fix-ci-dispatch: per-job dispatch protocol for sd-fix-ci (0.64.7)

**Date**: 2026-08-04
**Task**: 07-25-fix-ci-dispatch: per-job dispatch protocol for sd-fix-ci (0.64.7)
**Branch**: `feat/sd-fix-ci-dispatch`

### Summary

Tier 1 pilot of the SD dispatch pattern: sd-fix-ci fans out one read-only sub-agent per failing CI job (per-job log fetch), parent keeps enumeration/reruns/report. Section in skill body (audit-repo house template), thin adapters unchanged, trust restated not re-derived, fan-out bounded to waves of six. Shipped as release 0.64.7 with fleet candidate re-validated across 8 consumers.

### Main Changes

- Added ## Dispatch protocol to templates/.agents/skills/sd-fix-ci/SKILL.md; per-job gh run view -j <job-id> --log-failed replaces whole-run fetch
- Worker contract (read-only, typed class + quoted evidence + proposed disposition); parent owns run-level facts, shared max-reruns budget, all fixes/reruns; report contract unchanged
- Trust restated in one line (checkout-trust count=1, no generator-owned classifier duplicated); fan-out bounded to waves of at most six workers
- Release 0.64.7: manifest bump, CHANGELOG, catalog regen, dogfood mirror sync, fleet candidate ledger re-validated across 8 consumers


### Git Commits

| Hash | Message |
|------|---------|
| `ad63deca` | feat: add per-job dispatch protocol to sd-fix-ci (0.64.7) |
| `a38e4e2e` | docs: keep sd-fix-ci log-fetch command on one inline code span |
| `de8adf60` | chore(task): record branch for 07-25-fix-ci-dispatch finalization |
| `21165099` | chore(task): archive 07-25-fix-ci-dispatch |

### Testing

- [OK] make check green (shipped-surface closure clean, version gate 0.64.6->0.64.7, changelog heading, candidate ledger valid)
- [OK] make generate byte-stable (2nd run no diff); checkout-trust count=1; no classifier tokens in any SKILL.md
- [OK] sd-review scope=pr ready (check passed, local clean); CI all green; Copilot 1 finding fixed (a38e4e2e) + thread resolved

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 290: Add agent manifest kind + subagent capability gate (0.64.8)

**Date**: 2026-08-04
**Task**: Add agent manifest kind + subagent capability gate (0.64.8)
**Branch**: `feat/agent-artifact-kind`

### Summary

Made 'agent' a first-class SD manifest artifact kind gated by a per-platform subagent capability (claude/codex/gemini wave 1), read from the registry so later platforms are additive rows. Ships zero agent bodies, so the manifest and every generated surface stay byte-identical. Hardened the Codex TOML renderer to reject backslashes, and pinned the sd-review local stage to the clean gito reviewer (dropping the flaky non-deterministic prism).

### Main Changes

- Registered 'agent' in KNOWN_MANIFEST_KINDS + both byte-identical surface-check mirrors; kinds stay descriptive not dispatching
- Added agent_kind + agent_target_pattern to PlatformInfo (modeled on command_kind), gating agent rows to zero by construction
- Generator renders per-platform agents (markdown verbatim, codex TOML twin, gemini tool allowlist), rejects non-sd- names; capable set read from registry
- render_toml_agent now rejects backslashes in description/body (TOML basic strings interpret escapes) alongside the existing quote/fence guards
- Added .sd-ai-command-pack/review.json pinning sd-review local stage to gito; dropped flaky prism (consistent with full-check's PRISM=0 default)


### Git Commits

| Hash | Message |
|------|---------|
| `799999f1` | feat: register agent manifest kind (1/3) |
| `f5501b51` | feat: add subagent capability gate to PlatformInfo (2/3) |
| `02712f7f` | feat: render subagent artifacts for wave-1 platforms (3/3) |
| `e9289813` | chore(task): mark agent-artifact-kind acceptance criteria and disposition |
| `6353bf5d` | fix: reject backslashes in agent TOML description and body |
| `0b322f79` | chore(review): disable flaky prism local reviewer, keep gito |

### Testing

- [OK] make check green (installer 100% coverage, surface drift clean, version gate 0.64.7->0.64.8, changelog matched, candidate ledger valid)
- [OK] AgentGenerationTests 6/6 (markdown fan-out, TOML twin, sd- enforcement, gemini allowlist, backslash rejection)
- [OK] sd-review scope=pr: 8/8 deterministic checks pass, gito clean, review status ready

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 291: Register fleet-refresh.operator-policy structured decision (0.64.9)

**Date**: 2026-08-04
**Task**: Register fleet-refresh.operator-policy structured decision (0.64.9)
**Branch**: `feat/register-fleet-operator-policy`

### Summary

Registered the fleet-refresh.operator-policy interaction decision and bound it to sd-fleet-refresh, closing the last child of 07-24-correct-sd-skill-contract-drift (finding 1.6.2.1). Registry-side only: the ask/do-not-ask prose already existed. Added the required Structured decisions reference to the authored skill (a shipped surface test enforces it), regenerated adapters, bumped to 0.64.9.

### Main Changes

- installer/registry.py: one static InteractionDecision fleet-refresh.operator-policy (blocked-run-disposition, header 'Fleet policy', noninteractive=park, 3 exclusive dispositions, park recommended+first) plus interaction_decisions binding on the sd-fleet-refresh command row; registration+binding in one commit (validator raises at import on either half).
- Added a ## Structured decisions section to templates/.agents/skills/sd-fleet-refresh/SKILL.md (and its source-only dev mirror) linking structured-questions.md and naming the decision id; required by test_generated_interaction_reference_and_skills_share_one_contract. R2-R5 prose unchanged (not duplicated).
- Regenerated fleet-refresh adapters + structured-questions reference; Claude/Gemini name native question tools, neutral skill stays host-agnostic. Version 0.64.8->0.64.9, CHANGELOG, fleet candidate ledger re-validated.


### Git Commits

| Hash | Message |
|------|---------|
| `f2a77537` | feat: register fleet-refresh.operator-policy structured decision (0.64.9) |

### Testing

- [OK] Registry import validates 13->14 decisions; grep -c fleet-refresh.operator-policy installer/registry.py = 2
- [OK] AC2: .claude/commands/sd/fleet-refresh.md names AskUserQuestion; templates skill names no host tool
- [OK] make generate byte-stable (0 written, closure clean); make sync; make check green

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 292: Align review-preflight classifier for .claude/hooks (0.64.10)

**Date**: 2026-08-04
**Task**: Align review-preflight classifier for .claude/hooks (0.64.10)
**Branch**: `feat/align-review-preflight-claude-hooks`

### Summary

Added .claude/hooks/ to the mjs review-preflight copied-path classifier (isTrellisCopiedPath) so it matches the shell review-scope classifier, which already listed it. Paired parity tests pin both sides. Version 0.64.9 -> 0.64.10; PR #326.

### Main Changes

- mjs: classify .claude/hooks/* as trellis copied path (root + template twin, byte-identical)
- tests: copiedTemplateKind assertion (preflight) + behavioral shell advisory test (review-scope) as parity pair
- release: manifest 0.64.10, CHANGELOG, candidate ledger regenerated


### Git Commits

| Hash | Message |
|------|---------|
| `b1ddb073` | feat: classify .claude/hooks as copied in review-preflight (0.64.10) |
| `5e791227` | chore(task): record branch for align-review-preflight-claude-hooks |
| `793ac653` | chore(task): archive 07-27-align-review-preflight-claude-hooks |

### Testing

- [OK] make check: exit 0 (Full check complete)
- [OK] test_review_scope + test_review_preflight: 114 tests, 0 failures
- [OK] CI Result: pass; Copilot: COMMENTED, 0 findings

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 293: Add .gemini/settings.json review-scope parity coverage

**Date**: 2026-08-04
**Task**: Add .gemini/settings.json review-scope parity coverage
**Branch**: `feat/align-review-scope-gemini-settings`

### Summary

Both review-scope classifiers already treat .gemini/settings.json as copied; added the missing guard (copiedTemplateKind assertion + shell advisory test). Copilot flagged a stale PRD Requirements bullet; reworded it. Tests-only, no version change. PR #327.

### Main Changes

- tests: .gemini/settings.json parity pair (preflight assertion + review-scope behavioral advisory test)
- docs: reconcile PRD Requirements with already-classified state (Copilot review fix)


### Git Commits

| Hash | Message |
|------|---------|
| `df3acd01` | test: add .gemini/settings.json review-scope parity coverage |
| `c07ffac1` | docs: reconcile gemini-settings PRD requirements with discovered state |
| `eee0f54e` | chore(task): record branch for align-review-scope-gemini-settings |

### Testing

- [OK] make check: exit 0
- [OK] focused parity tests green; CI Result pass; Copilot finding resolved

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 294: Batch review-learnings GitHub review-thread fetches (0.64.11)

**Date**: 2026-08-04
**Task**: Batch review-learnings GitHub review-thread fetches (0.64.11)
**Branch**: `feat/batch-review-learnings-github`

### Summary

Collapsed the per-PR reviewThreads fan-out in sd-review-learnings to ceil(N/20) aliased GraphQL queries with a partial-failure fallback to the single-PR query; per-PR truncation and input ordering preserved. Tactical fix pending the parked reviewer-generalization rework.

### Main Changes

- _copilot_comments_for_prs resolves reviewThreads via _review_thread_connections/_batch_review_threads/_single_pr_review_threads; GITHUB_REVIEW_THREAD_BATCH_SIZE=20
- Version 0.64.10->0.64.11, changelog, generalization-task boundary note, regenerated surfaces


### Git Commits

| Hash | Message |
|------|---------|
| `c16f980651b7db7edfab82084e3fea2635fbd10f` | feat: batch review-learnings GitHub review-thread fetches (0.64.11) |

### Testing

- [OK] ./.venv/bin/python3 -m unittest tests.test_review_learnings (59 OK)
- [OK] full-check.sh FC_EXIT=0; review preflight 0 failures; live PR-scoped --dry-run EXIT=0

### Status

[OK] **Completed**

### Next Steps

- Merge PR #328 via housekeeping gate


## Session 295: Bound review-learnings unsafe-path diagnostics (0.64.12)

**Date**: 2026-08-04
**Task**: Bound review-learnings unsafe-path diagnostics (0.64.12)
**Branch**: `fix/bound-review-learnings-unsafe-path`

### Summary

Guard the main scan path's build_review_learning_signal call so unsafe planning changed-path inputs surface as a bounded [sd-review-learnings:planning] diagnostic (exit 2, JSON schema-valid) instead of an uncaught ValueError traceback. Narrowed the guard to wrap only the _normalize_planning_changed_paths call per Copilot review.

### Main Changes

- Wrapped _normalize_planning_changed_paths in try/except ValueError -> _print_early_failure(phase=planning) + return 2 on the main scan path; template edited first, root byte-mirrored.


### Git Commits

| Hash | Message |
|------|---------|
| `fc79dc8db1c23744f4234eb15fa4fe1c5b874b6c` | fix: scope unsafe-path guard to the normalize call (Copilot review) |

### Testing

- [OK] make check MK_EXIT=0; 61 review-learnings tests OK; two new CLI regression tests for traversal + control-char unsafe paths.

### Status

[OK] **Completed**

### Next Steps

- Merge PR #329 through housekeeping gate; continue autonomous loop iteration 8.


## Session 296: Parallelize sd-status fleet collection (0.64.13)

**Date**: 2026-08-05
**Task**: Parallelize sd-status fleet collection (0.64.13)
**Branch**: `feat/parallelize-fleet-status`

### Summary

collect_fleet now maps collect_local over consumers in a bounded ThreadPoolExecutor (min(8,len(consumers))), preserving registry order via input-order map and isolating a raising consumer to a degraded unavailable row.

### Main Changes

- Refactored collect_fleet serial loop into a worker + bounded ThreadPoolExecutor; template edited first, root byte-mirrored.


### Git Commits

| Hash | Message |
|------|---------|
| `42389dc0953bfffbf3a5c0c7ff131721cbe98512` | feat: parallelize sd-status fleet collection (0.64.13) |

### Testing

- [OK] make check MK_EXIT=0; new test_fleet_collection_isolates_a_raising_consumer; existing ordering test unchanged. Measured serial ~9.7s -> parallel ~1.76s (C=8,W=8).

### Status

[OK] **Completed**

### Next Steps

- Merge PR #330 through housekeeping gate; continue autonomous loop iteration 9.


## Session 297: Clarify fleet PR audit scope for Trellis adapters

**Date**: 2026-08-05
**Task**: Clarify fleet PR audit scope for Trellis adapters
**Branch**: `feat/clarify-fleet-pr-audit-scope`

### Summary

Distinguished pack-owned receipt/provenance coverage from Trellis-owned adapter validation in fleet rollout PR guidance (SD_AI_COMMAND_PACK.md template+mirror, FLEET_ROLLOUT.md); each ownership class attributed to its validating check. Added a regression test proving a newly-tracked Trellis-owned adapter forces remote-review and stays outside the pack-vouched set. Version 0.64.14.

### Main Changes

- docs+test: install audit/provenance vouch pack-owned receipt targets only; Trellis-owned adapters covered by classifier integration-only eligibility + consumer integration/readiness checks; new test_newly_tracked_trellis_adapter_stays_outside_pack_vouch


### Git Commits

| Hash | Message |
|------|---------|
| `4433ca2d4fe6b32d408dfc078057e941c688e2d7` | feat: clarify fleet PR audit scope for Trellis adapters (0.64.14) |

### Testing

- [OK] make check (green); ./.venv/bin/python3 -m unittest tests.test_fleet_review_classify (14/14 incl new test)

### Status

[OK] **Completed**

### Next Steps

- none — task complete, merged via housekeeping


## Session 298: Consolidate secret redactors behind one shared shape table

**Date**: 2026-08-05
**Task**: Consolidate secret redactors behind one shared shape table
**Branch**: `feat/consolidate-secret-redactors`

### Summary

Replaced the two divergent secret redactors (lib substituting regex + fleet-timing detector) with one shared _SECRET_SHAPES table carrying detector and substituter columns per shape; the lib substitutes and never raises, fleet-timing detects and raises. Fixed the fine-grained PAT leak, wired validate_environment_blocked_evidence into toolchain cache-setup failure (R5), and hardened two Copilot findings: sk- token-boundary anchoring and an unterminated-PEM fallback span.

### Main Changes

- One _SECRET_SHAPES definition site; both consumers derive from it (lib substitutes, fleet-timing raises)
- Fixed fine-grained github_pat_ leak and sk- mid-word over-redaction (token-boundary anchor)
- PEM substituter falls back to a bounded span from BEGIN when the END footer is missing, so truncated key bodies cannot leak
- R5: configure_cache_environment routes cache-setup failure through validate_environment_blocked_evidence with structured recoveryAction
- Captured single-shape-table redaction convention in logging-guidelines.md spec


### Git Commits

| Hash | Message |
|------|---------|
| `e4cbf61f` | feat: consolidate secret redactors behind one shared shape table (0.64.15) |
| `34976fc8` | docs(spec): capture single-shape-table secret-redaction convention |
| `8762a547` | fix: harden secret redactor for word-boundary and unterminated PEM (Copilot review) |
| `06dd2aca` | chore(task): record branch for consolidate-secret-redactors finalization |
| `62e7cd5d` | chore(task): archive 07-28-consolidate-secret-redactors |

### Testing

- [OK] make check: MK_EXIT=0, Full check complete, shipped-surface closure clean (17 paths)
- [OK] ScriptLibTests 45 ok incl new openai-boundary + unterminated-PEM tests; FleetTimingTests 28 ok
- [OK] sd-review scope=pr attempt 2 ready, local (gito) clean; Copilot round 2 no new comments

### Status

[OK] **Completed**

### Next Steps

- None — task complete; post-archive handoff (merge) owned by sd-housekeeping


## Session 299: Consolidate atomic-write and cache-env helpers (A-085, A-080); ship PR #333

**Date**: 2026-08-05
**Task**: Consolidate atomic-write and cache-env helpers (A-085, A-080); ship PR #333
**Branch**: `feat/consolidate-shared-script-helpers`

### Summary

Consolidated the atomic_write_text/default_text_file_mode writer and the cache-env key set into the shared library, shipped release 0.64.16, and split the remaining state-root (A-046) and git-invocation (A-076) clusters into dedicated follow-up tasks. Published PR #333 and converged its review loop: deterministic sd-check 8/8, two verified-false gito findings rebutted, and one real Copilot regression (over-permissive cache-key validation glob) fixed. Parent task stays open (planning finalization) because AC1/AC4 are deferred to the child tasks.

### Main Changes

- Consolidated atomic_write_text + default_text_file_mode into sd_ai_command_pack_lib.py (A-085) and repointed record-session, update-spec-kb, and review-learnings onto it
- Made the cache-env key set data-driven end to end (A-080): CACHE_ENV_KEYS is the single authority, shell paths validate keys generically, arity assertions dropped, doctor human/JSON cache paths parse the lib emission
- Fixed the A-080 cache-key validator (Copilot review): the case glob [A-Z_][A-Z0-9_]* let malformed keys through via the trailing *; now rejects empty, disallowed-char, and bad-first-char keys, verified in bash and sh
- Recorded the shared atomic-write lib contract in the backend spec, documented the A-046/A-076 delivery split, and populated the two follow-up task descriptions
- Released 0.64.16; regenerated version-stamped command surfaces and the fleet candidate ledger


### Git Commits

| Hash | Message |
|------|---------|
| `06cd2af3` | refactor: consolidate atomic_write_text into shared lib (A-085) |
| `06c52b2b` | refactor: make cache-env key set data-driven end to end (A-080) |
| `62ff3afd` | chore: release 0.64.16 (atomic-write + cache-env consolidation) |
| `53140882` | fix: pass doctor cache-env as positional arg, not a new env var (A-080) |
| `b7ff12be` | chore: regenerate version-stamped surfaces for 0.64.16 |
| `f3410469` | docs(spec): record shared atomic-write lib contract; fix split-task descriptions |
| `48a13b4a` | fix(cache-env): enforce full env-var-name shape on cache keys (Copilot review) |
| `6965937b` | chore(fleet): regenerate candidate ledger for cache-key validation fix |

### Testing

- [OK] .venv/bin/python -m unittest (cache/toolchain/script-lib suites): 93 tests pass
- [OK] sd-check: 8/8 deterministic gates pass at head 6965937b
- [OK] cache-key validation verified in bash and sh: 7 real keys + valid edge cases accepted; empty/lowercase/digit-first/punctuation rejected
- [OK] make generate rc=0; scripts/ and templates/scripts/ byte-identical; shellcheck clean

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 300: Unify outcome/status verdict vocabulary (A-077, PR #334)

**Date**: 2026-08-05
**Task**: Unify outcome/status verdict vocabulary (A-077, PR #334)
**Branch**: `feat/unify-outcome-status-vocabulary`

### Summary

Unified the emitted-payload verdict vocabulary behind a shared lib-level core, resolving the two top-level status/outcome type collisions (housekeeping result document vs outcome enum; review-local report envelope) while keeping deprecated aliases dual-emitted for one release.

### Main Changes

- Added VERDICT_CORE + declare_verdict_domain to the shared lib; each producer (housekeeping, review-local, fleet-stage, fleet-consumer) derives its verdict set from the core with explicit opt-outs, import-time drift raises VerdictVocabularyError.
- Housekeeping result now emits outcome.verdict (canonical) with outcome.status as a deprecated alias (removed_version 0.66.0); review-local report envelope converges on top-level outcome with a status alias; the review.py consumer migrated to local.get('outcome', local.get('status')).
- Strengthened tests per Copilot review: scoped the status-key walker to treat the top-level embedded sd-status document as opaque (envelope-scoped collision rule) and replaced a tautological domain test with exact per-domain member-set lock-ins plus a core-derivation guard.
- Recorded R3 justification (ok/recorded kept) and the R6 consumer file:line table; stamped 0.64.17, changelog, and regenerated the fleet candidate-validation payload digest.


### Git Commits

| Hash | Message |
|------|---------|
| `850a988e` | feat: unify outcome/status verdict vocabulary behind a shared core (A-077) |
| `8f235728` | test: strengthen verdict-vocabulary tests (Copilot review) |
| `cd9cb6d2` | docs(task): mark A-077 acceptance criteria satisfied |
| `4a759cad` | chore(task): record branch for unify-outcome-status-vocabulary finalization |

### Testing

- [OK] .venv/bin/python -m unittest tests.test_verdict_vocabulary — 12 tests OK
- [OK] make check — EXIT=0 (full suite + surface generation green)
- [OK] sd-review scope=pr — ready, sd-check 8/8, exactHeadReady at cd9cb6d2 (local doc finding verified false and rebutted; remote router absent)

### Status

[OK] **Completed**

### Next Steps

- None - task complete

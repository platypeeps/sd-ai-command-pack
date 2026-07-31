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

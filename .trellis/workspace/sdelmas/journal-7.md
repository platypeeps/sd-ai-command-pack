# Journal - sdelmas (Part 7)

> Continuation from `journal-6.md` (archived at ~2000 lines)
> Started: 2026-08-05

---



## Session 302: Consolidate git invocation into shared lib (A-076)

**Date**: 2026-08-05
**Task**: Consolidate git invocation into shared lib (A-076)
**Branch**: `feat/consolidate-git-invocation`

### Summary

Migrated every git-specific subprocess environment builder onto shared sd_ai_command_pack_lib helpers (run_git_minimal / run_git_cached) so no shipped script hand-builds a git-specific environment; added an AST boundary test; bumped manifest 0.64.19 and regenerated stamped surfaces to clear the release payload gate. Shipped via PR #336.

### Main Changes

- Added run_git_minimal (prompt-disabled cache-free) and run_git_cached (cache-backed) git helpers in the shared lib; migrated review-local, surface-check, install-audit, work-loop, fleet-controller, fleet-publish off inline git subprocess env builders while preserving each caller's exact stream/decoding/timeout/error semantics
- Added tests/test_git_invocation_boundary.py: AST gate proving only sd_ai_command_pack_lib builds a direct git subprocess call and the six migrated files carry no git-argv literal (with allowlist for the three generic shared-env runners)
- Bumped manifest 0.64.18 -> 0.64.19 with CHANGELOG heading and regenerated version-stamped surfaces + fleet candidate ledger via prepare-release to clear the release payload gate


### Git Commits

| Hash | Message |
|------|---------|
| `c3f246df` | feat: consolidate git subprocess invocation into shared lib (A-076) |
| `ab494ef8` | fix(review): clarify run_git env ownership and pre-bind git evidence locals |
| `948f3aa4` | fix(review): populate git evidence on full success instead of defaulting |
| `65dc3058` | fix(review): address Copilot findings on git-consolidation helpers |
| `83a7da59` | chore: bump manifest to 0.64.19 for git-invocation consolidation payload |
| `a10a15f4` | chore(task): record branch for A-076 finalization |

### Testing

- [OK] make test green (95% coverage); boundary + script-lib suites: Ran 53 tests OK
- [OK] surface-check clean (0 findings); mypy clean; all 9 PR #336 CI checks pass
- [OK] Copilot two consecutive no-new-comment reviews; 0 unresolved threads

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 303: Consolidate user-local state-root resolution into the shared lib (A-046)

**Date**: 2026-08-06
**Task**: Consolidate user-local state-root resolution into the shared lib (A-046)
**Branch**: `feat/consolidate-state-root-resolution`

### Summary

Replaced four forked copies of resolve_state_root/ensure_private_directory with one definition in sd_ai_command_pack_lib, reached through thin per-module wrappers bound by assignment so no existing call site changed. Added an AST boundary gate and closed two review findings about diagnostic path leakage.

### Main Changes

- sd_ai_command_pack_lib now owns STATE_HOME_ENV, resolve_state_root (explicit state_home -> SD_AI_COMMAND_PACK_STATE_HOME -> XDG_STATE_HOME -> Windows LOCALAPPDATA -> home), and ensure_private_directory(path, *, label, reference).
- work-loop, recovery-artifacts, fleet-timing, and fleet-controller delegate; each wrapper restates CommandError in its own error type. work-loop recovers __cause__ so a blocked mkdir stays a StatePersistenceError with its environment_blocked evidence.
- fleet-controller's default_state_home is deleted; CampaignStore appends fleet-campaigns only on the default path and still rejects a relative XDG_STATE_HOME with FleetControllerError.
- Behavior change: SD_AI_COMMAND_PACK_STATE_HOME now moves every private state surface, not only the work-loop ledger. CHANGELOG 0.64.20 documents the one-time mv, its reverse, and the Windows campaign-state case.
- Two review findings fixed: ensure_private_directory leaked the absolute target through str(OSError) in its mkdir message (now strerror only, OSError kept on __cause__), and the Windows test compared str() instead of as_posix().


### Git Commits

| Hash | Message |
|------|---------|
| `acfdda2a` | feat: consolidate user-local state-root resolution into the shared lib (A-046) |
| `d85f9c6a` | fix: close two review findings in the shared state-root helper |

### Testing

- [OK] make release-prep exit 0 (self-syncs, refreshes the fleet ledger, then the full make check)
- [OK] 1582 unittest tests, 0 failures; tests/test_state_root_boundary.py adds 12
- [OK] AC2 gate: grep '^def resolve_state_root|^def ensure_private_directory' scripts/*.py returns only sd_ai_command_pack_lib.py:2
- [OK] PR #338 CI all green; Copilot round 2 generated no new comments

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 304: Record the sd-review receipt-pinning defect and narrow the Gito .trellis exclusion

**Date**: 2026-08-06
**Task**: Record the sd-review receipt-pinning defect and narrow the Gito .trellis exclusion
**Branch**: `chore/task-review-check-receipt-pinning`

### Summary

Filed the planning task for the sd-review coordinator caching a failed sd-check receipt, then fixed the Gito exclusion that made that very task's PR unreviewable.

### Main Changes

- Added planning task 08-06-review-check-receipt-pinning (PRD only) documenting that scripts/sd-ai-command-pack-review.py:1796 recomputes the typed sd-check only when the stored result is None, so a failed result is cached and replayed for the same head-derived attempt ID.
- Narrowed the Gito .trellis exclusion from a blanket .trellis/** to the copied/generated boundary the review preflight defines in isTrellisCopiedPath, plus .trellis/tasks/archive/** and .trellis/workspace/**. Active task and spec documents are now reviewable.
- Bumped the pack to 0.64.21 with a CHANGELOG entry covering the behavior change and the if-not-exists install caveat for existing consumers.
- Rewrote test_gito_config_templates_are_installed, which pinned the old blanket entry by substring, to assert the narrowed contract from both sides.
- Applied two verified Copilot findings: qualified review.py path references to scripts/sd-ai-command-pack-review.py and reworded a non-standard word in the task title.


### Git Commits

| Hash | Message |
|------|---------|
| `dde46efd` | chore(task): add review-check-receipt-pinning planning task |
| `8fcf05e2` | fix(review): narrow the Gito .trellis exclusion to copied surfaces |
| `a407f75f` | docs(task): qualify review.py paths and reword the task title |

### Testing

- [OK] make check exit 0
- [OK] node scripts/sd-ai-command-pack-review-preflight.mjs: 0 failures, 0 warnings
- [OK] sd-review scope=pr at a407f75f: ready, check passed, gito clean 7133ms 0 findings, exactHeadReady true
- [OK] negative control: the rewritten assertion rejects the old blanket .trellis/** configuration
- [OK] CI on 8fcf05e2: unittest 3.10/3.13, macos, lint, security, Shell coverage, Release payload gate all SUCCESS

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 305: Broaden the receipt-pinning task to out-of-commit state

**Date**: 2026-08-06
**Task**: Broaden the receipt-pinning task to out-of-commit state
**Branch**: `chore/broaden-review-receipt-pinning-prd`

### Summary

Recorded a second occurrence of the sd-review cached-failed-check defect, this time on remote PR state rather than gitignored worktree state, and adjusted the PRD's scope, open questions, and acceptance criteria to match.

### Main Changes

- Added occurrence 2 to the PRD: pack.review-scope reads the pull request body over the GitHub API, so restoring the recognized Tooling/generated scope heading could not clear the pinned failure at head b4b6f028; only a fresh --artifact-root produced a live pass.
- Restated the goal as mutable state outside the commit rather than worktree-local gitignored state, since the two occurrences repair local and remote state respectively.
- Flagged against the open question proposing worktree-digest keying that such a key cannot cover occurrence 2 at all.
- Added an acceptance criterion for the PR-body case and widened the regression requirement to both observed sequences.
- Recorded that the --artifact-root workaround discards the whole attempt's durable state, including any paid provider round the receipt would have reused.
- Applied one verified Copilot finding: replaced the nonstandard word reintroduced in the task description.


### Git Commits

| Hash | Message |
|------|---------|
| `7952d9eb` | docs(task): broaden receipt-pinning scope to out-of-commit state |
| `556a7160` | docs(task): replace nonstandard "unclearable" in the description |

### Testing

- [OK] node scripts/sd-ai-command-pack-review-preflight.mjs: 0 failures, 0 warnings
- [OK] sd-review scope=pr at 556a7160: ready, check passed, gito clean 5952ms 0 findings, exactHeadReady true
- [OK] task.json parses as valid JSON; zero remaining occurrences of the flagged word

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 306: File local-provider-empty-scope planning task

**Date**: 2026-08-06
**Task**: File local-provider-empty-scope planning task
**Branch**: `chore/task-local-provider-empty-scope`

### Summary

Filed the Trellis planning task for sd-review misclassifying an all-excluded local diff as a provider failure, then converged it through PR #341 review: curated the task's context manifests and resolved a Copilot readability finding on the task description.

### Main Changes

- Added .trellis/tasks/08-06-local-provider-empty-scope with a PRD covering R1-R4, the three-row control table, and the empty-vs-real provider duration evidence (1308 ms vs 15384 ms)
- Curated implement.jsonl and check.jsonl with the tooling and guides spec indexes, replacing the scaffold placeholder that gito flagged
- Reworded the task.json description so the provider, not its configuration, is the subject of 'exits 0' (Copilot finding)


### Git Commits

| Hash | Message |
|------|---------|
| `0ec11bc6` | chore(task): add local-provider-empty-scope planning task |
| `d14b84a8` | chore(task): curate context manifests for local-provider-empty-scope |
| `84b9a483` | chore(task): clarify local-provider-empty-scope description |

### Testing

- [OK] sd-review scope=pr attempt 3: status ready, check passed, exactHeadReady true, gito local outcome clean
- [OK] jsonl manifests: all 4 entries parse as JSON and every referenced spec path exists
- [OK] task.json parses as valid JSON after the description rewrite

### Status

[OK] **Completed**

### Next Steps

- None - task complete

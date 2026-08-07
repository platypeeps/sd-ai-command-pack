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


## Session 307: File preflight-bare-filename-references planning task

**Date**: 2026-08-06
**Task**: File preflight-bare-filename-references planning task
**Branch**: `chore/task-preflight-bare-filename-references`

### Summary

Filed the third and last Trellis task from the 2026-08-06 audit: the review preflight never validates a bare-filename documentation reference, so a reference that names a tracked file by filename alone can rot silently. Converged through PR #342, correcting a base_branch seeded from the feature branch.

### Main Changes

- Added .trellis/tasks/08-06-preflight-bare-filename-references with a PRD recording the verified eligibility table, R1-R4 plus N1, the blocking-gate false-failure constraint, five open design questions, and six acceptance criteria
- Curated implement.jsonl and check.jsonl against the tooling and guides spec indexes at creation time, so the scaffold placeholder never reached review
- Corrected task.json base_branch from the feature branch to main (Copilot finding); task.py create seeds it from the current checkout


### Git Commits

| Hash | Message |
|------|---------|
| `77bdf7dd` | chore(task): add preflight-bare-filename-references planning task |
| `5779c242` | fix(task): point preflight-bare-filename-references base_branch at main |

### Testing

- [OK] shouldCheckDocumentationPathReference called directly on all five PRD table rows: every eligibility value matches the PRD
- [OK] review-preflight: 0 failures, 0 warnings (initially 3 failures -- the PRD's own code-span list of enumerated filenames named three files absent from this repository)
- [OK] sd-review scope=pr attempt 2: status ready, check passed, exactHeadReady true, gito local outcome clean

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 308: File task-create-base-branch-seed planning task

**Date**: 2026-08-06
**Task**: File task-create-base-branch-seed planning task
**Branch**: `chore/task-task-create-base-branch-seed`

### Summary

Filed the second audit gap: task.py create records the branch the author is standing on as base_branch, which names the PR target. A survey found one such record merged on 2026-07-30 and unnoticed for a week, and PR #342 reached a paid review round with the same defect after a clean preflight.

### Main Changes

- Added .trellis/tasks/08-06-task-create-base-branch-seed recording the seeding line, the three preflight base_branch rules and why each misses a fresh root record, R1-R4, and six acceptance criteria including a regression replay of PR #342's record
- Framed the upstream-versus-pack-local split as the first design decision: the seeding defect is in vendored Trellis, the detection is pack-local in review-preflight.mjs


### Git Commits

| Hash | Message |
|------|---------|
| `1b728f09` | chore(task): add task-create-base-branch-seed planning task |

### Testing

- [OK] Surveyed all 45 active task records: 43 name main; exceptions are 07-30-upstream-task-start-branch-recording (fix/silence-satisfied-scope-advisory) and this task's own record, corrected by hand
- [OK] Verified the three cited preflight line references resolve to the non-empty rule, the branch-differs rule, and the child-task allowed-targets rule
- [OK] review-preflight: 0 failures, 0 warnings; sd-review scope=pr: ready, check passed, gito clean

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 309: File fleet-provider-config-propagation planning task

**Date**: 2026-08-06
**Task**: File fleet-provider-config-propagation planning task
**Branch**: `chore/task-fleet-gito-exclusion-propagation`

### Summary

Filed the highest-value gap from the post-0.64.21 audit: the two if-not-exists provider configs have no delivery path for a corrected shipped default, so the Gito exclusion fix reached this repository and none of the six fleet consumers.

### Main Changes

- Added .trellis/tasks/08-06-fleet-provider-config-propagation with the measured per-consumer exclusion counts, R1-R4 plus N1, five open design questions, and six acceptance criteria covering .gito/config.toml and .prism/rules.json alike

### Git Commits

| Hash | Message |
|------|---------|
| `2303e982` | chore(task): add fleet-provider-config-propagation planning task |

### Testing

- [OK] Measured: 6 of 7 fleet repositories still carry the blanket ".trellis/**" entry; only sd-ai-command-pack is narrowed
- [OK] Measured: all six consumer configs are byte-identical to templates/.gito/config.toml at 0.64.20, so no local customization is at stake today
- [OK] Measured: exactly 2 of 776 manifest entries use install: if-not-exists
- [OK] review-preflight: 0 failures, 0 warnings; sd-review scope=pr: ready, check passed, gito clean

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 310: Rebase and land the external-symlink KB advisory fix (PR #321)

**Date**: 2026-08-06
**Task**: Rebase and land the external-symlink KB advisory fix (PR #321)
**Branch**: `codex/kb-advisory-external-symlink`

### Summary

PR #321 had sat 121 commits behind main since 2026-08-04, holding the only branch the housekeeping gate flagged as an anomaly. Rebased it onto current main, reapplied the release stamp for 0.64.22, and converged the review loop.

### Main Changes

- Rebased codex/kb-advisory-external-symlink onto dede0ae8; only docs/fleet/candidate-validation.json and the version-stamped catalogs conflicted, while check.py, its templates mirror, and tests/test_check.py auto-merged
- Reapplied the release stamp for 0.64.22 -- the branch's original 0.64.6 bump predated the current line by 15 releases -- and regenerated catalogs, the installed manifest mirror, and the fleet candidate ledger
- Unquoted the four cast() type expressions to match repo convention (Copilot suppressed comment); its stated reason was wrong, since mypy resolves string forward references in cast(), but the consistency point held
- Merged origin/main after PR #344 and PR #343 landed, renumbering this session from 308 to 310 because both of those branches had already claimed the intervening numbers

### Git Commits

| Hash | Message |
|------|---------|
| `7865666c` | fix(check): downgrade external-symlinked .obsidian-kb freshness to advisory |
| `d219bec5` | fix(check): converge review — cast KB advisory row values, bump to 0.64.6 |
| `b22e2a05` | chore(release): restamp KB advisory fix for 0.64.22 |
| `2b670088` | style(check): use bare type expressions in the KB advisory casts |

### Testing

- [OK] Negative control: reverting templates/scripts/sd-ai-command-pack-check.py to main fails test_external_symlink_kb_failure_is_advisory_skipped and test_is_external_symlink_discriminates_by_resolved_target, so both genuinely exercise the fix
- [OK] make check: 640 tests across nine suites, all OK, exit 0
- [OK] mypy scripts/sd-ai-command-pack-check.py: Success, no issues found
- [OK] diff scripts/ vs templates/scripts/ check.py: identical
- [OK] sd-review scope=pr pr=321: status ready, check passed, exactHeadReady true, gito clean

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 311: Land the Codex stdin-redirect contract and bump 0.64.23 (PR #345)

**Date**: 2026-08-06
**Task**: Land the Codex stdin-redirect contract and bump 0.64.23 (PR #345)
**Branch**: `docs/codex-lane-stdin-hang`

### Summary

Documented that codex exec must redirect stdin from /dev/null in the background adversarial-review lane, then cleared the release payload gate the shipped-surface change tripped.

### Main Changes

- Documented that the background `codex exec` lane must redirect stdin from /dev/null, along with the near-zero-CPU signature that distinguishes the hang from a real failure and the rule that a hung lane must not be reported as failed
- Merged origin/main after PR #321 landed; the only conflict was docs/fleet/candidate-validation.json, a generated fleet ledger, resolved by taking main's copy and regenerating rather than hand-merging
- Bumped 0.64.22 to 0.64.23 with a CHANGELOG entry: the planning adversarial-review contract is a shipped surface, so the doc change alone failed the release payload gate with "release version drift: shipped payload changed without manifest version bump"
- Authored the PR body's Tooling/generated scope section by hand; pr-body-scope.py --prepare-tooling-body correctly declined because the diff is not generated-only


### Git Commits

| Hash | Message |
|------|---------|
| `4f27104f` | docs(review): require stdin redirection on the Codex adversarial-review lane |
| `f82c15b4` | chore(release): bump to 0.64.23 for the Codex stdin-redirect contract |

### Testing

- [OK] review-preflight: 0 failures, 0 warnings
- [OK] sd-review scope=pr: ready, check passed, local clean, 0 findings, exactHeadReady true
- [OK] Rebutted Copilot's split-code-span finding: rendered the exact two lines through GitHub's /markdown API and got one <code> element with the newline collapsed to a space, matching CommonMark 6.1

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 312: Close out consolidate-shared-script-helpers

**Date**: 2026-08-06
**Task**: Close out consolidate-shared-script-helpers
**Branch**: `chore/close-consolidate-shared-script-helpers`

### Summary

Archived the repository's only in_progress Trellis task after verifying all five acceptance criteria against the tree, and recorded the verification rule as a thinking guide.

### Main Changes

- Verified all five acceptance criteria of 07-28-consolidate-shared-script-helpers against the working tree rather than commit messages, then archived it to .trellis/tasks/archive/2026-08/ with status completed.
- Established that a git log --grep for finding IDs is unsound evidence: A-046 matched dde46efd only because that commit's body cross-references it while describing a different task's work.
- Corrected the close-out's provenance claim after Copilot's suppressed review comment: commits 1-2 shipped under this task, but commits 3-4 were split into 08-05-consolidate-state-root-resolution and 08-05-consolidate-git-invocation, which own AC1 and AC4 and are themselves completed.
- Drafted a 'When Closing Out a Task Whose Work Already Landed' section for .trellis/spec/guides/index.md, then moved it off this branch: a completion finalization delta must contain only bookkeeping paths, and final-bundle rejected the spec file with bundle_scope_invalid ("finalization delta contains a non-bookkeeping path"). The archive commit landed before the spec work here, so no captured base could both include the archive move and exclude the spec file; without force-push the fix is to ship the guide separately.


### Git Commits

| Hash | Message |
|------|---------|
| `b4eb2d9f` | chore(task): archive 07-28-consolidate-shared-script-helpers |
| `e3ac3f32` | docs(spec): record the verify-against-the-tree rule for task close-outs |
| `50095bcf` | fix(task): correct how the close-out describes what this task delivered |

### Testing

- [OK] make check exit 0; 66, 103, 132, and 85 tests across four suites, all OK
- [OK] Review preflight: 0 failure(s), 0 warning(s)
- [OK] sd-review scope=pr attempt 2: status ready, check passed, local receipt clean
- [OK] Copilot round 2 on head 50095bcf: no new comments, no suppressed entries, commit_id equals head

### Status

[OK] **Completed**

### Next Steps

- None - task complete

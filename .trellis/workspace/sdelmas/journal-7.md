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

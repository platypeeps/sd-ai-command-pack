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

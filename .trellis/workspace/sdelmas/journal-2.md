# Journal - sdelmas (Part 2)

> Continuation from `journal-1.md` (archived at ~2000 lines)
> Started: 2026-07-07

---



## Session 50: KB runtime artifact exclusion hardening

**Date**: 2026-07-07
**Task**: KB runtime artifact exclusion hardening
**Branch**: `codex/kb-runtime-exclusion-hardening`

### Summary

Implemented Trellis task 07-06-kb-runtime-exclusion-hardening (PR #45's highest-priority follow-up). The Obsidian KB updater's is_excluded only knew literal part names plus .trellis/workspace, so local Trellis runtime state leaked into generated output: a gitignored .trellis/.backup-<timestamp> copy of agents.md mapped into Other Documentation (breaking --check with 'is not current'), and the new regression test showed .trellis/worktrees checkouts leaking as Package Documentation. is_excluded now path-aware excludes .backup-* parts, .runtime parts, and worktrees under .trellis, while durable spec/tasks/workflow knowledge stays eligible. Shipped as PR #51: Copilot reviewed with no comments, CI green.

### Main Changes

- Hardened is_excluded in update-spec-kb (both copies) against Trellis backup/runtime/worktree artifacts
- Added RED-verified regression test covering leaks and durable-doc inclusion plus deterministic --check


### Git Commits

| Hash | Message |
|------|---------|
| `8098d5a` | fix: exclude Trellis runtime and backup artifacts from KB source discovery |

### Testing

- [OK] 301 unittest tests green; full-check exit 0; CI green 3.10/3.13; template twin byte-identical

### Status

[OK] **Completed**

### Next Steps

- Continue set with 07-06-reconcile-legacy-cleanup-spec then 07-06-full-check-kb-freshness-gate

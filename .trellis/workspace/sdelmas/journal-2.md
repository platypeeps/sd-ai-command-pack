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


## Session 51: Legacy cleanup spec reconciliation

**Date**: 2026-07-07
**Task**: Legacy cleanup spec reconciliation
**Branch**: `codex/reconcile-legacy-cleanup-spec`

### Summary

Implemented Trellis task 07-06-reconcile-legacy-cleanup-spec (HIGH architecture finding). The backend spec still mandated the install-time legacy-conflict/obsolete-conflict cleanup pipeline deleted at pack 0.4.0. Decision recorded: the removal was deliberate; the advisory-only model is the documented contract. Replaced the two dead spec sections with Legacy And Obsolete Artifact Advisories, fixed the stale status bullets in logging-guidelines (now documenting the real symlink-conflict status) and quality-guidelines, added the adopted Silent Paths Must Say Why convention, and completed the audit's advisories: LEGACY_PACK_PATHS 11 to 33 entries and LEGACY_PACK_REFERENCES extended with rename-era tokens after Copilot round 1 flagged the wording/coverage mismatch. Round 2 clean, CI green. Shipped as PR #52.

### Main Changes

- Rewrote legacy/obsolete spec sections to the advisory model across three backend spec files and added the silent-paths convention
- Completed rename-era advisory coverage in the install audit (paths and reference tokens, both copies) with fixture and completeness-pin tests


### Git Commits

| Hash | Message |
|------|---------|
| `07d81c3` | fix: reconcile legacy-cleanup spec with advisory-only model and complete rename-era advisories |
| `d4f886d` | fix: address review feedback |

### Testing

- [OK] 303 tests green; full-check exit 0; CI green 3.10/3.13; template twin byte-identical

### Status

[OK] **Completed**

### Next Steps

- Final task of the set: 07-06-full-check-kb-freshness-gate


## Session 52: Full-check KB freshness gate

**Date**: 2026-07-07
**Task**: Full-check KB freshness gate
**Branch**: `codex/full-check-kb-freshness-gate`

### Summary

Implemented Trellis task 07-06-full-check-kb-freshness-gate, the last of the three-task set. Full-check previously passed while update-spec-kb --check failed, letting stale generated .obsidian-kb output ship. Added a KB freshness lane after the install audit following the existing lane conventions: SD_AI_COMMAND_PACK_FULL_CHECK_KB defaults to auto (checks only when a generated .obsidian-kb exists, skips with an explicit reason otherwise per the silent-paths convention), 0 skips, required fails when unavailable; stale output fails with the exact refresh command. Documented in README, the installed guide (env-var drift gate satisfied), and the sd-full-check skill; four-state tests. Sequenced after the KB exclusion hardening as required. Copilot round 1: two comments (run-helper consistency, env-pinned test helper), fixed; round 2 clean. Notably the lane made its first real catch during its own PR cycle: PRD-ticking edits staled this repo's KB and the gate failed until the documented refresh was run. Shipped as PR #53.

### Main Changes

- Added run_sd_ai_command_pack_kb_freshness_check lane to full-check (both copies) wired after the install audit
- Documented SD_AI_COMMAND_PACK_FULL_CHECK_KB across README, installed guide, and sd-full-check skill (twins byte-identical); added four-state lane tests


### Git Commits

| Hash | Message |
|------|---------|
| `889cd90` | feat: add Obsidian KB freshness lane to full-check |
| `e0c80df` | fix: address review feedback |

### Testing

- [OK] 305 tests green; shellcheck clean; full-check exit 0 with the new lane live; CI green 3.10/3.13

### Status

[OK] **Completed**

### Next Steps

- Set complete; remaining top candidates: introduce-platform-registry (check upstream mindfold-ai/Trellis issue 396 first) and installer-module-decomposition


## Session 53: Platform registry consolidation

**Date**: 2026-07-07
**Task**: Platform registry consolidation
**Branch**: `codex/introduce-platform-registry`

### Summary

Implemented Trellis task 07-06-introduce-platform-registry (HIGH architecture finding, the largest backlog item). PLATFORM_REGISTRY in install.py is now the single source of truth (one row per platform: directory, markers, init flag, gitignore group, Trellis local-only paths); all six per-platform tables derive from it, verified byte-identical to the pre-registry literals via snapshot comparison so consumer managed blocks see zero churn. Fixed the zcode-via-codex activation bug with a markers-under-own-directory invariant. Extended scanner coverage to all 16 platforms: audit PACK_FILE_PATTERNS 12 to 31, REFERENCE_SCAN_BASES complete, review-scope runtime paths from registry data. Added marker-miss hints and the manifest-less platform note; spec references the registry. Four Copilot rounds, each finding real: entry-level registry-driven coverage test (codex escaped via the manifest-files gate), five missing settings/config runtime paths, an overpromising header comment now test-enforced via order-tuple invariants, and the best catch - collect_pack_like_files walked a hardcoded bases list so the new patterns were unreachable there; scan bases now derive from the patterns themselves. Shipped as PR #54.

### Main Changes

- Replaced six parallel per-platform tables with PLATFORM_REGISTRY and derivations (byte-identical output)
- Extended audit and review-scope coverage to all platforms with registry-driven consistency tests; derived audit scan bases from patterns
- Added marker-miss hints, manifest-less platform note, zcode-owned markers, and registry-referencing spec


### Git Commits

| Hash | Message |
|------|---------|
| `45aedd9` | feat: introduce single platform registry and extend scanner coverage to all platforms |
| `a4cb2a5` | fix: address review feedback |
| `e7077a7` | fix: address review feedback round 2 |
| `15055d2` | fix: address review feedback round 3 |

### Testing

- [OK] 310 tests green; 100% install.py coverage; full-check exit 0; shellcheck clean; CI green 3.10/3.13

### Status

[OK] **Completed**

### Next Steps

- Registry landed; installer-module-decomposition can now build on it

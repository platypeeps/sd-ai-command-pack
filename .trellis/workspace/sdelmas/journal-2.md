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


## Session 54: Installer package decomposition

**Date**: 2026-07-07
**Task**: Installer package decomposition
**Branch**: `codex/installer-module-decomposition`

### Summary

Implemented Trellis task 07-06-installer-module-decomposition per its design.md. install.py went from 2,300 lines to a 330-line CLI entry with the implementation in a sibling installer/ package of six modules in one-way dependency order (registry, manifest, fileops, provenance, localonly, removal), every module under the 800-line guideline. Pure mechanical movement verified by the unchanged behavioral suite; the 100% coverage gate was deliberately widened to the whole package (1,007 statements, 0 missed) and CI bandit gained the installer target. Test churn confined to nine patch-target retargets the move semantically required. Three Copilot rounds: a keys() explicitness nit and design.md drift (both fixed), then a symlink-execution concern that turned out to be a false premise - CPython resolves script symlinks for sys.path[0], proven when the coverage gate flagged the proposed guard's branch as permanently dead; the guard was dropped, the symlink regression test kept, and the thread corrected on record. Shipped as PR #55.

### Main Changes

- Split install.py into installer/{registry,manifest,fileops,provenance,localonly,removal} with a thin re-exporting entry
- Widened .coveragerc to the package with a [paths] alias for the symlink subprocess; bandit target added; symlink execution test-pinned


### Git Commits

| Hash | Message |
|------|---------|
| `92822f4` | refactor: decompose install.py into an installer package with a thin CLI entry |
| `3a912cc` | fix: address review feedback |
| `8004349` | fix: address review feedback round 2 - pin symlink execution instead of dead guard |

### Testing

- [OK] 311 tests green; coverage --fail-under=100 across entry plus package; full-check exit 0; CI green 3.10/3.13

### Status

[OK] **Completed**

### Next Steps

- Remaining top candidates: harden-manifest-loading (now against installer/manifest.py) and the coverage tasks


## Session 55: Manifest loading hardening

**Date**: 2026-07-08
**Task**: Manifest loading hardening
**Branch**: `codex/harden-manifest-loading`

### Summary

Implemented Trellis task 07-06-harden-manifest-loading against the new installer/manifest.py. load_manifest now converts JSON parse errors, non-object top-level JSON, non-list files values, and per-entry missing-field/shape errors into single-line error messages naming the entry; validate_manifest enforces the closed KNOWN_MANIFEST_KINDS set (via the shared MANAGED_BLOCK_KIND constant) so a misspelled kind can never silently downgrade a managed-block entry into a plain-copy clobber; manifest.json carries schemaVersion 1 with newer-major rejection and type checks; requiresTrellis is wired into the Trellis-repo precondition with boolean type validation and an end-to-end opt-out test. Spec gained a Manifest Schema Contract section. Four Copilot rounds: top-level shape gaps plus matching test rows, requiresTrellis type check, constant reuse and doc wording; round 4 clean. Shipped as PR #56.

### Main Changes

- Hardened load_manifest/validate_manifest with table-driven failure-mode tests; schemaVersion and requiresTrellis wiring
- Documented the Manifest Schema Contract in the backend spec


### Git Commits

| Hash | Message |
|------|---------|
| `0e71416` | fix: harden manifest loading with schema version, kind validation, and clean errors |
| `9ab19f8` | fix: address review feedback |
| `f280bd0` | fix: address review feedback round 2 |
| `767f999` | fix: address review feedback round 3 |

### Testing

- [OK] 315 tests green; coverage 100% across the installer package; full-check exit 0; CI green 3.10/3.13

### Status

[OK] **Completed**

### Next Steps

- Continue the five-task set with enable-branch-coverage


## Session 56: Branch coverage gate

**Date**: 2026-07-08
**Task**: Branch coverage gate
**Branch**: `codex/enable-branch-coverage`

### Summary

Implemented Trellis task 07-06-enable-branch-coverage. The 100 percent gate was line-only; branch=True is now set in .coveragerc with fail_under=100 kept, and the measured 16 partial branches across fileops, localonly, manifest, provenance, and removal each received a focused test for the untaken direction (block merges with END markers at EOF and prefix newline variants, dry-run updated paths that must not write, system_exit_detail without the error prefix, receipts with comments and blanks, absolute git exclude paths, run_diff_check without paths, trellis init failure with empty output, may_remove_pack_file without a manifest file, and the remove flow passing a clean diff check). No pragmas. Final: 1,033 statements plus 417 branches, zero missed, zero partial. Four Copilot rounds of small test-quality nits, all applied; the task.json in_progress observation was rebutted as intentional lifecycle state. Shipped as PR #57.

### Main Changes

- Enabled branch coverage with fail_under 100 and closed all 16 partial branches with focused tests


### Git Commits

| Hash | Message |
|------|---------|
| `c270856` | test: enable branch coverage and close all 16 partial branches |
| `9bf9e68` | fix: address review feedback |
| `de829c4` | fix: address review feedback round 2 |
| `1323edc` | fix: address review feedback round 3 |

### Testing

- [OK] 319 tests green; coverage 100 percent lines and branches; full-check exit 0; CI green 3.10/3.13

### Status

[OK] **Completed**

### Next Steps

- Continue the set with measure-scripts-coverage


## Session 57: Shipped-scripts coverage measurement

**Date**: 2026-07-08
**Task**: Shipped-scripts coverage measurement
**Branch**: `codex/measure-scripts-coverage`

### Summary

Implemented Trellis task 07-06-measure-scripts-coverage. The ~1,800 statements of shipped scripts helpers now have measured coverage with a provisional 76 percent CI gate alongside the untouched installer 100 percent gate (default report scope stays installer-only via [report] include; the scripts step overrides on the CLI). The more valuable half was the en-route discovery: subprocess coverage collection had silently no-oped for every test that set cwd to a temp repo, because the relative COVERAGE_PROCESS_START resolved against the subprocess cwd and shards were written there and destroyed - the first honest measurement was 29 percent. The invocation now uses absolute COVERAGE_PROCESS_START and COVERAGE_FILE plus runner-level PYTHONPATH (prepending, preserving any existing value) so every subprocess is collected without per-test env wiring. Truthful baseline 76 percent: audit 95, update-spec-kb 81, pr-body-scope 76, record-session 74, review-learnings 58 (the ratchet laggard). Three Copilot rounds: PYTHONPATH clobber in two surfaces plus the stale CI-pinning test (the round-1 CI failure), stale README paragraph, and the bare-report footgun; all fixed with empirical verification. Shipped as PR #58.

### Main Changes

- Measured shipped scripts coverage with [paths] aliasing and precise includes; two-gate CI reports; fixed subprocess shard collection with absolute env paths


### Git Commits

| Hash | Message |
|------|---------|
| `291001d` | test: measure shipped-scripts coverage with a provisional gate and fix subprocess collection |
| `f5d2db8` | fix: address review feedback |
| `537820e` | fix: address review feedback round 2 |

### Testing

- [OK] 319 tests green; installer gate 100 percent lines+branches; scripts gate 76 percent; full-check exit 0; CI green

### Status

[OK] **Completed**

### Next Steps

- Continue the set with audit-installer-reporting-fixes


## Session 58: Audit and installer reporting fixes

**Date**: 2026-07-08
**Task**: Audit and installer reporting fixes
**Branch**: `codex/audit-installer-reporting-fixes`

### Summary

Implemented Trellis task 07-06-audit-installer-reporting-fixes: six operator-facing reporting defects. Audit advisories now print before the failure block (ordering pinned by test); an unreadable receipt on the install path yields a clean single-line error instead of a PermissionError traceback; a fresh gitignore reports created; git diff --check failures no longer leak git's exit code for non-git Trellis targets - after round-4 review feedback the blanket 128/129 handling became a precise rev-parse --is-inside-work-tree gate so real git failures inside a work tree propagate untouched; the audit env kill-switch runs after argparse so --help works while disabled; EACCES targets report cannot-be-inspected with stable path-free errno detail instead of the misleading missing (one pre-existing test pinning the old message updated). Five Copilot rounds, closing exactly at the limit with round 5 clean. Shipped as PR #59.

### Main Changes

- Fixed six reporting/error-path defects across the audit script (both copies) and installer fileops/provenance
- Added six regression tests including warning-order and work-tree-gate coverage


### Git Commits

| Hash | Message |
|------|---------|
| `c1bae00` | fix: audit and installer reporting gaps |
| `12ff5be` | fix: address review feedback |
| `d005f30` | fix: address review feedback round 2 |
| `be84a2e` | fix: address review feedback round 3 |
| `a6c59d6` | fix: address review feedback round 4 |

### Testing

- [OK] 325 tests green; installer gate 100 percent lines+branches; scripts gate 76 percent; full-check exit 0; CI green

### Status

[OK] **Completed**

### Next Steps

- Final task of the set: housekeeping-recorder-robustness

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


## Session 59: Helper robustness bundle

**Date**: 2026-07-08
**Task**: Helper robustness bundle
**Branch**: `codex/housekeeping-recorder-robustness`

### Summary

Implemented Trellis task 07-06-housekeeping-recorder-robustness, closing the five-task set. Eight fail-open/silent-degrade defects fixed across four shipped helpers: housekeeping's clean-tree check fails closed on git failures, dash-prefixed --remote values are rejected and the SC2295 expansion quoted, gh's literal null no longer short-circuits default-branch detection; the recorder raises a clean error on git status failures and parses renames via porcelain -z (round-1 feedback replaced quote-stripping with NUL parsing, and round-3's order concern was rebutted with the passing git-mv regression plus an explicit negative assertion); learnings tolerate non-object GraphQL payloads, neutralize managed markers in every rendered field including Finding entries (round-2 caught the parallel surface), and say why when no base ref resolves; KB refresh exits 3 on conflicts with exit codes documented (two pre-existing tests pinning old silent-success behavior updated). Five Copilot rounds closing clean at the limit. Shipped as PR #60.

### Main Changes

- Fixed eight robustness defects across housekeeping, record-session, review-learnings, and update-spec-kb (all twins byte-identical)
- Added eight-plus regression tests including awk-extracted shell probes and all-field marker injection coverage


### Git Commits

| Hash | Message |
|------|---------|
| `7784cd6` | fix: robustness bundle for housekeeping, recorder, learnings, and KB scripts |
| `465fcdb` | fix: address review feedback |
| `67d5fb6` | fix: address review feedback round 2 |
| `721fb5a` | fix: address review feedback round 3 |
| `3a5fec0` | fix: address review feedback round 4 |

### Testing

- [OK] 333 tests green; installer gate 100 percent; scripts gate 78 percent; housekeeping self-test green; shellcheck clean; full-check exit 0; CI green

### Status

[OK] **Completed**

### Next Steps

- Five-task set complete; remaining backlog is docs/tooling/process plus the fleet-loop and preflight-mjs tasks


## Session 60: Release versioning process

**Date**: 2026-07-08
**Task**: Release versioning process
**Branch**: `codex/release-0.6.0`

### Summary

Prepared the 0.6.0 release process update, added a changelog and README release instructions, and introduced a full-check guard that requires manifest version bumps for shipped payload changes.

### Main Changes

- Bumped sd-ai-command-pack manifest to 0.6.0 and started CHANGELOG.md with the accumulated shipped payload changes.
- Documented the release sequence, post-merge tagging, and fleet refresh expectations in README.md.
- Added and tested a pack-source full-check guard that detects shipped payload changes without a manifest version bump.


### Git Commits

| Hash | Message |
|------|---------|
| `deb4b5d` | chore: release sd-ai-command-pack 0.6.0 |

### Testing

- [OK] Focused release guard tests passed.
- [OK] Full unit suite passed: 344 tests.
- [OK] Coverage gates passed: installer 100%, shipped Python helpers 79% over the 76% floor.
- [OK] Full-check passed with Prism and Gito disabled; GitHub PR checks passed for PR #62.

### Status

[OK] **Completed**

### Next Steps

- None - task complete

## Session 61: PR-body scope bot actor exemption

**Date**: 2026-07-08
**Task**: PR-body scope bot actor exemption
**Branch**: `sdelmas/pr-body-scope-bot-actor-exemption`

### Summary

Reconciled the completed PR-body scope bot-actor task after PR #61 had already merged. The shipped checker now accepts an explicit or env-provided GitHub actor and skips strict PR-body scope validation for [bot]-suffixed automated authors while preserving strict behavior for humans and unspecified actors.

### Main Changes

- Added actor resolution to sd-ai-command-pack-pr-body-scope.py through --actor and SD_AI_COMMAND_PACK_PR_BODY_SCOPE_ACTOR with flag-over-env precedence and trimming.
- Exempted GitHub bot logins ending in [bot] from strict PR-body scope validation so Dependabot/Renovate-style PRs are not blocked by human scope headings.
- Updated README, installed docs, template twins, manifest version, and added focused behavioral tests for bot and human actor paths.


### Git Commits

| Hash | Message |
|------|---------|
| `7238a44` | feat: exempt automated PR authors from pr-body-scope check |

### Testing

- [OK] PR #61 merged at 2026-07-08T19:17:48Z with CI green.
- [OK] tests/test_pr_body_scope.py covers bot suffix matching, actor resolution precedence, bot skip behavior, and strict human/no-actor behavior.
- [OK] Source/template parity is covered by existing pack sync tests.

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 62: Trellis PR consent rule

**Date**: 2026-07-08
**Task**: Trellis PR consent rule
**Branch**: `codex/trellis-pr-consent-rule`

### Summary

Documented the maintainer rule that agents must not create upstream Trellis pull requests without explicit user approval for that specific PR. Published it through PR #64, addressed Copilot's wording/formatting comment, reran the deterministic full-check with Prism and Gito disabled, and confirmed GitHub Actions passed.

### Main Changes

- Added a maintainer rule to `AGENTS.md` outside the Trellis-managed block so
  future `trellis update` runs preserve it.
- Clarified after Copilot review that the required consent must come from the
  user for the specific upstream `Trellis` PR.
- Kept the rule explicit that `sd-ai-command-pack` work should produce a
  paste-ready handoff when a `Trellis`-owned change is found.

### Git Commits

| Hash | Message |
|------|---------|
| `be9249e` | docs: require consent for trellis prs |
| `9c2b9a1` | docs: clarify trellis pr consent rule |

### Testing

- [OK] `SD_AI_COMMAND_PACK_FULL_CHECK_PRISM=0 SD_AI_COMMAND_PACK_FULL_CHECK_GITO=0 bash scripts/sd-ai-command-pack-full-check.sh`
- [OK] GitHub Actions passed on PR #64: security, unittest (3.10),
  unittest (3.13), and CI Result.
- [OK] Copilot review round 2 reported no new comments after the wording fix.

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 63: Add backlog work loop command

**Date**: 2026-07-08
**Task**: Add backlog work loop command
**Branch**: `codex/backlog-work-loop-command`

### Summary

Added sd-work-backlog as a sequential Trellis backlog runner, shipped platform adapters, updated docs/specs/tests, bumped the pack to 0.7.0, and validated the PR gate.

### Main Changes

- Added `sd-work-backlog` as a shared SD skill plus thin platform adapters.
- Updated manifest mappings, docs, Trellis specs, and installer coverage for
  the new command.
- Bumped the pack manifest to `0.7.0` for the shipped command payload.

### Git Commits

| Hash | Message |
|------|---------|
| `07f6f4e` | (see git log) |

### Testing

- [OK] Generic skill validator for `sd-work-backlog`.
- [OK] `python3 -m unittest discover -s tests`.
- [OK] `SD_AI_COMMAND_PACK_FULL_CHECK_PRISM=0 SD_AI_COMMAND_PACK_FULL_CHECK_GITO=0 bash scripts/sd-ai-command-pack-full-check.sh`.

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 64: Harden review preflight entry handling

**Date**: 2026-07-08
**Task**: Harden review preflight entry handling
**Branch**: `codex/preflight-mjs-hardening`

### Summary

Hardened the review-preflight Node script so symlink invocation runs checks, Node versions below 16.9 receive a clear error, copied-surface detection includes untracked files, workspace index parsing tolerates trailing whitespace, and the runtime contract is documented in specs/docs with tests.

### Main Changes

- Hardened `sd-ai-command-pack-review-preflight.mjs` so symlink invocation
  resolves real paths and runs the preflight checks.
- Added a clear Node 16.9 minimum-version error path and removed syntax/runtime
  assumptions that would hide that message on older supported-parser runtimes.
- Included untracked files in copied-surface detection, tolerated trailing
  whitespace in workspace index rows, and documented regular-file-only docs
  scanning.
- Added focused tests, updated docs/specs, and bumped shipped payload metadata
  to 0.7.1.

### Git Commits

| Hash | Message |
|------|---------|
| `533c0db` | (see git log) |

### Testing

- [OK] `node --check scripts/sd-ai-command-pack-review-preflight.mjs`
- [OK] `node --check templates/scripts/sd-ai-command-pack-review-preflight.mjs`
- [OK] Focused review-preflight unittest cases.
- [OK] `.venv/bin/python -m unittest discover -s tests`
- [OK] `git diff --check`
- [OK] `git diff --cached --check`

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 65: Archive task metadata backfill

**Date**: 2026-07-08
**Task**: Archive task metadata backfill
**Branch**: `codex/archive-task-metadata-backfill`

### Summary

Backfilled archived Trellis task descriptions and added a regression guard before PR #68 review.

### Main Changes

- Backfilled descriptions for the three archived recorder tasks with blank metadata.
- Added a regression test requiring completed archived PRD-backed tasks to keep non-empty descriptions.
- Archived 07-06-archive-task-metadata-backfill after PR #68 review reached clean CI and no new Copilot comments.
- Tightened the archive-description guard to skip symlinked `task.json` and
  `prd.md` files, with regression coverage for the symlink case.


### Git Commits

| Hash | Message |
|------|---------|
| `5109ef2` | fix: backfill archived task descriptions |
| `8f632a2` | chore(task): archive metadata backfill |
| `dba44a3` | fix: skip symlinked archived task files |

### Testing

- [OK] .venv/bin/python -m unittest tests.test_install.InstallTests.test_archived_prd_backed_tasks_have_descriptions
- [OK] python3 ./.trellis/scripts/task.py list-archive
- [OK] .venv/bin/python -m unittest tests.test_install.InstallTests.test_archived_prd_backed_tasks_have_descriptions tests.test_install.InstallTests.test_archived_description_guard_skips_symlinked_task_files
- [OK] git diff --check
- [OK] .venv/bin/python -m unittest discover -s tests
- [OK] SD_AI_COMMAND_PACK_FULL_CHECK_PRISM=0 SD_AI_COMMAND_PACK_FULL_CHECK_GITO=0 bash scripts/sd-ai-command-pack-full-check.sh
- [OK] GitHub CI passed on PR #68: security, unittest (3.10), unittest (3.13), CI Result

### Status

[OK] **Completed**

### Next Steps

- Continue sd-work-backlog with the next actionable implementation-ready task.


## Session 66: Fix documentation accuracy gaps

**Date**: 2026-07-08
**Task**: Fix documentation accuracy gaps
**Branch**: `codex/docs-accuracy-fixes`

### Summary

Fixed shipped guide anchors, documented skill-only review variables, and widened the pack-source env-var docs gate for PR #69.

### Main Changes

- Fixed installed-guide quick links and documented SD_AI_COMMAND_PACK_REVIEW_PR_SELECTOR plus literal Semgrep local-review example variables.
- Widened the pack-source full-check env-var documentation gate so shipped skill templates and shipped scripts are both checked.
- Added maintainer guidance that templates/** are the shipped payload source of truth, replaced stale-prone README platform lists, bumped the manifest to 0.7.2, and archived 07-06-docs-accuracy-fixes.


### Git Commits

| Hash | Message |
|------|---------|
| `c3f3314` | fix: close docs accuracy gaps |
| `dea9e40` | chore(task): archive docs accuracy fixes |

### Testing

- [OK] .venv/bin/python -m unittest tests.test_install.InstallTests.test_shipped_env_vars_are_documented tests.test_install.InstallTests.test_full_check_script_runs_pack_source_drift_gates tests.test_install.InstallTests.test_pack_source_drift_gate_rejects_undocumented_skill_env_vars tests.test_install.InstallTests.test_tracked_pack_targets_match_templates
- [OK] python3 anchor sanity check for README.md, docs/SD_AI_COMMAND_PACK.md, templates/docs/SD_AI_COMMAND_PACK.md
- [OK] bash -n scripts/sd-ai-command-pack-full-check.sh && bash -n templates/scripts/sd-ai-command-pack-full-check.sh && git diff --check
- [OK] .venv/bin/python scripts/sd-ai-command-pack-update-spec-kb.py
- [OK] .venv/bin/python -m unittest discover -s tests
- [OK] SD_AI_COMMAND_PACK_FULL_CHECK_PRISM=0 SD_AI_COMMAND_PACK_FULL_CHECK_GITO=0 bash scripts/sd-ai-command-pack-full-check.sh
- [OK] GitHub CI passed on PR #69: security, unittest (3.10), unittest (3.13), CI Result

### Status

[OK] **Completed**

### Next Steps

- Continue sd-work-backlog with the next actionable implementation-ready task.


## Session 67: CI skip backstop and lint lane

**Date**: 2026-07-08
**Task**: CI skip backstop and lint lane
**Branch**: `codex/ci-skip-backstop-lint-lane`

### Summary

Added CI protections for skipped tests, reproducible Ruff/JavaScript linting, and a macOS unittest leg for sd-ai-command-pack.

### Main Changes

- Added a CI unittest matrix with Ubuntu Python 3.10/3.13 and macOS Python 3.13 plus a skip-summary backstop that fails on skipped tests.
- Pinned Ruff in dev dependencies, added pyproject Ruff config, and introduced a dedicated CI lint lane for Ruff and review-preflight JavaScript syntax checks.
- Documented the local lint workflow and captured the CI contract in Trellis quality guidelines and the task PRD.
- Addressed Copilot feedback by making the Ruff dependency test assert a pinned version pattern instead of a hard-coded exact version.


### Git Commits

| Hash | Message |
|------|---------|
| `c4ea71b` | ci: add skip backstop and lint lane |
| `0d33cba` | chore(task): confirm CI hardening checks |
| `ffa8c5a` | test: loosen Ruff pin assertion |

### Testing

- [OK] .venv/bin/python -m unittest tests.test_install.InstallTests.test_coverage_dependency_is_declared_and_used_by_ci
- [OK] .venv/bin/python -m unittest discover -s tests
- [OK] .venv/bin/python -m ruff check install.py installer scripts templates/scripts tests
- [OK] node --check scripts/sd-ai-command-pack-review-preflight.mjs
- [OK] node --check templates/scripts/sd-ai-command-pack-review-preflight.mjs
- [OK] git diff --check
- [OK] SD_AI_COMMAND_PACK_FULL_CHECK_PRISM=0 SD_AI_COMMAND_PACK_FULL_CHECK_GITO=0 bash scripts/sd-ai-command-pack-full-check.sh
- [OK] GitHub PR #70 CI Result, lint, security, Ubuntu unittest, and macOS unittest checks passed

### Status

[OK] **Completed**

### Next Steps

- Merge PR #70 and run housekeeping; no task-specific follow-up remains.


## Session 68: Contributor workflow baseline

**Date**: 2026-07-08
**Task**: Contributor workflow baseline
**Branch**: `codex/contributor-experience-baseline`

### Summary

Added a Makefile and CONTRIBUTING workflow, full-check hook warning, regression coverage, and shipped manifest/changelog updates for the contributor baseline task.

### Main Changes

- Added Makefile targets for setup, hooks, test, lint, audit, full-check, and check with Homebrew Python 3.13 preference.
- Added CONTRIBUTING.md and README pointers for setup, verification, manifest bumping, template source-of-truth, self-sync, and spec references.
- Updated source and shipped full-check scripts to warn when the pack source checkout has not armed .githooks.
- Pinned the OpenCode plugin dependency and bumped the shipped manifest to 0.7.3.


### Git Commits

| Hash | Message |
|------|---------|
| `eca1f9d` | chore: add contributor workflow baseline |

### Testing

- [OK] Focused contributor/full-check unittest coverage passed.
- [OK] Obsidian KB refresh completed with 182 copies and no conflicts.
- [OK] SD full-check passed with Prism and Gito disabled.
- [OK] GitHub CI passed on PR #71.

### Status

[OK] **Completed**

### Next Steps

- Continue the sd-work-backlog loop with the next actionable Trellis task after housekeeping.


## Session 69: Contributor workflow review follow-up

**Date**: 2026-07-08
**Task**: Contributor workflow review follow-up
**Branch**: `codex/contributor-experience-baseline`

### Summary

Addressed Copilot review feedback by making the Makefile Node syntax checks optional for Python-only contributor environments.

### Main Changes

- Guarded the Makefile review-preflight JavaScript syntax checks behind command -v node and emit a warning when Node is unavailable.
- Updated README and CONTRIBUTING.md to document optional Node/ShellCheck-style warnings for local maintainer checks.
- Extended contributor workflow regression coverage to assert the optional Node warning path is documented.


### Git Commits

| Hash | Message |
|------|---------|
| `72b0dfa` | fix: make node lint optional |

### Testing

- [OK] Focused contributor/full-check unittest coverage passed.
- [OK] make lint passes in a Python-only PATH and warns that Node/ShellCheck are unavailable.
- [OK] SD full-check passed with Prism and Gito disabled.

### Status

[OK] **Completed**

### Next Steps

- Push the review fix, request a fresh Copilot review, and merge after CI and review threads are clean.


## Session 70: README restructure and docs dedup

**Date**: 2026-07-08
**Task**: README restructure and docs dedup
**Branch**: `codex/readme-restructure-dedup`

### Summary

Restructured README into navigable overview, commands, install, and verify sections while moving duplicated guide details back to the installed guide.

### Main Changes

- Added README Overview and Commands sections with per-command headings and complete quick links.
- Removed duplicated managed-block examples, PR-body scope examples, local-review exclusions, Obsidian vault copy details, and helper internals from README in favor of docs/SD_AI_COMMAND_PACK.md links.
- Added sandbox cache exports to the README smoke test and updated regression coverage for the README/docs boundary.


### Git Commits

| Hash | Message |
|------|---------|
| `7a934f0` | docs: restructure readme and dedupe guide details |

### Testing

- [OK] Focused README/docs tests passed.
- [OK] Full unittest suite passed: 354 tests.
- [OK] KB refresh completed with 182 copies and no conflicts.
- [OK] SD full-check passed with Prism and Gito disabled.

### Status

[OK] **Completed**

### Next Steps

- Merge PR #72 and continue the sd-work-backlog loop with the next actionable Trellis task.


## Session 71: Deduplicate shell helpers across review scripts

**Date**: 2026-07-09
**Task**: Deduplicate shell helpers across review scripts
**Branch**: `codex/dedupe-shared-shell-helpers`

### Summary

Extracted duplicated Bash helpers into a shipped shared helper library and aligned full-check, review-local, and review-scope around the shared implementation.

### Main Changes

- Added scripts/sd-ai-command-pack-shell-lib.sh and template twin for shared review-scan exclusions, base-ref discovery, Gito env loading, uv cache setup, and HTTP-429 retry handling.
- Updated full-check, review-local, and review-scope to source the helper; full-check now uses bash -c for configured preflight and shared uv setup before Gito.
- Bumped manifest to 0.7.4 and updated docs, PR-body scope, install audit, and regression tests for the new shipped helper.
- Addressed Copilot feedback by clarifying the helper caller contract for REPO_ROOT, warn(), and section().
- Addressed follow-up review feedback by registering Gito temp output files with review-local cleanup when the optional cleanup array is present.


### Git Commits

| Hash | Message |
|------|---------|
| `81774bb` | refactor: share shell helpers across review scripts |
| `63a9fa2` | docs: clarify shell helper caller contract |
| `6e00e5e` | fix: register gito temp files for cleanup |

### Testing

- [OK] Focused helper/Gito/full-check tests passed: 17 tests.
- [OK] Full unittest suite passed: 359 tests.
- [OK] Shellcheck passed for changed shell scripts and template twins.
- [OK] KB refresh completed with 182 copies and no conflicts.
- [OK] SD full-check passed with Prism and Gito disabled.
- [OK] PR #73 CI passed after review fix: lint, security, Ubuntu 3.10/3.13, macOS 3.13, and CI Result.
- [OK] Focused temp cleanup/Gito follow-up tests passed.

### Status

[OK] **Completed**

### Next Steps

- Merge PR #73 and continue the sd-work-backlog loop with the next actionable Trellis task.


## Session 72: Move shared command templates to neutral source

**Date**: 2026-07-09
**Task**: Move shared command templates to neutral source
**Branch**: `codex/neutral-shared-command-templates`

### Summary

Moved generic Markdown command template sources out of Cursor-owned paths and into a neutral shared template directory while preserving installed target paths.

### Main Changes

- Moved twelve generic Markdown command bodies from templates/.cursor/commands/ to templates/.commands/ with byte-identical content.
- Updated Cursor and generic Markdown platform manifest entries to source from templates/.commands/ and bumped the manifest version to 0.7.5.
- Updated frontend/backend specs and installer tests to document and enforce the neutral shared command-source pattern.


### Git Commits

| Hash | Message |
|------|---------|
| `3939202` | refactor: move shared command templates to neutral source |

### Testing

- [OK] Full unit suite passed: 360 tests.
- [OK] Focused manifest/adapter tests passed.
- [OK] Verified moved command bodies are byte-identical to previous Cursor sources from main.
- [OK] Verified no manifest entry sources templates/.cursor/commands/ and 120 entries source templates/.commands/.
- [OK] KB refresh completed with 182 copies and no conflicts.
- [OK] SD full-check passed with Prism and Gito disabled.
- [OK] PR #74 CI passed and Copilot review generated no threads on the implementation commit.

### Status

[OK] **Completed**

### Next Steps

- Merge PR #74 and continue the sd-work-backlog loop with the next actionable Trellis task.


## Session 73: Partition pack test suite by subsystem

**Date**: 2026-07-09
**Task**: Partition pack test suite by subsystem
**Branch**: `codex/partition-pack-test-suite`

### Summary

Split the monolithic installer test suite into focused subsystem modules while preserving discovery, historical unittest node compatibility, and coverage gates.

### Main Changes

- Moved shared installer test fixtures and subprocess helpers into tests/install_test_support.py.
- Split the 351 tests formerly in tests/test_install.py across focused subsystem modules for install core, audit, review-local, full-check, review preflight, review scope, update-spec KB, record-session, housekeeping, removal, generated parity, and pack drift.
- Kept tests/test_install.py as a compatibility facade for historical tests.test_install.InstallTests node IDs without duplicating discovery.
- Updated Trellis specs and the archived task PRD to describe the new test layout and current 360-test baseline.


### Git Commits

| Hash | Message |
|------|---------|
| `64c2fbe` | test: partition pack suite by subsystem |

### Testing

- [OK] PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest discover -s tests (360 tests)
- [OK] PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest tests.test_install.InstallTests.test_archived_prd_backed_tasks_have_descriptions
- [OK] PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest tests.test_full_check.FullCheckTests.test_full_check_script_runs_pack_source_drift_gates
- [OK] .venv/bin/python -m ruff check install.py installer scripts templates/scripts tests
- [OK] git diff --check
- [OK] coverage gates via /private/tmp COVERAGE_FILE: installer 100%, shipped scripts 79% against 76% floor
- [OK] python3 scripts/sd-ai-command-pack-update-spec-kb.py
- [OK] SD_AI_COMMAND_PACK_FULL_CHECK_PRISM=0 SD_AI_COMMAND_PACK_FULL_CHECK_GITO=0 bash scripts/sd-ai-command-pack-full-check.sh

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 74: Add sd-work-designs command

**Date**: 2026-07-09
**Task**: Add sd-work-designs command
**Branch**: `codex/add-sd-work-designs`

### Summary

Added the sd-work-designs command and prepared the remaining backlog tasks with design and implementation artifacts.

### Main Changes

- Added the sd-work-designs shared skill and distributed adapters.
- Registered the command in the manifest, docs, frontend adapter specs, and installer/parity tests.
- Added design and implementation plans for the two remaining active backlog tasks.


### Git Commits

| Hash | Message |
|------|---------|
| `631f1f0` | feat: add sd work designs command |

### Testing

- [OK] PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest tests.test_generated_parity tests.test_install_core
- [OK] PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest discover -s tests
- [OK] .venv/bin/python -m ruff check install.py installer scripts templates/scripts tests
- [OK] python3 scripts/sd-ai-command-pack-update-spec-kb.py
- [OK] SD_AI_COMMAND_PACK_FULL_CHECK_PRISM=0 SD_AI_COMMAND_PACK_FULL_CHECK_GITO=0 bash scripts/sd-ai-command-pack-full-check.sh

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 75: Close fleet refresh loop

**Date**: 2026-07-09
**Task**: Close fleet refresh loop
**Branch**: `codex/close-fleet-refresh-loop`

### Summary

Reconciled the fleet refresh task records, fixed the session-recorder retry duplicate path, and prepared the 0.8.1 patch release.

### Main Changes

- made the session recorder reuse a pending latest same-title journal entry after post-append staging or commit failures
- reconciled fleet-refresh evidence, archived stale rollout acceptance criteria, and rerouted duplicate-session issue 5 away from upstream Trellis
- deduplicated Session 30, documented the recorder retry contract, and bumped the pack to 0.8.1


### Git Commits

| Hash | Message |
|------|---------|
| `050237a` | fix: make session recorder retry-safe |

### Testing

- [OK] PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest tests.test_record_session
- [OK] PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest discover -s tests
- [OK] SD_AI_COMMAND_PACK_FULL_CHECK_PRISM=0 SD_AI_COMMAND_PACK_FULL_CHECK_GITO=0 bash scripts/sd-ai-command-pack-full-check.sh

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 76: Close upstream Trellis issue references

**Date**: 2026-07-09
**Task**: Close upstream Trellis issue references
**Branch**: `codex/file-upstream-trellis-issues`

### Summary

Recorded live upstream Trellis issue state in superseded pack tasks and closed the upstream-issue reference backlog task.

### Main Changes

- linked platform registry, housekeeping/recorder robustness, and archive metadata tasks to the filed upstream Trellis issues
- recorded issue 5 as rerouted locally to the pack duplicate-session fix instead of filed upstream
- marked the upstream issue reference task acceptance criteria complete


### Git Commits

| Hash | Message |
|------|---------|
| `1f24bbb` | chore: close upstream issue reference task |

### Testing

- [OK] gh issue view 394/395/396/397 --repo mindfold-ai/Trellis --json number,title,state,url
- [OK] python3 ./.trellis/scripts/task.py list-archive
- [OK] git diff --check
- [OK] SD_AI_COMMAND_PACK_FULL_CHECK_PRISM=0 SD_AI_COMMAND_PACK_FULL_CHECK_GITO=0 bash scripts/sd-ai-command-pack-full-check.sh

### Status

[OK] **Completed**

### Next Steps

- None - task complete

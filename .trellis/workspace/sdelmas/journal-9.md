# Journal - sdelmas (Part 9)

> Continuation from `journal-8.md` (archived at ~2000 lines)
> Started: 2026-08-17

---



## Session 397: Correct the plugin-path task's scope figures to the whole skill tree

**Date**: 2026-08-17
**Task**: Correct the plugin-path task's scope figures to the whole skill tree
**Branch**: `task/plugin-path-version-split-design`

### Summary

Review of PR #502 found the task's site counts were measured against SKILL.md alone, which the Step 0 enumeration and the Step 4 gate both inherited. Re-derived every count over all .md under .agents/skills and corrected the artifacts, which also dissolved one earlier concern.

### Main Changes

- Class A is 50 occurrences across 22 files in 16 skills; a SKILL.md-only sweep reports 37 and silently skips eight reference and charter documents carrying 13 occurrences
- Bare-name occurrences are 11 rather than 9; the two extra are prose, so the executable count stays at one
- Step 0's script and Step 4's gate now glob *.md rather than SKILL.md, with the reason stated because the narrower glob is the tempting one
- Retracted the C-1 coincidence paragraph: class B is 9 and bare-name is 11, so they are no longer the same number and the explanation was wrong rather than merely unnecessary
- Replaced an executable-bit check that iterated $(ls ...) with a direct glob under nullglob plus a found flag, so no-helpers-at-all is its own diagnosis
- Rephrased four backticked ellipsis paths that the review preflight reads as references to files that do not exist


### Git Commits

| Hash | Message |
|------|---------|
| `2d39a97ca06606b6b2c76bf7a4c5be3296f42e49` | fix(task): count the whole skill tree, not just SKILL.md |

### Testing

- [OK] Counts re-derived from the filesystem for both denominators: SKILL.md 37/9, all .md 50/11
- [OK] Arithmetic reconciles across artifacts: 11 bare-name = 1 executable + 10 named-not-run
- [OK] review-preflight: 0 failures (was 1: prd.md referencing a missing path)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 398: Carry the wider gate scope into design.md

**Date**: 2026-08-17
**Task**: Carry the wider gate scope into design.md
**Branch**: `task/plugin-path-version-split-design`

### Summary

Review of PR #502 found design.md's Gate section still scoped to SKILL.md after implement.md Step 4 had been widened to every *.md under .agents/skills/. Corrected design.md so the two artifacts describe the same gate.

### Main Changes

- design.md's Gate section now globs every *.md under .agents/skills/ and states why the wider glob is load-bearing: eight reference and charter files carry 13 of the 50 class-A occurrences
- Recorded that the previous round's cross-artifact sweep searched for the changed counts but not for the scope wording that produced them, which is why the stale copy survived


### Git Commits

| Hash | Message |
|------|---------|
| `49c877dda0f231e771fb0f9235c7decbfec6a305` | fix(task): carry the wider gate scope into design.md |

### Testing

- [OK] Sweep for SKILL.md-scope statements across all three artifacts: design.md, implement.md Step 0, and implement.md Step 4 now agree on *.md
- [OK] review-preflight: 0 failures

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 399: Make the plugin-path plan able to pass its own gate

**Date**: 2026-08-17
**Task**: Make the plugin-path plan able to pass its own gate
**Branch**: `task/plugin-path-version-split-design`

### Summary

Review of PR #502 found Step 3 and Step 4 contradicted each other: Step 3 kept scripts/-prefixed toolchain operands while the Step 4 gate forbids that prefix anywhere in an executable block, so the converted tree would have failed the gate the plan installs.

### Main Changes

- Step 3 now strips the scripts/ prefix from toolchain operands as well as from the bootstrap, at the cost of one extra edit per operand
- Rejected the narrower alternative of exempting toolchain operands: the exemption would have to distinguish the harmless prefix from the CWD-relative bootstrap that is the defect, leaving a reader unable to tell which scripts/ token is which
- design.md records the tradeoff beside the gate rule, where it would otherwise be re-litigated


### Git Commits

| Hash | Message |
|------|---------|
| `cd70e0d2621235ee2d934639c2e829ae4364d645` | fix(task): make the plan able to pass its own gate |

### Testing

- [OK] Swept all three artifacts for any surviving statement that operands stay unchanged: none
- [OK] review-preflight: 0 failures

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 400: One rule for reaching a pack helper, and a gate that can see every way of breaking it

**Date**: 2026-08-18
**Task**: One rule for reaching a pack helper, and a gate that can see every way of breaking it
**Branch**: `task/plugin-path-version-split`

### Summary

A pack skill and the binaries it invoked were resolved by two independent mechanisms, so a skill from one release could silently drive helpers from another. Every shipped skill now locates the toolchain through one bootstrap and reaches every helper through it, sd-status reports the resolved binary beside its install root, and a gate enforces the rule over the authored trees.

### Main Changes

- Replaced three resolution forms across the shipped skills with one bootstrap plus toolchain invocation, and added the reference file that defines the bootstrap once
- Added sd-status helper-resolution reporting with bound, shadowed, and unresolved verdicts, proven against a deliberately constructed version split and a thin consumer checkout
- Added check-helper-resolution.py to make check and CI, covering scripts-prefixed, interpreter-direct, bare-name, run-interpreter, missing-bootstrap, and bootstrap-after-use forms
- Fixed the generator bug that rewrote the resolution reference's own counter-examples into copies of the right answer, via a per-file verbatim_spans table, and threaded the profile key the plugin generator had never passed
- Carried the change into the source-only sd-fleet-refresh mirror, which no installer writes and no gate watched, and added a parity test so the next source-only skill is covered


### Git Commits

| Hash | Message |
|------|---------|
| `83d1cb4fdea33845f1d6a16e27dd65e64a940b96` | fix(skills): resolve pack helpers through one bootstrap, never through PATH |
| `55a9cfbee09623bc7538152befd3b94b8b048c45` | chore(fleet): refresh the candidate ledger to all-pass at 0.71.30 |
| `cac9aa2637f65a220d1320f5b4d51ebf63e5bbb4` | fix(task): make the task artifacts pass the review-scope gate |
| `6ac3153fcbc91b0b6f0dd6b47253324c1623acbc` | fix(payload): keep the resolution reference's counter-examples verbatim |
| `ae91f6ed9d74a98452dffa2a83db882118cec9fc` | test: match the exempt toolchain variable as a whole name |
| `b359a2a74859e18fda59e1ff1e7c126c73c6f480` | test: treat any word character as an env-var name continuation |
| `78048da388f0bcb4f352a3b8b805a9d6bb3e0552` | fix(gate): inspect a block that uses the toolchain variable but names no helper |
| `429be1077770cf52b3db3c74ddd850c44be0ba37` | test: check payload residue through the profile, not a copy of its rules |
| `4915b10e0c242983c21756dd518e5c2d76e1ff0c` | fix(gate): a bootstrap below its first use is not a bootstrap |
| `a546f73ffced9785e6b3f9355dd5aa69c2274ca8` | docs(task): record the candidate-readability change as its own work |
| `6d2ad9e01033ad087614bab2953588973b9b659d` | docs(task): state the ledger criterion as all-pass, not as one digest |
| `fa1305e16615e0e6da7bed833ab9d80084408123` | fix(gate): match a direct invocation inside an indented block |
| `5962f8b9edc227d79790847459b81ddc33606f6f` | fix(gate): a long option does not hide a direct invocation |
| `5cb037cc87560e159addc6984477fd9e8ca49790` | test(gate): stop writing gate fixtures into the working tree |
| `ea97bca9979cc042161969e35b5b045bdd14176f` | fix(fleet-refresh): carry the bootstrap into the source-only mirror |
| `9d1fc937013cc6dd24db4b525cd27f4dd11931aa` | test(skills): gate the repository's own skill mirror against its source |
| `49e5fa947acbdd2065a5a5bf59806595b7112b94` | test(skills): name the mirrors that drop the model pin instead of tolerating it everywhere |
| `2a2e496216a45224b55c4a2a5acf2b857953e8ce` | fix(gate): stop telling the toolchain to resolve itself |
| `3f440c2e075408b7ad34206d810338ac3fbfe854` | test(gate): assert the run-interpreter block reports exactly one rule |
| `89a354df03500119f9ea857dd2a045a4b52acc5e` | fix(gate): read authored files as UTF-8 explicitly |
| `a492cc274d86fa399b79645141f59ae2a2ae8ce7` | fix(gate): catch the bare helper name the rule was written to remove |
| `1664aaf3cc3dde3075cafeaf8b95c05a9941db9b` | docs(task): mark the acceptance criteria met |
| `5b989b94e3a5b64f677e2d63d1ddb9337b777f2b` | chore(task): record the branch before finalization |
| `aaaf3363c300503dc5b43bc378ce2eea5a76701e` | docs(task): record the non-executable payload helper as its own work |

### Testing

- [OK] make check: EXIT=0, 80 passing suites, 0 failures
- [OK] pack-helper resolution gate: 73 authored files clean
- [OK] tests.test_helper_resolution_gate: Ran 15 tests, OK
- [OK] tests.test_skill_mirror_parity: Ran 2 tests, OK; fails as expected when a mirror is reverted
- [OK] CI on 89a354df: every job green, Shell coverage included

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 401: File the run-- helper defect and close the forwarder-retirement task

**Date**: 2026-08-18
**Task**: File the run-- helper defect and close the forwarder-retirement task
**Branch**: `task/trellis-bookkeeping-08-18`

### Summary

Filed the deferred 'run -- cannot execute a non-executable helper' defect as its own Trellis task, correcting the cost analysis it inherited: the machine payload derives a file's executable bit from its destination family, so a mode-only fix leaves the payload digest untouched. Then closed 08-17-anomaly-metric-creator-retire-forwarders, whose planning was moot because every acceptance criterion already held on merged branches.

### Main Changes

- New task 08-18-toolchain-run-non-executable-helper: PRD with the failing transcript, two ranked candidate fixes, and the digest-neutrality finding that reorders them
- Archived 08-17-anomaly-metric-creator-retire-forwarders as completed; its five acceptance criteria were verified against live state rather than taken from the recorded checkboxes


### Git Commits

| Hash | Message |
|------|---------|
| `64043860` | docs(task): file the run-- non-executable helper defect |
| `d440c4b1` | chore(task): record the branch for the forwarder-retirement closure |
| `ce9debde` | chore(task): archive 08-17-anomaly-metric-creator-retire-forwarders |

### Testing

- [OK] consumer default branch scripts/ listing: no sd-ai-command-pack-* forwarder and no _sd_pack_forward.py remain
- [OK] docs/fleet/candidate-validation.json: 8 of 8 consumers passed, anomaly-metric-creator among them
- [OK] filesystem_payload_digest(manifest.json) equals the ledger digest sha256:a5184b86, so nothing is candidate-stale
- [OK] review-preflight pre-archive: status valid, pre_archive_valid

### Status

[OK] **Completed**

### Next Steps

- None - task complete

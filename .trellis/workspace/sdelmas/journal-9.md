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

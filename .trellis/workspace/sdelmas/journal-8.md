# Journal - sdelmas (Part 8)

> Continuation from `journal-7.md` (archived at ~2000 lines)
> Started: 2026-08-09

---



## Session 351: sd-status worktree inventory shipped: held branches and leaked worktrees visible

**Date**: 2026-08-09
**Task**: sd-status worktree inventory shipped: held branches and leaked worktrees visible
**Branch**: `main`

### Summary

Planned, implemented, and finished 08-07-status-worktree-invisibility (PR #393, merged 59912b94, v0.64.32; feature commit ad6b1279 carried the collector, tests, and task artifacts and is cited in prose because the journal-recovery window only accepts non-task-path commits). sd-status previously had zero worktree awareness: a local branch checked out in a linked worktree looked identical to a free one, and leaked worktrees never surfaced. The collector now enumerates `git worktree list --porcelain -z` (NUL-delimited; worktree paths are externally controlled and may contain newlines) through a pure raw-value parser (parse_worktree_porcelain) into an additive git.worktrees JSON block plus a derived git.branchesHeldElsewhere set, with a `==> Worktrees` human section (porcelain row order, `(reporting)` marker, explicit none/unavailable states) and a ` [worktree]` suffix on held branches. Cleanliness probes run `git --no-optional-locks status --porcelain` only after a git-common-dir identity check, so a stale path reused by an unrelated repository reports clean: null, never the stranger's state, and no probe writes a foreign index. Schema stays version 2 (additive-key precedent 7ba4d0c9). Planning went through the full adversarial contract: 3 host findings plus two Codex rounds (8 concerns round 1, 5 round 2 - `-z` parsing, no-optional-locks, refusal-set circularity/forced-duplicate scoping, current-row detection from linked worktrees, stale-path identity, receipt-modification coverage, fail-before vs regression-invariant classification), all remediated before task.py start. Copilot round 1 raised one valid finding (a worktree HEAD symref'd outside refs/heads/ would leak a non-branch ref into branchesHeldElsewhere) - fixed by intersecting with localBranches plus a symref regression test; round 2 clean. Backend spec's stale "schema version 1" claim corrected to 2.

### Main Changes

- templates/scripts/sd-ai-command-pack-status.py + root twin: parse_worktree_porcelain (pure NUL-record parser, raw values; sanitization only at serialization), collect_worktrees (unavailable shape on any enumeration failure; identity-checked --no-optional-locks probes; resolved --show-toplevel current-row detection with OSError raw fallback), collect_git wiring with localBranches-intersected branchesHeldElsewhere, render_local Worktrees section + held-branch marking
- tests/test_status.py: 13 new test methods - porcelain row parity, external checkout-refusal oracle (hooks neutralized, `already used by worktree` stderr match, finally-restore), explicit empty state, read-only invariant (sentinel receipt tree + per-worktree index bytes + worktree-list bytes), recovery-classifier independence, prunable-not-pruned, dirty worktree, PATH-stub unavailable inventory, adversarial -z parser input, >300-char-path integration probe, linked-worktree --repo invocation, stale-path-reuse guard, non-branch symref exclusion
- Spec: manifest-and-filesystem.md delegation section gained the worktree-inventory contract; stale "schema version 1" corrected to 2
- Docs: sd-status SKILL.md step-4 report list gained the worktree inventory; command-catalog surfaces regenerated
- Release: 0.64.32 manifests + changelog + candidate ledger via make release-prep

### Git Commits

| Hash | Message |
|------|---------|
| `398c8cb5` | chore(release): prepare 0.64.32 |
| `611308bd` | fix(status): scope branchesHeldElsewhere to local branch names |

### Testing

- [OK] Baseline classification against `git show HEAD:` pre-change collector: 10 behavioral test methods fail before / pass after; the 2 regression invariants (read-only, recovery independence) pass on both sides; template restored byte-identical after the check
- [OK] Full tests.test_status suite: 68 tests OK (67 pre-Copilot-fix, 68 after the symref regression test)
- [OK] make release-prep exit 0 (full maintainer check gate)
- [OK] PR #393 CI fully green on both pushes; Copilot round 2 clean; 0 unresolved threads at merge

### Status

[OK] **Completed**

### Next Steps

- Return to 08-07-status-housekeeping-anomaly-disagreement (T-1): its worktree-held axis is now real; first correct its PRD's stale claim that this dependency was already "(merged)" before this task existed


## Session 352: Ship thin-surface-partition child: four-category partition artifact

**Date**: 2026-08-09
**Task**: Ship thin-surface-partition child: four-category partition artifact
**Branch**: `main`

### Summary

Converged thin-surface-partition planning through round-3 adversarial review, implemented partition-surfaces.py with fail-closed classification of all 776 manifest rows into four categories (593/94/83/6), committed docs/fleet/surface-partition.json with drift gate and 26 tests, merged as PR #395. Also pinned trellis-implement agent to Opus with CI guard test (PR #394).

### Git Commits

| Hash | Message |
|------|---------|
| `a37c7085` | (see git log) |
| `0fc5a4a1` | (see git log) |
| `545322d0` | (see git log) |
| `c2f9cf69` | (see git log) |
| `cef5903f` | (see git log) |

### Status

[OK] **Completed**

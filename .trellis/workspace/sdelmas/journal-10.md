# Journal - sdelmas (Part 10)

> Continuation from `journal-9.md` (archived at ~2000 lines)
> Started: 2026-08-28

---



## Session 450: Work the codex-lane rollout PRD through its review cycle
<!-- trellis-session: v=2 fp=fe91e786a0158564 -->

**Date**: 2026-08-28
**Task**: Work the codex-lane rollout PRD through its review cycle
**Branch**: `task/08-28-codex-lane-fleet-rollout`

### Summary

Published 08-28-codex-lane-fleet-rollout as PR #585 and drove five rounds of local codex review; every finding was verified against the checkout and every one was correct.

### Main Changes

- Corrected the second-lane premise: _blocking_limitations collects every TERMINAL_FAILURES limitation regardless of how many providers completed, so a second lane cannot make a codex failure locally terminal.
- Corrected the advisory-ceiling premise, which had it backwards: a clean codex run reaches eligible/local-stage-terminal with no ceiling consulted, so enabling codex alone is sufficient. The ceiling releases outstanding low/medium findings, and mandating it fleet-wide would weaken the gate in nine repositories at once.
- Added the real second-lane requirement, which is scope coverage rather than failure rescue: codex declares only worktree and branch_delta, while the default config enables prism and gito with codebase, so a codex-only review.json would break sd-review scope=codebase.
- Fixed two citation defects introduced by earlier remediation rounds: a known-blocker note naming acceptance criterion 5 after renumbering moved it to 6, and an AC3 verification command invoking --plan-only on sd-review, which has no such control.


### Git Commits

| Hash | Message |
|------|---------|
| `0711f0bb` | docs(task): drop the cross-repo path from the portability note |
| `3985dfdc` | docs(task): apply codex review findings on the rollout PRD |
| `3a6a628b` | docs(journal): correct the second-lane claim in session 449 |
| `96f170d8` | docs(task): the advisory ceiling is a policy choice, not a prerequisite |
| `5b48dce5` | docs(task): keep a codebase-capable lane in every consumer |
| `0b241722` | docs(task): point AC3 at the helper that owns --plan-only |

### Testing

- [OK] Local codex review round 6: status ready, outcome clean, remoteGate eligible/local-stage-terminal, 0 findings
- [OK] Review preflight: 0 failure(s), 0 warning(s)
- [OK] sd-check: 7 passed, 1 skipped, 0 failed
- [NOT VERIFIED] No routed review ran; this repository has no routed descriptor, so the receipt carries router-not-configured and zero-remote-confidence

### Status

[OK] **Completed**

### Next Steps

- Sequence 08-28-gito-blanket-exclusion-fleet ahead of the rollout, or narrow each consumer's pattern in the same change
- Prefer codex + gito as the per-consumer set; the builtin prism adapter never chunks deltas under its 100 KB ChunkThreshold and never loads .prism/rules.json


## Session 451: Adopt codex + gito as the rollout's default provider set
<!-- trellis-session: v=2 fp=a27a29e319f8b810 -->

**Date**: 2026-08-28
**Task**: Adopt codex + gito as the rollout's default provider set
**Branch**: `task/08-28-codex-lane-fleet-rollout`

### Summary

Recorded the second-lane decision in the PRD and made the acceptance checks enforce it.

### Main Changes

- Named codex + gito the default provider set and ruled out the builtin prism adapter as the second lane, with the measured evidence: prism never chunks a delta under its own 100 KB ChunkThreshold and never loads .prism/rules.json, and both failures are silent.
- Strengthened AC1 after review: it asserted only codex=True, so a rollout using codex + builtin prism across all eight consumers would have passed every automated criterion while violating the plan's central provider decision. It now asserts enabled codex, enabled gito, and an absent or disabled builtin prism.


### Git Commits

| Hash | Message |
|------|---------|
| `6f6a15be` | docs(task): make codex + gito the default provider set |
| `4ed524e3` | docs(task): make AC1 enforce the provider set requirement 1 names |

### Testing

- [OK] Local codex review at 4ed524e3: status ready, outcome clean, remoteGate eligible/local-stage-terminal, 0 findings
- [OK] Review preflight: 0 failure(s), 0 warning(s)
- [NOT VERIFIED] No routed review ran; this repository has no routed descriptor, so the receipt carries router-not-configured and zero-remote-confidence

### Status

[OK] **Completed**

### Next Steps

- Roll out codex + gito per consumer in the registry's cohort order, after or with the gito exclusion narrowing


## Session 452: Add answerbook/mezmo-world-simulator to the fleet as a thin consumer
<!-- trellis-session: v=2 fp=18aaf828366b6866 -->

**Date**: 2026-08-28
**Task**: Add answerbook/mezmo-world-simulator to the fleet as a thin consumer
**Branch**: `chore/fleet-add-mezmo-world-simulator`

### Summary

Registered answerbook/mezmo-world-simulator in the fleet registry, converted it to thin mode, regenerated the candidate-validation ledger for the converted consumer, and widened the fleet inventory test expectations to match. The registry now carries ten consumers.

### Main Changes

- Added the answerbook/mezmo-world-simulator entry to docs/fleet/consumers.json, taking the registry from nine consumers to ten.
- Converted the new consumer to thin mode so it matches every other fleet entry.
- Regenerated docs/fleet/candidate-validation.json so the candidate ledger reflects the thin conversion.
- Updated tests/test_fleet_preflight.py inventory expectations to include the new consumer.


### Git Commits

| Hash | Message |
|------|---------|
| `6c58ca01` | chore: add answerbook/mezmo-world-simulator to the fleet |
| `ad6c25d9` | chore: mezmo-world-simulator converted to thin |
| `bc2f9abc` | chore: regenerate candidate ledger for the thin mezmo-world-simulator row |
| `8a316bb8` | test: fleet inventory expectations include mezmo-world-simulator |

### Testing

- [OK] python -m unittest discover -s tests -p 'test_fleet*.py' — Ran 232 tests, OK
- [OK] python -m unittest tests.test_fleet_preflight — Ran 26 tests, OK

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 453: File the thin-only install task and correct its PRD under review
<!-- trellis-session: v=2 fp=c96f4ff544dcb389 -->

**Date**: 2026-08-28
**Task**: File the thin-only install task and correct its PRD under review
**Branch**: `task/08-28-thin-only-install`

### Summary

Filed the thin-only-install planning task, which proposes making install.py write the thin tree directly and deleting the fat payload plus the conversion and revert machinery. Corrected two defects the PR review found in the PRD: the consumer-count claim was attributed to this PR rather than to PR #586, and a hyphenated term had been split across a line break.

### Main Changes

- Filed .trellis/tasks/08-28-thin-only-install with a PRD covering the five-step fresh-install-then-convert sequence, the rejected make-thin-the-default alternative, and the deletion scope.
- Reattributed the ten-consumer claim to PR #586, which actually added answerbook/mezmo-world-simulator, and stated explicitly that this task record changes no registry row.
- Rewrapped the paragraph so plan-before-apply stays on one line instead of rendering as 'plan-before- apply'.


### Git Commits

| Hash | Message |
|------|---------|
| `8a1dff13` | docs(task): file thin-only install — remove the fat payload and the conversion path |
| `2629490b` | docs(task): correct the consumer-count attribution and the wrapped plan-before-apply term |

### Testing

- [OK] sd-ai-command-pack-review-preflight.mjs — Review preflight: 0 failure(s), 0 warning(s)
- [OK] docs/fleet/consumers.json on merged main — count: 10, all thin: True

### Status

[OK] **Completed**

### Next Steps

- The task stays in `planning`; this session filed the record and fixed its PRD, and
  implemented nothing. Implementation waits on a review gate and `task.py start`.


## Session 454: File the housekeeping merged-before-run defect and narrow its claim under review
<!-- trellis-session: v=2 fp=317e565bde3282cf -->

**Date**: 2026-08-28
**Task**: File the housekeeping merged-before-run defect and narrow its claim under review
**Branch**: `task/08-28-housekeeping-external-merge-unflagged`

### Summary

Filed the planning task for housekeeping's silent clean verdict when a PR is already MERGED at first lookup and a supplied finish-work receipt is discarded unverified. The review's one finding was correct: a MERGED first lookup cannot distinguish a foreign merge from housekeeping's own interrupted earlier run, so the requirement was narrowed to claim only that the merge preceded this invocation.

### Main Changes

- Filed .trellis/tasks/08-28-housekeeping-external-merge-unflagged with the observed PR #586 versus PR #587 evidence, the route_branch_pr_lifecycle mechanism, and the receipt-discard gap.
- Renamed the proposed anomaly to pull_request_merged_before_run, carrying mergedBy as evidence rather than attribution, and added the interrupted-run retry shape as a pinned acceptance case.


### Git Commits

| Hash | Message |
|------|---------|
| `13184021` | docs(task): file housekeeping's silent clean verdict on an externally merged PR |
| `de75b498` | docs(task): claim only that the PR merged before the run, not that the merge was external |

### Testing

- [OK] sd-ai-command-pack-review-preflight.mjs — Review preflight: 0 failure(s), 0 warning(s)
- [OK] sd-ai-command-pack-review.py --scope pr --attempt 2 — status ready, remoteGate eligible/local-stage-terminal

### Status

[OK] **Completed**

### Next Steps

- The task stays in `planning`; this session filed the record and implemented nothing.
  Implementation waits on a review gate and `task.py start`.


## Session 455: Housekeeping report fidelity: unverified receipts and worktree-held merges
<!-- trellis-session: v=2 fp=6fb00f40f98b9c7b -->

**Date**: 2026-08-28
**Task**: Housekeeping report fidelity: unverified receipts and worktree-held merges
**Branch**: `task/08-28-housekeeping-report-fidelity`

### Summary

Fixed two housekeeping defects in which the typed result disagreed with the evidence behind it: a finish-work receipt silently discarded when the pull request was already merged, and a successful worktree merge reporting verdict blocked because the default branch was held elsewhere.

### Main Changes

- MERGED-on-first-lookup with a supplied receipt now records the advisory pull_request_merged_before_run and identity.finishWork {provided: true, verified: false}, so a run that merged through the eligibility gate is no longer byte-identical to one that found the merge already done.
- Wording is deliberately unattributed -- merged before this run, never external -- because an interrupted earlier housekeeping run that merged and was retried is indistinguishable from a merge by another process; mergedBy is reported as GitHub evidence via a seventh view_pr_for_branch field that degrades to empty.
- strict_anomalies resolves the default branch holder from the worktree inventory itself and demotes only that hold's own consequences: current_branch_default_held_elsewhere, local_source_branch_held_by_this_worktree, and default_branch_behind_held_elsewhere.
- worktree_holding(exclude_current=) separates who else holds a branch from whether deletion was possible; the previous 'and not row.get("current")' condition was right for the first question and wrong as the gate for the second.
- refresh_remote_refs_after_deferred_cleanup runs before the held-default-branch return, restoring the prune that the return skipped along with the deletion it was written to follow.
- Merge evidence is now read from both default tips (mergedIntoDefault plus mergedIntoRemoteDefault), so the branch a run just merged upstream stops being classified unmerged-without-pull-request when the local fast-forward was blocked.
- Bumped the pack to 0.71.64 with a CHANGELOG entry; the release payload gate requires it whenever shipped files change.


### Git Commits

| Hash | Message |
|------|---------|
| `11b4eab6` | fix(housekeeping): make the result carry what the merge gate actually did |
| `0767551d` | chore(task): archive 08-28-housekeeping-external-merge-unflagged |
| `0a653aee` | chore(task): archive 08-28-housekeeping-verdict-worktree-held |

### Testing

- [OK] make check exit 0 (test, lint, audit, full-check)
- [OK] make generate: shipped-surface closure clean; all four copies of each changed script byte-identical
- [OK] test_housekeeping_reports_a_merge_that_predates_the_run and test_housekeeping_merge_with_default_branch_held_is_clean fail against HEAD's pre-fix scripts, verified by restoring them and re-running
- [OK] Six over-reach pins in tests/test_status.py hold every blocking code blocking in its ordinary case
- [OK] PR #592 CI all green; Copilot review generated no comments

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 456: Bound the KB refresh, stop reading branch names as paths, classify remote-only branches
<!-- trellis-session: v=2 fp=8ce945780ca0d026 -->

**Date**: 2026-08-28
**Task**: Bound the KB refresh, stop reading branch names as paths, classify remote-only branches
**Branch**: `task/08-28-bookkeeping-integrity`

### Summary

Addressed three independent stability/correctness tasks in one batch and released them as pack 0.71.65: the unbounded Obsidian KB refresh that could stall a whole housekeeping run, the review-preflight path gate that read a Git branch name as a repository path when its prefix collided, and the sd-status leftover-branch classification that never looked at remote-only refs.

### Main Changes

- housekeeping: bounded refresh_obsidian_kb with run_command_with_timeout under SD_AI_COMMAND_PACK_HOUSEKEEPING_KB_TIMEOUT_SECONDS (default 60, 0 disables); exit 124 degrades to the advisory kb_refresh_timed_out anomaly naming the resolved .obsidian-kb target, because the KB is a regenerable mirror the merge never reads
- review-preflight: a configured reference prefix now marks a path claim only when the tail is shaped like a location (line/range citation or a file extension on the final segment), so naming the branch docs/<slug> no longer fails the gate while origin/<slug> passes
- sd-status: added classify_remote_branches plus its own merge evidence walked from the remote default tip over refs/remotes, a closed-unmerged pull-request disposition, and a closed-PR GitHub listing; one row per branch and no new fetch
- registered kb_refresh_timed_out in both advisory anomaly sets, documented both new behaviours in docs/SD_AI_COMMAND_PACK.md and the sd-housekeeping/sd-status skills, and released the payload as 0.71.65


### Git Commits

| Hash | Message |
|------|---------|
| `ababa981` | fix(bookkeeping): bound the KB refresh, stop reading branch names as paths, classify remote-only branches |
| `8747dba6` | chore(task): archive 08-28-kb-refresh-blocking-io |
| `8c89a6cb` | chore(task): archive 08-28-preflight-branch-name-vs-path |
| `b7b5ee54` | chore(task): archive 08-28-status-remote-branch-detection |

### Testing

- [OK] make check -- MAKE_EXIT=0
- [OK] make generate -- shipped-surface closure: clean; 53 changed path(s)
- [OK] pre-archive gate -- valid ['pre_archive_valid'] across all three task directories
- [OK] old vs new preflight on the same document: old FAIL docs/scratch-branch-check.md:3 references missing path docs/file-review-and-kb-defects; new reports none

### Status

[OK] **Completed**

### Next Steps

- None - task complete

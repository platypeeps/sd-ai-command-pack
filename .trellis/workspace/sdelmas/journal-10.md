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

# Roll out housekeeping finish-work gate

## Goal

Eliminate repeated post-merge Trellis bookkeeping recovery pull requests by
rolling the tagged `sd-ai-command-pack` `0.30.4` release across the configured
consumer fleet and verifying that its exact-head finish-work handoff is present
and enforced in every refreshed installation.

## Confirmed Facts

- `platypeeps/se-ai-command-pack` PR #75 merged while its delivery task was
  still `in_progress`; recovery PR #76 archived the task and recorded the
  session after merge.
- The same consumer had the same lifecycle split for PR #72 followed by
  recovery PR #73.
- Both incidents occurred on installed pack `0.24.8`. Pack `0.30.1` added the
  executable `--finish-work-head` requirement specifically after observing
  delivery PRs merge before task archival.
- The `0.30.4` source self-test covers missing, malformed, stale, and matching
  finish-work head evidence. Its candidate ledger records a full-fleet pass.
- Three canaries reached `0.30.3` before CF-3 paused the prior timing run; all
  eight configured consumers require a fresh `0.30.4` terminal outcome.
- Cached fleet status found four consumers that need ownership or dirty-tree
  handling before refresh: `rwbp-website`, `mezmo_benchmark`,
  `sd-github-review`, and `anomaly-metric-creator`.
- `docs/FLEET_ROLLOUT.md`, the fleet manifest, and `sd-fleet-refresh` own the
  rollout order, release-identity guard, consumer gates, finding policy,
  timing evidence, and final report.

## Requirements

- R1: Run the canonical release-identity and candidate-ledger preflight for
  target `0.30.4`; do not mutate a consumer if that guard fails.
- R2: Process every manifest consumer in rollout priority order. Keep the
  canaries sequential and use a conservative one-consumer-at-a-time execution
  even where the manifest permits bounded post-canary overlap.
- R3: Never mutate a dirty consumer tree. Skip it with the exact reason; never
  stash, reset, clean, or overwrite its work.
- R4: Establish safe checkout ownership before switching a clean consumer that
  has an active work loop, in-progress task, non-default branch, or missing
  upstream. Skip when ownership cannot be established without disturbing that
  stream.
- R5: Install only the preflight-selected pack payload, receipts, provenance,
  and managed blocks. Consumer product code is outside this rollout.
- R6: Run the expected-platform audit and consumer-owned full-check before
  publishing a refresh pull request.
- R7: Classify each exact refresh head through the source fleet-review
  classifier. Use integration-only review only when both the source and review
  owner validate that exact head; otherwise use normal remote review.
- R8: Apply the finding-severity gate before watch, merge, or another consumer
  mutation. A pack correctness, security, install/audit, or compatibility
  blocker pauses the fleet and enters one corrective campaign.
- R9: Merge only through the refreshed consumer's green, comment-clean,
  exact-head housekeeping gate after `sd-finish-work` completes and its
  resulting head is pushed and green.
- R10: Use the source self-test plus install audit and provenance identity as
  the proof chain that each refreshed consumer contains the guarded
  housekeeping executable. Do not probe an actual PR with a speculative merge.
- R11: Confirm post-merge provenance, audit, clean default branch, branch
  cleanup, and target version before advancing.
- R12: Record mandatory timing evidence and a complete per-consumer outcome.
  Reuse the same timing run after interruption.
- R13: Do not add an independent task-state parser in this rollout. If a
  consumer on `0.30.4` reproduces stranded bookkeeping, pause and create or
  reuse one source corrective task with that evidence.

## Acceptance Criteria

- [x] Release identity, tagged/current payload equality, and both candidate
  ledgers validate for `0.30.4` before consumer mutation.
- [x] The source housekeeping self-test passes its missing, stale, malformed,
  and matching finish-work head scenarios.
- [x] `rwbp-coordinator` is at `0.30.4` or has an explicit skip reason.
- [x] `loadsmith` is at `0.30.4` or has an explicit skip reason.
- [x] `hoa-manager` is at `0.30.4` or has an explicit skip reason.
- [x] `rwbp-website` is at `0.30.4` or has an explicit skip reason.
- [x] `mezmo_benchmark` is at `0.30.4` or has an explicit skip reason.
- [x] `se-ai-command-pack` is at `0.30.4` or has an explicit skip reason.
- [x] `sd-github-review` is at `0.30.4` or has an explicit skip reason.
- [x] `anomaly-metric-creator` is at `0.30.4` or has an explicit skip reason.
- [x] Every refreshed consumer passes pre-PR and post-merge audit/provenance
  verification and ends clean on its default branch.
- [x] No consumer refresh contains product-code changes or bypasses review,
  CI, unresolved-thread, head-identity, or housekeeping safeguards.
- [x] The final fleet and timing reports identify every outcome, remaining
  stale consumer, finding disposition, retry, open PR, and anomaly.
- [x] No `0.30.4` consumer reproduces a merge followed by a Trellis
  bookkeeping recovery PR; any reproduction pauses rollout and becomes a
  source corrective task rather than an improvised consumer fix.

## Final Rollout Results

Timing run `fleet-0.30.4-20260722T191841Z` completed with four merged refreshes
and four no-touch skips. The final preflight verified immutable tag
`v0.30.4` at `1dd8400b7585c749e1731ed0bf9f30001da35860`; final fleet status reports
four consumers at target and the four skipped consumers still stale.

| Consumer | Before | Review | Result |
| --- | --- | --- | --- |
| `rwbp-coordinator` | `0.30.3` | remote | refreshed+merged in PR #171 |
| `loadsmith` | `0.30.3` | integration-only | refreshed+merged in PR #168 |
| `hoa-manager` | `0.30.3` | integration-only | refreshed+merged in PR #177 |
| `rwbp-website` | `0.25.3` | n/a | skipped: untracked `.obsidian-kb` |
| `mezmo_benchmark` | `0.30.3` | remote | refreshed+merged in PR #411 |
| `se-ai-command-pack` | `0.24.8` | n/a | skipped: untracked `.obsidian-kb` on a non-default branch |
| `sd-github-review` | `0.28.0+sd-github-review.1` | n/a | skipped: unpublished local commit on a branch without upstream |
| `anomaly-metric-creator` | `0.24.7` | n/a | skipped: untracked `.obsidian-kb` |

All four merged consumers passed their local gate, exact-head CI, review-thread
poll, finish-work head gate, housekeeping merge, post-merge install audit, and
clean-default-branch verification. Mezmo required a bounded consumer test
correction so its drift test rejected the retired redundant `.obsidian-kb/`
rule after `0.30.4` converged the canonical ignore entry; the focused test
passed 87 cases before its full gate and remote review passed.

The completed timing report recorded a 6039.112-second critical path,
5567.957 seconds of interval-union active time, 7345.963 seconds of summed
stage time, 1779.716 seconds of reviewer/CI overlap, and four retries. Mezmo
was the slowest consumer because it carried the corrective assertion cycle,
remote-review wait, two full CI passes, and a delayed aggregate CI runner.
The source-only timing anomaly CF-4 was corrected and the original timing state
resumed in place. Follow-up task `07-22-rerun-skipped-fleet-refresh-0304` owns
the four preserved stale checkouts.

## Out of Scope

- Automatically archiving a consumer task from inside the shell merge gate.
- Bypassing protected-branch policy or forcing Git operations.
- Adding a second task-state parsing layer without a `0.30.4` reproduction.
- Consumer product changes, dependency upgrades, or unrelated maintenance.
- Opening a pull request in the upstream Trellis repository.

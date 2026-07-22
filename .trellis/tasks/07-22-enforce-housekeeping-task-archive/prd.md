# Roll out housekeeping finish-work gate

## Goal

Eliminate repeated post-merge Trellis bookkeeping recovery pull requests by
rolling the tagged `sd-ai-command-pack` `0.30.2` release across the configured
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
- The `0.30.2` source self-test covers missing, malformed, stale, and matching
  finish-work head evidence. Its candidate ledger records a full-fleet pass.
- All eight configured consumers currently report a version different from
  the `0.30.2` source target.
- Cached fleet status found four consumers that need ownership or dirty-tree
  handling before refresh: `rwbp-website`, `mezmo_benchmark`,
  `sd-github-review`, and `anomaly-metric-creator`.
- `docs/FLEET_ROLLOUT.md`, the fleet manifest, and `sd-fleet-refresh` own the
  rollout order, release-identity guard, consumer gates, finding policy,
  timing evidence, and final report.

## Requirements

- R1: Run the canonical release-identity and candidate-ledger preflight for
  target `0.30.2`; do not mutate a consumer if that guard fails.
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
  consumer on `0.30.2` reproduces stranded bookkeeping, pause and create or
  reuse one source corrective task with that evidence.

## Acceptance Criteria

- [ ] Release identity, tagged/current payload equality, and both candidate
  ledgers validate for `0.30.2` before consumer mutation.
- [ ] The source housekeeping self-test passes its missing, stale, malformed,
  and matching finish-work head scenarios.
- [ ] `rwbp-coordinator` is at `0.30.2` or has an explicit skip reason.
- [ ] `loadsmith` is at `0.30.2` or has an explicit skip reason.
- [ ] `hoa-manager` is at `0.30.2` or has an explicit skip reason.
- [ ] `rwbp-website` is at `0.30.2` or has an explicit skip reason.
- [ ] `mezmo_benchmark` is at `0.30.2` or has an explicit skip reason.
- [ ] `se-ai-command-pack` is at `0.30.2` or has an explicit skip reason.
- [ ] `sd-github-review` is at `0.30.2` or has an explicit skip reason.
- [ ] `anomaly-metric-creator` is at `0.30.2` or has an explicit skip reason.
- [ ] Every refreshed consumer passes pre-PR and post-merge audit/provenance
  verification and ends clean on its default branch.
- [ ] No consumer refresh contains product-code changes or bypasses review,
  CI, unresolved-thread, head-identity, or housekeeping safeguards.
- [ ] The final fleet and timing reports identify every outcome, remaining
  stale consumer, finding disposition, retry, open PR, and anomaly.
- [ ] No `0.30.2` consumer reproduces a merge followed by a Trellis
  bookkeeping recovery PR; any reproduction pauses rollout and becomes a
  source corrective task rather than an improvised consumer fix.

## Out of Scope

- Automatically archiving a consumer task from inside the shell merge gate.
- Bypassing protected-branch policy or forcing Git operations.
- Adding a second task-state parsing layer without a `0.30.2` reproduction.
- Consumer product changes, dependency upgrades, or unrelated maintenance.
- Opening a pull request in the upstream Trellis repository.

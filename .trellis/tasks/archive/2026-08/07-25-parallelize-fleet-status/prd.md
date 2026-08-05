# Parallelize fleet status collection

## Goal

`sd-status fleet` wall time scales sub-linearly with fleet size: consumer repos are
collected concurrently instead of serially stacking subprocess and 20s network-timeout
latency (a 10-20 repo fleet currently costs 15-40s; degraded network stacks worse).

## Origin

SE-pack repo audit 2026-07-25 (se-ai-command-pack ledger A-027, P2/M). Defect lives in
this repo's source; the SE-side task was retired in favor of this one.

## Requirements

- `scripts/sd-ai-command-pack-status.py` `collect_fleet` (`:2299`): run `collect_local`
  (`:1817`) per consumer in a bounded ThreadPoolExecutor (work is subprocess-bound; repos
  independent).
- Preserve registry rollout order in output; keep per-command timeouts unchanged.
- Fix the worker bound in source with a comment naming its basis. `min(8, len(consumers))`
  unless a measurement justifies otherwise: the work is subprocess-bound so the useful
  ceiling tracks git/gh concurrency, not core count, and an unbounded pool over a large
  fleet opens as many concurrent subprocess trees as there are consumers.
- A consumer that raises must not abort the run. Each future's exception is caught and
  rendered as that consumer's degraded row, exactly as the serial path renders a failed
  `collect_local` today. One unreachable repository may not cost the other rows.
- No cancellation contract is added. On `KeyboardInterrupt` the executor shuts down and
  in-flight subprocesses finish or are killed by their existing per-command timeouts;
  partial output is not written.
- Coordinate with `07-24-track-clean-recovery-artifacts` R5 (recovery-receipt reporting in
  sd-status) — both change status collection; sequence or rebase deliberately.
- Also coordinate with `07-24-align-status-selector-contract` (streamline G01): it fixes
  the status/housekeeping selector CONTRACT while this task changes status COLLECTION.
  Three open tasks now touch the status surface — land the contract fix first or
  independently; avoid concurrent edits.

## Acceptance Criteria

- [x] Multi-repo fleet status measurably faster. With a bound of W workers over C
      consumers the floor is ceil(C/W) waves, not the single worst consumer — state the
      measured before/after wall time and the C and W it was measured at, rather than
      asserting "worst consumer dominates", which only holds when W ≥ C.
      Measured `sd-status fleet` on the configured fleet, C=8 (all present), W=min(8,8)=8:
      serial 9.71s/9.65s vs parallel 1.78s/1.74s (~5.5×). With W=C the floor is
      ceil(8/8)=1 wave, so parallel wall ≈ slowest single consumer; measured numbers match.
- [x] A consumer whose `collect_local` raises produces a degraded row and the remaining
      consumers still report. `collect_local` wrapped in `try/except Exception` →
      `status "unavailable"`, `report None`; `KeyboardInterrupt` (BaseException) propagates.
      `test_fleet_collection_isolates_a_raising_consumer` asserts the degraded row, the
      other two consumers still `available`, and order preserved.
- [x] Output ordering and content identical to serial for the same inputs.
      `ThreadPoolExecutor.map` yields in input order; row assembled from the indexed
      consumer, not completion order. Existing
      `test_fleet_report_uses_priority_and_surfaces_stale_and_missing_repos` ordering
      assertion still passes unchanged.
- [x] Changelog + version; fleet rollout via normal refresh. `manifest.json`
      0.64.12→0.64.13, CHANGELOG entry added, `make generate`/`make sync`/candidate-check
      run (shipped-surface closure clean); `make check` green.

## Notes

- Lightweight task; PRD-only is appropriate. Classified 2026-07-28: one loop becomes a
  bounded `ThreadPoolExecutor` map. The two things that would have made this a design
  task are both already settled by the code (below), so there is no contract or
  compatibility decision left to write down. The coordination constraints above are the
  real risk and they are already stated.
- **Both line citations are wrong.** `collect_fleet` is at
  `scripts/sd-ai-command-pack-status.py:2299`, not `~:1547`; `collect_local` is at
  `:1817`.
- **Ordering is free.** The loop at `:2318` appends one row per consumer in registry
  order, and each row is built from `consumer` alone plus the `collect_local` return.
  `ThreadPoolExecutor.map` yields in input order, so "preserve registry rollout order"
  needs no re-sort — it needs only that the row be assembled from the indexed consumer,
  not from completion order.
- **Thread safety is not an open question.** `scripts/sd-ai-command-pack-status.py` has no
  `os.chdir`, no `global` statement, and no module-level mutable cache; `collect_local`
  takes an explicit path and does subprocess work. The `missing`-path branch (`:2323`)
  never calls it at all.

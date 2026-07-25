# Parallelize fleet status collection

## Goal

`sd-status fleet` wall time scales sub-linearly with fleet size: consumer repos are
collected concurrently instead of serially stacking subprocess and 20s network-timeout
latency (a 10-20 repo fleet currently costs 15-40s; degraded network stacks worse).

## Origin

SE-pack repo audit 2026-07-25 (se-ai-command-pack ledger A-027, P2/M). Defect lives in
this repo's source; the SE-side task was retired in favor of this one.

## Requirements

- `scripts/sd-ai-command-pack-status.py` `collect_fleet` (~:1547): run collect_local per
  consumer in a bounded ThreadPoolExecutor (work is subprocess-bound; repos independent).
- Preserve registry rollout order in output; keep per-command timeouts unchanged.
- Coordinate with `07-24-track-clean-recovery-artifacts` R5 (recovery-receipt reporting in
  sd-status) — both change status collection; sequence or rebase deliberately.
- Also coordinate with `07-24-align-status-selector-contract` (streamline G01): it fixes
  the status/housekeeping selector CONTRACT while this task changes status COLLECTION.
  Three open tasks now touch the status surface — land the contract fix first or
  independently; avoid concurrent edits.

## Acceptance Criteria

- [ ] Multi-repo fleet status measurably faster (worst consumer dominates, not the sum).
- [ ] Output ordering and content identical to serial for the same inputs.
- [ ] Changelog + version; fleet rollout via normal refresh.

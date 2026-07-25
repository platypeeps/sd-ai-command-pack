# Fix work-loop stale-lock recovery race

## Goal

Stale-lock recovery in the work loop cannot delete a competitor's freshly created lock:
two processes recovering the same stale lock must not both acquire it and run autonomous
sessions concurrently.

## Origin

SE-pack repo audit 2026-07-25 (se-ai-command-pack ledger A-012, P2/M), found against the
vendored copies; the defect lives in this repo's source. The SE-side task was retired in
favor of this one.

## Requirements

- In `scripts/sd-ai-command-pack-work-loop.py` `acquire_lock` (~:937) and
  `acquire_terminal_lock` (~:1011): after judging a lock stale, verify identity at delete
  time — rename the stale lock aside and confirm content/runId (or compare st_ino) —
  before recreating with O_CREAT|O_EXCL. Plain unlink-by-path races a concurrent recoverer.
- Preserve the documented `--recover-stale-lock` operator flow (sd-work-backlog SKILL).
- Roll out to consumers via the normal pack refresh.

## Acceptance Criteria

- [ ] Concurrent recovery attempts cannot both acquire (regression test or deterministic
      simulated-race verification).
- [ ] Existing lock/heartbeat tests stay green; changelog + version per repo rules.

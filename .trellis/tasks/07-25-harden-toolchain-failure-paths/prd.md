# Harden toolchain failure paths

## Goal

Vendored automation scripts' failure paths are bounded and fd-safe: housekeeping cannot
loop forever on a misbehaving GraphQL cursor, and the work loop's atomic-write cleanup
cannot close a descriptor it no longer owns.

## Origin

SE-pack repo audit 2026-07-25 (se-ai-command-pack ledger A-015 + A-016, both P3/S).
Defects live in this repo's source; the SE-side bundle task was retired in favor of this.

## Requirements

- `scripts/sd-ai-command-pack-housekeeping.sh` review-thread pagination (~:529, :554):
  cap pages (e.g. 50) or break on a repeated endCursor; treat overflow as "failed to
  inspect review threads" so auto-merge is skipped, not spun.
- `scripts/sd-ai-command-pack-work-loop.py` atomic_write_json (~:564-570): adopt the
  descriptor-ownership handoff (descriptor = -1 once fdopen owns it) so except-cleanup
  only closes descriptors it still owns. Correct pattern exists in the SE pack's shipped
  skill_review.py:1738.

## Acceptance Criteria

- [ ] Pagination cap behavior tested (repeated-cursor fixture skips auto-merge).
- [ ] Cleanup-after-fdopen-failure test proves no double close.
- [ ] Changelog + version; fleet rollout via normal refresh.

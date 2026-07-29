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
  only closes descriptors it still owns. Correct pattern exists in a sibling repository,
  not this one: `se-ai-command-pack` at
  `templates/skills/se-review-skills/scripts/skill_review.py:1738` (verified 2026-07-28 —
  `descriptor = -1` is the first statement inside the `os.fdopen` context manager).

## Acceptance Criteria

- [ ] Pagination cap behavior tested (repeated-cursor fixture skips auto-merge).
- [ ] Cleanup-after-fdopen-failure test proves no double close.
- [ ] Changelog + version; fleet rollout via normal refresh.

## Notes

- Lightweight task; PRD-only is appropriate. Classified 2026-07-28: after the corrections
  below, the remaining work is a single descriptor-ownership assignment plus its
  regression test. No contract, data-flow, or compatibility decision is open.
- **R1 is already satisfied, and it names the wrong file.**
  `scripts/sd-ai-command-pack-housekeeping.sh` contains no pagination loop —
  `grep endCursor` returns nothing in it. Housekeeping delegates to
  `scripts/sd-ai-command-pack-pr-eligibility.py` (`:530`, `:587`), whose review-thread
  loop is already bounded: `MAX_THREAD_PAGES = 100` (`:28`) is enforced at `:643`, and
  overflow raises `EligibilityInputError("review thread pagination is incomplete")` —
  fail-closed, so auto-merge is skipped rather than spun. A server repeating one cursor
  forever is bounded by the same page count. The other review-thread queries
  (`review.py:1235`, `:1294`) hand pagination to `gh api graphql --paginate --slurp` and
  have no in-process loop either. Re-verify before writing code; do not add a second cap.
- **R2 is real and its citation is wrong.** `atomic_write_json` is at
  `work-loop.py:640`, not `~:564-570`. The defect: `os.fdopen(descriptor, ...)` at `:651`
  takes ownership of the descriptor, but the `except Exception:` handler at `:661`
  unconditionally calls `os.close(descriptor)` at `:663`. When `fdopen` succeeds and the
  write inside the `with` block fails, the context manager has already closed it, so
  `:663` closes a descriptor the process no longer owns.
- The `se-ai-command-pack` reference pattern in R2 is a deliberate cross-repository
  citation and does not resolve in this checkout. It is the one non-historical entry the
  citation sweep reports; leave it.

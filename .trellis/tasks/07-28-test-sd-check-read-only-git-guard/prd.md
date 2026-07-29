# Test the sd-check read-only git guard

## Goal

Cover the branch that enforces sd-check's headline guarantee — that configured checks are deterministic and read-only — so the guard cannot be deleted without a test failing.

## Requirements

- Add mutating-git entries (at minimum `git push` and `git commit`) to the invalid-config table at `tests/test_check.py:315` so the `READ_ONLY_GIT_SUBCOMMANDS` branch at `scripts/sd-ai-command-pack-check.py:513` executes.
- Also cover the currently uncovered `perl -e` branch at check.py:501.
- Raise the per-file coverage floor for `check.py` in `.github/scripts/check-shipped-script-coverage.sh:33` to at or just below the new measured value.

## Acceptance Criteria

- [ ] Lines 514-519 of `scripts/sd-ai-command-pack-check.py` leave the coverage missing list.
- [ ] Deleting the `READ_ONLY_GIT_SUBCOMMANDS` branch makes the suite fail.
- [ ] `make check` passes.

## Notes

- Source: `.trellis/audit/report-2026-07-28.md` — finding A-049 (P1 · S · Verified · testing).
- `tests/test_check.py:94` (`command_entry`) is the only argv construction site and never emits a `git` argv; the repo's own `.sd-ai-command-pack/check.json` has no git entry either.
- The floor for check.py is 70% against 73% actual, so deleting the guard currently lands green.
- Created from the 2026-07-28 repo audit with explicit user consent via the `audit.followups` decision.
- Lightweight task; PRD-only is appropriate. Classified 2026-07-28: test-only plus one
  numeric floor in `check-shipped-script-coverage.sh`. No production code changes, so
  there is no contract, compatibility surface, or rollback shape to design. The one
  judgement call — what to raise the floor to — is stated in R3 and settled by the
  measured value, not by a design decision.

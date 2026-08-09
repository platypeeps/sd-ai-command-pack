# Shell coverage kcov lane flakes on test_completion_successor_finds_recent_anchor_in_long_history

## Goal

Recurring infrastructure flake: the Shell coverage (kcov) lane failed twice on 2026-08-09 on test_completion_successor_finds_recent_anchor_in_long_history (PR #386 run 31291158452 first attempt; main push run 31291862939 first attempt), reason completion_successor_history_unavailable, with concurrent 'gh timed out after 60s' noise. Both reruns passed; the test passes locally (~2.4s) and in all three unittest lanes every time. Investigate kcov-instrumentation timing sensitivity in the long-history fixture (history generation vs gh timeout interplay) and either harden the test under kcov or bound/retry the lane. Shell coverage is not in ci-result.needs, so this is advisory-lane noise, but two hits in one evening will keep burning rerun time.

## Requirements

- TBD

## Acceptance Criteria

- [ ] TBD

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.

# Cache pip deps in CI

## Goal

Add cache: pip to the 3 setup-python steps (unittest/lint/security) to stop cold pip installs on every run. Keep pinned SHAs; keep zizmor + parity test green.

## Requirements

- TBD

## Acceptance Criteria

- [ ] TBD

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.

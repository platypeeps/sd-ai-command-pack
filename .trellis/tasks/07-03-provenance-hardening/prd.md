# Provenance hardening from consumer-PR review round

## Goal

Copilot review of the six 0.5.10 refresh PRs surfaced four audit gaps: (1) any symlink at a vouched path must fail (is_file follows symlinks, so symlink-to-file passed); (2) a vouched target that is missing and not gitignored must fail (removal from receipt+disk previously escaped both audits); (3) a symlinked or non-regular provenance.json must fail instead of silently skipping verification; (4) read_text calls need explicit errors= policy (mezmo defect-pattern guard flags the vendored line). Ship as 0.5.11 and refresh the six open PRs.

## Requirements

- TBD

## Acceptance Criteria

- [ ] TBD

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.

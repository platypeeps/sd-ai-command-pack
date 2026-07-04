# Add shellcheck/actionlint coverage for pack-shipped shell

## Goal

From loadsmith's security audit absences: consumers vendor ~10k lines of pack shell with only bash -n syntax gates. Add shellcheck (and actionlint for workflow templates if applicable) to the pack repo CI over templates/scripts and scripts/, fixing findings at least at severity=error, so every consumer inherits linted shell.

## Requirements

- TBD

## Acceptance Criteria

- [ ] TBD

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.

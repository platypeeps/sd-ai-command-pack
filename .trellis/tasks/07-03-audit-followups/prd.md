# Install audit follow-ups: receipt-policy tolerance and separator normalization

## Goal

Two audit refinements from the 0.5.9 fleet rollout. (1) rwbp-website's repo-local review guard enforces the OPPOSITE receipt policy (installed-targets must NOT list gitignored .claude/ files), and the pack audit errors on present-but-unlisted pack-like files, forcing that repo to run with SD_AI_COMMAND_PACK_INSTALL_AUDIT=0. Downgrade unlisted-but-gitignored pack-like files to a warning (mirror of 0.5.9's missing-but-gitignored downgrade) so both receipt policies pass, and document the two supported policies. (2) Copilot on mezmo_benchmark PR #313 (reply on comment 3522276141 promises this fix): normalize Windows-style separators in receipt targets before Path()/git check-ignore so hand-edited receipts degrade gracefully on POSIX.

## Requirements

- TBD

## Acceptance Criteria

- [ ] TBD

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.

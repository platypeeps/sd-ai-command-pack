# Record pack version and content hashes in the install receipt

## Goal

From loadsmith 07-02-supply-chain-pinning: consumer repos exempt vendored pack files from line review ('reviewed upstream') but nothing in-repo makes that claim checkable. Record the pack version plus per-file content hashes in .sd-ai-command-pack/ at install time and provide a verification entry point (install audit or a dedicated check) so tampered refresh PRs hiding command overrides in reviewer-exempted files are detectable.

## Requirements

- TBD

## Acceptance Criteria

- [ ] TBD

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.

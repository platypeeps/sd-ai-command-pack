# Accept path:line references in the preflight doc-path checker

## Goal

The review-preflight documentation path checker rejects markdown link/code-span targets carrying :line suffixes (path.md:42), which are the natural citation format agents produce. Hit three times in one week: AMC task PRD (ci.yml:267) broke AMC's local gate on main, the pack's own task design.md, and rwbp-website's 07-03-review-guard-doc-path-coverage task documents the systemic version incl. the docs-only-lane blind spot. Strip and optionally validate :line suffixes; consider a changed-files-scoped mode so docs-only diffs validate their own references.

## Requirements

- TBD

## Acceptance Criteria

- [ ] TBD

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.

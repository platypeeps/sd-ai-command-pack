# Rename the internal sd-review-local-stage and sd-review-local-policy identifiers

## Goal

The sd-review-local command surface was retired in pack 0.65.0, but the successor coordinator still carries sd-review-local-stage and sd-review-local-policy as internal receipt identifiers. Rename them to match the surviving sd-review vocabulary. This is a receipt-schema change: it moves values that appear in persisted review receipts, so it needs a schema-version decision and consumer-side compatibility handling, which is why it was deferred out of 07-24-remove-retired-review-surfaces.

## Requirements

- TBD

## Acceptance Criteria

- [ ] TBD

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.

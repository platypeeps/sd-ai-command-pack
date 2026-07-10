# Reproduce dropped Claude work-backlog install root cause

## Goal

Build an installer regression around the 0.7.0 hoa-manager/rwbp-coordinator failure mode where .claude/commands/sd/work-backlog.md was absent from disk, receipts, and provenance while audits passed. If the gitignored-.claude mechanism reproduces, fix the installer skip path; otherwise document the negative result and keep the 0.8.5 manifest completeness audit as the compensating control.

## Requirements

- R1: Construct a focused installer test that models the failing 0.7.0
  consumer shape as closely as possible: `.claude/` gitignored or otherwise
  locally special, selected Claude platform, and the
  `.claude/commands/sd/work-backlog.md` target missing from disk, receipts, and
  provenance.
- R2: Determine whether current installer selection or receipt/provenance
  writing can silently omit a selected target under that shape.
- R3: If the omission reproduces, fix the installer path so selected targets
  cannot be silently skipped and add regression coverage.
- R4: If the omission does not reproduce, document the negative result in this
  task and explicitly identify the 0.8.5 manifest completeness audit as the
  compensating control that catches the condition post-install.
- R5: Keep the installer core generic. Do not hardcode hoa-manager or
  rwbp-coordinator paths outside test fixture names or comments that explain
  the historical failure.

## Acceptance Criteria

- [ ] Focused regression test exists for the dropped Claude work-backlog
      scenario or a documented negative reproduction fixture exists.
- [ ] Any reproduced installer bug is fixed with tests that fail on the old
      behavior.
- [ ] If not reproduced, the task records why and references the passing 0.8.5
      manifest completeness audit as the safety net.
- [ ] `make test` and the pack full-check pass after the change or negative
      documentation.
- [ ] The fleet rollout task can rely on the result when validating
      hoa-manager and rwbp-coordinator.

## Notes

- Follow-up from archived task `07-09-fleet-refresh-081-completeness`: PR #88
  added the compensating completeness check, but did not prove the historical
  installer root cause.

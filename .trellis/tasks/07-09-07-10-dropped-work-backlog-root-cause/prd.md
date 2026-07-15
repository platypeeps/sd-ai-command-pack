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

## Root Cause Research - 2026-07-14

The historical install transcript reproduces the failure deterministically and
rules out a file-write race or a `.gitignore` exception bug.

- All six 0.7.0 consumers were refreshed with the same command shape:
  `python3 install.py <repo> --force`, without explicit `--platform` options.
- anomaly-metric-creator, loadsmith, rwbp-website, and mezmo_benchmark reported
  `created .claude/commands/sd/work-backlog.md`.
- hoa-manager and rwbp-coordinator reported every Claude adapter as skipped
  because `active Trellis claude install not detected`, including the new
  work-backlog command. The installer also printed the existing hint to pass
  `--platform claude` when Claude should be active.
- In both affected repos, `.claude/` and the previously installed SD commands
  were tracked, but none of the 0.7.0 active-Trellis markers existed in that
  checkout: `.claude/commands/trellis/continue.md`,
  `.claude/hooks/session-start.py`, or
  `.claude/skills/trellis-before-dev/SKILL.md`.

The resulting receipt behavior explains why only the new command appeared to
be dropped. `preserved_receipt_targets()` retained the existing Claude entries
when auto-detection skipped that platform, but the newly introduced
`work-backlog.md` entry did not exist in the old receipt and therefore could
not be preserved. The 0.7.0 audit then accepted the internally consistent but
incomplete receipt/provenance set.

This was an operator/preflight gap, not a production installer write bug. The
installer reported the skip, but the fleet workflow did not declare its
expected platforms or turn the warning into a failure. The current fleet
manifest and preflight close that gap by emitting explicit `--platform`
arguments for installation and matching `--expected-platform` arguments for a
provenance-independent audit. No installer selection change is recommended.

One focused regression is still worthwhile: install an older manifest without
the Claude work-backlog target, remove the active Claude marker while retaining
the old receipt, refresh with the newer manifest, and assert that the ordinary
audit reproduces the historical blind spot while `--expected-platform claude`
fails. That test should pin both the root cause and the compensating control.

## Notes

- Follow-up from archived task `07-09-fleet-refresh-081-completeness`: PR #88
  added the compensating completeness check, but did not prove the historical
  installer root cause.

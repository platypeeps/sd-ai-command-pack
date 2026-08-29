# Recover Paused Work-Loop Checkpoints Implementation Plan

1. Add failing unit and CLI tests reproducing a shipping checkpoint whose PR
   merges while the run is paused, including the exact downstream branch/head
   transition shape.
2. Extend checkpoint validation and creation to persist an owning resume phase,
   with compatibility fallback for phase-valued legacy targets and an explicit
   recovery argument for human-target-only ledgers.
3. Refactor verified reconciliation to compare lifecycle phases using the
   effective resume phase, validate complete evidence at the observed phase,
   and atomically clear a successful checkpoint.
4. Add negative coverage for partial/unverified recovery, illegal regressions,
   identity and PR conflicts, unverifiable commits, and malformed resume phases.
5. Update canonical `sd-work-backlog` instructions and any normalized status
   contract that needs to expose the resume phase.
6. Synchronize template and root mirrors, regenerate manifest/provenance and
   command documentation, and record the corrective release entry.
7. Run focused work-loop and status tests, generator/parity checks, `make check`,
   and the canonical full-check with optional local reviewers explicitly
   disabled.

## Risk And Rollback Points

- Keep candidate validation ahead of every ledger mutation; a partial write is
  a release blocker.
- Do not broaden checkpoint evidence permissions without recovering the owning
  lifecycle phase.
- Preserve schema-version-1 readability and test legacy states before release.
- Revert all shipped/template mirrors and release metadata as one unit if fleet
  canaries expose an incompatible status or resume contract.

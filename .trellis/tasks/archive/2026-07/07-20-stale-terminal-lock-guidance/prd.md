# Clarify stale terminal lock recovery

## Goal

Give operators an actionable recovery command when a stale terminal
reconciliation lock blocks either work-loop startup or terminal reconciliation.
The guidance must distinguish stale locks, which require explicit recovery,
from active locks, which should be allowed to finish normally.

## Background

RWBP consumer PR #149 exposed two upstream defects in
`templates/scripts/sd-ai-command-pack-work-loop.py`:

- `acquire_lock()` labels a terminal reconciliation lock as stale but still
  says to retry after reconciliation finishes, even though a stale owner will
  not finish without recovery.
- `acquire_terminal_lock()` reports a stale lock without naming the existing
  `--recover-stale-lock` command-line recovery flag.

The installed root script is a generated mirror of the canonical template, so
the fix must originate in `templates/**` and be synchronized through the normal
pack workflow.

## Requirements

1. When work-loop startup encounters an active terminal reconciliation lock,
   preserve the existing wait-and-retry guidance.
2. When work-loop startup encounters a stale terminal reconciliation lock,
   direct the operator to run terminal reconciliation with
   `--recover-stale-lock`; do not imply the stale owner will finish by itself.
3. When terminal reconciliation itself encounters a stale terminal lock without
   recovery enabled, explicitly require `--recover-stale-lock`.
4. Do not weaken exclusive locking or automatically delete stale locks.
5. Add focused regression tests covering active and stale terminal-lock
   diagnostics.
6. Keep the canonical template, installed mirror, manifest provenance,
   changelog, and release-candidate metadata synchronized as a compatible patch
   release.

## Acceptance Criteria

- [x] Active terminal locks still produce wait-and-retry guidance.
- [x] Stale terminal locks encountered during startup identify terminal
      reconciliation with `--recover-stale-lock` as the recovery action.
- [x] Stale terminal locks encountered during terminal reconciliation require
      `--recover-stale-lock`.
- [x] Recovery remains explicit and stale lock files are unchanged on the
      failing path.
- [x] Focused work-loop tests and the canonical `make check` gate pass.
- [x] The release payload gate recognizes the version/changelog/candidate
      metadata as one coherent patch release.

## Out of Scope

- Changing lock staleness detection or automatic recovery semantics.
- Altering terminal-reconciliation evidence validation.
- Editing consumer-generated copies independently of the upstream release.

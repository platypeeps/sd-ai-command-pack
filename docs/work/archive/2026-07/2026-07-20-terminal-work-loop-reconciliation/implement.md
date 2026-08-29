# Terminal Work-Loop Reconciliation Implementation Plan

## Execution Order

1. Add the optional terminal-reconciliation state model and validation to the
   canonical work-loop template, preserving old schema-version-1 ledgers and
   rejecting malformed partial records.
2. Implement short-lived terminal mutation locking, including absent/live/stale
   lock handling, post-lock ledger re-read, atomic write, and guaranteed release.
3. Add `reconcile-terminal` argument parsing, grouped PR evidence validation,
   archived-task containment/identity checks, default-branch cleanliness and
   synchronization checks, commit normalization, and idempotent conflict rules.
4. Update `sd-work-backlog` to collect task, Git, and GitHub evidence and invoke
   the terminal command only after explicit operator-directed reconciliation.
5. Update the status collector and housekeeping reporting to surface verified
   external completion, preserve historical counters, validate audit records,
   and suppress obsolete reconciliation next steps.
6. Add focused helper and status tests, then synchronize template/root copies,
   adapters, docs, specs, manifest provenance, changelog, and release metadata
   through the canonical installer workflow.

## Focused Test Matrix

- Stopped/red ledger, absent lock, clean synchronized default branch, completed
  archived task, merged delivery evidence, and optional bookkeeping evidence:
  success with green health and terminal phase preserved.
- Identical second invocation: successful no-op and unchanged ledger bytes.
- Conflicting second invocation: nonzero exit and unchanged ledger bytes.
- Active or paused run, live/ambiguous lock, unsafe stale lock, dirty worktree,
  feature branch, divergent local/remote default refs, missing commit,
  unrelated commit, path traversal/symlink archive target, incomplete task,
  task identity mismatch, malformed URL grouping, or PR mismatch: fail closed.
- Merge-commit, squash, and rebase delivery shapes: enforce only locally
  provable ancestry while retaining exact caller-supplied PR head evidence.
- Old ledger without `terminalReconciliation`: loads unchanged.
- New ledger read by compatibility paths: no regression in status, resume
  rejection, focus, ranking, or secret-key validation.
- Status output: unreconciled stopped/red still recommends reconciliation;
  verified terminal record reports historical completion and does not.
- Atomic write or lock-release fault injection: no partial terminal record and
  actionable recovery output.

## Validation Commands

```bash
bash scripts/sd-ai-command-pack-toolchain.sh run-python -- \
  -m unittest tests.test_work_loop tests.test_status

make check

SD_AI_COMMAND_PACK_FULL_CHECK_PRISM=0 \
SD_AI_COMMAND_PACK_FULL_CHECK_GITO=0 \
bash scripts/sd-ai-command-pack-full-check.sh
```

Run the canonical installer/parity and release-candidate checks surfaced by
`make check` after updating template sources and release metadata.

## Documentation And Spec Updates

- Document terminal reconciliation as an explicit operator recovery action,
  not an automatic resume or ordinary same-phase evidence update.
- Add the command signature, evidence trust boundary, rejection matrix,
  idempotency contract, and status interpretation to public command docs.
- Update `.trellis/spec/frontend/adapter-guidelines.md` with the full executable
  contract and keep adapters thin.
- Record the additive command in `CHANGELOG.md` and bump the minor pack version.

## Review Gates

- Review lock acquisition/release and time-of-check/time-of-use behavior first.
- Verify task archive path containment against symlinks and traversal.
- Verify all failed candidates leave the persisted ledger byte-for-byte
  unchanged.
- Confirm no existing command can use terminal reconciliation to revive or
  advance an active run.
- Confirm status distinguishes external completion from loop-owned counters.

## Rollback

- Before release metadata changes, revert helper, orchestration, status, and
  tests as one unit.
- After release metadata changes, revert the complete shipped payload change;
  do not leave template/root or version/provenance drift.
- Keep readers tolerant of a previously written terminal audit field so
  rollback does not strand user-local ledgers.

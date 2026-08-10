# Preserve force-install backup records across interrupted installs

## Goal

The machine-scope installer's `remove` must be able to restore a
force-displaced user file even when the install that displaced it was
interrupted before the receipt was committed.

## Problem

The machine-scope installer engine (landed by task
08-09-thin-machine-installer) records `--force` displacement backups only in
the receipt, which is committed after all writes succeed. The intent journal
(`machine-install.intent.json`) carries no backup data. If a `--force` install
is interrupted after displacing a user file but before the receipt commit, the
rerun adopts the written file as `owned-current` with `backup=None`: the `.bak`
file is orphaned on disk and `remove` will not restore the user's original.

The design promise "remove restores force-displaced originals from
receipt-recorded backups" silently weakens to "…unless the install that
displaced them was interrupted". User content is not lost (the `.bak` remains),
but nothing tracks it and nothing restores it.

Found by trellis-check during Step 2 review of 08-09-thin-machine-installer
(engine commit 7495b602, reporting-fix commit b55c48ea).

## Requirements

1. A backup created during `--force` apply must be recoverable by `remove`
   even when the install is interrupted at any point after the backup is
   written. Likely shape: journal entries carry
   `{path, backupPath, backupDigest}` at the moment the backup is created,
   before the destination write; the rerun adoption path merges journal backup
   records into the new receipt.
2. Rerun convergence stays idempotent: a second interrupted rerun must not
   create a second backup of the pack's own payload or lose the first record
   (first-backup-wins semantics already in the engine).
3. `remove` restoration semantics unchanged: digest-verified restore, `.bak`
   deleted after restore, every refusal decided before the first deletion.
4. Journal trust validation covers the new backup fields: family allowlist,
   relative normalized traversal-free paths, fail-closed on any invalid entry.

## Acceptance Criteria

- [ ] `remove` restores a force-displaced original after an install
      interrupted between backup creation and receipt commit, digest-verified.
- [ ] No orphaned `.bak` files remain after `remove` in any interruption
      window covered by the new tests (after backup write, after destination
      write, before receipt commit).
- [ ] Forged journal backup paths outside family roots are rejected
      fail-closed, with tests.
- [ ] Installer coverage gate stays at 100% line+branch; `make test` green.

## Constraints

- Additive change to the intent-journal schema; document the migration posture
  in `manifest-and-filesystem.md` alongside the receipt schema section.
- Do not weaken receipt-trust validation to accommodate journal data.

# Align installer symlink handling with the audit fail-closed contract

## Goal

Fix a verified HIGH contract mismatch between installer and audit:
`install_file` (`install.py:999-1005`) gates on
`path_is_occupied(destination) and not destination.is_file()` —
`Path.is_file()` follows symlinks, so a repo-internal symlink pointing
at byte-identical content passes, returns status `unchanged`, and
`provenance_content` (install.py:1414) vouches it. The audit
(`scripts/sd-ai-command-pack-install-audit.py:338-343`) uses `os.lstat`
and requires `S_ISREG`, so it fails the same target as
`vouched target is not a regular file` — permanently, because
re-running the installer keeps reporting `unchanged` and offers no
remediation path. The 07-03 provenance-hardening and
audit-traversal-hardening tasks deliberately made the AUDIT side
fail-closed on symlinks; the INSTALLER side was never aligned.

## Requirements

- R1: `install_file` detects a symlinked destination via
  `lstat`/`is_symlink` and treats it as a conflict (consistent with the
  audit's "provenance vouches plain regular files" contract), reported
  with a distinct status/message.
- R2: `--force` replaces the symlink with a regular file (atomic write
  targeting the path itself, not through the link), after which the
  audit passes.
- R3: Never vouch a symlinked target in provenance.
- R4: Tests cover: symlinked byte-identical target → conflict, not
  `unchanged`; `--force` → regular file installed, audit exit 0;
  dry-run reports the planned action truthfully.

## Acceptance Criteria

- [ ] Install + audit agree on symlinked targets in both default and
  `--force` modes; the permanent-audit-failure scenario is gone.
- [ ] Full battery green: unittest suite, 100% coverage on install.py,
  full-check, shellcheck.

## Notes

- Origin: 2026-07-06 deep review (Python M2, verified end-to-end:
  install exit 0 "unchanged" followed by audit exit 1 on the same
  tree). Completes the symlink hardening arc from tasks
  07-03-provenance-hardening / 07-03-audit-traversal-hardening.

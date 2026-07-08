# Fix audit and installer reporting gaps

## Goal

Bundle of MEDIUM/LOW reporting and error-path defects in
`scripts/sd-ai-command-pack-install-audit.py` and `install.py` from the
2026-07-06 deep review. None corrupts data; all mislead the operator
exactly when accurate reporting matters most.

1. **Audit warnings silently dropped when any failure exists**
   (`install-audit.py:479-486`): the failure branch returns before the
   warning loop, so a single drift failure suppresses all
   gitignored-adapter and legacy-migration advisories — precisely the
   context (operator debugging a failed audit) where they help.
2. **Unreadable receipt crashes the install path**
   (`install.py:1468-1477`, call site 2091-2093): a permission-denied
   `installed-targets.txt` raises an uncaught `PermissionError`; the
   remove path already has a hardened twin
   (`read_existing_installed_targets_for_remove`).
3. **Fresh `.gitignore` reported "updated", never "created"**
   (`install.py:1142`): existence is checked after the atomic write.
   Capture `existed` before writing, as the receipt/provenance
   installers already do.
4. **`git diff --check` exit 128 propagated as installer exit code**
   (`install.py:1969-1992, 2152-2160`): in a non-git-repo Trellis
   target (tarball export) a fully successful install exits 128 —
   neither documented code. Treat non-repo like the handled
   git-missing case (warn and continue), e.g. gate on
   `rev-parse --is-inside-work-tree`.
5. **Audit env kill-switch bypasses argparse**
   (`install-audit.py:456-458`): with `SD_AI_COMMAND_PACK_INSTALL_AUDIT`
   disabled, `--help` prints the skip warning and exits 0 and invalid
   flags are accepted. Move the check after `parse_args()`.
6. **EACCES-blocked targets reported as "missing"**
   (`install-audit.py:167-177, 236-249`): `path_exists` maps any
   `OSError` to False, so an unreadable installed target reads as
   `installed target is missing`. Distinguish `FileNotFoundError` from
   other `OSError`s as `audit_provenance` already does.

## Requirements

- R1-R6: fix each item above with a matching regression test.
- R7: fixes land in both `scripts/` and `templates/scripts/` copies.

## Acceptance Criteria

- [x] Audit run with 1 failure + N warnings prints both (warnings
  first; test_install_audit_prints_warnings_even_with_failures).
- [x] Unreadable receipt → controlled `error:` message, exit 1
  (test_install_reports_unreadable_receipt_cleanly).
- [x] Fresh gitignore reports `created`; non-repo diff-check warns and
  exits 0 (git 128/129 mirrored to the git-missing case); `--help`
  works with the audit disabled and invalid flags still exit 2; EACCES
  targets report `cannot be inspected` with the OS detail — a
  pre-existing test pinning the old misleading `missing` message was
  updated to the corrected contract.
- [x] Full battery green: 325 tests, both coverage gates, full-check
  exit 0; audit template twin byte-identical. Shipped as PR #59.

## Notes

- Origin: 2026-07-06 deep review (Python M3, M6, L1, L2, L8, L9).

# Manifest and registry self-validation tightening

## Problem

Audit findings A-005 and A-012 (both P2, design), 2026-07-15 @ f6f3932:

- A-005: `PackFile.install` is an unvalidated open string
  (`installer/manifest.py:85`); `validate_manifest` (:101-110) checks
  `platform`/`kind` against frozensets but never `install`;
  `fileops.py:165` silently falls through on unknown values. A typo like
  `"alway"` silently changes install selection across 384 entries.
- A-012: adding a platform requires editing three parallel structures
  synced only by convention (`installer/registry.py:452-453` order tuples,
  `__pack__` sentinel special-cased at :475-502); the invariant lives in a
  test (tests/test_install_core.py:1279-1285), so an omitted row silently
  drops gitignore/local-only patterns.

## Goal

The manifest and registry reject inconsistent data loudly at load/import
time instead of degrading silently.

## Requirements

- Add `IF_ANCHOR_EXISTS` constant + `KNOWN_INSTALL_MODES` frozenset;
  validate `file.install` in `validate_manifest` like `kind`/`platform`.
- Derive the two group-order tuples from `PLATFORM_REGISTRY` insertion
  order, or assert set-equality (registry keys vs order tuples) at import
  time with a clear error.
- Keep `__pack__` handling explicit and documented.

## Acceptance Criteria

- [x] A manifest entry with an unknown `install` value fails validation
      with a named-value error (test added).
- [x] Removing a platform from an order tuple (or adding a registry row
      without order membership) fails loudly at import/test time.
- [x] Installer coverage stays 100% line+branch.

## Implementation Notes

- `installer.registry` now defines `IF_ANCHOR_EXISTS`,
  `KNOWN_INSTALL_MODES`, and import-time order validation for the
  byte-stable registry group tuples.
- `installer.manifest.validate_manifest` rejects unknown install modes with
  the known values listed in the error, and `selected_files` defensively
  rejects unknown modes when called directly.
- Focused coverage in `tests/test_install_core.py` exercises invalid
  install modes and missing, unexpected, and duplicate order groups.

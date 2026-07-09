# Installer Import And Write Hygiene Implementation Plan

## Execution Order

1. Add `__all__` to the lowest-dependency modules first (`registry`,
   `manifest`, `fileops`, `provenance`, `localonly`, `removal`).
2. Replace wildcard imports with explicit imports, keeping `install.py` facade
   exports intentional.
3. Rename local variables that shadow imported modules.
4. Move `temporary_path = Path(temporary.name)` to the start of the
   `NamedTemporaryFile` block.
5. Reduce per-file ruff ignores and run ruff to surface remaining issues.
6. Add the ENOSPC temp cleanup regression.

## Validation Plan

Run `python3 -m unittest tests.test_install_core tests.test_remove`, then
`ruff check install.py installer`. Finish with the 100% installer coverage
gate.

## Documentation And Spec Updates

No user-facing docs are expected. If the installer package public surface is
documented in specs, update those references after imports settle.

## Review Notes

Review the diff for accidental public-surface removal. Tests may still import
via `install`; that is acceptable by design.

## Follow-Ups

If splitting `install_test_support.py` becomes desirable during this work,
park it under the review-nits task unless it is required to keep tests clear.

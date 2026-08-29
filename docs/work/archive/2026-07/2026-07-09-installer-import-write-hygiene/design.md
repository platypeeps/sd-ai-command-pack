# Installer Import And Write Hygiene Design

## Overview

The installer decomposition left broad star-import facades and a temp-file leak
in `atomic_write_bytes`. This task should restore lint coverage without
breaking the public `install.<name>` test surface and should close the write
failure leak.

## Proposal

Add explicit `__all__` lists to installer modules and replace cross-module
wildcard imports with explicit imports. Keep `install.py` as a facade for
tests and CLI compatibility, but have it import a deliberate public surface.
Rename the local `manifest` variable in `main()` so it no longer shadows the
imported module.

In `installer/fileops.py`, assign the temporary file path immediately after
`NamedTemporaryFile` opens and before writes/flush/fsync calls. The existing
`finally` cleanup then has the path even when ENOSPC or another `OSError`
fires mid-write.

Re-enable `F811` and preferably `F401` for `install.py` and `installer/*` in
`pyproject.toml`, resolving real findings rather than expanding ignores.

## Boundaries And Non-Goals

Do not migrate every test from `install.<symbol>` to direct module imports.
The facade can remain as long as it is explicit and lintable.

## Affected Files

- `install.py`
- `installer/__init__.py`
- `installer/fileops.py`
- Other `installer/*.py` modules for imports and `__all__`
- `pyproject.toml`
- `tests/test_install_core.py` or the closest fileops-focused tests

## Risks And Edge Cases

Import cycles are the main risk. Work module by module, keeping lower-level
helpers free of facade imports. Preserve object identity for symbols tests
expect through `install`.

## Validation

Run ruff with restored F rules, installer coverage at 100%, and the focused
atomic-write leak test.

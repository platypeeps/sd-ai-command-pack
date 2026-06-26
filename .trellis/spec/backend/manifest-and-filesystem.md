# Manifest And Filesystem

> Manifest-driven install behavior and local filesystem conventions.

---

## Overview

There is no database, ORM, migration system, or persistent app state. The
installer reads `manifest.json`, validates the target repo, and writes selected
template files into that target repo.

## Manifest Source Of Truth

`manifest.json` owns the installable file list. Each file record declares:

- `platform`
- `kind`
- `source`
- `target`
- optional `anchor`
- optional `install`

`install.py` converts each manifest entry into a frozen `PackFile` in
`load_manifest()`. When adding a file, update `manifest.json` first and keep
Python logic generic unless the install semantics really change.

Reference files:

- `manifest.json`
- `install.py`, `PackFile`
- `install.py`, `load_manifest()`

## Target Validation

The installer requires `.trellis/config.yaml` in the target repository before
copying files. Keep that validation early in `main()` through
`require_trellis_repo()` so invalid targets fail before side effects.

Reference file:

- `install.py`, `require_trellis_repo()`

## Selection Rules

Use `selected_files()` for platform filtering and anchor checks:

- `install: "always"` files are selected by default.
- `--all` selects all adapters even when platform directories are absent.
- `--platform` selects only requested platforms and bypasses anchor detection
  for those selected platforms.
- Default adapter installation depends on the target anchor directory, such as
  `.gemini`, `.github`, or `.opencode`.

Reference files:

- `install.py`, `selected_files()`
- `tests/test_install.py`, `test_installs_shared_skill_and_existing_platform_adapters`

## File Writes

Use `install_file()` for copy behavior:

- Return `unchanged` when the target already has identical bytes.
- Return `conflict` and leave the target untouched when content differs and
  `--force` is absent.
- Copy with `shutil.copyfile()` only after creating the target parent
  directory.
- In `--dry-run` mode, report the planned status without creating files.

Reference files:

- `install.py`, `install_file()`
- `tests/test_install.py`, `test_conflict_requires_force`
- `tests/test_install.py`, `test_dry_run_does_not_write_files`

## Anti-Patterns

- Do not infer installable files by scanning `templates/`.
- Do not hard-code new template paths only in Python.
- Do not preserve mutable installer state between runs.
- Do not overwrite user files without `--force`.

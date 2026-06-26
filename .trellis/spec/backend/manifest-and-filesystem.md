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

## Manifest Path Safety

Validate manifest paths before any target-repo writes:

- `source` must stay inside the pack root and must not contain `..` path
  components after it is made relative to the pack root.
- `target` must be a relative path and must not contain `..` path components.
- `anchor` must be a relative path and must not contain `..` path components.
- Reject Windows drive and root anchors too, including drive-relative paths such
  as `C:tmp\pwn`, drive-absolute paths such as `C:\tmp\pwn`, UNC paths, and
  backslash-separated `..` traversal.

Keep these checks in `validate_manifest()` so malformed or hostile manifests
fail before target validation, selection, backups, or file copies.

Reference files:

- `install.py`, `validate_manifest()`
- `install.py`, `validate_relative_manifest_path()`
- `install.py`, `validate_pack_source()`
- `tests/test_install.py`, `test_manifest_rejects_unsafe_target_paths`
- `tests/test_install.py`, `test_manifest_rejects_unsafe_anchor_paths`
- `tests/test_install.py`, `test_manifest_rejects_unsafe_source_paths`

## Target Validation

The installer requires `.trellis/config.yaml` in the target repository before
copying files. Keep that validation early in `main()` through
`require_trellis_repo()` so invalid targets fail before side effects.

Reference file:

- `install.py`, `require_trellis_repo()`

## Selection Rules

Use `selected_files()` for platform filtering and anchor checks:

- `install: "always"` files are selected by default.
- `install: "always"` files are also selected when `--platform` filters are
  present; adapters depend on the shared skill being installed.
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

- Before reading, backing up, or writing a target path, validate that the
  resolved destination stays inside the resolved target repository. This
  catches existing symlinks in the target repo that would otherwise redirect a
  relative manifest path outside the repo.
- Return `unchanged` when the target already has identical bytes.
- Return `conflict` and leave the target untouched when content differs and
  `--force` is absent.
- With `--force --backup`, copy the previous target file next to the original
  with a `.bak` suffix before overwriting it.
- Backup candidates must also resolve inside the target repo, and an existing
  symlinked `.bak` path counts as occupied even when the symlink is broken.
- Copy with `shutil.copyfile()` only after creating the target parent
  directory.
- In `--dry-run` mode, report the planned status without creating files.

## Diff Checks

Run the final `git diff --check` only against manifest-selected target paths.
The installer should not fail because an unrelated tracked file in the target
repo already has whitespace errors.

Reference files:

- `install.py`, `install_file()`
- `tests/test_install.py`, `test_conflict_requires_force`
- `tests/test_install.py`, `test_dry_run_does_not_write_files`

## Anti-Patterns

- Do not infer installable files by scanning `templates/`.
- Do not hard-code new template paths only in Python.
- Do not preserve mutable installer state between runs.
- Do not overwrite user files without `--force`.
- Do not run repo-wide validation that reports unrelated target work as an
  installer failure.

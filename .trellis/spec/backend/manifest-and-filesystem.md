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
- `source` must also resolve inside the pack root so a template symlink cannot
  copy host files from outside the pack.
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
- If the target path is already occupied by a directory, broken symlink,
  symlink to a directory, or other non-file path, fail with a controlled error.
  Do not let `read_bytes()` or `copyfile()` raise a traceback for expected
  target-repo state.
- Return `unchanged` when the target already has identical bytes.
- Return `conflict` and leave the target untouched when content differs and
  `--force` is absent.
- Return `preserved` and leave the target untouched when content differs and
  the target is `.prism/rules.json`, regardless of `--force`; repo-local Prism
  rules are intentionally protected during pack refreshes and must not be
  reported as conflicts.
- With `--force --backup`, copy the previous target file next to the original
  with a `.bak` suffix before overwriting it. Do not create backups for
  preserved `.prism/rules.json` files because they are not overwritten.
- Backup candidates must also resolve inside the target repo, and an existing
  symlinked `.bak` path counts as occupied even when the symlink is broken.
- Copy with `shutil.copyfile()` only after creating the target parent
  directory.
- In `--dry-run` mode, report the planned status without creating files.

## Diff Checks

Run the final `git diff --check` only against manifest-selected target paths.
The installer should not fail because an unrelated tracked file in the target
repo already has whitespace errors.

## Legacy Adapter Cleanup

When installing `sd` adapter files, remove old pack-generated `/trellis:*`
adapter files whose content still matches a known pack template variant. If a
legacy adapter path exists with other file content, report `legacy-conflict`
and leave it untouched unless `--force` is supplied. With `--force`, remove the
legacy file or symlink so the `sd` replacement becomes the only pack-owned
adapter. Do not introduce a separate keep status for legacy adapter files.
Validate the resolved parent directory before inspecting or unlinking legacy
adapter paths, but do not resolve the final path when it is a symlink slated for
conflict reporting or removal; unlinking the symlink itself is safe when its
parent remains inside the target repo.

Reference files:

- `install.py`, `install_file()`
- `tests/test_install.py`, `test_conflict_requires_force`
- `tests/test_install.py`, `test_dry_run_does_not_write_files`

## Obsolete Adapter Cleanup

When a pack-owned adapter path moves for platform-discovery reasons, remove the
old generated target if it still matches a known pack template variant. If the
old target contains custom content, report `obsolete-conflict` and leave it
untouched unless `--force` is supplied. This currently protects the OpenCode
move from nested `.opencode/commands/sd/<command>.md` files to flat
`.opencode/commands/sd-<command>.md` files, and the pack rename from
`docs/TRELLIS_REVIEW_PR_PACK.md` to `docs/SD_AI_COMMAND_PACK.md`.

## Anti-Patterns

- Do not infer installable files by scanning `templates/`.
- Do not hard-code new template paths only in Python.
- Do not preserve mutable installer state between runs.
- Do not overwrite user files without `--force`.
- Do not overwrite `.prism/rules.json` even with `--force`; users commonly tune
  Prism rules per repo after the initial install.
- Do not run repo-wide validation that reports unrelated target work as an
  installer failure.

# Error Handling

> How errors are handled in this project.

---

## Overview

This is a command-line installer. Errors should be clear, deterministic, and
expressed through process exit codes and concise terminal output.

## Error Types

- Use `SystemExit` for fatal CLI validation failures, as in
  `require_trellis_repo()` and missing template checks in `install_file()`.
- Use integer return codes from `main()` for expected command outcomes:
  normal install/remove uses `0` for success and `2` for file conflicts;
  inspection uses `0` for a successful current/informational result, `1` for
  invalid state or operational/audit failure, and `3` when `--check` finds a
  valid install or refresh action is required. Argparse usage errors remain
  `2` before `main()` runs.
- Reject incompatible flag combinations early, such as `--backup` without
  `--force`.
- Avoid custom exception classes until there is more than one caller that needs
  structured recovery.

## Error Handling Patterns

- Validate prerequisites before writing files. `require_trellis_repo()` runs
  before selecting and installing templates.
- Represent non-fatal install outcomes with status strings such as
  `unchanged`, `created`, `conflict`, and `overwritten`.
- Use `subprocess.run(..., check=False)` when a command result is part of the
  installer contract, such as `git diff --check`.
- Catch `FileNotFoundError` only for optional tooling. `run_diff_check()` warns
  and continues if `git` is missing.

## API Error Responses

There is no HTTP API. For CLI errors, print actionable text that names the
failing path or conflict and the user action, such as re-running with
`--force`.

## Common Mistakes

- Do not let Python tracebacks leak for expected user errors like a missing
  `.trellis/config.yaml`, conflicting target file, or target path occupied by a
  directory or other non-file.
- Do not collapse conflicts into success. Tests expect conflict handling to
  leave the target file untouched.
- Do not silently ignore safety flags that cannot take effect.
- Do not use `check=True` for commands whose failure should be reported as a
  normal installer result.

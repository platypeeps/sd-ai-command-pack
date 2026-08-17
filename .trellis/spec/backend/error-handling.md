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
  `unchanged`, `created`, `updated`, `conflict`, and `overwritten`. `updated`
  is a write that needed no `--force`, so it never contributes to the
  conflict exit `2`.
- Use `subprocess.run(..., check=False)` when a command result is part of the
  installer contract, such as `git diff --check`.
- Catch `FileNotFoundError` only for optional tooling. `run_diff_check()` warns
  and continues if `git` is missing.

### Don't: treat multiplicity as ambiguity

**Problem**: an external listing reports the same subject more than once, and
the reader refuses the whole result.

```python
# Don't do this
matches = [e for e in entries if e.get("id") == wanted]
if len(matches) > 1:
    return UNAVAILABLE, f"{wanted} is listed more than once"
```

**Why it's bad**: several entries usually mean several *registrations* of one
thing, not several things. `claude plugin list --json` emits one entry per
scope — user, then one per project that enables the plugin — and every entry
carries the same version and install path. Refusing them reports a machine
unknowable when it is perfectly knowable, and the failure text names an action
that does not exist ("resolve the duplicate install"), which sends the operator
to break a working configuration. The cost compounds: a refusal upstream of a
comparison suppresses the comparison's alarm too, so a real divergence goes
unreported rather than merely unexplained.

**Instead**: reconcile on the field actually consumed, and refuse only a
genuine disagreement. Normalize before deduplicating, so entries differing
only past a truncation limit do not read as a conflict.

```python
# Do this instead
versions: list[str] = []
for entry in matches:
    version = entry.get("version")
    normalized = safe_text(version, limit=80) if isinstance(version, str) else ""
    if normalized and normalized not in versions:
        versions.append(normalized)
if not versions:
    return UNAVAILABLE, f"no listed {wanted} entry carries a version"
if len(versions) > 1:
    return UNAVAILABLE, f"{wanted} is listed at conflicting versions ({', '.join(sorted(versions))})"
return versions[0], None
```

Each reader reconciles on its own consumed field: the status collector on
`version`, the machine updater on `installPath`. Two readers of the same
listing can legitimately disagree about whether a given listing is conflicting.

**Test point**: a fail-closed refusal needs a case proving the *benign* shape
still succeeds, not only cases proving failures refuse. Assert the reconciled
value and that the downstream verdict it feeds is reachable — a test that
injects the downstream verdict directly proves the renderer works, never that
the collector can produce it.

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

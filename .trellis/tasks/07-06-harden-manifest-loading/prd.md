# Harden manifest loading and validation

## Goal

The manifest is the declared source of truth, but its failure modes are
the worst-handled in the system:

- `load_manifest` (`install.py:483-484`) does
  `json.loads(read_text_strict(...))` with no `JSONDecodeError`
  handling — a truncated/corrupt `manifest.json` produces a raw
  traceback on every install/remove run, while the `--version` path
  (`manifest_cli_identity`, install.py:557-561) converts the same
  failure to a clean `error:` SystemExit. Inconsistent handling of the
  same failure.
- `item["platform"]` / `item["kind"]` / `item["source"]` /
  `item["target"]` (install.py:489-495) raise bare `KeyError`
  tracebacks for a malformed entry.
- `validate_manifest` (install.py:500-513) never validates `kind` — a
  typo like `"managed_block"` silently downgrades the copilot
  managed-block entry to a plain whole-file copy (`install_file`
  treats unknown kinds as plain copies, install.py:2074-2088), which
  under `--force` would clobber a consumer's entire
  `copilot-instructions.md`. This is the one path where a
  one-character manifest error becomes destructive rather than
  fail-safe.
- No `schemaVersion` field — a future record-shape change is
  undetectable by older checkouts.
- `requiresTrellis` is dead metadata: consumed nowhere (only asserted
  in tests); the Trellis requirement is independently hardcoded in
  `require_trellis_repo()`.

This violates the project's own
`.trellis/spec/backend/error-handling.md:42-44` ("Do not let Python
tracebacks leak for expected user errors").

## Requirements

- R1: Wrap `load_manifest` JSON parsing like `manifest_cli_identity`
  does (`error: manifest is not valid JSON: ...`, exit 1).
- R2: Convert missing-field `KeyError`s to
  `SystemExit("error: manifest entry missing 'kind': ...")`-style
  messages naming the offending entry.
- R3: Validate `kind` against the closed set of known kinds in
  `validate_manifest`; unknown kind is a hard error, never a silent
  plain-copy fallback.
- R4: Add `schemaVersion` to manifest.json and reject manifests with a
  newer major schema than the installer understands.
- R5: Either wire `requiresTrellis` into `require_trellis_repo()` or
  remove the field (and its test assertion).
- R6: Tests for each failure mode: corrupt JSON, missing field,
  unknown kind, unsupported schemaVersion.

## Acceptance Criteria

- [x] No raw traceback for any malformed-manifest scenario; each
  prints a single actionable `error:` line and exits 1 (six-case
  test_load_manifest_rejects_malformed_manifests).
- [x] Unknown `kind` can no longer clobber a consumer file under
  `--force` — validate_manifest enforces KNOWN_MANIFEST_KINDS as a
  hard error before any write. schemaVersion 1 added to manifest.json
  with a newer-major rejection; requiresTrellis wired into the
  Trellis-repo precondition (opt-out tested); spec section added.
- [x] Full battery green: 314 tests, 100% coverage across the
  installer package (1,025 stmts), full-check exit 0. Shipped as
  PR #56.

## Notes

- Origin: 2026-07-06 deep review (Architecture finding 4 MEDIUM +
  Python M5).

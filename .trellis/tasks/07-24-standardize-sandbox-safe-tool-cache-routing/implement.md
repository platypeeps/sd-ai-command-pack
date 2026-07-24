# Implementation plan: shared sandbox-safe tool environment

## 1. Lock environment behavior in tests

- Add fixtures for unwritable home cache, explicit safe override, temporary
  fallback, repository-contained/relative/symlink roots, permissions, and
  concurrent creation.
- Assert GitHub auth/config paths and unrelated environment variables remain
  unchanged.

## 2. Implement the shared builder

- Add strict root selection, digest namespacing, private directory creation,
  cache-class adapters, typed diagnostics, and argv-safe execution.
- Preserve current uv behavior through the new implementation before deleting
  duplicate setup.

## 3. Migrate callers

- Route `sd-check`, review/GitHub observation, fleet, status, and housekeeping
  tool invocations through the common environment.
- Remove command-specific cache fragments and document explicit overrides and
  cache-retention behavior.

## 4. Validate

- Run toolchain/subprocess tests, shell lint, generated parity, install audit,
  `make sync`, and `make check`.
- Reproduce a GitHub CLI log read with an unwritable default cache and verify
  successful execution with unchanged authentication configuration.

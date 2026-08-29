---
title: Standardize sandbox-safe tool cache routing
status: done
created: 2026-07-24
branch: codex/standardize-sandbox-safe-tool-cache-routing
---
# Standardize sandbox-safe tool cache routing

## Goal

Prevent avoidable tool retries by giving every pack-owned subprocess one
portable, sandbox-safe cache environment without changing authentication or
tracked repository state.

## Confirmed Evidence

- A recent `gh run view --log-failed` invocation failed before reading logs
  because GitHub CLI attempted to create `~/.cache/gh`. The same command worked
  immediately when `XDG_CACHE_HOME` was routed to a task-scoped writable
  directory under the system temporary root.
- The pack already centralizes parts of Python/uv execution, but GitHub CLI and
  other cache-writing tools still rely on callers remembering environment
  overrides.
- `07-24-implement-read-only-sd-check` requires cache and temporary tool state
  outside tracked paths, but the requirement applies equally to review,
  status, CI triage, fleet, and housekeeping helpers.

## Dependencies And Boundaries

- Parent: `07-22-streamline-sd-skill-workflows`.
- Extend the existing pack toolchain/shared subprocess environment rather than
  adding per-skill shell snippets.
- Do not change `GH_CONFIG_DIR`, credential helpers, keychains, tokens, or
  provider configuration. Cache routing must not hide or replace
  authentication state.
- Consumers may override documented cache locations explicitly; invalid or
  unsafe overrides fail with a controlled diagnostic.

## Requirements

- R1: Add one shared environment builder used by pack-owned Python and shell
  entry points. It returns validated argument arrays and an environment map;
  callers do not construct shell strings.
- R2: Route supported cache classes, including XDG/GitHub CLI, uv, pip, and
  other pack-invoked tool caches, to private task/repository-scoped directories
  below a validated writable temporary or user-cache root. Never create cache
  content under tracked repository paths.
- R3: Preserve inherited environment and authentication variables unless a
  documented cache variable is being set. In particular, never set or rewrite
  GitHub CLI's configuration/authentication directory merely to solve cache
  writes.
- R4: Validate that cache roots are absolute, bounded, not symlinks where
  private creation is required, not repository-contained, and owned with
  private permissions where supported. Handle concurrent creation safely.
- R5: Use deterministic per-user and per-repository names that avoid
  cross-user collisions without embedding raw repository paths or secrets.
- R6: If no safe writable cache can be prepared, stop with the tool, attempted
  cache class, and corrective option. Do not silently run a mutating tool in
  the repository or report the underlying operation as failed.
- R7: Apply the helper to `sd-check`, review, GitHub observation/CI triage,
  fleet, status, and housekeeping subprocess paths through shared execution
  code. Remove superseded duplicate cache setup.
- R8: Keep cleanup bounded to pack-created cache directories and make cache
  retention policy explicit; ordinary command success must not require cleanup
  of reusable cache content.

## Acceptance Criteria

- [x] A fixture with an unwritable home cache successfully runs a stubbed
  GitHub CLI through the safe XDG cache while retaining its existing auth
  configuration path.
- [x] uv, pip, GitHub CLI, and generic XDG fixtures use private external cache
  paths and never write inside the repository.
- [x] Relative, repository-contained, symlinked, non-directory, permission
  denied, and concurrent cache-root cases fail or recover as specified without
  raw tracebacks.
- [x] All owning commands consume the shared helper; duplicate environment
  fragments and command-specific hidden defaults are removed.
- [x] Tests instrument environment and filesystem writes and prove credentials
  and non-cache variables remain unchanged.
- [x] Focused toolchain tests, shell lint, generated parity, `make sync`, and
  `make check` pass.

## Out Of Scope

- Installing or upgrading external tools.
- Moving or copying authentication and provider configuration.
- Clearing user-created or non-pack cache directories.

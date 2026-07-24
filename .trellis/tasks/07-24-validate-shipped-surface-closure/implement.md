# Implementation plan: shipped-surface closure validator

## 1. Capture graph fixtures

- Model representative installable skills, source-only references, generated
  adapters, docs/help identifiers, retired targets, checker registrations, and
  release evidence.
- Reproduce PR #237's unregistered reference and PR #234's omitted platform,
  duplicate finding, invalid registry type, and local/CI scope drift.

## 2. Implement the read-only graph

- Reuse canonical registry/manifest loaders and generator metadata.
- Add strict node/edge validation, bounded NUL-safe change collection,
  transitive closure, deterministic deduplication, and typed output.
- Keep refresh/preparation ownership outside the validator.

## 3. Unify callers

- Add the helper to `sd-check` and local pre-publication.
- Make CI invoke the same executable and configuration instead of maintaining
  a parallel file list.
- Preserve existing release-payload, provenance, install-audit, and candidate
  evidence gates.

## 4. Validate and migrate

- Run graph unit/error tests, pack drift, generated parity, install audit, and
  workflow-structure tests.
- Run `make sync` and `make check`.
- Remove only parity/scope logic that is demonstrably redundant and covered by
  the graph; retain orthogonal behavioral tests.

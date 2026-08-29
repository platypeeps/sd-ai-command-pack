# Design: boundary contract regression matrix

## Architecture

Keep boundary detection in the canonical review-preflight implementation. Add
a small declarative category table whose entries contain:

- stable category identifier and display label;
- production-source match signals;
- bounded good/base/failure regression prompts;
- optional extension or language applicability.

The existing changed-line scanner produces matched categories. Rendering
deduplicates by identifier, follows table order, and caps both examples and
paths. This keeps the output deterministic and unit-testable.

## Category contract

The first version covers six evidence-backed families:

1. Strict structured-input types, including Python `bool` versus `int`.
2. Missing commands, unset/empty `PATH`, nonzero exits, and timeouts.
3. Environment/process-global restoration across success and failure.
4. Path traversal, symlinks, file-size limits, global-ignore state, and TOCTOU.
5. Normalization before comparison/persistence and canonical SHA/ref evidence.
6. Accurate diagnostics with bounded, secret-safe path and exception handling.

Each family provides prompts rather than asserting tests exist. The author and
`sd-review-pr` remain responsible for citing focused coverage or explaining why
a variant is not applicable.

## Compatibility and scope

Reuse the current executable-path filters so tests and copied/generated
surfaces remain excluded. Preserve current environment overrides and preflight
exit semantics. Any shipped guidance change starts in `templates/**` and keeps
installed mirrors synchronized.

## Verification

Extend preflight tests with small diff fixtures per language/category, combined
signals, output caps, and negative path-classification cases. Pin rendered
category identifiers rather than brittle whitespace.

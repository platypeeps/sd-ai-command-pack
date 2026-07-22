# Add a boundary contract regression matrix

## Goal

Convert recurring parser, subprocess, filesystem, normalization, and type-boundary review feedback into an explicit locally verified regression matrix.

## Background

The recent review window repeatedly found missing variants around otherwise
correct happy-path changes:

- PRs #188 and #199: strict JSON types, symlink/TOCTOU handling, path privacy,
  duplicate parsing, and aggregate interval semantics.
- PRs #195 and #205: missing commands, unset `PATH`, nonzero command results,
  malformed lock state, and diagnostics that recommend unavailable commands.
- PRs #172 and #190: raw-versus-normalized comparisons, symbolic commit-ish
  values, missing branches, legacy recovery state, and incomplete evidence.
- PRs #179 and #205: tests coupled to private APIs, host-global ignores, or
  environment assumptions rather than public behavior.

Review preflight already warns when boundary-sensitive production code changes
and `sd-review-pr` requires an author-time disposition. The remaining gap is
that its output is generic, so the same concrete variants are rediscovered by
remote review.

## Requirements

- Replace the generic boundary advisory detail with deterministic categories
  derived from the changed production lines:
  - structured input and strict type validation;
  - subprocess, command availability, exit, and timeout behavior;
  - environment and process-global state;
  - path, symlink, size, and TOCTOU behavior;
  - normalization and canonical persisted evidence;
  - diagnostic fidelity and secret/path redaction.
- For every triggered category, print a bounded regression matrix naming the
  concrete good, base, and failure variants authors should cover or explicitly
  mark not applicable.
- Keep the check advisory. Do not claim test presence can be proved from token
  matching, and do not block solely because a category triggered.
- Preserve the production-source boundary: conventional test, fixture,
  generated, vendored, and copied payload paths must not create false
  production-risk triggers.
- Make category matching deterministic, reviewable, and configurable through
  the existing preflight configuration rather than an opaque heuristic model.
- Add tests for representative Python, JavaScript, shell, YAML/workflow, and
  mixed-diff examples, including overlapping categories and bounded output.
- Update `sd-review-pr` guidance and adapter specs only as needed so authors
  disposition the emitted categories before the first remote review.
- Keep template/root parity and generated adapter checks green.

## Out of Scope

- Inferring line or branch coverage from source text.
- Automatically writing tests or modifying product code.
- Running Prism, Gito, or a remote reviewer from preflight.
- Reopening historical defects already fixed in their owning PRs.

## Acceptance Criteria

- [x] Representative changed production lines trigger the correct named
      boundary categories and concrete regression variants.
- [x] Overlapping signals produce one deterministic matrix entry per category,
      with stable ordering and bounded output.
- [x] Test-only, generated, copied, and vendored changes do not create a false
      production boundary warning.
- [x] Unknown or unreadable diff state retains the current fail-safe diagnostic
      instead of reporting a false PASS.
- [x] `sd-review-pr` requires an evidence-backed category disposition before
      its first remote request without turning the advisory into an unreliable
      automatic coverage gate.
- [x] Focused tests, adapter parity, install audit, and full-check pass.

## Notes

- Evidence source: `docs/review-learnings.md`, refreshed 2026-07-21.

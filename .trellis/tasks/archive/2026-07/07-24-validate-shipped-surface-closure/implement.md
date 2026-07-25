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

## Implementation record

- Added `scripts/sd-ai-command-pack-surface-check.py` from the authoritative
  `templates/scripts/` payload and registered it in the manifest.
- Added strict schema/path/type bounds, NUL-safe committed/staged/unstaged/
  untracked inventory, transitive affected-node closure, deterministic
  finding deduplication, generated-mirror checks, and release evidence.
- Replaced the directory-wide source-only test allowance with the exact
  `SOURCE_ONLY_SKILL_REFERENCES` registry contract.
- Routed `.sd-ai-command-pack/check.json`, full-check, and the CI release gate
  through the same helper; the focused command-surface lint is now internal to
  that entry point.
- Added PR #237 and PR #234 regression fixtures plus platform, retired, docs,
  checker, schema, unsafe path, symlink, oversize, mutation, and Git-layer
  coverage in `tests/test_surface_closure.py`.
- Candidate validation passed all eight consumers after Mezmo's review-cycle
  policy identified and the implementation removed repeated path literals.

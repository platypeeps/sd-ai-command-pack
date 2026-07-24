# Harden Audit Read-Only Methods And Path Handling Implementation Plan

## Execution Order

1. Add failing charter assertions that ban `make -n`, arbitrary `--help`, and
   the `git ls-files | xargs wc` pipeline.
2. Add failing subprocess fixtures for hostile tracked filenames, an empty
   repository, and checkout-owned Make/help handlers with marker side effects.
3. Implement the template-first audit inventory helper and register it in the
   manifest; synchronize its root mirror.
4. Rewrite the two canonical charter methods to use static inspection and the
   new helper, then synchronize the dogfood charter mirrors.
5. Record the read-only audit-method convention in the adapter specification.
6. Apply the required minor release bump, changelog entry, generated
   surfaces/provenance updates, and refreshed fleet candidate ledger.

## Validation Plan

- `python -m unittest tests.test_audit_repo tests.test_audit_inventory`
- focused generated-parity, manifest, and install-core tests
- `make sync`
- `bash scripts/sd-ai-command-pack-toolchain.sh run-python -- scripts/sd-ai-command-pack-fleet-candidate-check.py --json`
- `make check`

Tests must compare marker-file absence before and after helper execution, round
trip exact hostile path strings from JSON, verify deterministic descending
ordering and limits, and assert controlled failures never become success.

## Documentation And Spec Updates

- Update the evidence-routed audit scenario in
  `.trellis/spec/frontend/adapter-guidelines.md`.
- Add the release note and ensure the top changelog version matches the
  manifest patch version.
- Keep templates authoritative and use `make sync` for every generated/dogfood
  mirror rather than hand-maintaining installed copies.

## Review Notes

- Review every subprocess argument boundary for shell avoidance.
- Confirm filenames are transported only as NUL-delimited Git bytes or escaped
  JSON strings and are never passed as options or revision/path expressions.
- Confirm `git ls-tree` supplies NUL-delimited committed-tree metadata and that
  only regular blob modes are included.
- Confirm the tooling charter contains no execution-shaped replacement probe.

## Rollback Points

- Before manifest registration, the helper and tests can be removed without an
  installed-surface migration.
- After registration, rollback the complete patch release; do not restore the
  unsafe charter commands as a fallback.

## Follow-Ups

- None. Broader audit routing and upstream Trellis behavior remain outside this
  task.

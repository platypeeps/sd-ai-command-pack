# Implementation plan: thin-surface-partition

## Ordered checklist

1. [ ] Write `.github/scripts/partition-surfaces.py`: rule engine
       (target-path overrides → platform disposition → hard error),
       runtime registry enumeration, table-vs-registry mismatch
       errors both directions, schema emission, `--check` mode.
2. [ ] Generate and commit `docs/fleet/surface-partition.json`;
       verify counts sum to 776 and every platform present. Publish
       the category counts and per-platform dispositions to this
       task's `research/partition-counts.md` (explicit AC).
3. [ ] Wire gates: Makefile generate target + live-tree unittest
       running `--check` against the committed tree (the
       `test_surface_generation.py` pattern — CI runs the suite, no
       separate lane) + `make generate` idempotence. Join the enumerated lint/type
       inventories: the ruff and mypy invocations in `Makefile`
       (lines ~55-56) and `.github/workflows/tests.yml` (~574, ~581)
       list `.github/scripts` files by name — add
       `partition-surfaces.py` to every occurrence (grep for
       `check-command-surface-drift.py` to enumerate them).
4. [ ] Tests `tests/test_partition_surfaces.py` (unittest): rule
       order, override wins over platform, unknown-platform error,
       unknown-kind error, stale target-path override error,
       missing/stale disposition entries, provisional flag
       round-trip, `sharedRuntime` flag emission, `--check` drift
       detection, byte-idempotence — each PRD fail-closed condition
       gets its own negative test.
5. [ ] Spec/doc updates by enumeration: grep fleet/install spec
       surfaces for places that must mention the partition artifact;
       update in same PR. Update sibling child PRDs
       (`thin-plugin-packaging`, `thin-machine-installer`,
       `thin-migration`) to cite `docs/fleet/surface-partition.json`
       and its schema semantics (`provisional` fail-closed,
       `sharedRuntime` consumption) — explicit AC: siblings must
       reference the documented contract, not a generic "partition
       output".
6. [ ] Publish branch PR (`sd-create-pr` flow), converge review + CI,
       merge on explicit approval.

## Validation commands

- `.venv/bin/python -m unittest` — full suite green, new tests
  included.
- `python3 .github/scripts/partition-surfaces.py --check` — exit 0 on
  clean tree; nonzero demo on a synthetic unclassified row (test
  covers).
- `make generate && git diff --exit-code` — idempotent regeneration.
- `node scripts/sd-ai-command-pack-review-preflight.mjs` before
  publication.

## Rollback points

- Pure addition (new script, new artifact, new gate); revert = drop
  the commit. No installed-consumer surface changes.

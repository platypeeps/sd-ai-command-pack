# Fleet candidate preparation implementation plan

## Implementation Steps

1. Add parser tests for required, empty, valid, and malformed
   `candidatePrepare` declarations; advance the fleet schema and extend
   `FleetConsumer` with immutable preparation argv arrays.
2. Update every fleet fixture and the checked-in consumer manifest. Assign the
   Repomix refresh to all six map owners, move HOA's refresh out of checks, and
   declare empty preparation for SE.
3. Add candidate-runner tests proving install/audit/prepare/check ordering,
   clone-only mutation, empty preparation, preparation-failure diagnostics,
   check suppression after preparation failure, and continued fleet behavior.
4. Run declared preparation commands before checks with the existing direct
   argv, environment, and timeout primitives. Update success summaries without
   expanding failure output beyond existing bounds.
5. Advance candidate-ledger schema to version 2, record `prepares`, and reject
   evidence whose preparation or check arrays drift from the fleet manifest.
6. Expose `candidatePrepare` in fleet-preflight JSON and add focused output
   coverage.
7. Update `docs/FLEET_ROLLOUT.md` and the fleet contract in
   `.trellis/spec/backend/manifest-and-filesystem.md` to document the separate
   mutating preparation and read-only validation phases.
8. Run focused fleet tests and per-file coverage. Fix any release-ledger,
   generated-parity, or source-drift expectations revealed by the schema bump.
9. Run a full disposable fleet candidate validation to regenerate schema-2
   evidence after the source and manifest are final.
10. Refresh the repository KB/spec artifacts as required, then run `make check`
    and deterministic full-check with explicit local-review-provider opt-outs.

## Primary Files

- `docs/fleet/consumers.json`
- `docs/fleet/candidate-validation.json`
- `scripts/sd_ai_command_pack_fleet_lib.py`
- `scripts/sd-ai-command-pack-fleet-candidate-check.py`
- `scripts/sd-ai-command-pack-fleet-preflight.py`
- `tests/test_fleet_candidate.py`
- `tests/test_fleet_preflight.py`
- `tests/test_release_ledger.py`
- `docs/FLEET_ROLLOUT.md`
- `.trellis/spec/backend/manifest-and-filesystem.md`

## Validation Commands

```bash
PYTHONPYCACHEPREFIX=/private/tmp/sd-ai-command-pack-pycache \
  /opt/homebrew/bin/python3.13 -m unittest \
  tests.test_fleet_candidate tests.test_fleet_preflight \
  tests.test_release_ledger

PYTHONPYCACHEPREFIX=/private/tmp/sd-ai-command-pack-pycache \
  /opt/homebrew/bin/python3.13 -m coverage run --branch -m unittest \
  tests.test_fleet_candidate tests.test_fleet_preflight

PYTHONPYCACHEPREFIX=/private/tmp/sd-ai-command-pack-pycache \
  /opt/homebrew/bin/python3.13 -m coverage report --include='scripts/sd-ai-command-pack-fleet-candidate-check.py,scripts/sd_ai_command_pack_fleet_lib.py,scripts/sd-ai-command-pack-fleet-preflight.py'

bash scripts/sd-ai-command-pack-toolchain.sh run-python -- \
  scripts/sd-ai-command-pack-fleet-candidate-check.py

make check

SD_AI_COMMAND_PACK_FULL_CHECK_PRISM=0 \
SD_AI_COMMAND_PACK_FULL_CHECK_GITO=0 \
  bash scripts/sd-ai-command-pack-full-check.sh
```

## Risk And Rollback

- Risk: a consumer's refresh command is unavailable or nondeterministic. The
  disposable candidate run fails that consumer with a stage-specific error;
  active worktrees and prior canonical evidence remain untouched.
- Risk: schema migration leaves a fixture or reader on version 2/1. Focused
  parser, preflight, ledger, release, and full-check tests cover all readers.
- Risk: preparation is accidentally run after validation. The ordering test
  makes the check depend on an artifact written by preparation.
- Rollback is a normal revert of the source-only fleet tooling, schema,
  manifest, docs, and regenerated ledger. No consumer installation migration
  is introduced.

## Start Gate

Do not run `task.py start` or edit implementation files until the user reviews
and approves `prd.md`, `design.md`, and this implementation plan.

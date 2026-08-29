# Batch Source Defect Sweeps Before Corrective Fleet Releases Implementation Plan

## Execution Order

1. Strengthen `tests/test_sdlc_commands.py` with a focused corrective-campaign
   contract test that fails against the current skill.
2. Update the canonical fleet guide with campaign entry, finding-ledger,
   bounded sweep, iteration, freeze, release, and resume stages.
3. Update `templates/.agents/skills/sd-fleet-refresh/SKILL.md` to execute the
   same stages and preserve the urgent-security exception.
4. Synchronize `.agents/skills/sd-fleet-refresh/SKILL.md` byte-for-byte from the
   template source.
5. Run focused tests, then inspect the complete diff for duplicated or
   contradictory rollout ownership.
6. Bump the pack patch version, add the top changelog entry, and update any
   generated release surfaces required by repository checks.
7. Run the canonical full-fleet candidate validation for the stable payload and
   verify the committed ledger.
8. Run `make check`, then ship through the normal source PR lifecycle.

## Validation Plan

- `.venv/bin/python -m unittest tests.test_sdlc_commands`
- `.venv/bin/python -m unittest tests.test_generated_parity`
- `bash scripts/sd-ai-command-pack-toolchain.sh run-python -- scripts/sd-ai-command-pack-fleet-candidate-check.py`
- `bash scripts/sd-ai-command-pack-toolchain.sh run-python -- scripts/sd-ai-command-pack-fleet-candidate-check.py --check-ledger`
- `make check`

## Documentation And Spec Updates

- Keep `docs/FLEET_ROLLOUT.md` authoritative and the shared skill operational.
- Update `.trellis/spec/frontend/adapter-guidelines.md` only if implementation
  reveals a reusable command-contract rule not already captured.
- Do not change thin platform adapters because they already delegate to the
  shared skill without duplicating workflow details.

## Review Notes

- Confirm the campaign cannot update the canonical ledger from a partial run.
- Confirm the wording requires one version selection after convergence rather
  than forbidding an urgent independent security release.
- Confirm the original fleet task is resumed instead of duplicated.
- Treat the six new task directories as one consented backlog-definition
  outcome for this first PR.

## Rollback Points

- Before the version bump, revert only the guide, skill twins, and focused test.
- After the version bump, keep version, changelog, payload, manifest mirror, and
  candidate ledger atomic; do not retag or reuse a published version.

## Follow-Ups

- `07-20-fleet-interruption-severity-gate` owns richer blocker/follow-up
  classification.
- `07-20-fleet-integration-only-review` owns skipping redundant remote review
  for pure consumer refreshes.

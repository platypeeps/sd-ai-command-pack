# Fleet release identity guard implementation plan

## Implementation steps

1. Add focused failing tests for a valid release, missing local tag, local and
   remote tag mismatch, tagged-version mismatch, tagged-payload mismatch,
   stale current candidate ledger, and post-release bookkeeping commits.
2. Extract exact-commit manifest, payload, symlink, and candidate-ledger
   validation from `.github/scripts/create-release-tag.py` into a source-only
   release-identity module and keep the tag planner on that shared contract.
3. Add existing-release verification that compares local and remote tag
   identity, ancestry, tagged payload, tagged evidence, and current evidence.
4. Invoke the guard at the start of fleet preflight, before consumer selection
   and classification. Add an explicit `--remote` argument with `origin` as the
   default.
5. Change JSON preflight output to a schema-versioned object containing
   `releaseIdentity` and `consumers`; update human output and controlled error
   diagnostics.
6. Update `docs/FLEET_ROLLOUT.md`, `README.md`, the detailed command guide, and
   the canonical `sd-fleet-refresh` skill template. Regenerate/synchronize the
   installed source-checkout mirrors.
7. Bump the pack patch version and changelog because the source skill and
   installed command guide are shipped payload. Regenerate the canonical
   full-fleet candidate ledger after all payload bytes stabilize.
8. Run focused release/preflight tests, generated parity, the full candidate
   validator, `make sync`, and `make check` before shipping.

## Primary files

- `.github/scripts/release_identity.py`
- `.github/scripts/create-release-tag.py`
- `scripts/sd-ai-command-pack-fleet-preflight.py`
- `tests/test_fleet_preflight.py`
- `tests/test_release_identity.py`
- `tests/test_release_ledger.py`
- `templates/.agents/skills/sd-fleet-refresh/SKILL.md`
- `.agents/skills/sd-fleet-refresh/SKILL.md`
- `templates/docs/SD_AI_COMMAND_PACK.md`
- `docs/SD_AI_COMMAND_PACK.md`
- `docs/FLEET_ROLLOUT.md`
- `README.md`
- `manifest.json`
- `CHANGELOG.md`
- `docs/fleet/candidate-validation.json`

## Validation commands

```bash
bash scripts/sd-ai-command-pack-toolchain.sh run-python -- -m unittest \
  tests.test_release_identity tests.test_fleet_preflight \
  tests.test_release_ledger tests.test_sdlc_commands tests.test_generated_parity

make generate
make sync

bash scripts/sd-ai-command-pack-toolchain.sh run-python -- \
  scripts/sd-ai-command-pack-fleet-candidate-check.py

make check
```

## Risks and rollback

- Risk: a newly published remote tag is not present locally. The guard fails
  before mutation and tells the operator to fetch tags, then rerun.
- Risk: exact-tree refactoring changes tag-planner behavior. Existing release
  ledger and symlink tests run alongside new identity tests.
- Risk: JSON consumers expect the legacy top-level array. Preflight is
  source-only, and the schema wrapper is documented and regression-tested.
- Rollback is a normal revert of the source guard, docs, generated mirrors, and
  release payload. No consumer state migration is introduced.

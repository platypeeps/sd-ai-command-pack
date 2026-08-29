# SD status command implementation plan

## Implementation Steps

1. Add failing focused tests and fixtures for local human/JSON reporting,
   clean/dirty/detached/diverged/missing-upstream states, optional GitHub and
   Trellis data, strict cleanup expectations, no-write snapshots, fleet order,
   missing clones, profile/override resolution, malformed configuration,
   missing-configuration remedies, and bounded rendering.
2. Implement the standard-library status collector in the template script with
   normalized records, one subprocess boundary, structured JSON readers,
   control-character-safe rendering, and stable schema version 1.
3. Ship the shared fleet parser as a static script, add the status script
   manifest row and per-script coverage floor, and keep root scripts
   byte-identical with their templates.
4. Add the canonical `sd-status` skill and neutral adapter, register the command,
   then run the command-surface generator for all adapters, skill fanout,
   manifest entries, and help catalog.
5. Replace housekeeping final-state/inventory collection with one strict call
   to the status script. Preserve its action log, mutation safety gates,
   self-test, Bash 3.2 compatibility, and recognizable report headings.
6. Update housekeeping and status tests to prove delegation, prior-anomaly
   propagation, status-launch failure handling, dry-run semantics, and existing
   merge/cleanup scenarios.
7. Add the opt-in `install.py --configure-fleet` profile writer with dry-run,
   update-preservation, malformed-config, and incompatible-mode tests.
8. Document command usage, profile discovery and precedence, local/fleet
   boundaries, JSON/read-only semantics, freshness labels, report
   interpretation, and housekeeping ownership in the README, distributed
   guide, adapter spec, and housekeeping/status skills.
9. Bump `manifest.json` to `0.19.0`, add the changelog entry, run generation and
   dogfood sync, and update release/version assertions.
10. Run focused unit, registry/parity, installer, housekeeping, shell syntax,
   Ruff, mypy, and coverage checks. Review the complete diff for generated or
   unrelated churn.
11. Run all seven disposable fleet candidate checks to write fresh release
    evidence, refresh the KB, and run `make check` plus deterministic
    full-check.

## Primary Files

- `templates/scripts/sd-ai-command-pack-status.py` (new)
- `scripts/sd-ai-command-pack-status.py` (generated/dogfood mirror)
- `templates/scripts/sd_ai_command_pack_fleet_lib.py` (new shipped helper)
- `scripts/sd_ai_command_pack_fleet_lib.py` (dogfood mirror)
- `templates/.agents/skills/sd-status/SKILL.md` (new)
- `templates/.commands/sd-status.md` (new)
- `installer/registry.py`
- `manifest.json`
- `templates/scripts/sd-ai-command-pack-housekeeping.sh`
- `scripts/sd-ai-command-pack-housekeeping.sh`
- `.github/scripts/generate-command-surfaces.py`
- `.github/scripts/check-shipped-script-coverage.sh`
- `tests/test_status.py` (new)
- `tests/test_housekeeping.py`
- `tests/test_generated_parity.py`
- `docs/SD_AI_COMMAND_PACK.md`
- `README.md`
- `CHANGELOG.md`

## Validation Commands

```bash
PYTHONPYCACHEPREFIX=/private/tmp/sd-ai-command-pack-pycache \
  .venv/bin/python -m unittest \
  tests.test_status tests.test_housekeeping tests.test_generated_parity

.venv/bin/ruff check installer scripts templates/scripts tests
.venv/bin/mypy installer install.py scripts
bash -n templates/scripts/sd-ai-command-pack-housekeeping.sh

PYTHON_BIN=.venv/bin/python \
  bash .github/scripts/check-shipped-script-coverage.sh

bash scripts/sd-ai-command-pack-toolchain.sh run-python -- \
  scripts/sd-ai-command-pack-fleet-candidate-check.py

make check

SD_AI_COMMAND_PACK_FULL_CHECK_PRISM=0 \
SD_AI_COMMAND_PACK_FULL_CHECK_GITO=0 \
  bash scripts/sd-ai-command-pack-full-check.sh
```

## Risk And Rollback

- Risk: housekeeping loses a safety invariant while delegating. Preserve the
  mutation gate unchanged and assert every former final-state invariant through
  strict status integration tests before removing old collectors.
- Risk: optional GitHub calls make status slow or brittle. Bound timeouts and
  result counts; `--no-network` and visible unavailable states keep local data
  useful.
- Risk: generated command fanout causes broad drift. Change only registry,
  canonical skill/body, and static script registration, then review generator
  output and parity tests.
- Risk: report output leaks credentials or uncontrolled text. Never render raw
  remote URLs or environments; sanitize and bound external titles.
- Rollback reverts the versioned payload, command registry/surfaces, status
  script, housekeeping delegation, docs, and candidate ledger together. No
  consumer state migration is required.

## Start Gate

Do not run `task.py start` or modify implementation files until the user
reviews and approves `prd.md`, `design.md`, and this implementation plan.

# Installer status, check, and JSON implementation plan

## Implementation Steps

1. Add focused failing tests for parser help and valid/invalid combinations,
   inspection state classification, exit codes, deterministic human/JSON
   output, audit invocation/results, platform reporting, and no-write behavior.
2. Add immutable inspection and audit result models in
   `installer/inspection.py`, with strict installed receipt/manifest/provenance
   readers and stable version/platform helpers.
3. Extract or expose the smallest dry-run-safe planning helpers needed from
   existing installer modules. Reuse destination and retired-target semantics;
   do not create a second file-status implementation.
4. Implement the aggregate inspection classifier and bounded human/JSON
   serializers. Keep JSON schema version `1` and sort keys/lists where output
   order is externally visible.
5. Extend `install.py` argument parsing with `--status`, `--check`, `--audit`,
   and `--json`; validate combinations before target mutation and route
   inspection through a dedicated early-return path.
6. Implement audit invocation with the current interpreter and source-owned
   `scripts/sd-ai-command-pack-install-audit.py`, a bounded timeout, captured
   output, and explicit pass/fail/error/not-applicable states. `--check`
   implies this path for an existing installation.
7. Add CLI integration tests for current, behind, ahead, not-installed,
   drifted, missing, malformed, audit-failed, and audit-launch-error fixtures.
   Assert exact exit `0`/`1`/`2`/`3` behavior and target tree identity.
8. Update `README.md` and `docs/SD_AI_COMMAND_PACK.md` with examples, JSON
   schema, status definitions, compatibility rules, and exit codes.
9. Bump the current manifest to the next minor version, add the matching dated
   changelog heading, refresh the candidate ledger, and update any generated
   provenance or KB artifacts required by repository gates.
10. Run focused installer tests, coverage with branches, parity/drift checks,
    `make check`, deterministic full-check, and candidate-ledger validation.

## Primary Files

- `install.py`
- `installer/inspection.py` (new)
- narrowly required helpers in `installer/fileops.py`,
  `installer/provenance.py`, or `installer/removal.py`
- `tests/test_install_core.py` or a focused split installer test module
- `README.md`
- `docs/SD_AI_COMMAND_PACK.md`
- `manifest.json`
- `CHANGELOG.md`
- `docs/fleet/candidate-validation.json`

## Validation Commands

```bash
PYTHONPYCACHEPREFIX=/private/tmp/sd-ai-command-pack-pycache \
  /opt/homebrew/bin/python3.13 -m unittest \
  tests.test_install_core

PYTHONPYCACHEPREFIX=/private/tmp/sd-ai-command-pack-pycache \
  /opt/homebrew/bin/python3.13 -m coverage run --branch -m unittest tests.test_install

PYTHONPYCACHEPREFIX=/private/tmp/sd-ai-command-pack-pycache \
  /opt/homebrew/bin/python3.13 -m coverage report --fail-under=100

make check

SD_AI_COMMAND_PACK_FULL_CHECK_PRISM=0 \
SD_AI_COMMAND_PACK_FULL_CHECK_GITO=0 \
  bash scripts/sd-ai-command-pack-full-check.sh
```

Run the fleet candidate validator required by the release payload gate after
the final versioned payload is stable.

## Risk And Rollback

- Risk: inspection accidentally writes through reused install helpers. Guard
  with full-tree before/after assertions and avoid the applying orchestration
  path entirely.
- Risk: status and audit disagree. Audit owns validity; expose both planning
  state and audit result, with audit failure determining exit `1`.
- Risk: JSON becomes unstable. Freeze schema version `1`, deterministic field
  names, and exact fixture assertions.
- Risk: argument additions change normal CLI behavior. Keep inspection routing
  behind explicit flags and run the complete existing installer suite.
- Rollback before merge is a normal branch discard. After merge, revert the
  feature commit; no consumer state migration is required because inspection
  adds no persisted fields.

## Start Gate

Do not run `task.py start` or modify installer code until the user reviews and
approves `prd.md`, `design.md`, and this implementation plan. The unrelated
`scope-advisory-early-signal` branch edits remain untouched.

# Implementation plan: Correct fleet merge finalization head epochs

## Corrective Ledger

See `research/corrective-findings.md` for the classifier-owned finding and
contract-surface disposition.

## Checklist

- [x] Add merge to the controller's bounded PR-head republication stages and
      update the controlled validation diagnostic.
- [x] Add unit coverage for a successful merge-stage successor publication,
      bounded second head advance, exact PR/head enforcement, immutable prior
      receipts, and unchanged terminal corrective recovery.
- [x] Update the fleet skill, recovery reference, operator guide, and backend
      spec to distinguish normal finish-work successor republication from
      terminal corrective recovery.
- [x] Update textual/parity tests for the new action-owner guidance.
- [x] Bump the corrective patch version and changelog, then run generation and
      synchronization so template and installed mirrors stay byte-identical.
- [x] Run focused controller/skill tests, source checks, and one canonical
      full-fleet candidate validation.
- [ ] Publish, review, merge, and tag the corrective release through the source
      lifecycle.
- [ ] Recover the original 0.55.2 campaign and resume PR #180 from the
      controller-issued publication action.

## Validation

```bash
bash scripts/sd-ai-command-pack-toolchain.sh run-python -- \
  -m unittest tests.test_fleet_controller

bash scripts/sd-ai-command-pack-toolchain.sh run-python -- \
  -m unittest tests.test_sdlc_commands tests.test_generated_parity

bash scripts/sd-ai-command-pack-toolchain.sh run-python -- \
  scripts/sd-ai-command-pack-fleet-candidate-check.py

make check
```

## Recovery Point

If any controller state, exact-head, candidate, source-review, CI, or release
gate fails, keep the source task, original campaign, consumer PR, and retained
finish-work receipt intact. Do not recover the consumer lane until the
corrective version is the current manifest release.

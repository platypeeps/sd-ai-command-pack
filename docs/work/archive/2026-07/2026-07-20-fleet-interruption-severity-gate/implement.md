# Fleet interruption severity gate implementation plan

## Execution order

1. Add focused tests for schema validation, every default family, blocker
   escalation, explicit upgrade/downgrade overrides, duplicate ownership,
   conflicting duplicates, safe paths/IDs, deterministic JSON, human output,
   and exit codes.
2. Implement the source-only finding classifier with typed immutable results,
   bounded normalization, canonical duplicate signatures, and fail-closed
   schema validation.
3. Register the classifier in source-only install-audit policy and the shipped
   script coverage gate without adding it to `manifest.json`.
4. Update the canonical `sd-fleet-refresh` skill template to build the
   temporary input, run the gate before further consumer mutation, reuse one
   owner disposition, settle every observation, and report blockers, deferred
   owners, duplicates, overrides, and follow-up identifiers.
5. Update the rollout guide, detailed guide, README, generated command catalog,
   and backend seven-part contract; synchronize root mirrors from templates.
6. Bump the patch release and changelog because fleet skill and shipped guide
   behavior changes.
7. Regenerate the canonical full-fleet candidate ledger after all payload
   bytes settle, then run the complete local gate and normal source PR review.

## Validation plan

```bash
bash scripts/sd-ai-command-pack-toolchain.sh run-python -- -m unittest \
  tests.test_fleet_finding_classify tests.test_sdlc_commands \
  tests.test_install_audit tests.test_generated_parity tests.test_release_ledger

make generate
make sync

bash scripts/sd-ai-command-pack-toolchain.sh run-python -- \
  scripts/sd-ai-command-pack-fleet-candidate-check.py --json

make check
```

Keep a per-file classifier coverage floor of at least 85%. Exercise the CLI
with disposable JSON fixtures for blocker, deferred, duplicate, escalation,
override, and malformed-input outcomes.

## Documentation and spec updates

- `docs/FLEET_ROLLOUT.md` defines the input table, exit meanings, duplicate
  ownership, follow-up/thread obligations, and report shape.
- `templates/.agents/skills/sd-fleet-refresh/SKILL.md` is canonical; keep the
  source-checkout root mirror byte-identical.
- `templates/docs/SD_AI_COMMAND_PACK.md` is canonical for the installed guide;
  keep `docs/SD_AI_COMMAND_PACK.md` synchronized.
- `.trellis/spec/backend/manifest-and-filesystem.md` receives the mandatory
  seven-section executable contract.

## Review notes

- Confirm downgrade overrides cannot be implicit or omit rationale.
- Confirm duplicate observations cannot disagree with the owning policy data.
- Confirm a deferred disposition never skips replies, thread settlement, or
  follow-up capture.
- Confirm invalid input pauses instead of returning a successful defer result.
- Confirm the source-only script never enters the consumer install manifest.

## Rollback points

The change is additive. A normal revert removes the classifier, skill wiring,
docs/spec contract, version metadata, mirrors, and tests. No consumer state or
persisted fleet-ledger migration is introduced.

## Follow-ups

Post-canary waves and timing telemetry remain separate planned tasks. They may
consume this gate's stable outcome/count schema later but are not prerequisites
for this PR.

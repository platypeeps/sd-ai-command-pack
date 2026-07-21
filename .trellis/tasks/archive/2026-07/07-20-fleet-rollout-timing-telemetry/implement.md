# Fleet rollout timing telemetry implementation plan

## Execution order

1. Add focused fake-clock tests for initialization/resume, successful stages,
   skips and failures, retries, overlapping reviewer/CI waits, critical-path
   math, partial report/resume, completion, strict schema, privacy rejection,
   atomic permissions, lock recovery, human output, and CLI exit behavior.
2. Implement the source-only timing state machine with strict immutable input
   normalization, validated atomic state updates, bounded operation locking,
   monotonic elapsed measurements, wall interval math, and deterministic JSON
   and human reports.
3. Register the helper in source-only install-audit policy and the shipped
   script coverage gate without adding it to `manifest.json`.
4. Update the canonical `sd-fleet-refresh` skill template to initialize one
   run, bracket existing stages, preserve partial state, model reviewer/CI
   overlap, record final consumer outcomes, and report timing anomalies without
   weakening delivery gates.
5. Update orchestration tests, the fleet rollout guide, detailed guide, README,
   and backend seven-part contract; keep source-checkout and installed mirrors
   synchronized from templates.
6. Bump the patch release and changelog, regenerate command/help knowledge, run
   the canonical full-fleet candidate validation after payload bytes settle,
   and finish with `make check` plus the normal source PR lifecycle.

## Validation plan

```bash
bash scripts/sd-ai-command-pack-toolchain.sh run-python -- -m unittest \
  tests.test_fleet_timing tests.test_sdlc_commands tests.test_install_audit \
  tests.test_generated_parity tests.test_release_ledger

make generate
make sync

bash scripts/sd-ai-command-pack-toolchain.sh run-python -- \
  scripts/sd-ai-command-pack-fleet-candidate-check.py --json

make check
```

Keep a per-file timing-helper coverage floor of at least 88%. Exercise the CLI
against a temporary state root for init, overlap, retry, interruption, resume,
completion, malformed state, secret-like reason, and invalid path outcomes.

## Documentation and spec updates

- `docs/FLEET_ROLLOUT.md` defines stage boundaries, state/resume behavior,
  overlap and critical-path math, privacy rules, and report shape.
- `templates/.agents/skills/sd-fleet-refresh/SKILL.md` is canonical; keep the
  source-checkout root mirror byte-identical.
- `templates/docs/SD_AI_COMMAND_PACK.md` is canonical for the installed guide;
  keep `docs/SD_AI_COMMAND_PACK.md` synchronized.
- `.trellis/spec/backend/manifest-and-filesystem.md` receives the mandatory
  seven-section executable contract.

## Review notes

- Confirm elapsed time always comes from the monotonic clock.
- Confirm reviewer and CI overlap is represented, not double-counted.
- Confirm a repeated operation cannot duplicate completed stages or consumers.
- Confirm no durable field or final report contains an absolute path or
  secret-like value.
- Confirm telemetry failure remains visible without changing a delivery gate's
  pass/fail outcome.
- Confirm the source-only helper never enters the consumer install manifest.

## Rollback points

The feature is additive and keeps state outside the repository. A normal revert
removes the helper, orchestration, docs/spec, version metadata, mirrors, and
tests. Existing local timing records become inert and may be retained for
inspection; no consumer migration or cleanup is required.

## Follow-ups

`fleet-post-canary-waves` consumes the stable stage and summary schema after
this baseline lands. Wave-specific concurrency policy remains out of scope.

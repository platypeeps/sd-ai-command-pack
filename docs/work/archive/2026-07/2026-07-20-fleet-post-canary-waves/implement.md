# Controlled post-canary fleet waves — implementation plan

## Implementation

1. Raise `docs/fleet/consumers.json` to schema 4 and add the explicit canary,
   bounded post-canary, and solo-final cohorts.
2. Add rollout-policy dataclasses and strict parsing to
   `scripts/sd_ai_command_pack_fleet_lib.py`; keep consumer parsing and
   candidate-ledger identity behavior stable.
3. Add the source-only `scripts/sd-ai-command-pack-fleet-wave-plan.py` helper
   with strict observation parsing and a pure deterministic scheduling result.
4. Add focused parser, scheduler, CLI, privacy, and failure-mode tests. Register
   the source-only helper with install-audit and shipped-script coverage rules,
   with a per-file coverage floor.
5. Rewrite the canonical `templates/.agents/skills/sd-fleet-refresh/SKILL.md`
   orchestration around controller-owned scheduling and isolated bounded
   consumer workers. Preserve timing, integration-only review, finding,
   watch, housekeeping, and post-merge audit ownership exactly once.
6. Update `docs/FLEET_ROLLOUT.md`, the installed guide template, README, and
   executable backend code-spec. Regenerate installed mirrors and command
   surfaces from templates.
7. Bump the pack minor version, changelog, generated catalog/manifest mirrors,
   and candidate ledger as one release candidate.

## Validation

1. Run focused fleet library/wave planner/skill/parity/install-audit tests with
   branch coverage for the new helper.
2. Run the source review preflight and verify no adapter exposes wave-state or
   timing controls.
3. Run `make check` with template parity, Ruff, mypy, coverage, audit, docs,
   release, and generated-surface gates.
4. Run the canonical no-filter full-fleet candidate validation and update only
   its generated ledger.
5. Use `sd-ship` as the sole PR/review/watch/housekeeping owner. Address all
   configured-review comments in bounded rounds and rerun affected checks after
   each changed head.

## Rollback

- Before release, revert the policy/parser/helper/skill/docs/test changes as one
  unit and restore schema 3.
- After release but before a fleet run, publish a patch restoring sequential
  orchestration while retaining schema-4 parsing compatibility.
- During a fleet run, stop dispatching new workers; never delete or reinterpret
  durable timing, PR, finding, or consumer outcomes. Resume sequentially from
  live preflight/GitHub evidence if the scheduler is unavailable.

## Completion evidence

- Schema 4 declares three sequential canaries, a post-canary cohort bounded at
  two, and a solo final cohort; strict parsing rejects unsafe or reordered
  policy.
- The source-only planner is read-only, resumes from observed live state,
  returns bounded starts and one manifest-order merge candidate, and freezes
  starts/merges for verified pack blockers.
- Focused scheduler branch coverage is 94 percent; combined shared fleet-library
  coverage is 91 percent.
- The canonical no-filter candidate validation passed all seven consumers and
  wrote the schema-version-2 ledger for pack 0.25.0.
- `make check` passed tests, Ruff, mypy, workflow lint, install audit, generated
  parity, release/candidate gates, and the deterministic full check.
- First-review risk is concentrated in the new strict schema parser and
  source-only planner. The boundary matrix covers malformed schemas and fields,
  unknown/repeated/reordered identities, invalid concurrency, blocker and
  partial-failure paths, missing/symlink/oversized inputs, controlled privacy
  errors, resume behavior, and human/JSON rendering.

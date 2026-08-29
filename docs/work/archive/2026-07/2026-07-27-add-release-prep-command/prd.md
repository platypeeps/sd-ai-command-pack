---
title: Add canonical release-prep command
status: done
created: 2026-07-27
branch: codex/add-release-prep-command
---
# Add canonical release-prep command

## Goal

Automate the ordered generate, self-sync, exact-payload fleet candidate validation, and final release-readiness checks so expensive validation cannot run against a stale payload.

## Requirements

- Provide one maintainer-facing command, `make release-prep`, as the canonical
  way to prepare the current checkout for release.
- Keep the command source-only. It must not add an installed `/sd` command or
  expand the consumer payload.
- Run preparation in this order: regenerate command surfaces, self-sync the
  dogfood install and knowledge base, validate cheap release prerequisites,
  refresh stale full-fleet candidate evidence when required, then run the
  repository's final `make check` gate.
- Before starting fleet candidate validation, require generated surfaces and
  mirrors to be current and require any shipped-payload change to carry a
  manifest version bump and matching top changelog heading.
- Treat a stale candidate ledger as the only closure finding that may advance
  into fleet validation. Any other finding must fail fast before consumer
  clones or compatibility commands run.
- Skip fleet validation when the existing ledger already matches the exact
  payload and fleet manifest.
- Fail closed on invalid JSON, unresolved comparison state, command failures,
  or a post-validation closure defect. Preserve the candidate validator's
  atomic-ledger behavior.
- Document `make release-prep` as the normal release workflow and remove the
  fragile manual ordering from maintainer-facing guidance.

## Acceptance Criteria

- [x] `make release-prep` is available and uses the repository's selected
      virtual-environment Python.
- [x] Generation and self-sync always complete before release preflight.
- [x] The preflight rejects version, changelog, generated-surface, mirror, or
      other closure defects without invoking fleet candidate validation.
- [x] The preflight accepts only a clean report or the single expected
      `provenance.candidate-stale` finding for
      `docs/fleet/candidate-validation.json`.
- [x] Candidate validation runs exactly once when evidence is stale and is
      skipped when evidence is already current.
- [x] A successful run finishes with `make check`; any failed step prevents all
      later steps.
- [x] Automated tests cover ordering, fail-fast behavior, stale-ledger
      filtering, candidate skip/run decisions, and final-check execution.
- [x] CONTRIBUTING, README release guidance, the fleet runbook, and the
      manifest/filesystem spec identify the canonical command and its contract.

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.

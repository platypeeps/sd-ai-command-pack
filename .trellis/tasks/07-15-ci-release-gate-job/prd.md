# Wire the release/drift gate into CI as a PR job

## Problem

Audit finding A-001 (P1·M, tooling), 2026-07-15 @ f6f3932: the release
version-bump/CHANGELOG gate exists only in the local full-check
(`scripts/sd-ai-command-pack-full-check.sh:609` via `main()` at `:852`). No CI
job runs it against a real PR diff (`.github/workflows/tests.yml` has no such
job; tests exercise the gate on synthetic fixtures only), and
`.github/scripts/create-release-tag.py:72-73` silently no-ops when
`manifest.json` did not change. A PR that edits shipped payload without a
manifest bump merges green and never ships to the fleet as a release.

## Goal

Every PR that changes shipped payload (`templates/**`, shipped `scripts/**`,
the installed guide, `manifest.json`) is blocked in CI unless it carries a
manifest version bump and matching CHANGELOG heading — the same contract the
local gate enforces.

## Requirements

- Add a PR-triggered CI job that runs the real release/drift gate against the
  PR base (`SD_AI_COMMAND_PACK_FULL_CHECK_RELEASE_BASE_REF` already exists per
  tests/test_pack_drift.py:351); checkout must make the base commit available.
- Wire the job into the `ci-result` aggregate so branch protection covers it.
- Non-payload PRs must pass without a bump (gate scopes to payload paths).
- Keep runtime small (no full test suite in this job).

## Acceptance Criteria

- [x] A PR editing `templates/**` without a manifest bump fails the new job.
- [x] The same PR passes after bumping manifest + CHANGELOG.
- [x] A docs-only (non-payload) PR passes without a bump.
- [x] `ci-result` requires the new job; CI docs/spec updated.

## Implementation Notes

- Added the pull-request-only `Release payload gate` workflow job. It checks
  out full history, verifies the PR base SHA exists locally, and runs
  `run_pack_source_drift_gates` with
  `SD_AI_COMMAND_PACK_FULL_CHECK_RELEASE_BASE_REF=<base-sha>`.
- Wired the job into the `CI Result` aggregate so branch protection covers it
  while allowing the job to be skipped on non-PR events.
- Updated README, CONTRIBUTING, and backend manifest/filesystem spec guidance,
  plus workflow-structure tests.

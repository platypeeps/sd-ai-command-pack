# Enforce Changelog And Tags In The Release Gate Design

## Overview

The version bump gate exists, but the release ledger still depends on memory:
CHANGELOG entries and tags were skipped after v0.6.0. This task should backfill
the ledger and make future omissions fail locally and in CI.

## Proposal

Backfill `CHANGELOG.md` for 0.7.4, 0.7.5, and 0.8.0 using the known release
commits from the PRD, then create tags for unambiguous manifest-version bump
commits from 0.6.1 through 0.8.1.

Extend the pack-source drift gate in `scripts/sd-ai-command-pack-full-check.sh`
and its template twin so a manifest version change relative to the base ref
requires a matching top-level `CHANGELOG.md` heading. Mirror the existing
payload-without-version tests in `tests/test_pack_drift.py`: create a fixture
that bumps `manifest.json` without adding a changelog heading and assert the
gate fails with an actionable message.

For tagging, prefer a GitHub Actions job that runs on pushes to `main`, detects
a manifest version change, and creates `v<version>` when absent. If direct tag
creation from CI is not desirable, document and test a one-command release step
that the gate enforces.

## Boundaries And Non-Goals

Do not generate GitHub Releases or backfill pre-0.6.0 notes.

## Affected Files

- `CHANGELOG.md`
- `manifest.json` only when a future release actually bumps version
- `scripts/sd-ai-command-pack-full-check.sh` and template twin
- `tests/test_pack_drift.py`
- `.github/workflows/tests.yml` or a new release workflow

## Risks And Edge Cases

Base refs can be missing in local clones. Match the current drift gate's
fallback behavior and fail with a clear message only when the manifest bump can
be compared.

## Validation

Run the pack drift tests, shell syntax checks for the updated full-check twin,
and a dry-run or no-op verification for the tag automation.

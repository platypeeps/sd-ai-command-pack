# Enforce changelog and tags in the release gate

## Goal

Make the release ledger self-enforcing so the CHANGELOG-and-tag process
established in `07-06-release-versioning-process` cannot lapse again. Right
now it already has: backfill the holes and add the mechanical guard that
was the whole point.

## Problem

`07-06-release-versioning-process` shipped a CHANGELOG, a tag-per-bump
convention, and a working full-check release gate that fails on a payload
change without a manifest version bump
(`scripts/sd-ai-command-pack-full-check.sh:413-562`). Within a day the
process lapsed exactly as before:

- **CHANGELOG holes.** `CHANGELOG.md` jumps `0.8.1` → `0.7.3`; versions
  0.7.4 (81774bb, shell-lib dedup), 0.7.5 (3939202, neutral command
  templates), and 0.8.0 (631f1f0, the new sd-work-designs command) have no
  entries. A feature release shipped with no changelog note.
- **Tags abandoned.** `git tag` shows only `v0.6.0`; every release through
  0.9.1 since then is untagged, so the documented fleet-refresh anchor
  (README "tag the release commit … then refresh the fleet") points at
  nothing, and provenance versions recorded in consumers have no git ref.

The existing gate catches payload-without-bump but not bump-without-
changelog and not bump-without-tag, which is why 0.7.4/0.7.5/0.8.0 slipped
through green.

## Requirements

- R1: Backfill `CHANGELOG.md` entries for 0.7.4, 0.7.5, and 0.8.0
  (the 0.8.0 entry announces sd-work-designs), so the ledger is contiguous
  from 0.6.0 to 0.8.1.
- R2: Backfill tags for the identifiable release commits since v0.6.0
  (0.6.1→0.9.1) where the bump commit is unambiguous; document any gap.
- R3: Extend the full-check release gate so that when the manifest version
  changes relative to the base ref, a matching top `CHANGELOG.md` heading
  for the new version is required — a bump without a changelog entry fails
  the gate.
- R4: Automate tagging: on merge to main where `manifest.json` version
  changed, CI creates and pushes `v<version>` (or a documented one-command
  release step that is enforced), removing the human tag step that has now
  lapsed twice.

## Acceptance Criteria

- [x] CHANGELOG contiguous 0.6.0→0.9.2; sd-work-designs noted under 0.8.0.
- [x] Tags exist for all identifiable releases since v0.6.0; `git tag`
      no longer shows a lone v0.6.0.
- [x] A test/gate proves a manifest bump without a matching CHANGELOG
      heading fails full-check (mirror the existing payload-bump gate
      tests in `tests/test_pack_drift.py`).
- [x] Auto-tag mechanism verified (CI dry-run or documented+tested step).

## Non-goals

- Retro-filling CHANGELOG entries for pre-0.6.0 releases (out of scope per
  the original release-process task).
- Generated GitHub release notes tooling — a plain CHANGELOG + tags is
  sufficient.

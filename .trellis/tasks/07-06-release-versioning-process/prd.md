# Establish release tagging and changelog process

## Goal

The pack has shipped 28+ releases (manifest version 0.5.28) with
**zero git tags** and no changelog. The release-commit convention
(`chore: release sd-ai-command-pack 0.5.24`) lapsed after 0.5.24 —
0.5.25 through 0.5.28 were bumped inside ordinary `fix:` commits. No
release process is documented in README, AGENTS.md, or the installed
guide. This matters beyond hygiene: consumer repos compare installed
provenance versions against pack versions (README:656-659), and
versions 0.5.20-0.5.26 have no history in either the task archive or
the workspace journal — without tags there is no auditable anchor for
"what was in 0.5.23".

## Requirements

- R1: Tag the current release (`v0.5.28`) and adopt tag-per-bump going
  forward. Backfilling older tags is optional — only where the exact
  bump commit is identifiable.
- R2: Document the release sequence in a short "Releasing" README (or
  CONTRIBUTING) section: bump `manifest.json` version whenever the
  shipped payload changes → conventional release commit → tag → (if
  applicable) fleet refresh.
- R3: Add a minimal CHANGELOG.md (or adopt generated GitHub release
  notes per tag) starting from 0.5.28; retro-filling is out of scope.
- R4: Optional guard: a full-check or CI check that fails when
  tracked `templates/**`/`manifest.json` payload changes in a commit
  that does not bump the manifest version (prevents the silent-bump
  drift that produced the 0.5.25-0.5.28 gap). If deferred, record the
  decision.

## Acceptance Criteria

- [ ] `git tag` lists `v0.5.28`; the process doc exists and matches
  what CI/hooks enforce.
- [ ] Next release after this task lands follows the documented
  sequence (verifiable in history).
- [ ] Full battery green.

## Notes

- Origin: 2026-07-06 deep review (Tooling finding 5 MEDIUM). Version
  anchor also strengthens the provenance story from
  07-03-receipt-provenance.

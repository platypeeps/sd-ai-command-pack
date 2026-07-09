# Move shared command templates to a neutral source location

## Goal

Manifest entries for nine platforms (antigravity, codebuddy, devin,
droid, kilo, pi, qoder, trae, zcode) use the Cursor command templates
under `templates/.cursor/commands/` as their install `source` (e.g.
codebuddy's `sd/start.md` is sourced from the cursor `sd-start.md`).
The path encodes the wrong ownership: a contributor making a
Cursor-specific tweak silently changes the installed prompt text of
nine other platforms, and nothing in the frontend spec documents that
these files are the shared generic-markdown command body. The skills
side already solved this correctly with a single neutral source
(`templates/.agents/skills/`) reused by all platforms.

## Requirements

- R1: Move the shared command bodies to a neutral source location — a
  new shared commands directory under `templates/` (suggested name:
  `.commands`, or another name that clearly signals shared ownership).
- R2: Update all manifest entries — including Cursor's own — to point
  at the neutral source. Installed target paths must not change;
  consumers see no diff in installed content (byte-identical bodies,
  so provenance hashes are unaffected).
- R3: Update `.trellis/spec/frontend/directory-structure.md` and
  `adapter-guidelines.md` to document the shared-source pattern for
  command bodies (mirroring the existing skills-sharing documentation).
- R4: Update any tests that reference the old source paths; add or
  keep a test asserting the nine platforms and Cursor share one source
  file per command.
- R5: Bump the manifest version per the release convention (payload
  paths change even though content is identical).

## Acceptance Criteria

- [x] No manifest entry sources command bodies from
  `templates/.cursor/commands/`; a fresh install into a consumer
  fixture produces byte-identical installed files vs. before the move.
- [x] Frontend spec documents the shared command-source pattern.
- [x] Full battery green: unittest suite, 100% coverage on install.py,
  full-check, shellcheck; template twins byte-identical.

## Implementation Notes

- Moved the twelve generic Markdown command bodies from
  `templates/.cursor/commands/` to `templates/.commands/`.
- Updated all Cursor and generic Markdown platform manifest entries to source
  from `templates/.commands/` while leaving installed target paths unchanged.
- Bumped the manifest version to `0.7.5` for the shipped payload source-layout
  change.
- Updated frontend and backend specs to document the neutral shared command
  source pattern.
- Added regression coverage that each generic Markdown platform shares the same
  neutral command source per command.

## Validation

- [x] Verified all moved command bodies are byte-identical to the previous
  Cursor command sources from `main`.
- [x] Verified manifest sources resolve, no entry sources
  `templates/.cursor/commands/`, and 120 entries source `templates/.commands/`.
- [x] Focused manifest/adapter tests passed.
- [x] Full unit suite passed: 360 tests.

## Notes

- Origin: 2026-07-06 deep review (Architecture finding 5 MEDIUM),
  adopted as a task per session decision on 2026-07-06.
- Sequence with `07-06-introduce-platform-registry` — both edit the
  manifest heavily; landing them together (or registry first) avoids
  double churn.

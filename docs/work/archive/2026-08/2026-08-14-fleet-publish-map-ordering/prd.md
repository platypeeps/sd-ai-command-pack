---
title: Enforce post-archive generated-map ordering in fleet publication
status: done
created: 2026-08-14
branch: fix/generated-map-ordering-guard
---
# Enforce post-archive generated-map ordering in fleet publication

## Problem

Campaign `refresh-0.71.5-20260814T113545Z` published four consumer PRs whose
`docs/repomix-map.md` listed `.trellis/tasks/<slug>/` — a directory that no
longer existed at the PR head, because finalization had archived the task to
`.trellis/tasks/archive/<month>/<slug>/` after the map was generated. Copilot
caught it in rwbp-coordinator; the other three were corrected pre-emptively.
Each correction cost an extra post-push commit, a head advance, and a
`pr-head-advanced` republication epoch in the fleet controller.

The pack already solves this. `scripts/sd-ai-command-pack-fleet-publish.py`
transactionally moves the active task to its archive path, regenerates the map
against that post-archive layout, moves the task back, and only then makes the
work commit — so the map committed at H1 already matches the tree finalization
will produce.

Two things let the defect through anyway:

1. The `pr-publication` bullet in `.agents/skills/sd-fleet-refresh/SKILL.md`
   lists "commit ... classify ... push, and create or reuse one PR" *before* it
   mentions folding finish-work with the helper. An operator following the
   bullet in written order pushes first and reaches the fold too late. The
   helper is named, but the sequence around it is wrong.
2. Nothing detects the drift. `checkDocumentationPathReferences` in
   `scripts/sd-ai-command-pack-review-preflight.mjs` explicitly exempts
   `docs/repomix-map.md`, so a map naming a path that does not exist passes
   every local gate. Only a remote reviewer noticed.

## Goal

Make the correct ordering the one the procedure states, and make a violation
fail a deterministic local check rather than depend on operator memory or a
remote reviewer.

## Requirements

- The `pr-publication` procedure must state the publication sequence in the
  order it must be executed, with the helper as the step that produces the
  pushed head rather than an aside after "push".
- `docs/FLEET_ROLLOUT.md` must agree with the skill on that sequence, including
  what a consumer without the helper does instead.
- A deterministic, read-only check must fail when a tracked generated
  structural map names a `.trellis/` path that does not exist in the working
  tree.
- The check must ship to consumers through the normal payload, so the next
  refresh installs it everywhere.
- The check must not fire on a repository that owns no such map.

## Non-goals

- Changing `sd-ai-command-pack-fleet-publish.py`'s own behaviour. It already
  produces the correct ordering.
- Changing any consumer's own repomix map generator or repomix configuration.
  Those paths exist only in consumer checkouts; the fix stays in the pack.
- Making the check regenerate the map. It stays read-only; regeneration belongs
  to `candidatePrepare` and the publish helper.

## Acceptance Criteria

- [x] `.agents/skills/sd-fleet-refresh/SKILL.md` states the `pr-publication`
      steps in executable order, with the publish helper before push.
- [x] `docs/FLEET_ROLLOUT.md` describes the same sequence and does not
      contradict the skill.
- [x] A new review-preflight check fails on a map that names a missing
      `.trellis/` path and passes on a map whose paths all exist.
- [x] The check passes silently in a repository with no generated map.
- [x] Reconstructed paths come from the map's own `# Directory Structure`
      section; no other section is parsed.
- [x] New tests cover: drift detected, clean map, no map, map with no
      directory-structure section, a map whose non-`.trellis/` entries are
      missing (not reported), and a map whose indentation is malformed (warns,
      does not fail).
- [x] `make generate`, `make sync`, and the full `sd-check` gate pass.
- [x] The manifest version is bumped and `CHANGELOG.md` records the change,
      because shipped payload changes.

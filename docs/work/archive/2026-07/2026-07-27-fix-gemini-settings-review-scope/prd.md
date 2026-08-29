---
title: Fix Gemini settings review-scope parity
status: done
created: 2026-07-27
branch: codex/fix-gemini-settings-review-scope
---
# Fix Gemini settings review-scope parity

## Goal

Ship a compatible command-pack correction so `.gemini/settings.json` is
classified consistently as a Trellis-owned runtime path by the platform
registry, JavaScript review preflight, and shell review-scope scanner.

## Background

- `templates/scripts/sd-ai-command-pack-review-preflight.mjs` already treats
  `.gemini/settings.json` as a Trellis-copied path.
- `installer/registry.py` omits that path from Gemini's
  `trellis_local_only`, and
  `templates/scripts/sd-ai-command-pack-review-scope.sh:104` consequently
  omits it from `is_trellis_runtime_path`.
- The root `scripts/` copies are generated dogfood mirrors; `templates/**` is
  authoritative.
- Current `main` is version `0.55.4`, so this compatible fix is version
  `0.55.5` under the repository's patch-version policy.

## Requirements

- R1. Add `.gemini/settings.json` to Gemini's canonical Trellis-local ownership
  data in `installer/registry.py`.
- R2. Add the same path to the template shell classifier and synchronize its
  root mirror through canonical generation/sync tooling.
- R3. Extend focused tests so registry/classifier drift recreates a failure.
- R4. Bump the manifest to `0.55.5`, add a matching top `CHANGELOG.md` entry,
  and regenerate all required release/provenance evidence.
- R5. Preserve every unrelated source checkout and task; this task operates
  only in the isolated branch and clone.
- R6. Publish through the normal pull-request, review, CI, finish-work, merge,
  and release-tag lifecycle. Do not modify upstream Trellis.

## Acceptance Criteria

- [ ] Registry, template shell classifier, root mirror, and JavaScript
  classifier agree that `.gemini/settings.json` is Trellis-owned.
- [ ] Focused regression tests pass and fail when the new registry or shell
  classification is removed.
- [ ] Template/root parity and the full canonical `make release-prep` gate pass
  for the exact source head.
- [ ] Version `0.55.5` and its changelog/release evidence are internally
  consistent.
- [ ] The upstream PR has no unresolved actionable review threads and required
  CI is green before merge.
- [ ] Release tag `v0.55.5` identifies the merged payload used for the consumer
  refresh.

## Out of Scope

- Changes to Trellis or Trellis-owned generated platform behavior.
- Any command-pack feature beyond the Gemini settings-path parity correction.

# Docs accuracy batch: backend spec split + versioning policy

## Problem

Audit findings A-006 and A-007 (both P2·S), 2026-07-15 @ f6f3932:

- A-006 (documentation): `.trellis/spec/backend/directory-structure.md`
  predates the installer/ package split — `:62` says `PLATFORM_REGISTRY`
  lives in `install.py` (reality: `installer/registry.py:27`), `:40`/`:71`
  describe a single-file installer, the layout tree (:16-36) omits
  `installer/` entirely, and it contradicts sibling
  `manifest-and-filesystem.md:307`. AGENTS.md and CONTRIBUTING.md point
  contributors at this spec as the canonical map.
- A-007 (release-hygiene): the versioning scheme and public-surface
  stability boundary are undocumented — CONTRIBUTING.md:52-63 says when to
  bump but never what major/minor/patch mean or which installed surfaces
  (env vars, command names, script paths) are stable vs internal.

## Goal

The backend spec matches the real module layout, and consumers can reason
about upgrade safety from a documented versioning policy.

## Requirements

- Update directory-structure.md: add installer/ package to the layout tree
  and module organization; correct all PLATFORM_REGISTRY/install.py
  statements; align with manifest-and-filesystem.md.
- Add a Versioning section to CONTRIBUTING.md: 0.x scheme (what triggers
  minor vs patch), and name the stable public surface (commands, env vars,
  shipped script CLIs) vs internal helpers.
- Fold in A-025/A-026 if trivial (backfilled 0.7.1-0.7.4 changelog dates;
  REVIEW_PREFLIGHT_PR_BODY deprecation sunset) — optional scope.

## Acceptance Criteria

- [ ] Spec references resolve to real modules; no install.py-owns-registry
      claims remain.
- [ ] CONTRIBUTING has the versioning + stability-boundary section.
- [ ] Doc-path preflight and full-check pass.

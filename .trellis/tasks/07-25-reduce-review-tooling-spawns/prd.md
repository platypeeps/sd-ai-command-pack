# Reduce review tooling process spawns

## Goal

The per-change review path stops paying redundant process spawns: review-preflight
computes changed-paths and base-refs once per run, and review-scope answers 378 membership
tests with one process instead of ~1500 forks (full-check pays review-scope twice).

## Origin

SE-pack repo audit 2026-07-25 (se-ai-command-pack ledger A-029 + A-030, both P3/S).
Related in-repo finding: this repo's own ledger A-024 (preflight recomputes documentation
file list) — same class; fix together. SE-side bundle task retired in favor of this.

## Requirements

- `scripts/sd-ai-command-pack-review-preflight.mjs`: memoize defaultReviewBaseRef() and
  currentChangedPaths() (~:2040; call sites ~:485/:598/:935/:1281) in per-run module
  caches reset in runReviewPreflight(), alongside the existing readTextCache pattern —
  and fold in the A-024 documentation-list recomputation while there.
- `scripts/sd-ai-command-pack-review-scope.sh` (~:127, :259-273): load
  installed-targets.txt once into an associative array (or one grep -Fxf pass); drop
  per-file command-substitution subshells.

## Acceptance Criteria

- [ ] Identical classification output on a fixture diff.
- [ ] Measurable spawn reduction on a 378-target pack-refresh diff, in both full-check
      passes.
- [ ] Changelog + version; fleet rollout via normal refresh.

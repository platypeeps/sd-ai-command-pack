---
title: Cut CI lane cost in tests.yml
status: planning
created: 2026-08-08
---
# Cut CI lane cost in tests.yml

## Problem

2026-08-08 CI audit of the single tests.yml workflow: the bookkeeping fast
lane fired on only 6 of 59 runs because `ALLOWED_PATH_PREFIXES` admits only
`.trellis/tasks|workspace`; the shell-coverage job runs on every PR yet gates
nothing; the macOS leg would be 73% of billable minutes on private consumers
(10x multiplier; $0 here on the public repo but the pack pattern is copied).
Merges to main re-run the full suite already run on the PR head.

## Requirements

1. Widen the bookkeeping allowlist to `docs/` + top-level `*.md` — staying
   INSIDE the byte-identical-classifier trust model; never `.github/` or
   `scripts/`.
2. Shell-coverage moves to nightly/main-only with a kcov cache.
3. macOS leg main-only.
4. Skip full re-run on merge to main when the merged head already passed;
   KEEP the first-push-always-full rule (`action != synchronize`,
   tests.yml:137-139).

## Acceptance criteria

- [ ] Classifier trust model unchanged (byte-identical rule intact) —
      documented reasoning in design.md.
- [ ] Fast-lane hit rate measured before/after over a 2-week window.
- [ ] No gate that previously blocked a merge is weakened; shell-coverage was
      verified non-gating before the move.
- [ ] Private-consumer guidance updated (fleet one-path task carries
      propagation).

## Evidence

59-run sample; 6 fast-lane hits; shell-coverage gates nothing (job has no
required-check wiring); macOS 73% share computed from run timings.

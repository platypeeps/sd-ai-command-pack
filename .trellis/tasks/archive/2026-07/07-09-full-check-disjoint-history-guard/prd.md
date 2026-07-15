# Guard full-check against disjoint-history diffs

## Goal

Make the shipped `full-check.sh` degrade gracefully when it cannot compute a
diff base (disjoint history / missing merge-base), instead of hard-exiting the
whole gate under `set -e`.

## Problem

Surfaced by the 2026-07-09 tooling review (PLAUSIBLE, edge case). In
`collect_reviewable_changed_paths`, `full-check.sh:119` runs
`git diff "$base_ref"...HEAD`. When the three-dot form cannot find a merge-base
(shallow clones, disjoint/unrelated histories, a base ref with no common
ancestor), git exits non-zero; under `set -e` and the pipefail'd command
substitution at `full-check.sh:306`, that failure propagates and kills the
script. By contrast the unreachable-ref case already warns and continues — so
the behavior is inconsistent: one base-resolution failure warns, another aborts.

Consumers vendor this script and run it as their local gate, so an abort on a
legitimate disjoint-history checkout blocks the gate rather than degrading.

## Requirements

- R1: A merge-base / disjoint-history failure when computing the diff base is
  handled like the existing unreachable-ref case: emit a clear warning and
  continue (fall back to a safe changed-path set, e.g. treat all tracked paths
  as reviewable, or skip the base-scoped narrowing) rather than exiting.
- R2: Genuine git errors that are not base-resolution failures still surface
  (do not blanket-swallow git failures).
- R3: The behavior is covered by a test (the pack has `tests/test_full_check.py`
  and a subprocess harness) that constructs a disjoint-history repo and asserts
  full-check warns-and-continues instead of aborting.

## Acceptance Criteria

- [x] Running full-check in a repo whose base ref shares no history with HEAD
      warns and completes instead of exiting on the diff step.
- [x] A non-base git error still fails the gate (no over-broad swallow).
- [x] Test added and green on the CI matrix; shellcheck `-S warning` stays
      clean; `scripts/` and `templates/scripts/` copies byte-identical.

## Non-goals

- Reworking the change-classification/scoping logic beyond the base-resolution
  fallback.

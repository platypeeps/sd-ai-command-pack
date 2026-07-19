# Harden work-loop file I/O and best-effort cleanup

## Goal

Make the shipped work-loop helper's file boundaries explicit and portable,
while preserving its intentional best-effort permission and cleanup semantics.

## Background

The sd-ai-command-pack 0.21.0 refresh PR for rwbp-coordinator surfaced four
duplicate GitHub Code Quality findings in
`scripts/sd-ai-command-pack-work-loop.py`. The reviewer flags the bare
`except OSError: pass` handlers in `ensure_private_directory()` and
`atomic_write_json()` as unexplained empty exception blocks. These are
pack-owned implementation findings and therefore must be fixed upstream rather
than patched in consumer refresh PRs.

The same rollout later failed mezmo_benchmark's full pytest suite because the
candidate-file `Path.read_text()` call selected UTF-8 without an explicit error
policy. That repository's production Python defect scanner requires both
parameters so file decoding remains deliberate and locale-independent.

## Requirements

- Add concise rationale to each intentional best-effort `OSError` handler in
  the canonical template helper.
- Read candidate JSON with explicit `encoding="utf-8"` and `errors="strict"`.
- Keep `scripts/sd-ai-command-pack-work-loop.py` synchronized with its template
  twin.
- Preserve current chmod, cleanup, original-exception, and exit-code behavior.
- Add or update focused tests only if executable behavior changes.
- Ship through the normal pack release and fleet-refresh process; do not patch
  provenance-managed consumer copies manually.

## Acceptance Criteria

- [ ] Every intentional empty `OSError` handler in the affected functions has
  a short explanation of why failure is suppressed.
- [ ] Candidate-file reads pin strict UTF-8 decoding and have focused
  regression coverage.
- [ ] Template/generated parity checks pass.
- [ ] Focused work-loop tests and the canonical pack checks pass.
- [ ] Consumer refresh reviews no longer need a local implementation patch for
  these findings.

## Evidence

- rwbp-coordinator PR #123 review threads:
  `discussion_r3610522360`, `discussion_r3610522361`,
  `discussion_r3610522363`, and `discussion_r3610522366`.
- mezmo_benchmark fleet validation: 4,254 tests passed, 9 skipped, and the sole
  failure identified missing `errors=` at
  `scripts/sd-ai-command-pack-work-loop.py:1256`.

## Out Of Scope

- Changing the atomic-write algorithm or swallowing new error classes.
- Editing consumer copies directly.

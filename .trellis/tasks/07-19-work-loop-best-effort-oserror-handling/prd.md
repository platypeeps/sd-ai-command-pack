# Clarify work-loop best-effort OSError handling

## Goal

Make the shipped work-loop helper's intentional best-effort permission and
cleanup behavior explicit without changing runtime semantics.

## Background

The sd-ai-command-pack 0.21.0 refresh PR for rwbp-coordinator surfaced four
duplicate GitHub Code Quality findings in
`scripts/sd-ai-command-pack-work-loop.py`. The reviewer flags the bare
`except OSError: pass` handlers in `ensure_private_directory()` and
`atomic_write_json()` as unexplained empty exception blocks. These are
pack-owned implementation findings and therefore must be fixed upstream rather
than patched in consumer refresh PRs.

## Requirements

- Add concise rationale to each intentional best-effort `OSError` handler in
  the canonical template helper.
- Keep `scripts/sd-ai-command-pack-work-loop.py` synchronized with its template
  twin.
- Preserve current chmod, cleanup, original-exception, and exit-code behavior.
- Add or update focused tests only if executable behavior changes.
- Ship through the normal pack release and fleet-refresh process; do not patch
  provenance-managed consumer copies manually.

## Acceptance Criteria

- [ ] Every intentional empty `OSError` handler in the affected functions has
  a short explanation of why failure is suppressed.
- [ ] Template/generated parity checks pass.
- [ ] Focused work-loop tests and the canonical pack checks pass.
- [ ] Consumer refresh reviews no longer need a local implementation patch for
  these findings.

## Evidence

- rwbp-coordinator PR #123 review threads:
  `discussion_r3610522360`, `discussion_r3610522361`,
  `discussion_r3610522363`, and `discussion_r3610522366`.

## Out Of Scope

- Changing the atomic-write algorithm or swallowing new error classes.
- Editing consumer copies directly.

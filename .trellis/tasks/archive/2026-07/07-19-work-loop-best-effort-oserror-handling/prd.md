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

After the 0.21.1 correction, Copilot found that `atomic_write_json()` still
called `os.chmod()` on the temporary file before entering the existing
best-effort final permission block. `tempfile.mkstemp()` already creates the
temporary file privately, so that redundant call made otherwise valid writes
fail on filesystems without chmod support.

## Requirements

- Add concise rationale to each intentional best-effort `OSError` handler in
  the canonical template helper.
- Read candidate JSON with explicit `encoding="utf-8"` and `errors="strict"`.
- Rely on `tempfile.mkstemp()` for private temporary-file creation and keep the
  final permission tightening best-effort.
- Keep `scripts/sd-ai-command-pack-work-loop.py` synchronized with its template
  twin.
- Preserve cleanup, original-exception, and exit-code behavior.
- Add or update focused tests only if executable behavior changes.
- Ship through the normal pack release and fleet-refresh process; do not patch
  provenance-managed consumer copies manually.

## Acceptance Criteria

- [x] Every intentional empty `OSError` handler in the affected functions has
  a short explanation of why failure is suppressed.
- [x] Candidate-file reads pin strict UTF-8 decoding and have focused
  regression coverage.
- [x] Atomic state writes succeed when chmod is unsupported and retain focused
  regression coverage.
- [x] Template/generated parity checks pass.
- [x] Focused work-loop tests and the canonical pack checks pass.
- [x] Consumer refresh reviews no longer need a local implementation patch for
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

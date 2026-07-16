# Batch install-audit git check-ignore calls

## Problem

Audit finding A-014 (P2·M, performance), 2026-07-15 @ f6f3932:
`scripts/sd-ai-command-pack-install-audit.py:507-516` (`is_gitignored`) runs
one `git check-ignore` subprocess per queried path, invoked per-item from
three loops (`:535`, `:552`, `:627`). On a checkout with gitignored adapter
directories, a routine audit forks roughly one `git` process per absent
target across all manifest targets, and the cost scales linearly with pack
size (the pack just grew ~55 entries in 0.11.0).

## Decision history

Deliberately declined in the July 2026 optimization pass as risky/low-gain
(three call sites with different candidate sets; restructuring a shipped
audit script for milliseconds). Reopened by the maintainer on 2026-07-16
after the first repo audit independently rediscovered it and scored it P2
on the scaling argument. The prior risk concern stands: the refactor must
be behavior-preserving and well-covered, not just faster.

## Goal

Ignore-status resolution costs one subprocess per audit run regardless of
target count, with byte-identical audit output and exit codes.

## Requirements

- Collect candidate paths per pass and resolve them with a single
  `git check-ignore --stdin -z` invocation (set-membership lookup after).
- Preserve exact output text, ordering, and exit codes of the audit script
  (existing tests must pass unmodified except for internals they stub).
- Handle the batch call's exit-code semantics correctly (check-ignore exits
  1 when no path matches — not an error) and degrade exactly as today when
  git is unavailable.
- Keep the three call sites' differing candidate sets correct — no
  cross-contamination between the structural, pack-like, and provenance
  passes.
- Twin the change under templates/scripts/ (drift gate) and bump the
  manifest version with a CHANGELOG entry (shipped payload).

## Acceptance Criteria

- [x] One check-ignore subprocess per pass (or per run) — verified by a test
      counting subprocess invocations via a stubbed git.
- [x] Byte-identical audit output and exit codes on the existing test matrix.
- [x] Exit-code-1 (no matches) and missing-git paths covered by tests.
- [x] Coverage floors hold; ledger A-014 can be marked fixed by the next
      follow-up audit.

## Implementation Notes

- Added `gitignored_paths()` to the shipped install-audit script and template
  twin, using `git check-ignore --stdin -z` to resolve each audit phase's
  candidate paths in one subprocess.
- Reworked expected-target, structural, and provenance checks to collect
  candidate paths before classification, then replay the existing
  warning/failure wording and ordering.
- Added focused regression tests for structural, expected-target, and
  provenance batching plus the exit-code-1 no-match behavior. The existing
  missing-git CLI test continues to cover fail-closed behavior when git is
  unavailable.
- Bumped the pack manifest to `0.13.2` and recorded the shipped-payload change
  in `CHANGELOG.md`.

# Partition pack test suite by subsystem

## Goal

Partition the monolithic installer test file into subsystem-focused test files without reducing behavior coverage.

## Problem

`tests/test_install.py` has grown into a broad test surface covering installer behavior plus review-local, KB generation, preflight checks, housekeeping, drift checks, and generated file assertions. The coverage is valuable, but the file is large enough that it is hard to find the right test area, run focused subsets, and review future changes.

## Requirements

- Split the monolithic test file into subsystem-focused test modules while preserving behavior coverage.
- Keep shared fixtures and helpers obvious and lightweight. Prefer a small shared helper module over copying setup logic across many files.
- Preserve compatibility with `python3 -m unittest discover -s tests`.
- Avoid changing production behavior as part of the test move.
- Preserve test names or comments where they encode important historical regressions.
- Make it easier to run focused areas such as installer CLI, provenance, review-local, update-spec KB, full-check, housekeeping, and generated/platform parity.
- Verify the collected test count is identical before and after the split
  (360 tests as of 2026-07-09) so no test is silently dropped by
  discovery.
- Before renaming any test, grep docs and the preflight fixtures for
  hardcoded test node ids: `sd-ai-command-pack-review-preflight.mjs`
  resolves pytest node ids, so a rename can break documented references.
- Update `.trellis/spec/backend/directory-structure.md` (test layout
  section) to describe the new multi-file structure; its current "one
  file unless volume justifies splitting" clause is the trigger this
  task executes.

## Acceptance Criteria

- [x] `python3 -m unittest discover -s tests` discovers and runs the full suite after partitioning.
- [x] The total number of meaningful assertions/regression scenarios is not reduced.
- [x] Subsystem files have clear names, for example `test_install_core.py`, `test_install_audit.py`, `test_update_spec_kb.py`, `test_review_local.py`, and `test_housekeeping.py`.
- [x] Shared setup helpers live in a single obvious test support location.
- [x] Coverage thresholds remain satisfied.
- [x] `git diff --check` passes.
- [x] Future contributors can identify where to add tests for each major pack subsystem.

## Implementation Notes

- Move tests mechanically first, then do any small helper cleanup in a second pass.
- Keep imports local and simple so the tests still run without installing the pack as a package.
- Avoid changing assertions during the move unless a test is already wrong or duplicated.

## Notes

- This task is lower priority than the KB correctness tasks, but it will make future pack maintenance less brittle.

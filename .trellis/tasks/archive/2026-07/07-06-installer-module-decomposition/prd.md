# Decompose installer module boundaries

## Goal

Split the large installer implementation into focused internal modules while preserving CLI behavior, safety checks, provenance, and tests.

## Problem

`install.py` is the central installer entrypoint and currently carries many independent responsibilities in one large file: CLI parsing, manifest loading, path safety, platform selection, install/update, managed blocks, local-only behavior, gitignore updates, provenance, removal, install audit, and command dispatch.

The current behavior is well tested, but continued feature work is increasing the risk of accidental coupling and makes review harder than it needs to be.

## Requirements

- Preserve the public CLI contract of `python3 install.py`, including `--help`, `--version`, install/update behavior, `--local-only`, `--remove`, and all documented options.
- Preserve manifest semantics and the generated/provenance behavior already covered by tests.
- Split implementation into focused internal modules without introducing an external package dependency or requiring installation before use.
- Keep imports simple for direct execution from a cloned repo.
- Do not make broad behavioral changes while decomposing. Any behavior change discovered during the refactor should become a separate task unless it is required to preserve existing tests.
- Keep tests meaningful during the transition; avoid snapshot-style churn that hides real behavior changes.

## Acceptance Criteria

- [x] `python3 install.py --help` and `python3 install.py --version` continue to work from a fresh clone (plus remote-cwd and symlink execution, both test-pinned).
- [x] Existing install/update/remove/local-only tests pass without reducing coverage — the 100% gate was widened to cover the whole package (1,007 stmts, 0 miss).
- [x] Core responsibilities separated: installer/{registry,manifest,fileops,provenance,localonly,removal} in one-way dependency order; largest module 564 lines.
- [x] The top-level `install.py` is a 330-line thin entry (argparse, main, exit, re-exports).
- [x] No end-user documentation changes needed; internal layout documented in the task design.md.
- [x] `python3 -m unittest discover -s tests` passes (311 tests).
- [x] `git diff --check` passes.

## Suggested Phasing

1. Extract pure helpers first, starting with manifest parsing and path safety.
2. Move provenance and install receipt logic into a focused module.
3. Move install/remove planning and file writes behind explicit functions with narrow inputs.
4. Leave CLI parsing and process exit handling in `install.py`.
5. Run the full test suite after each phase to keep the refactor safe.

## Notes

- This is a maintainability task. It should not be bundled with functional installer changes.
- Because this task is larger and architectural, add a `design.md` before implementation.

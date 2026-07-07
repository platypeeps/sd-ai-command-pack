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

- [ ] `python3 install.py --help` and `python3 install.py --version` continue to work from a fresh clone.
- [ ] Existing install/update/remove/local-only tests pass without reducing coverage.
- [ ] Core responsibilities are separated into named modules or clearly bounded components, for example manifest handling, path safety, install planning, file operations, provenance, and CLI orchestration.
- [ ] The top-level `install.py` becomes a thin CLI entrypoint rather than the home for most implementation details.
- [ ] Documentation does not need to change for end users except possibly developer-facing notes about the new internal layout.
- [ ] `python3 -m unittest discover -s tests` passes.
- [ ] `git diff --check` passes.

## Suggested Phasing

1. Extract pure helpers first, starting with manifest parsing and path safety.
2. Move provenance and install receipt logic into a focused module.
3. Move install/remove planning and file writes behind explicit functions with narrow inputs.
4. Leave CLI parsing and process exit handling in `install.py`.
5. Run the full test suite after each phase to keep the refactor safe.

## Notes

- This is a maintainability task. It should not be bundled with functional installer changes.
- Because this task is larger and architectural, add a `design.md` before implementation.

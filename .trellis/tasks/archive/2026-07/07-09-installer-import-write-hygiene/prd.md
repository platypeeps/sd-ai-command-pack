# Installer import and write hygiene

## Goal

Restore the ruff `F` lane's ability to guard the freshly-decomposed
`installer/` package, and fix a confirmed temp-file leak on the atomic
write path. Two independent low-severity cleanups that both reduce the risk
of the *next* refactor bug going unnoticed.

## Problem

- **Star-import facade defeats the linter where it matters most.**
  `install.py:28-37` chains `from installer.X import *` for all six
  modules, and every module re-star-imports its dependencies
  (`removal.py:17-21`, etc.). There is no `__all__` anywhere, and
  `pyproject.toml` disables `F401/F403/F405/F811` for `install.py` and
  `installer/*.py`. Consequences: ruff cannot catch undefined names,
  unused imports, or redefinitions in exactly the package under the 100%
  coverage gate; with F811 off and last-import-wins star semantics,
  defining the same name in two modules silently changes which
  implementation the facade exposes — lint-clean and possibly test-green.
  `main()` already shadows the imported `manifest` module with a local
  variable (`install.py` uses `manifest` as a local at ~line 149 while the
  module is imported at line 23). Flagged independently by the
  architecture, Python, and tooling reviewers.
- **Atomic write leaks its temp file on write failure.**
  `installer/fileops.py:47-71`: `temporary_path` is assigned only after
  `write`/`flush`/`fsync` succeed inside the `with NamedTemporaryFile(...)`
  block. If any of those raise `OSError` (e.g. ENOSPC), control leaves the
  block with `temporary_path` still `None` (and `delete=False`), so the
  `finally` cleanup is skipped and a stray `.<name>.<rand>.tmp` is orphaned
  in the destination dir. Reproduced by injecting an ENOSPC-raising writer;
  on a full disk every attempted write orphans a temp file.

## Requirements

- R1: Replace wildcard imports with explicit imports across `install.py`
  and `installer/*.py`; add `__all__` to each installer module naming its
  public surface.
- R2: Re-enable `F811` (and ideally `F401`) for `install.py` and
  `installer/*` in `pyproject.toml`; resolve any real findings (including
  the `manifest` local-vs-module shadow) rather than re-suppressing.
- R3: In `atomic_write_bytes`, capture `temporary_path = Path(temporary.name)`
  as the first statement inside the `with` block (before writing) so the
  `finally` always cleans up on a failed write/flush/fsync.
- R4: Behavior is otherwise unchanged — facade aliases stay identity-equal
  to the package functions; no test node-ID churn beyond import lines.

## Acceptance Criteria

- [x] `ruff check` passes with F811/F401 active on install.py + installer/*;
      per-file-ignore block for those files removed or reduced to a
      justified minimum.
- [x] New test: an injected ENOSPC-raising write leaves no `.tmp` file in
      the destination directory (reproduces then locks the leak).
- [x] 100% line+branch coverage on install.py + installer/* maintained;
      full suite green.

## Non-goals

- Migrating every test from `install.<name>` to
  `installer.<module>.<name>` — a larger churn deferred; keeping the facade
  re-exports is fine as long as they are explicit and `__all__`-scoped.
- Adding a mypy lane (separate static-analysis improvement).

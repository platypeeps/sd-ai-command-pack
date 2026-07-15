# Installer simplifications from optimization review

## Goal

Remove duplicated installer code and a few redundant filesystem/IO operations
surfaced by the 2026-07-14 optimization analysis, without changing behavior and
without dropping the enforced 100% line+branch coverage on `install.py` +
`installer/*`. Each item is a confirmed structural win, branch-neutral or
coverage-cheap.

## Requirements

- R1: Collapse the three near-identical generated-file installers —
  `install_provenance_file`, `install_pack_manifest_file`,
  `install_installed_targets_file` (`installer/provenance.py`) — whose bodies
  are byte-identical except the `PackFile.kind` and the content expression, into
  one shared `_install_generated_text_file(file, target, content, *, dry_run)`
  helper. Also fold the 7-line `PackFile(platform="shared", …,
  source=MANIFEST_PATH, anchor=None, install=ALWAYS_INSTALL)` literal (recurs 4×,
  incl. `fileops.install_trellis_gitignore`) into a `_generated_pack_file(kind,
  target)` factory. ~40 LOC.
- R2: Memoize source digests in `provenance_content` (`installer/provenance.py`):
  the manifest has 343 non-managed targets but ~83 distinct source paths, so the
  same file is `read_bytes()`+`sha256` up to 11×. Cache by source path within the
  call (343 → 83 hash operations). Behavior identical.
- R3: Extract one `installed_targets_set(selected, extra_targets) -> set[str]`
  used by both `install.py` (the `receipt_target_set` at ~551) and
  `installer/provenance.installed_targets_content` (~34), which currently build
  the identical set independently — making the "provenance coverage == receipt
  contents" invariant structural instead of coincidental.
- R4: Read + JSON-parse `provenance.json` once per `--remove`. It is currently
  parsed twice (`installer/removal.py` `installed_target_candidates` and
  `remove_installed_pack`). Parse once and pass the dict in.
- R5: Centralize the stringly-typed status vocabulary as co-located module-level
  `frozenset` constants (e.g. `CONFLICT_STATUSES`, `VOUCHABLE_STATUSES`) in
  `fileops.py` next to `InstallResult`, imported at the comparison sites
  (`install.py` conflict checks; `provenance.py` vouchable check). A typo becomes
  a `NameError` instead of a silent membership miss. Rename-only; do NOT convert
  statuses to an Enum (they are printed with width specifiers).
- R6: Extract the repeated `path_is_occupied(dest) and not dest.is_file()` guard
  + identical error message (3 sites in `fileops.py`) into one helper.

## Constraints

- No behavior change; facade aliases stay identity-equal. Any `__all__` /
  re-export lists in `install.py`/`installer/*` must stay consistent (this repo
  uses explicit imports, not star, in `install.py`).
- `make test` must pass with installer coverage at 100% (line+branch) and the
  scripts gate ≥76%; `make lint` (ruff+mypy) and `make full-check` green.
- No new tests should be required for R1/R3/R4/R5/R6 (existing callers cover the
  branches); R2 adds at most one branch already hit by any all-platforms install.

## Acceptance Criteria

- [ ] R1–R6 implemented; net installer LOC reduced (~40+ from R1 alone).
- [ ] `make test` green, installer coverage 100% line+branch, scripts ≥76%.
- [ ] `make lint` and `make full-check` green.
- [ ] No behavioral diff: install/reinstall/remove/dry-run/local-only outputs
      unchanged (existing suite is the oracle).

## Non-goals

- `main()` decomposition, redundant `resolve()` cleanup, and batching
  `git check-ignore` (installer findings 7–9) — lower value, deferred.
- The star-import/`__all__` question is out of scope here (`install.py` already
  uses explicit imports).

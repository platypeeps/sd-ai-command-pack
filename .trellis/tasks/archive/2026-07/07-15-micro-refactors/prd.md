# Micro-refactors: script + installer cleanups

## Goal

Close the deferred low-value tail of the optimization review — a set of
behavior-preserving concision/efficiency micro-refactors across the shipped
scripts and the installer. Each is independent; any that doesn't come out clean
should be dropped rather than forced. 100% installer coverage held; script twins
byte-identical.

## Requirements

Scripts (each fix applies to BOTH `scripts/` and its `templates/scripts/` twin):

- R1 (review-learnings git wrappers, finding 7): `_run_git` (raises on bad rc),
  `_run_git_optional` ("" on failure), `_git_ref_exists` (bool) differ only in
  return-handling. Introduce one `_run_git(args, root, *, check=True)` returning
  a `CompletedProcess`; make `_run_git_optional`/`_git_ref_exists` thin wrappers.
  Keep `_git_untracked_paths` separate (bytes/`-z`). Preserve raise-vs-quiet and
  text-vs-bytes parity exactly.
- R2 (install-audit check-ignore batch, finding 12): `is_gitignored` spawns one
  `git check-ignore` per path. Where it's called over a set of paths, batch into
  a single `git check-ignore --stdin` (drop `-q`, read the ignored subset). Only
  if the call sites make batching clean; per-path correctness must be identical.
- R3 (pr-body-scope pattern normalize, finding 13): `_matches_pattern`
  re-normalizes static `ScopeRule` patterns (`_remove_dot_slash(pattern.replace(
  "\\","/"))`) inside the path×rule×pattern loop. Precompute normalized patterns
  at rule build/merge time so the match loop uses them directly.

Installer (`install.py` / `installer/`, not shipped payload → NO version bump):

- R4 (main() decomposition, installer finding 7): `main()` (~185 lines) does ~10
  jobs. Extract the receipt/provenance assembly block and the results/hints/notes
  printing block (four sequential loops) into helpers so `main()` reads as a
  top-level sequence. Pure clarity; branch-neutral.
- R5 (redundant resolve, finding 8): remove per-file redundant `.resolve()` calls
  where the path is already resolved (e.g. `ROOT` is already resolved;
  `validate_resolved_target_path` re-resolves an already-resolved `target`). Only
  where provably a no-op; keep any defensive resolve that guards untrusted input.

## Constraints (HARD)

- No behavior change: emitted text, exit codes, receipts, and audit results
  identical. The existing suite is the oracle — run `make test` after each R.
- Script twins byte-identical (`diff` empty; pack-drift gate green).
- 100% line+branch installer coverage held; shipped-scripts ≥76% (don't drop the
  touched files). `make lint` (ruff+mypy) + `make full-check` green.
- Scripts changing = shipped payload → the main session bumps the manifest
  (to 0.10.4) + CHANGELOG at commit time; the sub-agent must NOT bump.
- DROP any item that can't be done cleanly/behavior-preservingly and say so.

## Acceptance Criteria

- [ ] The R's that came out clean are implemented; twins byte-identical.
- [ ] `make test` green (installer 100%, scripts ≥76%); behavior unchanged.
- [ ] `make lint` green; anything dropped is reported with a reason.

## Non-goals

- The write/plan mirror-merge and any dry-run/`--check` parity-sensitive change
  (excluded as risky earlier).
- The installer batch-`git check-ignore` in `preserved_receipt_targets`
  (finding 9) — include only if trivially clean; otherwise drop.

# Deduplicate shared shell helpers across pack scripts

## Goal

The shipped shell scripts copy-paste ~9 helper functions across
full-check / review-local / review-scope with no shared lib and no
intra-script drift gate (the pack drift gate only compares `scripts/`
to `templates/`), and the copies have already diverged:

- **Two different Gito rate-limit detectors**:
  `full-check.sh:120-136` uses a two-stage heuristic (collect
  status-like lines from the last 200, require the LAST to be 429);
  `review-local.sh:520-523` uses a single anchored `grep -Eiq` over
  the whole tail. Concrete divergence: a run logging an early
  transient 429 but dying on a 500 is retried by review-local but not
  by full-check. Converge on full-check's stronger implementation.
- Duplicated across 2-3 scripts: `default_review_base_ref`, `has_ref`,
  `configured_review_base_ref`, `load_gito_pack_env`,
  `positive_int_or_default`, `run_gito_command`, and the
  `REVIEW_SCAN_EXCLUDE_DIRS` block.
- **Execution-env inconsistency**: full-check.sh:748 runs the
  operator-configured preflight command with `bash -lc` (login shell,
  sources user profile) while review-local.sh:810 uses plain
  `bash -c`. Pick one (plain `-c` is safer/more predictable).
- **uv cache env only wired in review-local**
  (`prepare_gito_uv_env`, review-local.sh:796-805): the same `gito`
  binary uses different uv cache locations depending on entry point,
  and `SD_AI_COMMAND_PACK_REVIEW_LOCAL_UV_CACHE_DIR` silently has no
  effect under full-check.

## Requirements

- R1: Extract the shared helpers into a new sourced helper library
  under `scripts/` (suggested name: `sd-ai-command-pack-lib` with a
  `.sh` extension, shipped via manifest with a
  template twin), OR — if standalone-script constraints forbid
  sourcing — add an intra-script drift gate to full-check that
  byte-compares the designated shared function blocks across the
  sibling scripts.
- R2: One rate-limit detector (full-check's semantics) used by both
  entry points, with a test capturing the early-429-then-500 case.
- R3: Unify custom-command execution on `bash -c`.
- R4: Wire the uv cache env preparation into full-check's Gito path
  (or hoist it into the shared lib).
- R5: All changes mirrored in `templates/scripts/`; manifest updated
  if a new lib file ships.

## Acceptance Criteria

- [x] No divergent copies of the shared helpers remain (verified by
  the chosen mechanism: sourcing or drift gate).
- [x] Rate-limit retry behavior identical across entry points (test).
- [x] Full battery green: unittest suite, full-check, shellcheck;
  template twins byte-identical.

## Implementation Notes

- Added `scripts/sd-ai-command-pack-shell-lib.sh` and matching template twin as
  the single source for review-scan exclusions, base-ref discovery,
  `MAX_CONCURRENT_TASKS` loading, uv cache/tool directory setup, and Gito
  HTTP-429 retry handling.
- Updated full-check, review-local, and review-scope scripts to source the
  shared helper instead of carrying divergent copies. Full-check now uses the
  shared uv cache setup before Gito and runs configured review-preflight
  commands with `bash -c`.
- Bumped the manifest to `0.7.4`, added the helper as an always-installed
  shared script, and updated README/installed-guide references plus PR-body
  scope and install-audit script lists.
- Added regression tests for helper sourcing, installed helper coverage, the
  early-429-then-500 non-retry case in both entry points, full-check uv cache
  setup, and non-login preflight execution.

## Validation

- [x] Focused helper/Gito/full-check tests: 17 tests passed.
- [x] Full unit suite: 359 tests passed.
- [x] Shellcheck passed for changed shell scripts and template twins.
- [x] Final `sd-ai-command-pack-full-check.sh` gate passed after KB refresh.

## Notes

- Origin: 2026-07-06 deep review (Shell M1, L4, L5). Watch bash 3.2
  compatibility in whatever lib mechanism is chosen (see companion
  task 07-06-fix-bash32-empty-array-crash).

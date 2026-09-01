---
title: Retire the full-check script family and recompose make check
status: planning
parked: 2026-09-01 bulk-park (D2)
created: 2026-08-21
---
# Retire the full-check script family and recompose make check

> Child 3 of 3 under `08-09-retire-review-pr-surface`. Ordering is a
> requirement of this task, not an implication of tree position.
>
> **Correctness-independent of children 1 and 2.** The full-check scripts are
> not reachable from `sd-review-pr`: `templates/.agents/skills/sd-review-pr/SKILL.md:295-297`
> explicitly forbids falling back to either. This task is ordered after child 2
> only so that `RETIRED_TARGETS` is edited by one task at a time. If child 2
> stalls, this task may be re-ordered ahead of it, provided the
> `RETIRED_TARGETS` edit is coordinated.

## Goal

Delete `sd-ai-command-pack-full-check.sh` across all four trees, relocate the
`run_pack_source_drift_gates` gate to a surviving home first, and recompose
`make check` so no lane passes only because it never runs.

## Why the gate moves before the script dies

`run_pack_source_drift_gates` is a *function inside* `full-check.sh`, and the
CI workflow sources the script to reach it. Three checkers and five test
modules assert its presence. Deleting the script without relocating the gate
silently removes a drift check that CI still believes it is running.

## Current state (verified 2026-08-21)

| Fact | Location |
| --- | --- |
| `full-check.sh`, 1123 lines, four identical copies | `scripts/`, `templates/scripts/`, `plugins/sd/bin/`, `plugins/sd/machine-payload/scripts/` |
| gate definition | `plugins/sd/bin/sd-ai-command-pack-full-check.sh:611` (and each twin) |
| gate self-call | same file `:1083` |
| CI invocation | `.github/workflows/tests.yml:665` — `bash -c 'source scripts/sd-ai-command-pack-full-check.sh; run_pack_source_drift_gates'` |
| `make` targets | `Makefile:123` (`full-check:`), `:124` (the `PRISM=0 GITO=0` line), `:126` (`check: test lint audit full-check`) |
| surface-check graph node | `scripts/sd-ai-command-pack-surface-check.py:37`, `:463`, `:524`, `:530`, `:531` |
| surface-check text/workflow assertions | same file `:587`, `:593`, `:596`, `:600` |
| tests asserting the gate | `tests/test_pack_drift.py` (14 call sites: `:374,386,403,418,438,457,475,502,526,612,649,673,695,718`), `tests/test_full_check.py:1615,1620`, `tests/test_generated_parity.py:1308`, `tests/test_release_ledger.py:370`, `tests/install_test_support.py:1381,1403` |
| tests to delete | `tests/test_full_check.py` (1633 lines) |
| env family | 24 `SD_AI_COMMAND_PACK_FULL_CHECK_*` keys |

`make` fails at parse time on a prerequisite whose target is gone, so the
`Makefile` edit must land in the same commit as the script deletion.

## Requirements

- R1: `run_pack_source_drift_gates` runs green from a surviving home, and
  `tests.yml`, `surface-check.py`, and every asserting test reference only that
  home. This lands **before** any deletion.
- R2: `make check` has a working composition after `full-check` is gone, and no
  lane passes only because it never runs.
- R3: `Makefile:124`'s `SD_AI_COMMAND_PACK_FULL_CHECK_PRISM=0
  SD_AI_COMMAND_PACK_FULL_CHECK_GITO=0` disabling is removed together with the
  lanes it disables. Removing the disabling without deleting the lanes would
  enable code that has never run in this repo's gate.
- R4: All four `full-check.sh` copies are deleted, and the 24-key
  `SD_AI_COMMAND_PACK_FULL_CHECK_*` family with them.
- R5: `RETIRED_TARGETS` gains the deleted script paths.
  `command_installed_targets()` returns command paths only and no `scripts/`
  path, so consumer copies would otherwise be undeletable forever.
- R6: `tests/test_full_check.py` is deleted; the gate coverage it held survives
  at the gate's new home.
- R7: Audit findings A-102 and A-114 are marked `resolved-by-removal` in
  `.trellis/audit/ledger.md` in the deletion commit. A-102 is the gito filter
  argv overflow at `full-check.sh:231,:256,:261,:454` (measured 142,524 joined
  bytes, past Linux `MAX_ARG_STRLEN`); A-114 is the stale contract text.

## Acceptance Criteria

- [ ] `run_pack_source_drift_gates` runs green from its new home; `tests.yml`
      and `surface-check.py` reference only that home.
- [ ] No `full-check.sh` copy remains in any of the four trees.
- [ ] `make check` passes with the new composition, and no `PRISM=0`/`GITO=0`
      disabling survives anywhere.
- [ ] No `SD_AI_COMMAND_PACK_FULL_CHECK_*` key survives in any tree.
- [ ] `RETIRED_TARGETS` carries the deleted script paths; an upgrade removes an
      unchanged consumer copy and preserves plus reports a modified one.
- [ ] A-102 and A-114 are marked `resolved-by-removal` in the audit ledger in
      the deletion commit.
- [ ] `make check` is green.

## Dependencies And Ceded Scope

- **`review-full-check.sh` is NOT in this task.** Ownership stays with
  `08-08-phase0-dead-surface-cleanup`, which already scopes deleting it and its
  `templates/` twin. Decision recorded 2026-08-21. Do not delete it here; if
  that task has already landed, record the file as absent and move on.
- **`07-25-reduce-review-tooling-spawns` R1/R2/R4 are resolved-by-removal.**
  Those requirements memoize base-ref discovery inside `full-check.sh`, a file
  this task deletes. Mark them resolved-by-removal when this task lands. That
  task's `review-preflight.mjs` scope is unaffected and survives.
- Ordered after `08-21-delete-review-pr-surface` for `RETIRED_TARGETS`
  serialization only; see the header note.

## Out Of Scope

- Any `sd-review-pr` identifier, adapter, or registry change.
- Optimizing `full-check.sh` in any way. It is being deleted.

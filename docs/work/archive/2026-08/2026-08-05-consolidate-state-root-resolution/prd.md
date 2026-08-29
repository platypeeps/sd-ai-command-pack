---
title: Consolidate state-root resolution into shared lib (A-046)
status: done
created: 2026-08-05
branch: feat/consolidate-state-root-resolution
---
# Consolidate state-root resolution into the shared library (A-046)

## Goal

Make work-loop and fleet state resolve to one state root through a single
`resolve_state_root` / `ensure_private_directory` contract in
`scripts/sd_ai_command_pack_lib.py`, so the four current copies stop diverging
(AC1 of the parent task `07-28-consolidate-shared-script-helpers`).

This is the third of four clusters from that parent task. Clusters A-085
(atomic write) and A-080 (cache-env key set) shipped in release 0.64.16. This
cluster was split out because it is **not a refactor — it is a live-state
relocation** that needs a recorded migration decision the parent PRD did not
surface.

## Confirmed evidence (re-derived 2026-08-05)

Four sites; two ignore the pack's own state-home variable today:

| site | function | honors `SD_AI_COMMAND_PACK_STATE_HOME`? |
|---|---|---|
| `sd-ai-command-pack-work-loop.py:329` | `resolve_state_root(*, environ, home, os_name)` | yes — `STATE_HOME_ENV` at `:38`; full pack-var → XDG → Windows → home ladder; raises `WorkLoopError` |
| `sd-ai-command-pack-recovery-artifacts.py:124` | `resolve_state_root(...)` | yes — `STATE_HOME_ENV` at `:50`; raises `RecoveryError` |
| `sd-ai-command-pack-fleet-timing.py:390` | `resolve_state_root(state_home=None)` | **no** — XDG / `$HOME` only |
| `sd-ai-command-pack-fleet-controller.py:332` | `default_state_home()` | **no** — XDG or `$HOME`, then appends `/fleet-campaigns` |

`fleet-controller`'s `default_state_home` is not a fourth copy of the same
function: different name, different signature, no absolute-path validation, no
Windows branch, and `/fleet-campaigns` baked into the root rather than supplied
by the caller.

`ensure_private_directory` exists in three files (`work-loop.py:368`,
`recovery-artifacts.py:156`, `fleet-timing.py:411`). `work-loop`'s twin raises
evidence via `_user_state_blocked` (an `environment_blocked` fragment);
`recovery-artifacts`' twin lets a raw `OSError` escape. The lib owner must adopt
the **evidence-raising** form, not the leaking one (parent PRD R5).

## The migration decision (RESOLVED 2026-08-06)

**Selected: documented one-time move.** Recorded with full rationale in
`design.md`; see the adversarial-review ledger there for why the alternative was
rejected.

For a user with `SD_AI_COMMAND_PACK_STATE_HOME` set, unifying **moves** live
fleet timing records and campaign state to the pack-var root. State at the old
path is not read after the change, so the changelog must name both paths and the
exact `mv` (forward and reverse), and require that no fleet operation be in
flight during the move.

Windows is affected even with the variable unset: `default_state_home` has no
Windows branch today (`sd-ai-command-pack-fleet-controller.py:332-336`), so
campaign state moves from `~/.local/state/...` to `LOCALAPPDATA/...` once the
shared ladder applies. The migration note must cover those users too.

The rejected alternative was a read-through fallback: resolve the new root, read
legacy when the new path is absent, always write new. It was rejected because
`timing_store` and `CampaignStore` each derive `state_path` and `lock_path` from
a single directory, leaving no seam for a read/write split and putting old and
new processes on different lock files.

## Requirements

- R1: One `resolve_state_root` and one `ensure_private_directory` in the lib,
  carrying the canonical pack-var → XDG → Windows → home ladder and
  absolute-path validation. Callers keep only their subdirectory name (e.g.
  `work-loops/<digest>`, `fleet-campaigns`).
- R2: `ensure_private_directory` raises the evidence-bearing form on a
  filesystem boundary; no raw `OSError` escapes. Preserve `environment_blocked`
  behavior (parent R5).
- R3: Each caller's module-specific error type (`WorkLoopError`,
  `RecoveryError`) continues to surface at its call sites — either by catching a
  lib-level `CommandError` and re-raising, or by the lib raising a type the
  callers already handle. Do not change the observable error behavior at the 8
  `resolve_state_root` / `default_state_home` call sites (and 8
  `ensure_private_directory` call sites), with two recorded exceptions:
  (a) the raw `OSError` leak in `recovery-artifacts`' `ensure_private_directory`
  is *required* to change by R2 — it becomes `RecoveryError`; and
  (b) a relative `XDG_STATE_HOME` currently reaches `CampaignStore` and raises
  `FleetControllerError`, which must be preserved explicitly because the shared
  ladder would otherwise skip it and fall through to the home root.
- R4: Move `fleet-controller`'s `/fleet-campaigns` suffix to the caller.
- R5: Implement the recorded migration decision above.

## Acceptance criteria

- AC1: `SD_AI_COMMAND_PACK_STATE_HOME=/tmp/x` makes work-loop, recovery,
  fleet-timing, and fleet-controller all resolve under `/tmp/x`. Verify with
  `pytest tests/ -k "state_root or state_home"`.
- AC2: exactly one `def resolve_state_root` and one `def ensure_private_directory`
  across `scripts/*.py`, both in the lib.
- AC3: the migration decision is recorded in `design.md` and, if a one-time
  move, in `CHANGELOG.md`.
- AC4: template parity (`templates/scripts/*`) and the full test suite green.

## Boundaries

Complex task — needs `design.md` and `implement.md` before start. The migration
decision is a gate and a judgement call, not a check; do not start
implementation until it is recorded.

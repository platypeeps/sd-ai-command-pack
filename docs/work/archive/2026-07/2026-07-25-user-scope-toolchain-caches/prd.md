---
title: User-scope toolchain tmp caches
status: done
created: 2026-07-25
branch: codex/stabilize-self-hosted-delivery-lifecycle
---
# User-scope toolchain tmp caches

## Goal

The toolchain resolver's Python bytecode / uv / ruff cache and tool directories are
per-user and 0700, so another local user on a shared host cannot pre-create them and plant
bytecode or tool binaries executed under the victim's identity.

## Origin

SE-pack repo audit 2026-07-25 (se-ai-command-pack ledger A-018, P2/S). Defect lives in
this repo's source; the SE-side task was retired in favor of this one.

## Requirements

- `scripts/sd-ai-command-pack-toolchain.sh` `configure_cache_defaults` (~:390-396):
  qualify the `${TMPDIR:-/tmp}/sd-ai-command-pack-*` fallbacks with `${UID}` exactly as
  `prepare_gito_uv_env` (scripts/sd-ai-command-pack-shell-lib.sh:165) already does.
- Create directories 0700; fail or skip with a clear message when an existing path is not
  owned by the current user.
- Update the fleet-facing docs of these variables (docs/SD_AI_COMMAND_PACK.md ~:1290,
  which currently blesses the unqualified pattern for consumer shells).

## Acceptance Criteria

- [x] All cache/tool paths contain the UID; fresh creation is 0700.
- [x] Foreign-owned pre-existing path is rejected, not used.
- [x] Docs updated; changelog + version.

## Post-Archive Handoff

- Fleet rollout reaches consumers through the normal `sd-fleet-refresh`
  path after this stabilization PR merges; it is owned by the separate
  `07-28-roll-out-stabilized-pack-release-to-fleet` task and does not run
  from this PR.

## Reconciliation with prior program work (2026-07-25)

- Extends the COMPLETED `07-24-standardize-sandbox-safe-tool-cache-routing` (streamline
  program H06), which centralized cache/env routing. The UID-scoping + 0700 + ownership
  checks here are the remaining gap on top of that standardization — build on its
  structure, do not re-route.

## References

Research notes that lived beside this item's Trellis record and were not carried
into docs/work. Recover the bodies from git history under `.trellis/tasks/archive/2026-07/07-25-user-scope-toolchain-caches`:

- validation.md

# Prevent stale fleet candidate ledger from reaching CI and main

## Goal

Stop `docs/fleet/candidate-validation.json` payloadDigest staleness from
reaching CI. A shipped-payload change whose author forgets to regenerate the
ledger currently produces a clean local tree (nothing in the edit loop forces
the check before push) and reds CI at `test_surface_closure` with
`provenance.candidate-stale`. Close that gap with a fast, offline pre-push
gate so the failure surfaces locally, in <1s, with the exact fix command.

## Background (verified 2026-08-02)

- CI red on `main` (run 30720359738, push event, 2026-08-01) and on PR
  `claude/vibrant-banach` (30712921186) both failed
  `tests.test_surface_closure.test_live_surface_is_clean_and_json_is_versioned`
  with `provenance.candidate-stale`: committed ledger payloadDigest did not
  match the current pack payload.
- `scripts/sd-ai-command-pack-surface-check.py` already emits
  `provenance.candidate-stale` (:553) for a stale ledger — the digest gate
  exists and runs in `make generate` / `make check`. (Distinct from
  `provenance.stale` at :523, which is an installed-manifest mismatch.)
- `scripts/sd-ai-command-pack-fleet-candidate-check.py --check-ledger` is the
  fast path: **0.05s, offline, read-only, digest-based** ("valid for the current
  pack payload and fleet"). It does not rewrite the ledger.
- Full regeneration (no `--check-ledger`) runs the consumer compat loop:
  **~63s, rewrites the wall-clock `validatedAt` field**. This is a manual
  "fix" step, not something to run on every push/generate — the timestamp
  churns every run even when payloadDigest is unchanged.
- `.githooks/pre-push` (active via `core.hooksPath=.githooks`) is today a
  **chore-scope guard for direct `refs/heads/main` pushes only**. It runs no
  surface/digest check and does nothing for feature-branch pushes.
- Ledger content is deterministic in `payloadDigest`; only `validatedAt`
  varies run-to-run.

## Scope decision (user, 2026-08-02)

- **In scope:** the in-pack pre-push digest gate (R1–R3 below).
- **Out of scope, documented follow-up only:** the `main`-branch merge-skew
  cause is branch protection `strict=false` (`required_status_checks.strict`
  on `platypeeps/sd-ai-command-pack`), which lets two payload PRs each merge
  green and leave combined `main` stale. This task documents the recommended
  remediation (enable "require branches up to date" or a merge queue) as an
  ops action for the maintainer to apply; it does not change repository
  settings.

## Requirements

- **R1 — Pre-push digest gate.** Extend `.githooks/pre-push` so every push
  (not only direct-to-main) runs the fast, offline candidate-ledger digest
  check and **fails closed** when the ledger is stale for the current payload.
  Must not regenerate the ledger (no `validatedAt` churn) and must add no
  network dependency. Fail-closed scope is bounded by R6: the gate only
  applies inside a pack-source checkout.
- **R6 — Skip outside pack source.** The gate must **skip silently** when the
  checker script (`scripts/sd-ai-command-pack-fleet-candidate-check.py`) or the
  ledger (`docs/fleet/candidate-validation.json`) is absent — i.e. this is not
  a pack-source checkout (consumer clone, partial fixture, test sandbox). This
  is required for correctness: the existing hook integration test copies only
  the hook into the working clone of a bare origin
  (`tests/test_review_preflight.py:3433`), so an unconditional invocation would
  error and break it.
- **R2 — Legible failure + bypass.** On a stale ledger, print the exact
  regeneration command and honor an explicit escape hatch consistent with the
  existing `SD_AI_COMMAND_PACK_CHORE_SCOPE_BYPASS` pattern for intentional WIP
  pushes.
- **R3 — No regression to the existing chore-scope guard.** The current
  direct-to-main chore-scope behavior and its bypass keep working unchanged;
  the new gate composes with it rather than replacing it.
- **R4 — Documented merge-skew follow-up.** Record the branch-protection
  `strict=false` finding and the recommended remediation where a maintainer
  will find it (task notes plus a short repo ops note); no settings change.
- **R5 — Source-only tooling; no release hygiene for the hook.**
  `.githooks/pre-push` is repo source tooling, **not** shipped payload — it is
  absent from `manifest.json`, `install.py`, `installer/`, and `templates/`,
  and has no `templates/` twin. Editing it therefore requires **no** manifest
  version bump, CHANGELOG entry, `make generate`, or mirror-parity work. It is
  covered by `make lint` shellcheck (`Makefile:68`), so the change must be
  shellcheck-clean and land `make check` green. (The ops-note doc under R4
  targets `docs/FLEET_ROLLOUT.md`, also confirmed non-shipped.)

## Acceptance Criteria

- [ ] With a deliberately stale ledger (exit 1), a push on a feature branch is
      **blocked** by pre-push with a message naming the regeneration command;
      the same push succeeds after regeneration.
- [ ] A checker config/input failure (exit 2) blocks with a **generic
      execution-failure** message that does *not* misattribute the cause to a
      stale ledger; any other nonzero exit is treated the same way.
- [ ] In a checkout without the checker script or ledger (e.g. the bare-clone
      fixture at `tests/test_review_preflight.py:3398`), the gate **skips
      silently** and the existing chore-scope pushes still pass unchanged (R6).
- [ ] The pre-push gate adds < 1s to a push with a fresh ledger and makes no
      network call (verified offline).
- [ ] The gate does **not** modify `validatedAt` or otherwise dirty the tree.
- [ ] The `SD_AI_COMMAND_PACK_LEDGER_BYPASS=1` env var skips only the ledger
      gate and allows an intentional stale-ledger push; the chore-scope guard
      remains active.
- [ ] In a pack-source checkout with no runnable interpreter, the gate **fails
      closed** with a setup diagnostic (consistent with R1), not a silent skip.
- [ ] When the working tree is dirty or a pushed `local_sha != HEAD` and the
      check passes, the gate prints a non-authoritative **advisory** (validated
      against working tree, not the pushed commit) — and prints it only on a
      passing check, never in place of a block.
- [ ] Branch-protection `strict=false` merge-skew finding + remediation are
      documented (task notes + `docs/FLEET_ROLLOUT.md`).
- [ ] `make lint` shellcheck lane is clean on the edited hook and `make check`
      passes. No manifest/CHANGELOG/generate/mirror work (hook is source-only,
      R5).
- [ ] New behavioral fresh/stale/exit-2/ledger-bypass coverage is added
      alongside the existing hook test in `tests/test_review_preflight.py`.

## Non-goals

- Changing GitHub branch-protection settings or adding a merge queue.
- Wiring the 63s full regeneration into `make generate` (rejected: timestamp
  churn + cost; the digest check already lives in the check path).
- Altering `test_surface_closure`, `surface-check.py`, or the ledger schema.

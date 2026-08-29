# Implement — Prevent stale fleet candidate ledger from reaching CI and main

Execute in order. Run the **test suite** with the repo-local venv
(`.venv/bin/python`): the *test-support* import needs `yaml`, which bare
`python3` lacks. This does **not** apply to the hook's own `--check-ledger`
path, which imports stdlib + repo-local modules only and runs fine under bare
`python3` (verified 2026-08-02, exit 0).

## Preconditions (verified in planning)

- `.githooks/pre-push` is the only copy; not shipped/mirrored → no manifest
  bump, no `templates/` twin, no `make generate` for the hook.
- Hook arming detection is `core.hooksPath`-based (`full-check.sh:153`), not
  content-hash → editing the hook body is safe for `test_full_check`.
- `--check-ledger` is offline, read-only, ~0.05s, digest-based; exit `1` =
  ledger missing/invalid/mismatched (`check_ledger` swallows the read error,
  `fleet-candidate-check.py:394`), exit `2` = manifest/fleet config error
  raised before ledger validation.

## Steps

1. **Add the ledger gate to `.githooks/pre-push`** — implement the ordered
   steps from design.md "Gate contract", under `set -uo pipefail`:
   - **Step 0 bypass:** if `SD_AI_COMMAND_PACK_LEDGER_BYPASS=1`, skip the gate.
   - **Step 1 pack-source guard (C-3/R6):** resolve repo toplevel; if
     `scripts/sd-ai-command-pack-fleet-candidate-check.py` **or**
     `docs/fleet/candidate-validation.json` is missing, **skip silently**.
     This is what keeps the existing bare-clone test green.
   - **Step 2 interpreter (C-2):** prefer `.venv/bin/python`, else `python3`.
     If neither is runnable *here* (we passed Step 1, so it is a pack repo),
     **fail closed** (`status=1`) with the missing-interpreter diagnostic — do
     not skip.
   - **Step 3 run + exit-code split (C-4):** run `"$py"
     scripts/sd-ai-command-pack-fleet-candidate-check.py --check-ledger` from
     toplevel, capture stderr + code. `0`→pass; `1`→ledger
     missing/invalid/mismatched message + regen fix (rendered with `$py`, not
     hardcoded `.venv`), `status=1`; `2`/other→generic execution-failure
     message (no stale claim), `status=1`. Messages per design.md "Failure
     messages".
   - **Pushed-SHA advisory (C-1):** when working tree is dirty or a pushed
     `local_sha != HEAD`, and the check *passes*, print the one-line advisory
     that validation was against the working tree, not the pushed commit(s).
   - Document `SD_AI_COMMAND_PACK_LEDGER_BYPASS` and the retained
     `SD_AI_COMMAND_PACK_CHORE_SCOPE_BYPASS` in the hook header.
   - Fold into the single final `exit $status`; do not early-exit before the
     gate for non-main pushes.

2. **Ops note for the merge-skew follow-up (PRD R4).**
   - Add a short section recording branch-protection `strict=false` + the
     recommended remediation (enable strict / merge queue) and its trade-off.
   - Home: append to `docs/FLEET_ROLLOUT.md` — confirmed **not** shipped
     payload (no `templates/docs/FLEET_ROLLOUT.md` twin, absent from
     `manifest.json`), so a direct edit needs no version bump or parity work.
     Do not create a new top-level doc tree.

3. **Automated tests — two fixtures (C-3).** Follow design.md "Testing".
   - **Existing test unchanged:**
     `test_chore_scope_pre_push_hook_gates_direct_main_pushes`
     (`tests/test_review_preflight.py:3398`) copies only the hook into the
     working clone of a bare origin (`:3433`). Leave it byte-for-byte
     unchanged; it now also proves the R6 Step-1 skip (no checker/ledger → skip
     → chore-scope assertions still pass). Do **not** add checker/ledger here.
   - **New helper/fixture variant** for ledger cases: copy the hook **plus**
     `scripts/sd-ai-command-pack-fleet-candidate-check.py` (+ its
     `sd_ai_command_pack_lib` / `sd_ai_command_pack_fleet_lib` deps),
     `manifest.json`, the fleet manifest, and
     `docs/fleet/candidate-validation.json` into the working clone, then drive
     real `git push` to the bare origin:
     - fresh ledger → **succeeds**;
     - corrupted `payloadDigest` (exit 1) → **blocked**, ledger message;
     - broken `manifest.json`/fleet manifest with ledger **present** (exit 2)
       → **blocked**, generic message. (A *missing* ledger is a Step-1 skip,
       not exit 2 — do not use it here.)
     - `SD_AI_COMMAND_PACK_LEDGER_BYPASS=1` + stale ledger → **succeeds**;
     - checker+ledger present, no `.venv/bin/python` and `python3` stripped
       from `PATH` → **blocked**, setup diagnostic (C-2 AC);
     - dirty tree or pushed `local_sha != HEAD` + fresh ledger → **succeeds**
       and the C-1 advisory line appears (only on a passing check).
   - If copying the checker's dependency closure proves impractical, **say so**
     and fall back to the manual V-sequence below as the evidence; do not claim
     automated coverage that was not written.

## Validation (falsifiable — run and quote output)

- **V1 (exit 1):** on a throwaway feature branch, corrupt
  `docs/fleet/candidate-validation.json` payloadDigest, `git push` →
  **blocked**, message names the fix command (rendered with the selected
  interpreter). Restore/regenerate → push **succeeds**.
- **V2 (latency/offline):** time a push with a fresh ledger; added latency
  < 1s; run in an offline shell to prove no network.
- **V3 (no churn):** `git status --porcelain` clean before and after a blocked
  push — `validatedAt` not rewritten.
- **V4 (bypass):** `SD_AI_COMMAND_PACK_LEDGER_BYPASS=1 git push` with a stale
  ledger → succeeds; chore-scope guard still active.
- **V5 (exit-2):** with the ledger present, break the fleet/pack manifest to
  raise `FleetConfigError` before ledger validation → blocked with the generic
  message, no stale claim.
- **V6 (interpreter fail-closed):** in a pack-source checkout with checker +
  ledger present, no `.venv/bin/python`, `python3` off `PATH` → blocked with
  the setup diagnostic (not a silent skip).
- **V7 (advisory):** dirty tree or `local_sha != HEAD` + fresh ledger → push
  succeeds and prints the non-authoritative advisory.
- **V8 (skip / R6 + arming):** `.venv/bin/python -m unittest
  tests.test_review_preflight` green, including the unchanged `:3398` skip
  case; `tests/test_full_check.py` arming tests still green (hook detected as
  armed via `core.hooksPath`).
- **V9 (lint/check):** `make lint` shellcheck lane clean on the edited hook;
  then full `make check` green.

  Note: the suite runs under `.venv` via `run-tests.sh`; use `.venv/bin/python`
  (bare `python3` lacks `yaml` for the *test-support* import — unrelated to the
  hook's own `--check-ledger` path, which needs no yaml).

## Review gates

- Planning adversarial review (host + optional Codex) already required before
  `task.py start` per `.claude/rules/sd-planning-adversarial-review.md`; run it
  against this prd/design/implement batch.
- Before commit: re-run full `make check` and quote the decisive
  `Review preflight: N failure(s)` line.

## Rollback

- Single-file hook change → `git checkout .githooks/pre-push` reverts the
  gate; ops-note doc revert is independent. No data migration, no shipped
  surface to unwind.

## Out of scope (do not do)

- Changing GitHub branch-protection settings / adding a merge queue.
- Wiring the 63s full regeneration into `make generate`.
- Editing `surface-check.py`, the fleet check script, `test_surface_closure`,
  or the ledger schema.

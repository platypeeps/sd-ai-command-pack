# Design — Prevent stale fleet candidate ledger from reaching CI and main

## Summary

Add a second, independent guard to `.githooks/pre-push`: a fast, offline
candidate-ledger digest check that runs on **every** push and fails closed
when `docs/fleet/candidate-validation.json` is stale for the current payload.
It composes with — does not replace — the existing direct-to-main chore-scope
guard.

## Boundaries / what changes

This task touches three files:

- **`.githooks/pre-push` (hook, changed):** repo tooling, not shipped payload —
  absent from `manifest.json`, `install.py`, `installer/`, `templates/`, and
  the surface generator. Therefore **no** manifest-version bump, CHANGELOG
  entry, `make generate`, or `scripts/` ↔ `templates/` parity work is required
  for the hook (PRD R5 is a no-op here). It **is** covered by `make lint`
  shellcheck (`Makefile:68`, `... shellcheck -S warning .githooks/pre-push`),
  so the addition must be shellcheck-clean under `set -uo pipefail`.
- **`docs/FLEET_ROLLOUT.md` (ops note, changed):** a short section documenting
  the branch-protection `strict=false` merge-skew finding (PRD R4). Confirmed
  non-shipped (no `templates/docs/FLEET_ROLLOUT.md` twin, absent from
  `manifest.json`), so no version/parity work. Do not create a new doc tree.
- **`tests/test_review_preflight.py` (tests, changed):** new gate coverage
  (see "Testing").
- **Unchanged:** `sd-ai-command-pack-fleet-candidate-check.py`,
  `surface-check.py`, `test_surface_closure.py`, the ledger schema, CI.

## Gate contract

Evaluate these steps in order, per `git push`:

- **Step 0 — Ledger bypass (R2):** if `SD_AI_COMMAND_PACK_LEDGER_BYPASS=1`,
  skip the gate entirely (chore-scope guard still runs).
- **Step 1 — Pack-source guard (C-3 / R6):** if
  `scripts/sd-ai-command-pack-fleet-candidate-check.py` **or**
  `docs/fleet/candidate-validation.json` is absent (relative to the repo
  toplevel), **skip silently** — this is not a pack-source checkout (consumer
  clone, partial fixture, the bare-clone integration test at
  `tests/test_review_preflight.py:3433` that copies only the hook). This guard
  is mandatory: without it an unconditional invocation errors in those
  contexts and breaks the existing test.
- **Step 2 — Interpreter resolution (C-2):** prefer `.venv/bin/python`, else
  `python3` on PATH. Verified 2026-08-02: bare `python3 …--check-ledger` exits
  0 — the `--check-ledger` path imports stdlib + repo-local modules only, no
  `yaml`, so the `python3` fallback is genuinely viable (the *test suite*, not
  this gate, is what needs the venv). If we reached Step 2 (so this *is* a
  pack-source checkout) but **neither** interpreter is runnable, **fail closed**
  (`status=1`) with a setup diagnostic — do not silently skip. This honors R1;
  a pack-source repo that cannot self-validate should not push unnoticed.
- **Step 3 — Run the check:** `<py>
  scripts/sd-ai-command-pack-fleet-candidate-check.py --check-ledger` from repo
  toplevel. Verified read-only, offline, ~0.05s, digest-based; does **not**
  rewrite `validatedAt`. Interpret the exit code (C-4):
  - `0` → pass; contribute nothing to `status`.
  - `1` → **ledger missing / invalid / mismatched** (`candidate ledger error:`
    at `fleet-candidate-check.py:442`). This code covers a stale payloadDigest
    **and** an unreadable/malformed ledger, because `check_ledger` catches
    `load_json_object`'s `FleetConfigError` and returns it as a validation
    error (`fleet-candidate-check.py:394`, `fleet_lib.py:94`). `status=1`,
    print the ledger-problem message with the regeneration fix line (regen
    fixes the common stale case; a malformed ledger is also surfaced verbatim).
  - `2` or any other nonzero → **config/execution failure** raised *before*
    ledger validation, e.g. a missing/invalid pack `manifest.json` or fleet
    manifest, or `--check-ledger` misuse (`candidate validation error:` /
    `FleetConfigError` at `fleet-candidate-check.py:524`); note a **missing
    ledger at the default path is a Step-1 skip, not exit 2**. `status=1`,
    print a **generic execution-failure** message that forwards the checker's
    stderr and does *not* claim the ledger is stale.
- **Pushed-SHA authority (C-1):** `--check-ledger` validates working-tree files
  (`manifest.json`, fleet manifest, ledger) via `current_evidence`, not the
  exact commits being pushed. In the dominant case — pushing the current branch
  with a clean tree — working tree == pushed tip, so the check is authoritative.
  When it is **not** authoritative (working tree dirty, or a pushed `local_sha`
  differs from `HEAD`, e.g. `git push origin other-branch`), the gate must not
  give false assurance: on a **pass** in a non-authoritative state, print a
  one-line advisory that the ledger was validated against the working tree, not
  the pushed commit(s), and recommend `make check` on that ref; on a **fail**,
  block as normal. Detect via `git rev-parse HEAD`, `git status --porcelain`,
  and the per-ref `local_sha` values the hook already reads on stdin
  (`.githooks/pre-push:22`). Rejected as disproportionate: validating each
  pushed `local_sha` in a throwaway detached worktree — correct but adds a
  checkout + ~0.05s per distinct SHA to every push for a local convenience
  guard that CI already backstops. The advisory keeps the common path honest
  without that cost.

## Bypass (PRD R2) — decided: granular

Add `SD_AI_COMMAND_PACK_LEDGER_BYPASS=1` (Step 0) that skips **only** the
ledger gate, leaving the chore-scope guard active. The two guards protect
different things; a WIP payload push should not also have to disable the
main-scope guard. The existing `SD_AI_COMMAND_PACK_CHORE_SCOPE_BYPASS=1`
(short-circuits the whole hook at `.githooks/pre-push:14`) is left unchanged
and continues to bypass everything. Document both env vars in the hook header.

## Failure messages (PRD R2, C-4)

Ledger missing/invalid/mismatched (exit 1) — stderr (`$py` is the interpreter
selected in Step 2, not hardcoded):

```
pre-push: fleet candidate ledger is stale or invalid for the current payload.
  <forwarded checker stderr: candidate ledger error: … expected sha256:… >
  Fix:   $py scripts/sd-ai-command-pack-fleet-candidate-check.py
         (regenerates docs/fleet/candidate-validation.json; ~60s, rewrites validatedAt)
  Bypass (intentional WIP): SD_AI_COMMAND_PACK_LEDGER_BYPASS=1 git push ...
```

Config/execution failure (exit 2 or other) — stderr, no stale claim:

```
pre-push: fleet candidate ledger check could not run.
  <forwarded checker stderr: candidate validation error: … >
  This is not a stale-ledger failure; fix the reported condition, or bypass
  with SD_AI_COMMAND_PACK_LEDGER_BYPASS=1 if intentional.
```

Missing-interpreter (Step 2 fail-closed) — stderr:

```
pre-push: no runnable Python (.venv/bin/python or python3) to verify the fleet
  candidate ledger; set up the venv (make setup) or bypass with
  SD_AI_COMMAND_PACK_LEDGER_BYPASS=1.
```

## Composition with the existing guard

The current hook loops over pushed refs and only acts on
`refs/heads/main`. The ledger gate is ref-independent, so structure it as a
single check either before or after that loop, folding its result into the
same `status` variable the hook already returns. Keep one final `exit
$status`. Do not early-`exit 0` in a way that skips the ledger gate for
non-main pushes (that is the whole point — feature branches must be gated).

## Merge-skew follow-up (PRD R4, documentation only)

Record: `required_status_checks.strict=false` on
`platypeeps/sd-ai-command-pack` (verified via
`gh api repos/.../branches/main/protection` 2026-08-02). With strict off, two
payload PRs each pass CI in isolation, merge sequentially, and leave combined
`main` with a payloadDigest matching neither ledger → `main` reds on the merge
push (observed: run 30720359738, 2026-08-01). Recommended remediation for the
maintainer: enable "Require branches to be up to date before merging" (strict)
or adopt a GitHub merge queue. Trade-off to state: strict forces a rebase +
ledger regen before every merge, adding churn on the ~6-min CI. Not applied by
this task.

## Risks / tradeoffs

- **False block from unrelated stale ledger** on an unrelated branch push →
  mitigated by the granular bypass and by the fact that a stale committed
  ledger is genuinely a problem worth surfacing.
- **Interpreter missing inside a pack-source repo** → **fail closed** (Step 2)
  with a setup diagnostic, honoring R1; not a silent skip. Outside a
  pack-source repo the Step-1 guard has already skipped, so this only bites a
  genuine pack checkout with no Python — rare, and the message says how to fix
  or bypass.
- **Non-authoritative working tree** (dirty, or pushing a ref ≠ HEAD) → the
  gate validates the tree, not the pushed SHA; a passing check in that state
  emits an advisory rather than false assurance (C-1). Full per-SHA worktree
  validation rejected as disproportionate for a CI-backstopped local guard.

## Testing (resolves C-3 fixture split)

Two distinct fixtures in `tests/test_review_preflight.py`:

- **Existing, unchanged:** `test_chore_scope_pre_push_hook_gates_direct_main_pushes`
  (`:3398`) builds a bare origin and a working clone into which it copies
  **only** the hook (`:3433`). It stays byte-for-byte unchanged and now
  doubles as the R6 skip proof: with no checker/ledger present, Step 1 skips
  and its chore-scope assertions still pass. Do **not** add checker/ledger to
  this fixture.
- **New helper variant:** a separate fixture (or a parametrised helper) that,
  in addition to the hook, copies the checker
  (`scripts/sd-ai-command-pack-fleet-candidate-check.py` + its
  `sd_ai_command_pack_lib` / `sd_ai_command_pack_fleet_lib` deps),
  `manifest.json`, the fleet manifest, and
  `docs/fleet/candidate-validation.json` into the working clone, then drives
  real `git push` to the local bare origin. Cases:
  1. fresh ledger → push succeeds;
  2. corrupted `payloadDigest` (exit 1) → blocked, ledger message;
  3. broken `manifest.json`/fleet manifest with ledger present (exit 2) →
     blocked, generic message (note: a *missing ledger* is a Step-1 skip, not
     exit 2 — do not use it to exercise exit 2);
  4. `SD_AI_COMMAND_PACK_LEDGER_BYPASS=1` + stale ledger → succeeds;
  5. checker+ledger present, interpreter unavailable (no `.venv/bin/python`,
     `python3` stripped from `PATH`) → blocked with the setup diagnostic
     (C-2 AC);
  6. dirty working tree or pushed `local_sha != HEAD` with a fresh ledger →
     push succeeds **and** the C-1 advisory line appears (advisory only on a
     passing check).

## Verification (falsifiable)

1. New automated cases 1–6 above green under `.venv/bin/python -m unittest
   tests.test_review_preflight`; existing `:3398` test unchanged and green.
2. `git status --porcelain` clean before/after a blocked push — no
   `validatedAt` rewrite (AC 3), asserted in the fixture and by manual check.
3. Fresh-ledger push added latency < 1s; offline shell proves no network
   (AC 2).
4. `make lint` shellcheck lane clean on the edited hook; full `make check`
   green (AC lint/check).

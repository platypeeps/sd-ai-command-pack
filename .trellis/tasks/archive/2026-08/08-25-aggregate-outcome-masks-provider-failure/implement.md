# Implement — a failed provider reaches the gate

Red-first. Source of truth is `templates/scripts/sd-ai-command-pack-review-local.py`;
the three copies under `scripts/`, `plugins/sd/bin/`, and
`plugins/sd/machine-payload/scripts/` are generated — never hand-edit them.

## 0. Baseline

- [x] `.venv/bin/python -m unittest tests.test_review_stage` green. Record the
      count.
- [x] Confirm the defect: a `severity-low` + `fail` run under a ceiling reports
      `remoteGate.state == "eligible"` today.

## 1. Tests first (red)

In `tests/test_review_stage.py`. The fixture already has everything needed:
`write_config(..., modes=..., ceiling=...)` and the `severity-low` and `fail`
provider modes.

- [x] `test_a_failed_provider_limits_the_gate_even_when_another_found_things`
      — `modes=("severity-low", "fail")` with a ceiling that makes the finding
      advisory, so `outstanding == 0`. Assert `remoteGate.state ==
      "eligible-with-limitations"`, reason `local-review-limited`, and that
      `confidence.limitations` names the failed provider. **This is acceptance
      criterion 1 and it must fail against current code.**
- [x] `test_a_findings_run_with_no_failure_is_unchanged`
      — same but `modes=("severity-low", "clean")`: still `eligible`, and
      `limitations` empty. Acceptance criterion 2.
- [x] `test_a_required_policy_blocks_when_a_provider_dies_alongside_findings`
      — same shape with `--local-policy required`: `blocked`,
      `required-local-review-failed`.
- [x] `test_outstanding_findings_outrank_a_degraded_lane`
      — `modes=("finding", "fail")` with no ceiling, so `outstanding > 0`.
      Assert `blocked` / `actionable-local-findings`. Pins the ordering
      decision in `design.md` rather than leaving it implicit.
- [x] `test_aggregate_outcome_still_reports_findings_over_failure`
      — asserts `receipt["outcome"] == "findings"` for the degraded run.
      Precedence asserted by test, not by reading the tuple — requirement 4 —
      and it fails if someone later "fixes" this by reordering.
- [x] Run; confirm the new tests fail and no existing test does.

## 2. Implement

- [x] Add `degraded: bool = False` to `_remote_gate`, keyword-only, defaulted.
- [x] Change the terminal-failure branch to `if degraded or outcome in
      TERMINAL_FAILURES:`.
- [x] `:2669` (receipt construction): pass `degraded=bool(limitations)` from
      the local built at `:2646`.
- [x] `:2381` (re-gate of a stored receipt): `attempts` and `limitations` are
      **not** in scope. Read the persisted `confidence.limitations` instead,
      defensively (a non-list reads as empty). Do not recompute from `attempts`
      — requirement 2 is that the counts and records come from one decision, and
      here that decision is the one the stored receipt already carries.
- [x] Add a test for the re-gate path specifically: a stored degraded receipt
      re-gated after a disposition stays `eligible-with-limitations`. The two
      call sites are easy to fix asymmetrically and nothing else would catch it.
- [x] Leave `_aggregate_outcome` untouched.

## 3. Validate

- [x] `.venv/bin/python -m unittest tests.test_review_stage` — all green.
- [x] `.github/scripts/run-tests.sh` — full suite, 0 failures. **Not optional:
      the targeted suite missed a shipped-shell drift rule on the previous
      task.**
- [x] `.venv/bin/python -m coverage report --include="install.py,installer/*"
      --fail-under=100` via `make test`.

## 4. Ship

- [x] Re-read `main`'s manifest version immediately before bumping. Two sessions
      are landing versions; #551 vs #549 already collided once.
- [x] `make sync` → `make generate` → `fleet-candidate-check.py` →
      `make generate`. The second `generate` is load-bearing: the ledger digests
      the generated tree.
- [x] Confirm all four copies of the script are hash-identical.
- [x] `make check` exit 0.
- [x] PR. No admin override.

## 5. Cross-task

- [ ] `08-25-bookkeeping-successor-absent-router` cites the shared
      outcome-vocabulary decision in `design.md` rather than re-settling it.

## Rollback

Revert the commit. The parameter is additive and defaulted; no receipt field
changes and no digest moves.

## Verification record

Run on the branch that became PR #556 (0.71.56).

- Baseline before any edit: `Ran 89 tests ... OK`.
- Red-first, after the six tests and before the implementation:
  `FAILED (failures=3)` — the three asserting the new behaviour
  (`..._limits_the_gate_even_when_another_found_things`,
  `..._blocks_when_a_provider_dies_alongside_findings`,
  `..._regating_a_stored_degraded_receipt_keeps_the_limitation`).
  The other three passed as regression guards, as intended.
- After: `Ran 95 tests in 64.464s ... OK`.
- Full suite: `PYTHON_BIN=".venv/bin/python" bash .github/scripts/run-tests.sh`
  exit 0, 83 modules, no `FAILED`/`ERROR` line.
- `PYTHON_BIN=".venv/bin/python" make test` exit 0 (carries the
  `--fail-under=100` installer coverage gate).
- `make generate` exit 0, `shipped-surface closure: clean`; four copies at
  `sha256:3bb1f37ec66574e83dde1b20a6bce8afbe182279930f9cb6b780b6c65c736d0a`.
- `make check` exit 0. The `error:` lines in its log are unittest fixture
  output from inside a dot-progress run, not gate findings.

One build wrinkle worth recording, because it is the second task in a row to
hit it: after the version bump, `make sync` does not refresh the two
`command-catalog.md` mirrors (the installer preserves them), so `make generate`
fails with `mirror.stale`. The fix is `cp` from `templates/`, then a second
`make sync` to refresh the provenance digests — without that second sync,
`make check` reports the copies as drifted installed targets.

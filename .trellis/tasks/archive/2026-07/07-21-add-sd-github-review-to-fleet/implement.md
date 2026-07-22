# Implementation Plan: Add sd-github-review to fleet

## 1. Update Fleet Policy

- Add `sd-github-review` to the end of the `post-canary` cohort.
- Insert its priority-70 consumer record between `se-ai-command-pack` and
  `anomaly-metric-creator`.
- Preserve every existing consumer field and relative position.

## 2. Update Regression Coverage

- Add the GitHub slug to the checked-in real-consumer set.
- Update expected consumer and priority order to eight rows.
- Replace the binary repomix-preparation assertion with explicit preparation
  expectations for repomix consumers, `sd-github-review`, and
  `se-ai-command-pack`.
- Assert the new consumer's candidate checks, timeout, platforms, and cohort.

## 3. Update Operator Documentation

- Add `sd-github-review` to the documented fast-first order and post-canary
  cohort.
- Change preparation wording from six map owners plus one exception to six
  repomix consumers, one npm-prepared consumer, and one no-preparation
  consumer.
- Update any explicit seven-consumer/count references found by focused search.

## 4. Validate The New Consumer

- Run focused fleet unit tests.
- Run a filtered disposable candidate diagnostic:
  `bash scripts/sd-ai-command-pack-toolchain.sh run-python -- scripts/sd-ai-command-pack-fleet-candidate-check.py --consumer sd-github-review`.
- Confirm the active `~/repos/platypeeps/sd-github-review` checkout is unchanged
  by the diagnostic, preserving and recording any pre-existing work.

## 5. Refresh Canonical Evidence

- Run the unfiltered candidate validator across all eight consumers.
- Commit the resulting `docs/fleet/candidate-validation.json`; do not edit it
  manually.
- Verify the ledger with `--check-ledger`.

## 6. Final Verification

- Run `make check` as required by `CONTRIBUTING.md`.
- Run `git diff --check` and inspect the final manifest, docs, tests, and ledger
  diff for unrelated changes.
- Use `trellis-check` for the Phase 2 quality gate before spec update and
  commit.

## Rollback Points

- If the filtered candidate fails, stop before the full ledger run and fix the
  declared preparation/check contract.
- If an existing consumer fails during the full run, preserve the prior ledger
  and classify the failure before retrying.
- Do not weaken a target repository gate or remove an existing fleet check to
  obtain an all-pass ledger.

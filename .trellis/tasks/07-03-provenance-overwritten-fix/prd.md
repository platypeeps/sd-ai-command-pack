# Vouch force-overwritten targets in provenance

## Goal

Fix the provenance gap the 0.5.13 fleet refresh exposed: `install_file`
returns status `overwritten` for `--force` overwrites of drifted content,
but `provenance_content` only vouched created/updated/unchanged — so
single-pass refreshes kept stale hashes (audit drift failures in the AMC
and rwbp-website refresh worktrees) and force-overwritten files were
silently unvouched since 0.5.11. Two-pass (claude-platform) refreshes
self-healed via the second pass's `unchanged` status, which is why only
two of six repos surfaced it.

## Requirements

- R1: `overwritten` joins the vouchable statuses — every status that ends
  with the target byte-equal to the template source is hashed; `preserved`
  and `conflict` stay excluded.
- R2: A regression test drives the exact fleet path: install, drift a
  vouched script, `--force` refresh, assert the provenance entry equals
  the template hash and the audit passes.
- R3: The two affected 0.5.13 refresh branches (anomaly-metric-creator
  #193, rwbp-website #85) are repaired with corrected provenance before
  merge.
- R4: No version bump — `install.py` is not consumer-shipped (PR #15
  precedent); consumers receive correct provenance from the repaired
  refresh runs.

## Acceptance Criteria

- [x] Regression test green; full suite at 100% install.py coverage;
      full-check clean.
- [ ] AMC #193 and website #85 branch worktrees pass the install audit
      after re-running the fixed installer (pre-merge step).

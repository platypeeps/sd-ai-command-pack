# Audit traversal hardening: symlinked parents and per-target lstat

## Goal

Close the round-2 consumer-PR findings on the vendored audit
(mezmo_benchmark #314 comment 3522423050, rwbp-coordinator #75 comment
3522422385) upstream and ship as 0.5.12.

## Requirements

- R1: Vouched-path verification fails closed when the target's real path
  escapes the repository root (symlinked parent directories previously let
  the audit read and hash content outside the repo).
- R2: Vouched-target inspection uses per-target `os.lstat` (mirroring the
  provenance-file gate): missing, symlink, non-regular, and
  cannot-be-inspected are distinguished without `exists()`/`is_file()`
  OSError ambiguity, and inspection failures carry the exception text.
- R3: `path_exists` in the structural audit is lstat-based so unreadable
  parent directories degrade to missing-target reports instead of crashing
  on Python versions where `Path.exists()` raises.
- R4: Docs/spec updated; version 0.5.12; six consumer PRs refreshed after
  merge.

## Acceptance Criteria

- [x] A vouched path behind a symlinked parent directory pointing outside
      the repo fails with "escapes the repository root".
- [x] An unreadable parent directory yields "vouched target cannot be
      inspected" plus a structural missing-target report — no crash.
- [x] Existing symlink/missing/non-regular behaviors keep their messages;
      full suite green at 100% install.py coverage; full-check clean.
- [x] Six consumer PRs refreshed to 0.5.12 with threads answered
      (post-merge step).

## Reconciliation Note - 2026-07-09

Reconciled by `07-06-close-fleet-refresh-loop`: Session 20 and the archived
task state record the implementation as shipped, and the named 0.5.12 review
threads in mezmo PR #314 and rwbp-coordinator PR #75 are resolved/obsolete on
merged PRs. Current consumer installs are on pack `0.7.0` with install audit
exit 0.

# Shell and hook hardening batch

## Goal

Fix a batch of confirmed shell/hook defects surfaced by the 2026-07-09
tooling review — one real guard bypass plus several interrupt-safety and
robustness gaps — and give the pre-push guard the behavioral tests it has
never had.

## Problem

- **Pre-push chore guard is rename-blind (the one outright bypass).**
  `.githooks/pre-push:37,44` uses `git diff --name-only` with default
  rename detection, which lists only the NEW path for a rename. Verified:
  `git mv src/code.txt .trellis/workspace/code.txt` emits only the
  `.trellis/workspace/` path, which the guard's
  `grep -Ev '^\.trellis/(tasks|workspace)/'` passes — so a direct push to
  main that moves a source file into a chore path deletes it from the
  non-chore tree while the guard sees "chore-only". Deletions and reverse
  renames are caught (old path appears).
- **Pre-push has zero behavioral tests.** It is the only enforcement on
  admin direct pushes to main, yet its fail-closed branches (diff failure,
  `grep` rc≥2, unknown remote SHA, remote-main creation) have never
  executed under test; `tests/test_full_check.py:95-110` only asserts the
  "guard not armed" warning.
- **full-check.sh has no EXIT traps.** The gito retry loop (30–120s sleeps)
  and the mktemp files at `full-check.sh:115,145,673` leak on Ctrl-C or on
  a `set -e` git failure between mktemp and `rm -f`. Commit 6e00e5e's
  temp-file registration only actually protects `review-local.sh` (and even
  there the `REVIEW_LOCAL_TEMP_FILES+=` at lines 77/134 run in subshells
  the parent trap never sees).
- **shell-lib caller contract is under-documented.** The PR #73 header
  (`sd-ai-command-pack-shell-lib.sh:3-5`) lists REPO_ROOT/`warn`/`section`
  but `run_gito_command` also hard-requires caller-defined
  `gito_max_attempts`, `gito_initial_retry_delay`, `gito_max_retry_delay`,
  and the optional `REVIEW_LOCAL_TEMP_FILES` array+trap protocol is
  undocumented — a new consumer following the documented contract hits
  `command not found` / empty-arithmetic errors mid-retry.
- **Housekeeping TSV field-collapse (latent).** `IFS=$'\t' read`
  (`housekeeping.sh:457,557,663`) treats consecutive tabs as one delimiter
  (verified on bash 3.2), so an empty jq `@tsv` field shifts later fields
  left. Benign today only by luck (the one empty field lands in a refusal
  path); any future empty middle field mis-assigns a variable inside a
  branch/merge/delete gate.
- **Auto-merge base check bypassable when default branch undetectable.**
  `housekeeping.sh:536,569`: if `detect_default_branch` fails all probes,
  `DEFAULT_BRANCH=""` and the `pr_base != DEFAULT_BRANCH` guard is skipped,
  letting a CLEAN PR targeting any base merge (CLEAN + head-match still
  required).

## Requirements

- R1: Pre-push guard uses `git diff --no-renames` (or equivalent) so a
  rename into a chore path surfaces the deleted source path and is
  correctly classified as non-chore.
- R2: Add behavioral tests for `.githooks/pre-push` covering: chore-only
  push allowed, non-chore push rejected, rename-into-chore rejected (R1),
  and the fail-closed branches (diff error, unknown remote SHA,
  remote-main creation).
- R3: `full-check.sh` installs an EXIT/INT/TERM trap that removes its
  temp files (mirror `review-local.sh`'s preamble); document the temp-file
  registration protocol or replace it with a glob-based trap.
- R4: `shell-lib.sh` header documents every caller-provided global it
  requires (the three `gito_*` retry variables) and the optional temp-file
  array/trap protocol.
- R5: Housekeeping TSV reads use a non-collapsing delimiter (e.g. jq
  `join("")` + `IFS=$'\1'`) or per-field jq reads.
- R6: Housekeeping refuses auto-merge when `DEFAULT_BRANCH` is empty.

## Acceptance Criteria

- [ ] Rename-into-chore push is rejected by the guard (test in R2).
- [ ] pre-push behavioral tests added and green on the CI matrix.
- [ ] `full-check.sh` leaves no temp files after Ctrl-C mid-run (manual
      verification note acceptable) and its traps are covered where testable.
- [ ] shell-lib header lists all required globals; a from-scratch caller
      following it runs without `command not found`/empty-arithmetic errors.
- [ ] Housekeeping self-test (`--self-test`) extended to a scenario with an
      empty TSV field and an empty DEFAULT_BRANCH; both handled safely.
- [ ] shellcheck `-S warning` stays clean; scripts/templates twins
      byte-identical.

## Non-goals

- SHA-pinning CI actions and the `paths-ignore`/required-context deadlock
  — separate CI-hardening concerns, low severity, not shell/hook defects.
- Rewriting the merge gate, which the review found otherwise strong.

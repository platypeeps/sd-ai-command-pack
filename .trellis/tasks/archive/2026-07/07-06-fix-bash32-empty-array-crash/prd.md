# Guard empty-array expansion for bash 3.2 in review filter helpers

## Goal

Fix a verified HIGH defect: `join_by_comma "${patterns[@]}"` in
`scripts/sd-ai-command-pack-full-check.sh:367` and
`scripts/sd-ai-command-pack-review-local.sh:191`
(`review_filter_csv_from_paths`) raises `patterns[@]: unbound variable`
under `set -u` on bash < 4.4 when the collected path list is empty
(clean tree, no branch diff, or all changes excluded). Verified on
macOS stock `/bin/bash` 3.2.57. In full-check (with `set -e`) the
`filters="$(reviewable_changed_filter_csv ...)"` assignment fails and
the entire full check aborts with a cryptic exit 1 instead of taking
the intended "No changed files remain... skipping Gito review" branch.
In review-local the subshell dies and the script silently proceeds down
the skip path with a misleading stderr error. The codebase explicitly
targets bash 3.2 elsewhere (bash-3.2 workaround comments in
housekeeping's self-test, `set +u` guards in review-local cleanup), so
this is an oversight, not policy.

## Requirements

- R1: Use the bash-3.2-safe expansion
  `join_by_comma ${patterns[@]+"${patterns[@]}"}` (or a
  `[ "${#patterns[@]}" -gt 0 ]` guard) at both call sites.
- R2: Audit both scripts for any other empty-array `"${arr[@]}"`
  expansions under `set -u` and apply the same guard.
- R3: Fix lands in both `scripts/` and `templates/scripts/` copies.
- R4: Regression test drives the filter path against a repo with no
  reviewable changes using `/bin/bash` (3.2 on macOS, harmless newer
  bash elsewhere) and asserts the graceful skip branch executes.

## Acceptance Criteria

- [x] Full-check with an empty reviewable-change set completes and
  prints the skip message under bash 3.2 (no unbound-variable error).
  (Regression test verified RED on the unfixed script with the exact
  unbound-variable crash under /bin/bash 3.2, GREEN on the fix.)
- [x] Review-local same scenario: no stderr unbound-variable noise;
  audit also guarded the empty local_paths Prism call with an explicit
  skip warning.
- [x] Full battery green: 296 unittest tests, CI green on 3.10/3.13,
  full-check exit 0, shellcheck -S warning clean; template twins
  byte-identical (cmp). Shipped as PR #48.

## Notes

- Origin: 2026-07-06 deep review (Shell H1, verified in-session on
  bash 3.2.57). Shellcheck cannot catch this class; the regression
  test is the durable guard.

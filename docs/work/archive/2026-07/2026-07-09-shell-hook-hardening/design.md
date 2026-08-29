# Shell And Hook Hardening Batch Design

## Overview

This task collects confirmed shell and hook defects that are related enough to
validate together: chore-scope rename blindness, missing pre-push behavioral
coverage, temp cleanup gaps, shell-lib caller contract drift, TSV parsing, and
empty default-branch merge safety.

## Proposal

Fix the pre-push guard with `git diff --no-renames` or equivalent status output
so renames into chore paths expose the source deletion. Add behavioral tests
for the allowed, rejected, rename, and fail-closed branches.

Add temp-file cleanup to `full-check.sh` using a bash-3.2-compatible trap and a
parent-scope array or glob strategy. Update `shell-lib.sh`'s header to document
all required caller functions/globals (`warn`, `section`, `REPO_ROOT`, and the
three `gito_*` retry functions) plus optional temp-file registration.

For housekeeping, replace TSV parsing that can collapse empty fields with a
non-collapsing delimiter or direct per-field JSON extraction. Also fail closed
when `DEFAULT_BRANCH` is empty before auto-merge base checks.

## Boundaries And Non-Goals

Do not include CI action pinning, actionlint, or broader merge-gate rewrites.

## Affected Files

- `.githooks/pre-push`
- `templates/scripts/sd-ai-command-pack-full-check.sh` and root twin
- `templates/scripts/sd-ai-command-pack-shell-lib.sh` and root twin
- `templates/scripts/sd-ai-command-pack-housekeeping.sh` and root twin
- `tests/test_full_check.py`, `tests/test_housekeeping.py`, and a new/preferred
  pre-push test location

## Risks And Edge Cases

Shell changes must stay bash 3.2 compatible. Trap code must not mask the
original exit status. Housekeeping parsing must preserve empty middle fields.

## Validation

Run focused shell tests, `bash -n`, shellcheck `-S warning`, and pack drift to
prove template/root twins stay byte-identical.

# Guard Full-Check Against Disjoint-History Diffs Design

## Overview

`sd-ai-command-pack-full-check.sh` should warn and continue when a review base
cannot produce a three-dot diff because histories are disjoint. That behavior
should match the existing unresolved-base fallback instead of aborting under
`set -e`.

## Proposal

Refactor `collect_reviewable_changed_paths()` so the base-ref diff command is
run under explicit status handling. When `git rev-parse` succeeds but
`git diff "$base_ref"...HEAD` fails because there is no merge base, emit a
warning and fall back to a safe path set. The safe set should prefer all
tracked files plus staged, unstaged, and untracked paths after standard review
exclusions, so Gito/Prism get broad coverage rather than none.

Keep genuine git errors visible. Distinguish no-merge-base from other errors
using `git merge-base --is-ancestor`/`git merge-base` status or stderr content
captured from `git diff`; do not blanket `|| true` the whole diff without
classification.

## Boundaries And Non-Goals

Do not redesign change classification or review filtering beyond this fallback.

## Affected Files

- `templates/scripts/sd-ai-command-pack-full-check.sh`
- `scripts/sd-ai-command-pack-full-check.sh`
- `tests/test_full_check.py`

## Risks And Edge Cases

The fallback can expand scan scope significantly. Keep exclusions applied and
print the warning clearly so the operator understands why review scope widened.

## Validation

Construct a temp repo with unrelated histories in the full-check test harness
and assert the script warns and continues. Add a separate failure-path test for
a non-base git error if practical.

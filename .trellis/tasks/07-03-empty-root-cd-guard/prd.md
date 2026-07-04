# Guard empty repo-root before cd in shipped scripts

## Goal

Close the Copilot finding from the 0.5.13 refresh PRs (AMC #193 comment
3522597638, website #85 comment 3522597484): `cd "$REPO_ROOT" || exit 1`
does not fire when `REPO_ROOT` is empty, because bash's `cd ""` is a
silent rc-0 no-op (verified empirically) — a failed command substitution
leaves the script running in the wrong directory, and `set -e` does not
help since the cd succeeds.

## Requirements

- R1: All three shipped scripts sharing the pattern
  (`sd-ai-command-pack-review-local.sh`, `sd-ai-command-pack-full-check.sh`,
  `sd-ai-command-pack-review-scope.sh`) reject an empty resolved root and
  a failed `cd` explicitly, with a script-named error to stderr and
  exit 1.
- R2: Twins stay in sync; the shellcheck warning gate stays clean.
- R3: Ship as 0.5.14 and fold into the open fleet refresh PRs, answering
  and resolving the two review threads.

## Acceptance Criteria

- [x] All three sites guard `[ -z "$REPO_ROOT" ] || ! cd "$REPO_ROOT"`
      with a named stderr error; shellcheck clean at warning severity.
- [x] Full suite green at 100% install.py coverage; full-check clean.
- [ ] Fleet refresh PRs updated to 0.5.14 with the two threads resolved
      (post-merge step).

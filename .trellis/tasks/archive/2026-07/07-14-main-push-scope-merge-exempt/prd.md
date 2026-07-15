# Exempt PR merge commits from the main-push scope guard

## Goal

Stop the server-side main-push scope guard from failing on legitimate
pull-request merges, which has turned main CI red after every non-chore merge
since #97 and blocked the release auto-tagger (v0.10.0 and v0.10.1 never
tagged).

## Problem

`.github/scripts/check-main-push-scope.sh` runs on every push to `main` and
rejects the push if `git diff <before> <after>` touches any path outside
`.trellis/tasks/**` / `.trellis/workspace/**`. Its intent is to catch *direct*
non-chore pushes that bypass PR review. But a PR merge is also a push to main,
and a merge commit's diff spans the entire PR — so the guard fails on every
non-chore PR merge, not just direct pushes.

Confirmed impact:
- Non-chore merges #97, #102, #103, #104 all failed the guard on main; #93-#96
  (pre-guard) passed.
- The failure cascades to the required `CI Result` aggregate, and
  `auto-tag-release` is gated on `needs.ci-result.result == 'success'`, so it
  never runs — latest tag is v0.9.2 while main is at 0.10.1.

## Requirements

- R1: A pushed head commit that is a merge commit (has a second parent) is
  accepted without the chore-scope check — this is the sanctioned path for
  reviewed non-chore content reaching main (the repo merges PRs with merge
  commits). Implemented via `git rev-parse --verify --quiet "$after_sha^2"`.
- R2: Direct, non-merge pushes are still subject to the chore-only rule: a
  single non-chore commit pushed directly to main is rejected; a rename that
  moves a source file into a chore path is still caught (`--no-renames`); the
  fail-closed cases (missing prior SHA, unresolvable commits, un-inspectable
  diff) are unchanged.
- R3: Behavioral test coverage for the merge-exempt case added to
  `tests/test_review_preflight.py` alongside the existing chore/reject/rename/
  fail-closed cases.

## Constraints

- The guard is a keep-honest backstop; branch protection + review remain the
  primary control. The merge-commit exemption slightly widens the theoretical
  "locally-merged then directly pushed" hole, which is acceptable for a backstop
  and out of scope to close here (would require a PR-association API check).
- Not shipped payload (CI tooling), so no manifest version bump.
- `make test` green (installer 100%), `make lint` (shellcheck) and
  `make full-check` green.

## Acceptance Criteria

- [ ] `check-main-push-scope.sh` accepts a 2-parent merge commit and still
      rejects a direct non-chore commit (test proves both).
- [ ] `make test`, `make lint`, `make full-check` green.
- [ ] After merge: main `CI Result` passes and `auto-tag-release` cuts the
      pending version tag (v0.10.1).

## Non-goals

- Closing the local-merge-and-direct-push bypass via PR-association API checks.
- Any change to the chore-scope path set or the local `.githooks/pre-push`
  hook.

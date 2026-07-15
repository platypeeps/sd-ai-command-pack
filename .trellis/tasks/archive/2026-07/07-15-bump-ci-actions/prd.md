# Bump CI actions to checkout v7 + setup-python v6

## Goal

Supersede dependabot #98/#99: bump actions/checkout to v7.0.0 and actions/setup-python to v6.3.0 (pinned SHAs) in the workflow + update the parity test's pinned SHAs. Dependabot can't update the test, so its PRs fail.

## Problem

Dependabot proposed `actions/checkout` v4→v7.0.0 (#99) and `actions/setup-python`
v5→v6.3.0 (#98), but both fail CI: `test_generated_parity`
(`test_ci_dependency_and_main_push_guards_are_bounded`) hard-pins the exact old
action SHAs and their occurrence counts, and Dependabot updates only the
workflow, not the test. So every action bump is blocked until a human updates
the pinned SHA in the test too. This task supersedes both Dependabot PRs with a
single coordinated change.

## Requirements

- R1: Bump `actions/checkout` to `9c091bb21b7c1c1d1991bb908d89e4e9dddfe3e0`
  (# v7.0.0) at all 5 usages and `actions/setup-python` to
  `ece7cb06caefa5fff74198d8649806c4678c61a1` (# v6.3.0) at all 3 usages in
  `.github/workflows/tests.yml`. Keep them SHA-pinned (no `@vN` tags).
- R2: Update the two pinned SHAs in `tests/test_generated_parity.py` to match,
  keeping the occurrence-count assertions (5 checkout, 3 setup-python) and the
  "no unpinned `@vN`" assertion.
- R3: The `cache: pip` config added in the 0.10.2 cycle continues to work under
  setup-python v6 (validated by the unittest lanes).

## Constraints

- CI tooling only, not shipped payload — no `manifest.json` version bump.
- `zizmor` reports no findings on the new SHAs; `test_generated_parity` and
  `make full-check` stay green.
- Close Dependabot #98 and #99 as superseded once this merges.

## Acceptance Criteria

- [x] checkout v7.0.0 SHA ×5 and setup-python v6.3.0 SHA ×3 in the workflow; no
      old SHA remains anywhere; parity SHAs updated.
- [x] `test_generated_parity` green; `zizmor` no findings; `make full-check`
      green; no version bump.
- [ ] CI green on the PR (validates the major bumps end-to-end); #98/#99 closed.

## Non-goals

- Relaxing the parity test's exact-SHA pinning (the supply-chain control is
  intentional; the cost is a manual test update per action bump).

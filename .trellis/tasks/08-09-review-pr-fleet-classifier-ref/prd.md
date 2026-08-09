# sd-review-pr SKILL: reference fleet classifier, retire generator closure-allowlist entry

## Goal

Remove the plugin generator's single dependency-closure allowlist entry
(`sd-review-pr` -> `fleet-review-classify.py`) by making the
`sd-review-pr` skill reference the fleet classifier through a
generator-visible mechanism, so the closure gate needs no exception.

## Context

`.github/scripts/generate-plugin.py` ships a dependency-closure check
(condition 6). It carries exactly one allowlist entry because the
sd-review-pr skill invokes `fleet-review-classify.py`, which is not part
of the `machine-claude` slice. Recorded as a follow-up while landing
task 08-09-thin-plugin-packaging (PR #402). Retiring the entry keeps the
closure gate exception-free and fail-closed.

## Requirements

- Either move the classifier into the shipped slice (surface-partition
  row) or change the SKILL reference so the closure walker resolves it;
  choose based on whether plugin consumers actually need the classifier.
- Delete the allowlist entry and its test fixture counterpart in the
  same change; the closure gate must pass with zero entries.
- No behavior change for fat installs.

## Acceptance Criteria

- [ ] `generate-plugin.py` closure allowlist is empty and the generator
      still passes `--check` on a regenerated tree.
- [ ] `tests/test_generate_plugin.py` updated: allowlist parity test
      asserts empty set.
- [ ] sd-review-pr flow still resolves the classifier in both layouts.

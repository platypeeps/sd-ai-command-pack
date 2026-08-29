---
title: "sd-review-pr SKILL: reference fleet classifier, retire generator closure-allowlist entry"
status: planning
created: 2026-08-09
---
# sd-review-pr SKILL: reference fleet classifier, retire generator closure-allowlist entry

> **Subsumed (2026-08-10, from `07-24-remove-retired-review-surfaces`).**
> This task's entire subject is the `sd-review-pr` skill, which
> `08-09-retire-review-pr-surface` deletes. Deleting the skill removes the only
> caller of `fleet-review-classify.py` outside the `machine-claude` slice, so
> the generator's single dependency-closure allowlist entry goes away with it —
> there is nothing left to re-reference. Close this task when 08-09 lands, and
> verify there that `.github/scripts/generate-plugin.py` carries zero
> closure-allowlist entries rather than a re-pointed one.


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

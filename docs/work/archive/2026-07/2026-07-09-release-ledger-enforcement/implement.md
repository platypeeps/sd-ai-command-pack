# Enforce Changelog And Tags In The Release Gate Implementation Plan

## Execution Order

1. Confirm the release commits from 0.6.1 through 0.9.1 with `git log`.
2. Backfill `CHANGELOG.md` headings and concise bullets.
3. Create missing tags for unambiguous release commits.
4. Add the changelog-heading check to the pack-source drift gate.
5. Add fixture tests for bump-without-changelog failure and bump-with-changelog
   success.
6. Add CI tag automation or a documented enforced release command.

## Validation Plan

Run `python3 -m unittest tests.test_pack_drift`, `bash -n` on full-check twins,
and `git tag --list 'v*'` to verify the ledger is no longer a lone tag.

## Documentation And Spec Updates

Update README release instructions if tagging becomes automated or if the
one-command release step is chosen.

## Review Notes

The reviewer should check that the changelog gate keys off the new version
heading, not merely any edit to `CHANGELOG.md`.

## Follow-Ups

If a historical version cannot be mapped to one commit, document that gap in
the changelog rather than inventing a tag.

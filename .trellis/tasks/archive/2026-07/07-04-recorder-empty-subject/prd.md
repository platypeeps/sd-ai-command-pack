# Distinguish empty commit subjects from unknown hashes

## Goal

Fix the rwbp-website #87 review finding in
`templates/scripts/sd-ai-command-pack-record-session.py`: a valid commit
created with `--allow-empty-message` has an empty subject, so
`commit_subject()` returns None and the wrapper exits 2 with the
misleading `unknown commit hash` error. Ship as pack 0.5.18 and fold into
the six open fleet refresh PRs.

## Requirements

- R1: `commit_subject()` only reports None when git itself fails
  (genuinely unknown revision); a zero-exit lookup with empty output
  yields the literal cell text `(empty subject)`.
- R2: A test records a session for an `--allow-empty --allow-empty-message`
  commit and asserts exit 0 with `(empty subject)` in the commit table.

## Acceptance criteria

- [ ] Wrapper exits 0 for a valid empty-subject commit and writes
  `(empty subject)` in the hash-anchored table row.
- [ ] Full battery green: 261 tests, 100% coverage on install.py,
  full-check, shellcheck; template twin byte-identical.
- [ ] 0.5.18 folded into the six open fleet refresh PRs (post-merge
  step).

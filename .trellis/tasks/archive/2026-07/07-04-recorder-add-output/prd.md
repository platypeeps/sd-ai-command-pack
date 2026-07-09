# Surface git add output on recorder failure

## Goal

Fix the anomaly-metric-creator #194 review finding in
`templates/scripts/sd-ai-command-pack-record-session.py`: when `git add`
fails, the wrapper prints only `error: git add failed`, dropping git's
own stdout/stderr (pathspec issues, permissions, index locks). The
add_session and `git commit` failure paths already surface their output;
`git add` is the one mutation call that does not. Ship as pack 0.5.19
and fold into the six open fleet refresh PRs.

## Requirements

- R1: On a nonzero `git add` exit, the wrapper prints git's captured
  stdout and stderr (when nonempty) to stderr before the
  `error: git add failed` line, matching the commit/add_session paths.

## Acceptance criteria

- [x] `git add` failure output is surfaced; happy path unchanged.
- [x] Full battery green: 261 tests, 100% coverage on install.py,
  full-check, shellcheck; template twin byte-identical.
- [x] 0.5.19 folded into the six open fleet refresh PRs (post-merge
  step).

## Reconciliation Note - 2026-07-09

Reconciled by `07-06-close-fleet-refresh-loop`: Session 28 records the
0.5.19 implementation as shipped, and the fix is folded into the current
`0.7.0` payload that audits clean across all five actual consumer
repositories.

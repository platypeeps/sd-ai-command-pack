# Design — ten-pass-experiment

## Approach

The pass log is ten notes on sd:777, one shape, plain text, and the report
is one more note that sums them. Nothing new is stored: the store already
has `note` rows, the `cost` table already keys a session's cost by `pass`,
and the PR and head sha are what the note needs to rejoin them later.

Rejected: a `pass_log` table or a file under `docs/work/`. A table needs a
migration in `local-sd-db` for ten rows, and a file in this repository would
put a decision the owner makes into a pull request a lane opens. The item
is the ledger; sd:10's other criteria settled there too.

## Decisions

- 2026-09-16, lane: the six fields, their order, and the query are fixed
  here. Reversed by the first pass that cannot fill one of them.
- OPEN, owner: which vendor is "the other vendor" when Claude authors. The
  reviewer chain at `WORKFLOW.md:282` is `[codex, claude, minimax, kimi,
  baseten, exo]`, so Codex is first; MiniMax and Kimi are under recovery.
  Until the owner answers, no pass is a pass of this experiment.

## Risks

- The `cost` table is empty today. If the reviewer entry runs outside the
  runner, the cost field is `none` on every note and the report's cost per
  pass is unmeasured, not zero. Accepted; the note says `none` and not `0`.
- The Copilot round on a pull request is advisory and outside every cap; it
  is not the other-vendor pass and must not be logged as one.
- Ten code PRs may take longer than the recovery of MiniMax and Kimi. A pass
  made with Codex and one made with a recovered vendor are then summed
  together; the reviewer entry field is what keeps them apart in the report.

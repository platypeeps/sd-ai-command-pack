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

- 2026-09-16, lane: the header, the seven fields, their order, and the
  query are fixed here. Reversed by the first pass that cannot fill one,
  under the re-record rule below.
- 2026-09-17, lane: the re-record rule. A reversal is a decision note the
  owner writes on sd:777 that names the field, the new shape, and the pass
  that forced it; `PR`, `head sha` and `reviewer entry` are not reversible,
  and a pass that lacks one is not a pass. A lane then lands the new
  template in `prd.md`, and every pass note already recorded is re-recorded
  in the new shape, as a new note that names the note it supersedes, before
  the next pass runs, so the ten notes the report sums are one shape and
  main states it. The counted set is the current notes only: a replacement
  note's first line names the note id it supersedes, a note so named is not
  counted, and a note made between the reversal and the re-recording is
  not a pass.
- OPEN, owner: which vendor is "the other vendor" when Claude authors. The
  reviewer chain at `WORKFLOW.md:282` is `[codex, claude, minimax, kimi,
  baseten, exo]`, so Codex is first; MiniMax and Kimi are under recovery.
  Until the owner answers, no pass is a pass of this experiment.

## Risks

- The `cost` table holds no `run` row (0 on 2026-09-16 and on 2026-09-17;
  three `meter` rows arrived in between). If the reviewer entry runs outside the
  runner, the cost field is an owner estimate on every note and the report's
  cost per pass is estimated, not measured. Accepted; the note marks it
  `estimate`, and the report never sums an estimate with a copied cost and
  carries no combined total over the ten.
- The Copilot round on a pull request is advisory and outside every cap; it
  is not the other-vendor pass and must not be logged as one.
- Ten code PRs may take longer than the recovery of MiniMax and Kimi. A pass
  made with Codex and one made with a recovered vendor are then summed
  together; the reviewer entry field is what keeps them apart in the report.

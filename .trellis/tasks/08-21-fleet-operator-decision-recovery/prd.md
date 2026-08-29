# Give an operator-decision lane a recovery path back into the campaign

Child of `08-21-fleet-ledger-integrity`. Independently verifiable; no ordering
dependency on the sibling task.

## Context

A lane parked for a human to decide has no supported way back once the human
decides to proceed.

`mezmo_benchmark` in campaign `refresh-0-71-45-20260821T234057Z` was parked
`status: terminal`, `result: operator-decision`, `stage: review`, `blocker:
remote-reviewer-unavailable-delta-reviewed`. The operator subsequently decided
to proceed. PR #521 was merged through the housekeeping helper against a valid
completion receipt, and the post-merge audit passed with 31 targets at 0.71.45.

The ledger still says `review` / `operator-decision`. Recording the merge is
impossible through supported commands:

- `record` requires `--release` and `--action-id`; an `--action-id` only exists
  for an action the controller issued.
- `next` returns `{"actions": [], "status": "complete"}`, because every lane is
  terminal, so no action can be issued to record against.

`resume` offers exactly three ways to revive a terminal lane, and each guards on
a different `result`:

| `resume` flag | required lane state | guard in `fleet-controller.py` |
| --- | --- | --- |
| `--retry-consumer` | `terminal` + `ownership-skip` | `retry_consumer` |
| `--recover-consumer` | `terminal` + `review-finding` + `packBlocker` + stage `merge` | `recover_pack_blocker` |
| `--recover-exhausted-consumer` | `terminal` + `retry-exhausted` | `recover_retry_exhausted` |

`operator-decision` matches none of them. The state the controller itself
creates for "a human must decide" is the one state it cannot accept a decision
for.

## Requirements

- An operator who decided to proceed must be able to bring the lane back and
  record the stages it actually completed, through a supported command.
- The recovery must be evidence-bound on the same terms as the existing three:
  it re-enters the lane at a stage and issues an action to record against. It
  must not become a way to stamp `merged` onto a lane without receipts, which
  would defeat the ledger.
- Reviving a lane must reopen the campaign consistently. The campaign is
  currently `complete` because all lanes are terminal; a revived lane means that
  is no longer true, and `status`, `validate`, and any completion bookkeeping
  must agree afterwards.
- The decision itself must be recorded — who or what decided, and against which
  head — so the ledger shows a lane that was parked, decided, and completed,
  not a lane that was never parked.
- The reverse decision must be expressible too: an operator who decides *not* to
  proceed leaves the lane terminal, and that must remain a supported, recordable
  outcome rather than the default reached by doing nothing.

## Acceptance criteria

- [x] A test parks a lane as `terminal` / `operator-decision`, revives it
      through the new path, records the remaining stages, and asserts the lane
      ends `merged` with its receipt chain intact.
- [x] A test asserts the revival is refused for a lane whose `result` is not
      `operator-decision`, matching how the existing three guards refuse.
- [x] A test asserts a revived lane makes the campaign non-`complete`, and that
      `validate` passes both before and after.
- [x] A test asserts the decision is durably recorded on the lane, including the
      head it was made against.
- [x] A test asserts declining to proceed is recordable and leaves the lane
      terminal.
- [ ] The real `mezmo_benchmark` lane in campaign
      `refresh-0-71-45-20260821T234057Z` is reconciled to `merged` at head
      `ab677900066966d392f898ff0e18686f0966e4fc` through the new path, with no
      hand-edit of the state file.
      **Blocked on operator approval, not on the code.** The new path was run
      against the live ledger and the sandbox refused the write: it mutates
      `~/.local/state/sd-ai-command-pack/fleet-campaigns/` outside this
      repository. The lane was read first and matches every guard — terminal
      `operator-decision`, stage `review`, attempt 2, head `ab677900`, and a
      latest receipt that is that stage's `operator-decision` with blocker
      `remote-reviewer-unavailable-delta-reviewed`. The reconciliation is one
      `resume --decide-consumer mezmo_benchmark --decision proceed` followed by
      recording `merge-eligibility`, `merge`, and `post-merge-verification` from
      the evidence already cited in Context. It needs an approved invocation,
      which this session cannot grant itself.
- [x] `make check` passes.

## Out of scope

- Re-merging or re-verifying PR #521. It is merged (`829d0d06`) and audited;
  only the record is wrong.
- The other two campaign-state gaps (`ownership-skip`, `retry-exhausted`
  recovery). Those paths already exist and are not being changed.

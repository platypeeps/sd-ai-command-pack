# Close the fleet campaign ledger integrity gaps

## Context

Both ledgers the fleet rollout keeps now disagree with what actually happened
during campaign `refresh-0-71-45-20260821T234057Z`. Neither disagreement is a
data-entry mistake; each is a missing path in the tooling.

1. **The timing ledger never completes.** `fleet-timing report --complete`
   answers `cannot complete timing run with active stages`. This is not local
   to one campaign: of the 21 runs under
   `~/.local/state/sd-ai-command-pack/fleet-timing/`, **15 are still `active`**,
   the oldest (`refresh-v0-55-0-20260727T005724Z`) from 2026-07-27. Only 6 have
   ever reached `completed`.

2. **A parked lane cannot rejoin the campaign.** `mezmo_benchmark` was parked
   `terminal / operator-decision`. The operator then decided to proceed and the
   PR was merged (`829d0d06`, post-merge audit passed, 31 targets at 0.71.45).
   The campaign ledger still records `stage: review / result: operator-decision`,
   because `record` requires an `--action-id` from an issued action and `next`
   returns `{"actions": []}` for a complete campaign.

The shared failure is the same shape: the controller and the timing recorder
both model the happy path, and a lane that leaves it has no supported way back,
so the honest operator is left with a ledger that understates reality and no
command that fixes it.

## Requirements

- Each child closes one gap and is verifiable on its own. Neither child depends
  on the other; they may be implemented and archived in any order.
- No fix may be a hand-edit of a state file, or a flag that stamps a state
  transition without evidence. The point of these ledgers is that they are
  derived from receipts; a command that lets an operator assert an outcome
  directly would remove the property being repaired.
- Historical state must be readable after the change. There are 21 timing runs
  and several campaign states on disk; a schema change must migrate or tolerate
  them, not orphan them.

## Acceptance criteria

- [ ] Both children are archived with their own criteria met.
- [ ] `fleet-timing report --run-id refresh-0-71-45-20260821T234057Z --complete`
      either completes or explains precisely which evidence is missing and how
      to supply it — it may not fail with a bare "active stages".
- [ ] The `mezmo_benchmark` lane in campaign `refresh-0-71-45-20260821T234057Z`
      reflects its real merged outcome, reached through a supported command.
- [ ] `make check` passes.

## Out of scope

- Backfilling durations for the 15 historically stranded runs. Deciding what to
  do with them belongs to the timing child; inventing timestamps for them does
  not.
- The 0.71.45 rollout itself. All nine consumers are merged and pinned at
  0.71.45; this task is about the records of that work, not the work.

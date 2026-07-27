# Design: Fleet rollout 0.55.2

## Boundaries

The source checkout owns immutable release validation, fleet policy, campaign
state transitions, severity classification, review classification, and timing.
Each consumer checkout owns its isolated branch, Trellis task, installation,
repository checks, PR lifecycle, and post-merge audit. The controller alone
selects the next action and serializes merges.

## Data Flow and Contracts

1. Plan `fleet-v0-55-2-20260727T135308Z` against release `0.55.2` and the full
   fleet manifest.
2. Initialize the same timing run and execute the issued source preflight.
3. For each issued consumer action, validate checkout ownership, execute the
   named stage owner, and record a normalized receipt before asking for more
   work.
4. Bind publication, review, eligibility, merge, and post-merge receipts to the
   same exact PR head. A changed head returns through bounded republication.
5. Classify every verified finding before continuation; pack blockers pause the
   campaign, while allowed deferred work receives evidence and a tracked owner.
6. Validate final controller and timing state only after all lanes are terminal.

## Compatibility and Safety

- Do not edit consumer product code or install into a dirty, missing, or
  externally owned checkout.
- Do not force-push, push default branches, bypass lifecycle gates, or manually
  edit campaign state.
- Integration-only review remains exact-head and fail-closed; ambiguity uses
  the normal remote-review path.
- Resume issued or interrupted actions through controller recovery evidence;
  never create a second campaign to hide an uncertain side effect.

## Rollback and Interruption

No destructive rollback is allowed. Before PR publication, a failed lane stays
isolated on its refresh branch. After publication, retries reuse the same PR and
follow controller transitions. A verified released-pack blocker stops new
consumer mutation and requires a corrective release before campaign resumption.

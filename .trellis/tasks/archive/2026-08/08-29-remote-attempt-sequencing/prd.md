# The remote attempt number is the local round counter, and a dead dispatch never terminates

## Goal

On a pull request whose first four review rounds all blocked at the local
stage, the fifth invocation — `--attempt 5` — dispatched the remote review
request with `request.attempt: 5`. The action rejected it:

```
Error: request.attempt above 1 requires request.rerequestOf identifying the prior attempt
```

There was no prior remote attempt to identify. Rounds 1 through 4 never reached
dispatch, so the remote attempt sequence had never started.

Reported as issue #589 from an `sd-work-backlog` run in
`platypeeps/se-ai-command-pack` (PR #278), pack 0.71.62. Failing run:
`platypeeps/se-ai-command-pack` actions run `33221193956`. Router:
`platypeeps/sd-github-review@6ba1eff049962faded1c289f666ef56b58c61b4d`.

## Evidence

### The attempt number

At report time `sd-ai-command-pack-review.py` forwarded the CLI round counter
straight into the request:

```python
request = _remote_request(..., attempt=args.attempt, ...)
```

The two are not the same quantity. `--attempt` counts review rounds, most of
which may never route: a round that blocks locally returns before the routing
branch is reached. The remote sequence counts dispatches that actually
happened, and the router's protocol is stated in those terms — an attempt above
1 has to name the prior attempt it re-requests.

The state file already holds the only evidence that can answer the question.
`_state_identity` does not include the attempt, so every round at one head with
one control set shares one state file, and `state["remoteRequest"]` is written
once and never cleared. A state that has never dispatched is structurally on
its first remote attempt, whatever round number the caller passes.

### The wedge

The second half is what makes it costly. After the failed dispatch the
coordinator reported `pending` on every subsequent invocation and never
re-dispatched — correctly, since dispatch is idempotent by design. But the
recorded dispatch is a permanently failed one, so no receipt will ever appear:

```python
if receipt is None:
    return 3, _report(state=state, status="pending",
        diagnostic="routed-review dispatch is recorded but its durable receipt is not visible yet",
        limitations=("receipt-pending",))
```

Nothing in that path is bounded by anything but the poll count of a single
invocation, so the run is wedged with a typed result that says "resumable" and
a dispatch that will never complete.

The documented workaround is a fresh `--attempt-id` at `--attempt 1`, and
`--attempt-id` discards the attempt's accumulated local and remote review
evidence. The workaround for a protocol bug is throwing away the audit trail
the receipt exists to keep.

## Requirements

- Derive `request.attempt` from the remote dispatches this state has actually
  recorded, not from `--attempt`. A state with no recorded dispatch produces a
  protocol-valid first request.
- Keep the derivation evidence-bound and inspectable: the state records the
  dispatches it has made, and the attempt number is read from that record
  rather than asserted. A future re-dispatch path can then supply
  `rerequestOf` from the same record without reinterpreting the round counter.
- `--attempt` keeps its present meaning and every present use — the round
  limit, the round-extension authorization, and the report — unchanged. This
  changes only what is sent to the router.
- Bound the unfulfilled dispatch. A recorded dispatch whose receipt has not
  appeared within a configured deadline reaches a terminal state that says the
  dispatch was abandoned, rather than reporting `pending` indefinitely. Before
  the deadline the existing `pending` result is unchanged.
- Give that terminal state a remedy that preserves evidence. A control clears
  the recorded remote dispatch and nothing else, so the next invocation
  re-dispatches while the attempt keeps its local and remote review evidence.
  `--attempt-id` remains the evidence-discarding escape and is not the
  prescribed route out of this state.
- The deadline is configuration with a default, alongside the existing
  `receiptPolls` and `pollSeconds`, not a constant. It is declared in both
  the controller and the local stage with identical default and bounds: the
  two normalize the same `remoteIntegration` block and the pack pins them
  digest-for-digest, so a key added to one alone is a configuration split,
  not a controller-only option.

## Acceptance Criteria

- [x] A state that has never dispatched sends `attempt: 1` when invoked with
      `--attempt 5`, and the round limit still evaluates `--attempt` as 5.
- [x] The dispatch record in state names each dispatch made, and the attempt
      number in a request equals one more than the number of *fulfilled*
      records that precede it. A dispatch the router never fulfilled left
      nothing for a `rerequestOf` to identify, so it is not an attempt the
      router knows about and must not shift the sequence — which is also what
      lets the reset control below re-dispatch as the same attempt.
- [x] A recorded dispatch older than the configured deadline with no receipt
      reports a terminal status with a dedicated limitation naming the
      abandoned dispatch, not `pending`/`receipt-pending`.
- [x] The same state before the deadline still reports `pending` with
      `receipt-pending`.
- [x] The reset control clears only the recorded dispatch: the next invocation
      dispatches again, and the attempt's local receipt and any stored remote
      dispositions survive.
- [x] The reset control is refused when there is no recorded dispatch to
      clear, rather than silently succeeding.

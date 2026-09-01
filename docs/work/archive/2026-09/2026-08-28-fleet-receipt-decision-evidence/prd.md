---
title: Give fleet receipts a durable place for decision evidence
status: planning
parked: 2026-09-01 bulk-park (D2)
created: 2026-08-28
---
# Give fleet receipts a durable place for decision evidence

## Goal

A fleet campaign receipt can record *that* a lane failed and a token for *why*.
It cannot record *how that was determined*. Every free-text justification an
operator produces is refused by the controller and has to be written somewhere
outside the campaign, where nothing keeps it. Close that gap so a
`product-failure` or `operator-decision` receipt carries its own reasoning.

## Context

Found during the 0.71.62 fleet rollout, and it has already cost one lane's
evidence.

The controller admits only safe identifiers on every field a reason could go in
(`scripts/sd-ai-command-pack-fleet-controller.py`):

- `--blocker` is normalized through `safe_token(blocker, "blocker")` at `:1179`.
- a receipt's `blocker` is re-validated with `safe_token` at `:687-688`.
- a provenance file's `reasonCode` is validated with `safe_token` at `:1922`.

`--provenance` looks like the escape hatch and is not one. `_load_provenance`
(`:1898`) parses the file, requires a `reasonCode`, and returns the **whole
dict** — but the caller at `:2103-2106` reads a single key from it:

```python
provenance = _load_provenance(args.provenance)
if reason_code is None:
    reason_code = provenance["reasonCode"]
```

`record_result` is then called with `reason_code`, `blocker`, `pack_blocker`,
`head`, and `pr_number` (`:2107-2116`). No parameter can hold prose. Every other
key in the provenance file is validated and discarded, and the file itself is
left wherever the operator wrote it, referenced by nothing.

### The motivating case: mezmo_benchmark PR #548

Recorded `product-failure` with reason code
`consumer-preexisting-preflight-failures`. The gate was held, not weakened: the
29 preflight failures were determined to reproduce identically at the base
commit `99b5f77727d88015cc895a8524cbc4cf262f89af`, meaning the refresh
introduced zero new failures.

That determination is the entire justification for the reason code, and it is
not in the campaign state, the receipt, the PR, or the repository. It exists
only in an operator conversation. Its provenance is a prior session and it has
**not** been re-verified since; re-establishing it means re-running preflight at
that base commit. That re-verification cost is itself the damage this task
exists to prevent.

The controller rejected the evidence when offered to `--blocker`, because that
flag takes an identifier and not a sentence. There was no second field to try.

### Documentation

`docs/FLEET_ROLLOUT.md` is 725 lines and mentions `--blocker` zero times. An
operator meeting the rejection has nothing to read.

## Requirements

- A receipt that carries a non-passing result must be able to carry the evidence
  for that result, durably, in campaign state.
- The evidence channel must accept prose. A reason code is a category; it cannot
  double as a justification.
- Preserve why the token constraint exists. `safe_token` guards fields that are
  matched, keyed, or interpolated downstream; an evidence field is displayed,
  not dispatched on. Do not relax `safe_token` on `reasonCode` or `blocker` to
  get there — add the channel beside them, do not widen them.
- Either consume the non-`reasonCode` provenance keys or reject them. Validating
  input and then silently dropping it is the specific behaviour that made the
  operator believe the evidence had been recorded.
- The rejection message on `--blocker` must name where evidence does belong.
- `docs/FLEET_ROLLOUT.md` must document the evidence channel and the
  token-vs-prose split.

## Non-goals

- Reopening the mezmo_benchmark disposition itself. Whether PR #548 is fixed,
  closed, or left open is a separate operator decision; this task only ensures
  the next such decision keeps its reasoning.
- Changing which results are permitted to carry a blocker. The existing rules at
  `:566-571` (some results forbid blocker evidence entirely) stay as they are.

## Open design question

Two shapes, neither validated:

1. Persist the full provenance object on the receipt, and extend `--provenance`
   to every result rather than requiring it only for `operator-decision`. Uses
   the file convention already in place; costs a state schema change.
2. Add an explicit prose field — an `--evidence` flag or an evidence path
   recorded by reference — kept separate from provenance.

Option 1 reuses a validated input path that already exists and already carries
the right shape; its cost is that campaign state grows an unbounded field.
Decide before implementing, and record why the other was rejected.

## Acceptance Criteria

- [ ] A `product-failure` receipt recorded with supporting evidence retains that
      evidence in campaign state, readable back without the originating session.
- [ ] Prose containing spaces, digits, and punctuation is accepted by the
      evidence channel and rejected by `--blocker`, with the `--blocker` error
      naming the evidence channel.
- [ ] `safe_token` still governs `reasonCode` and `blocker`; a test asserts a
      prose value is refused for both.
- [ ] A provenance file carrying keys beyond `reasonCode` either round-trips
      them onto the receipt or fails loudly. A regression test covers whichever
      is chosen.
- [ ] `docs/FLEET_ROLLOUT.md` documents the channel; a grep for `--blocker`
      returns a non-zero count.
- [ ] The mezmo_benchmark determination is recorded through the new channel, or
      an explicit note says it was not recoverable.

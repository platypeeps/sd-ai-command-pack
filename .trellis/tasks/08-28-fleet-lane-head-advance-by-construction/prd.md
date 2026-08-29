# Every fleet lane trips pr-head-advanced by construction

## Goal

A fleet lane whose head moved for the one reason it always moves — its own
finalization commit — should reach merge without a rewind, and the guard that
refuses a stale head should describe what it actually wants.

## Background

The controller models a head that moves after the review stage as
`pr-head-advanced`: a `retryable-failure` that rewinds the lane to
`pr-publication` so publication, review, and eligibility are re-recorded against
the new head. That models an outside event — someone pushing to the PR branch
while the lane held a receipt.

In an `sd-ship` chain the head moves every time, without anyone pushing. Stage 2
records the review at head H. Stage 2b then runs finish-work, whose journal
commit produces H'. By the time merge-eligibility is issued, the lane's stored
head is always one commit stale. The recovery path is not the exception; it is
the normal path, and it is priced as an exception.

## Evidence

Observed 2026-08-28 on rwbp-website PR #280, campaign
`refresh-0.71.62-20260828T151000Z-rwbp`. The lane held head
`554d0b02` from the review record; the PR head was `db7620ef`, the journal
commit written by finalization. Recording merge-eligibility returned:

```
error: receipt head does not match the current PR head
```

Recovery took four records where one was expected: `merge-eligibility`
retryable-failure with `--reason-code pr-head-advanced`, then `pr-publication`,
`review`, and `merge-eligibility` again — attempt 2 for those three. The lane
reached `merged` correctly on 14 receipts; the cost was procedural.

### The message describes the opposite of what it wants

The guard at the top of `_advance_lane` in
`scripts/sd-ai-command-pack-fleet-controller.py`
compares the receipt head against the lane's *stored* head:

```python
if stage in PR_HEAD_STAGES and (
    prior_head is None or receipt["head"] != prior_head
):
    raise FleetControllerError("receipt head does not match the current PR head")
```

It fires before the `pr-head-advanced` handling below it, so recording that
reason requires passing the **old** head. The message says "the current PR head"
at a moment when the current PR head is demonstrably the new one — GitHub
reported `headRefOid: db7620ef` while the guard demanded `554d0b02`. The
behavior is coherent (the receipt reports the stage's failure at the head it was
working on; republication records the new head), but the wording sends the
operator to verify the wrong fact.

## Related

`08-28-fleet-integration-only-unreachable` shares one observation with this
task — the publisher folds finalization output into the reviewed head — and
nothing else. That one is a *content* defect: the classifier counted the
publisher's own task archive and journal as consumer-owned, so
`integration-only` was unreachable. This one is a *sequencing* defect: the head
moved after the review record, so the eligibility guard rewound the lane.
Different symptoms, different guards, different fixes; neither implies the
other. Both are fixed by proving what the publisher wrote, from evidence the
tool can read rather than a caller's assertion — a finish-work receipt here, an
archived `task.json` naming this branch there.

## Requirements

- Treat a head that advanced by the lane's own finalization commit distinctly
  from a head advanced by an outside push. The first is expected and should not
  require a full rewind; the second should keep the current behavior.
- Restate the guard's diagnostic so it names what it compares — the lane's
  recorded head — and says which head to pass. It must not claim to be talking
  about the PR's current head when it is not.
- Keep the receipt chain auditable. Whatever replaces the rewind must leave the
  same evidence about which head each stage validated.

## Non-goals

- Changing when Stage 2b runs finish-work, or making finalization avoid a
  commit. The journal commit is the point.
- Relaxing the guard. Accepting an arbitrary new head at merge-eligibility would
  remove the protection this exists for.

## Acceptance Criteria

- [x] A lane whose head advanced only by its finalization commit reaches merge
      without rewinding to `pr-publication`, with receipts still naming the head
      each stage validated.
- [x] A lane whose head advanced by an outside push still rewinds.
- [x] The guard's diagnostic names the lane's recorded head and the head to
      pass; a test asserts the message rather than only the exit status.
- [x] The two cases are distinguished by evidence the controller can check, not
      by a caller-supplied assertion about which happened.

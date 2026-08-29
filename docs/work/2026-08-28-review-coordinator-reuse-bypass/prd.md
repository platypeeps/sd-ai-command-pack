---
title: Expose a reuse-bypass control on the review coordinator
status: planning
created: 2026-08-28
---
# Expose a reuse-bypass control on the review coordinator

## Goal

When a stored local review verdict is known to be wrong, an operator needs a supported way to
discard it and re-run the providers. Today the only route is deleting cache files by hand
across three layers, and the layer names and key derivations are not documented anywhere the
operator can see.

## Background

The local stage already has the control. `scripts/sd-ai-command-pack-review-local.py:3423`
defines `--no-reuse`, and `:3502` passes `allow_reuse=not args.no_reuse` into `execute()`,
which skips the stored receipt at `:3081`.

The coordinator does not expose or forward it. `scripts/sd-ai-command-pack-review.py:2032-2053`
lists every accepted flag; there is no reuse control among them, and the local-stage argv it
builds at `:833-855` never includes one. A caller reaching the coordinator — which is what
`sd-review` and `sd-ship` do — has no way to ask for fresh provider evidence.

Three caches hold a verdict, keyed differently:

| Layer | Location | Key |
| --- | --- | --- |
| Coordinator state | `<tool namespace>/review-controller/<attempt-id>.json` (`:612`) | attempt id |
| Local receipt | `.build/sd-review/receipts/<identity>.json` | `_receipt_identity(target, plan)` (`review-local.py:2999`) |
| Local run dir | `.build/sd-review/runs/<attempt-id>/` | attempt id |

`--attempt-id` does not help: the receipt is keyed by a digest over target and plan, so a new
attempt id finds the same receipt and reuses it. Clearing the coordinator state alone does not
help either — the local stage re-reads its receipt and returns the same verdict.

Re-running the local stage into an existing attempt id with `--no-reuse` is also refused:

```text
attempt <id> already exists without a reusable exact receipt; reconcile it before retrying
```

## Evidence

Observed on PR #574 (2026-08-28), recovering from a poisoned verdict (see the related task).
Working the problem required: deleting the coordinator state file, then discovering the receipt
identity by reading `receiptId` out of the returned JSON, then running the local stage directly
with a fresh attempt id *and* `--no-reuse` so it would neither collide with the existing run
directory nor reuse the receipt. That rewrote the identity-keyed receipt with real evidence,
after which the coordinator behaved correctly. None of this is documented; it was derived by
reading the implementation.

## Requirements

- The coordinator accepts a reuse-bypass control and forwards it to the local stage.
- Using it re-runs the selected providers and overwrites the stored receipt for the same
  target identity, rather than requiring a fresh attempt id to avoid a run-directory collision.
- The refusal path stays intact for the case it protects: this control is an explicit operator
  request, never an automatic retry, and it does not weaken the round limit, the disposition
  requirement, or any gate. Re-running providers is not the same as re-deciding a verdict.
- Discarded evidence is reported, not silent: the run states what it invalidated.
- The three cache layers and their key derivations are documented where an operator working a
  stuck review will find them.

## Open question to settle during design

Whether reuse should be bypassed automatically when the stored verdict came from a provider
classified `unavailable`. If the related task lands first, a crashed provider never produces a
reusable verdict in the first place, which may make the automatic case unnecessary. Decide
explicitly and record the reasoning.

## Non-goals

- Changing where the local stage keeps its artifacts. The in-repo, git-ignored root is
  deliberate (`review.py:830-832`).
- A general cache-eviction or garbage-collection policy.

## Acceptance Criteria

- [ ] A coordinator invocation with the reuse-bypass control re-executes providers and returns
      a receipt whose creation timestamp is newer than the discarded one.
- [ ] The same invocation without the control still reuses a valid stored receipt.
- [ ] Bypassing reuse against an attempt id that already has a run directory succeeds rather
      than failing with the reconcile error.
- [ ] The cache layers, their locations, and their key derivations are documented.

## Related

- `.trellis/tasks/08-26-local-provider-failure-masked` — the defect that produced the
  verdict this task makes recoverable.

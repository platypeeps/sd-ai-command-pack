# `_aggregate_outcome` ranks findings above failure, so a failed provider never reaches the gate

## Problem

`templates/scripts/sd-ai-command-pack-review-local.py:2165` walks a fixed
precedence tuple:

```python
for status_value in ("findings", "failed", "unavailable", "cancelled"):
    if status_value in statuses:
        return status_value
```

`findings` is checked first. So a run where one provider returns findings and
another *fails outright* carries `outcome: "findings"`, and `_remote_gate`'s
`outcome in TERMINAL_FAILURES` branch never runs. The failed provider is
recorded in `limitations`, but the gate reports plain `eligible` rather than
`eligible-with-limitations`.

The receipt therefore contains the evidence that a provider failed and
simultaneously reports a verdict that says nothing did. A reader who trusts the
verdict — which is the whole point of a verdict — is misled by a receipt that is
internally complete.

## Why now

Pre-existing, and verified identical on `main` before the advisory ceiling
landed, so the ceiling did not cause it. What the ceiling changed is its
*reachability*.

Before, reaching `outstanding == 0` on a `findings` receipt required the caller
to disposition every finding by hand — a deliberate act, performed by someone
who had just read the receipt and would likely notice a dead provider. A
severity ceiling reaches that state with no caller act at all. The path opens
without anyone deciding to open it, which is an argument for fixing it promptly
rather than evidence that the ceiling introduced it.

Carried as follow-up 4b.3 in `08-24-local-gate-advisory-severity`.

## Requirements

1. A run in which any provider `failed`, `unavailable` or `cancelled` must not
   report an outcome that hides it, regardless of what the other providers
   returned.
2. Decide deliberately whether the fix is reordering the precedence tuple or
   replacing single-outcome aggregation with something that can express "found
   things *and* one lane died". Reordering is one line and makes `failed`
   dominate `findings`, which suppresses real findings in the outcome — the
   opposite error. A composite outcome, or a separate degraded flag the gate
   consults, is likely the honest shape. Choose, and record why.
3. Whatever shape is chosen, `eligible-with-limitations` must actually become
   reachable — it is currently dead code for this path.
4. Precedence must be asserted by test, not by reading the tuple. The current
   ordering looks intentional; nothing in the code says it is not.

## Acceptance criteria

1. A receipt with one `findings` provider and one `failed` provider reaches
   `eligible-with-limitations`, not `eligible`.
2. A receipt with one `findings` provider and no failures is unchanged.
3. The `TERMINAL_FAILURES` branch in `_remote_gate` is covered by a test that
   fails if the branch stops being reachable.
4. No existing gate outcome changes for runs where every provider succeeded.

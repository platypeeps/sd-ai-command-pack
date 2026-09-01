---
title: The review controller has never read remoteGate or familyGate
status: planning
parked: 2026-09-01 bulk-park (D2)
created: 2026-08-25
---
# The review controller has never read `remoteGate` or `familyGate`

## Problem

The controller normalizes a `findings` outcome to `clean` when
`outstanding == 0`, without consulting `remoteGate.state`. A
`sibling-audit-required` family gate is therefore not honoured: the receipt
carries the gate, and the controller decides as though it did not.

The scope is wider than a missed condition. Over
`templates/scripts/sd-ai-command-pack-review.py`:

```
$ grep -c 'remoteGate\|familyGate' templates/scripts/sd-ai-command-pack-review.py
0
```

Not one reference. This is not a branch that forgets a case — it is a channel
the controller has never read at all. The producing side computes and publishes
both gates; the consuming side does not know they exist.

## Why now

Same reachability argument as its sibling follow-up
`08-25-aggregate-outcome-masks-provider-failure`. Reaching `outstanding == 0`
used to require a caller to disposition every finding by hand; the advisory
severity ceiling reaches it with no caller act. A gate that was rarely consulted
because the state was rarely reached is now a gate that is routinely not
consulted in a state that is routinely reached.

Carried as follow-up 4b.4 in `08-24-local-gate-advisory-severity`.

## Requirements

1. Establish what `remoteGate` and `familyGate` are *supposed* to do to a
   controller decision before changing any behaviour. A channel that has never
   been read has never been exercised, so its intended semantics live in the
   producing code and in whatever documentation describes it — not in observed
   behaviour, of which there is none.
2. The audit must cover both gates and every controller decision point, not
   only the `outstanding == 0` normalization that surfaced this. That
   normalization is where it was noticed; there is no reason to think it is the
   only place.
3. Check whether any published documentation claims these gates are honoured. If
   it does, that is a second defect — a false claim about enforcement — and it
   must be corrected in the same change, not left for a reader to discover.
4. Decide whether honouring the gates changes any currently-passing consumer
   run. A gate that starts being enforced can newly block work that was
   previously allowed through; that is the correct outcome, but it must be a
   stated, deliberate consequence rather than a surprise in the fleet.

## Acceptance criteria

1. A receipt carrying `remoteGate.state: sibling-audit-required` does not
   normalize to `clean` on `outstanding == 0`.
2. `familyGate` is consulted wherever the audit finds it should be, with a test
   per decision point.
3. A test asserts the controller reads both channels, so the count above cannot
   silently return to zero.
4. Any documentation claiming these gates are enforced either becomes true or is
   corrected.

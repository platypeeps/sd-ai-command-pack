---
title: Write the advisory classification back to each finding, not only into the counts
status: done
created: 2026-08-24
branch: fix/advisory-classification-per-finding
---
# Write the advisory classification back to each finding, not only into the counts

## Goal

`_disposition_counts` decides, per finding, whether the severity ceiling
releases it as advisory — and then throws that decision away, returning only
counts (four of them since the accepted-disposition ground shipped):

```python
        elif disposition == "outstanding":
            if _is_advisory(item, ceiling):
                advisory += 1
            else:
                blocking += 1
    return blocking, advisory, dispositioned, accepted
```

`receipt.findings[]` still carries `disposition: "outstanding"` for both kinds.
So a receipt says *how many* findings the ceiling released and never says
*which*, even though the runner knew per finding at the moment it counted.

## Why it matters

- A reader reconciling a receipt against a review has to re-derive the
  classification by hand, re-applying the ceiling to every finding's severity —
  which means re-implementing `_is_advisory`, including its vocabulary rules and
  its rank-0 handling, in whatever is reading the receipt.
- The counts are a summary of a decision the receipt does not otherwise contain.
  If `_is_advisory` and a downstream reader ever disagree, nothing in the
  artifact reveals it.
- It blocks anything that wants to *act* per finding — surfacing only the
  blocking set in a summary, or letting a caller disposition exactly the
  findings that are actually holding the gate.

## Scope

Filed as follow-up **4b.5** from `08-24-prism-rules-flag-fleet-safe`, which
deferred it explicitly rather than widening that task. No ordering dependency in
either direction with `08-24-accepted-finding-disposition-ground`, though a
per-finding record is likely useful to it.

## Requirements

1. Each finding the ceiling releases is marked as such in `receipt.findings[]`,
   distinguishably from a finding that is outstanding and blocking, and from one
   dispositioned by the caller.
2. The counts and the per-finding records are produced from the same decision,
   not computed twice. A test should fail if they can disagree.
3. Receipt shape changes are policy changes: whatever field this adds flows into
   the digest that governs receipt identity, the same as any other policy
   change, rather than silently reinterpreting cached receipts.
4. Absent a configured ceiling, the receipt is byte-identical to today's. The
   existing suite passing unchanged is the check.

## Non-goals

- Changing which findings the ceiling releases. `_is_advisory` is not in scope;
  only whether its answer is recorded.
- Adding a new disposition ground. That is
  `08-24-accepted-finding-disposition-ground`.

## Acceptance criteria

- [ ] A receipt produced with a ceiling configured lets a reader partition
      `findings[]` into released, blocking, and dispositioned without applying
      any severity logic of its own — asserted by a test that reads only the
      finding records.
- [ ] A test fails if the per-finding records and the summary counts can
      disagree.
- [ ] With no ceiling configured, the existing suite passes unchanged and the
      receipt is byte-identical to today's.
- [ ] The added field appears in the receipt-identity digest, asserted by a
      test showing that adopting it changes the digest rather than reusing a
      cached receipt.

## Notes

- Planned on 2026-08-26: `design.md` and `implement.md` are written, and the
  host adversarial review ran against all three.

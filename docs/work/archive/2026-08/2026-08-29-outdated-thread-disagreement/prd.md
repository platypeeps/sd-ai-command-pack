---
title: Two thread readers disagree about outdated review threads and neither says so
status: done
created: 2026-08-29
branch: task/08-29-review-coordinator-correctness
---
# Two thread readers disagree about outdated review threads and neither says so

## Goal

Two evidence readers in the pack, reading the same pull request at the same
head about two minutes apart, report different unresolved-thread counts, and a
merge decision hangs on which one is right.

Reported as issue #590 from an `sd-work-backlog` run in
`platypeeps/se-ai-command-pack`, pack 0.71.62.

## Evidence

`sd-review`'s remote observation, at head
`0aab7366922c8a48743fd2acebef0aebee6d04ec`:

```json
"reviewThreads": {"fetched": 4, "items": [], "total": 4, "unresolved": 0}
```

`sd-ai-command-pack-pr-eligibility.py`, same head, about two minutes later:

```json
"reviewThreads": {"pageCount": 1, "totalCount": 4, "unresolvedCount": 2},
"reasonCodes": ["merge_blocked_conversation"],
"status": "blocked"
```

Both readings are correct under their own rule, and the rules differ.
At report time `sd-ai-command-pack-review.py` built its unresolved list as

```python
[row for row in threads if not row["resolved"] and not row["outdated"] and row["comments"]]
```

while `sd-ai-command-pack-pr-eligibility.py` counted `not node["isResolved"]`
and did not request `isOutdated` at all. The two threads in question were both
`isOutdated: true` — Copilot comments left against earlier heads whose findings
had since been addressed in the diff.

`sd-ship` sequences the two readers back to back: Stage 2's review loop
finishes clean on the first reading, and Stage 3's watch coordinator
immediately reports `settled-blocked` on the second, which stops the chain and
leaves the pull request unmerged. The eligibility diagnostic then reads

```
PR #278 is mergeable with checks green but blocked; resolve 2 unresolved review thread(s), then re-run
```

which sends an operator hunting for a new finding that Stage 2 has just
reported as clean.

## Decision

Neither rule changes. They answer different questions and both answers are
right for the question asked: `sd-review` reports what a reviewer still has to
act on, and an outdated thread's finding is by construction no longer in the
diff; `pr-eligibility` reports what GitHub will let a merge do, and GitHub's
conversation-resolution requirement counts an unresolved thread whether or not
it is outdated. Making either adopt the other's rule would make it wrong about
its own subject.

The defect is that neither output says which rule it applied, so the
disagreement is invisible and reads as a contradiction. Both readers will
report the outdated count beside the unresolved count, and the eligibility
diagnostic will name it.

## Requirements

- `sd-ai-command-pack-pr-eligibility.py` requests `isOutdated` on its review
  thread query and reports, beside `unresolvedCount`, how many of those
  unresolved threads are outdated.
- A node missing `isOutdated`, or carrying a non-boolean, is rejected the same
  way an invalid `isResolved` already is. This reader fails closed on malformed
  evidence and that must not change.
- The `merge_blocked_conversation` diagnostic names the outdated share when it
  is non-zero, so the operator is told to verify and resolve rather than to
  look for a finding that is not there.
- `sd-ai-command-pack-review.py`'s observation reports the outdated count in
  its `reviewThreads` block. Its `unresolved` count and `items` list keep their
  current meaning and contents; the new field is additive.
- The rule each reader applies is stated in the code where it is applied, not
  only in this record.

## Acceptance Criteria

- [x] For a pull request with four threads of which two are unresolved and
      outdated, `pr-eligibility` reports `unresolvedCount: 2` and an outdated
      count of 2, and `sd-review`'s observation reports `unresolved: 0` with
      the same outdated count — the two outputs no longer have to be
      reconciled by hand.
- [x] The `merge_blocked_conversation` diagnostic for that pull request names
      the outdated threads.
- [x] A thread node whose `isOutdated` is absent or non-boolean is rejected by
      `pr-eligibility` with its existing invalid-node error.
- [x] Existing callers and receipts that read `unresolvedCount`, `totalCount`,
      `pageCount`, `unresolved`, `total`, or `fetched` keep working unchanged.

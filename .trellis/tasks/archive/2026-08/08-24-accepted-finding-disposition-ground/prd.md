# Add an accepted-finding disposition ground so a correct finding the repository declines can clear the gate

## Goal

`sd-review`'s local disposition vocabulary has a ground for *"this finding is
wrong"* (`rebutted`) and a ground for *"this finding is pointed at the wrong
place"* (`miscited`). It has no ground for **"this finding is right, and the
answer is still no."**

Without it, an accurate finding that the repository has deliberately accepted
has no honest disposition. Calling it `rebutted` is a false classification,
which requirement 1 of `08-24-local-gate-advisory-severity` forbids. Leaving it
undispositioned blocks the merge. The only remaining exit is a human
round-extension decision — the exact failure the advisory-ceiling work exists to
remove.

## Where this comes from

Measured on `platypeeps/sd-github-review`, task
`08-09-review-gate-advisory-convergence`, replaying its PR #70 sequence against
the gate shipped in 0.71.47.

Thirty-seven findings. The severity ceiling released 30 as advisory. All seven
survivors were verified against the checkout and **none is a defect in the
change**. Four were dispositionable with today's vocabulary — three `rebutted`,
one `miscited`. Applied against the same receipt with no provider
re-invocation:

```
"advisory": 30, "dispositioned": 4, "outstanding": 3
remoteGate: {"state": "blocked", "reason": "actionable-local-findings"}
```

The three that block:

| finding | why no ground fits |
| --- | --- |
| sd-github-review's workflow example, at the reviewer job's `permissions` block — the token grants write to a third-party container | True. It is a deliberate, documented decision; the surrounding comment narrows the grant specifically so the container cannot write durable receipts. |
| sd-github-review's workflow example, in the provider `env` block — empty API key vars for non-selected providers | True. Trivial impact, understood, not worth a change. |
| sd-github-review's consumer installer, where the settings block is re-serialized — `JSON.stringify` key-order sensitivity | Mechanism is real. Consequence is one redundant idempotent rewrite. |

That is criterion 6 of the upstream task, and it is the only one still unmet.

## Requirements

1. An accurate finding that the repository accepts — a deliberate design
   decision, or an observation whose consequence is not worth a change — must be
   dispositionable on that ground, distinctly from `rebutted` and from
   `miscited`.

2. The ground must not weaken the gate. `rebutted` and `miscited` are both
   checkable against the checkout: one asserts the claim is untrue there, the
   other asserts the cited location does not contain the described code. An
   accepted finding is checkable against neither, because the claim *is* true.
   Whatever substitutes for that check must make the acceptance visible and
   attributable rather than silent — a required reason string is the obvious
   candidate, but the design is open.

3. The disposition must survive into the receipt, so a reader can tell an
   accepted finding from a rebutted one and from one that never blocked because
   the ceiling released it. Today the receipt records disposition counts;
   whether the per-finding record carries the ground is part of this task's
   scope only insofar as the new ground needs it (see the related follow-up on
   `_disposition_counts`).

4. A ground this permissive is a standing risk: it can dispose of any finding,
   including a real defect. The task must decide, and record, whether that risk
   is bounded by policy (a required reason, a distinct receipt field, an
   `accepted` count surfaced separately in the summary) or left to the operator.
   Shipping it without deciding is not acceptable.

## Non-goals

- Changing the advisory severity ceiling. It works; 30 of 37 findings released.
- Anything about provider agreement. That non-convergence result is real and is
  recorded upstream, but a disposition ground does not address it.
- Filing the gate's `_aggregate_outcome` and controller `remoteGate` gaps —
  those are follow-ups 4b.3 and 4b.4 on `08-24-local-gate-advisory-severity`.

## Acceptance criteria

- [x] A `high` finding with a good citation, whose claim is true, can be
      dispositioned as accepted and stops blocking — asserted by a test, and
      paired in the same test with the same finding blocking when no
      disposition is supplied, so the release cannot be confused with the gate
      being weak.
      — `tests/test_review_stage.py:1916`
      `test_accepted_releases_a_high_finding_that_otherwise_blocks`. The pairing
      is genuine: the test asserts `remoteGate.state == "blocked"`,
      `reason == "actionable-local-findings"` and `severity == "high"` *before*
      the disposition, then `eligible` / `outstanding: 0` / `accepted: 1` after.
- [x] The accepted ground is distinct from `rebutted` and `miscited` in both
      the CLI grammar and the receipt, asserted by a test that would fail if
      accepted were implemented as an alias of `rebutted`.
      — `tests/test_review_stage.py:1951`
      `test_accepted_is_not_an_alias_of_rebutted_or_miscited`.
- [x] Whatever bound requirement 4 selects is enforced, not documented — a
      disposition that omits it is refused with a bounded error, not a
      traceback.
      — `tests/test_review_stage.py:2106`
      `test_accepted_grammar_requires_a_bounded_reason`. The bound requirement 4
      selected is a required, non-empty reason capped at `MAX_ACCEPTED_REASON`
      (500), plus a distinct `accepted` count and a distinct
      `local-findings-accepted` gate reason. Recorded in `design.md`.
- [x] `sd-review`'s public control list documents the new ground alongside
      `--local-disposition '<id>=rebutted'` and
      `'<id>=miscited@<path>:<line>'`.
      — `plugins/sd/skills/sd-review/SKILL.md:241` documents
      `--local-disposition '<stable-id>=accepted@<reason>'`, alongside rebutted
      (:213) and miscited (:226).
- [x] The `sd-github-review` PR #70 replay reaches `remoteGate: eligible` with
      the accepted findings dispositioned on the new ground and no human
      round-extension — which closes criterion 6 of
      `08-09-review-gate-advisory-convergence`. This is the acceptance test that
      motivated the task, and it runs in a different repository, so record it as
      external evidence rather than as a unit test here.
      — **MET 2026-08-25**, recorded in that task's PRD (now archived at
      `.trellis/tasks/archive/2026-08/08-09-review-gate-advisory-convergence/`
      in the consumer repo): `remoteGate: {"state": "eligible", "reason":
      "local-findings-accepted"}`, `outstanding: 0`, `accepted: 2`,
      `advisory: 3`, one provider attempt, no round-extension. Receipt
      `01bc26a47bed8804…`.
      **The criterion said "three accepted findings"; the replay accepted two.**
      The three is not wrong about anything that happened — it is the
      `outstanding: 3` of the *second* replay, which is the state this task was
      filed from. Between that replay and the third, 0.71.50 forbade
      `severityOverrides`, and one of the three was released by the advisory
      ceiling instead of needing a disposition. Two remained, both verified
      individually, both true, both fixed on `main` in PR #150, and both
      accepted on the frozen replay head with the fix named in the reason. The
      criterion's substance — eligible, on the new ground, no round-extension —
      is met; only its count was written before the ceiling change moved it.

## Notes

- Filed 2026-08-24 with `design.md` and `implement.md` unwritten and requirement
  4 open. Both were written before `task.py start`, and requirement 4 was
  settled there — bound by attributability rather than prevention. Shipped in
  0.71.51.
- Verified and archived 2026-08-25. Criteria 1–4 re-run at archive time:
  `.venv/bin/python -m unittest tests.test_review_stage -k accepted -v` →
  `Ran 6 tests in 5.296s / OK`. Criterion 5 is external and was verified by
  reading the consumer task's own record, not by re-running the replay.

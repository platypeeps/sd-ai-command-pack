# Design — accepted-finding disposition ground

## The shape of the change

A third caller-supplied ground, `accepted`, joining `rebutted` and `miscited`.
It parses through the same `--local-disposition` flag, lands on the finding in
the receipt, stops the finding blocking, and is counted separately from the
other two everywhere a count is written.

Everything below is in `templates/scripts/sd-ai-command-pack-review-local.py`.
The copies under `scripts/`, `plugins/sd/bin/`, and
`plugins/sd/machine-payload/scripts/` are byte-identical mirrors produced by
`make generate` — verified with `diff -q` at planning time — so the template is
the only edit site and the mirrors must be regenerated, never hand-edited.

## Requirement 4: what bounds a ground that can dispose of anything

This is the question the PRD says must be settled here, so it is settled first.

**Decision: bound it by attributability, not by prevention. A required reason
string and a separate receipt count. No cap.**

The argument that makes this safe is not that `accepted` is weak — it is that
it adds no power the operator did not already hold:

- `_parse_local_dispositions` states outright that the pack "never verifies it
  by reading the checkout — doing so would make the gate depend on worktree
  state the receipt cannot pin." Both existing grounds are already assertions
  taken on trust.
- So an operator who wants to wave a real defect through can do it today by
  writing `rebutted`. `accepted` does not open that door; the door is open.

What `accepted` changes is the *incentive*. Today the only way to clear a true
finding you have decided not to act on is to file a false classification —
which requirement 1 of `08-24-local-gate-advisory-severity` forbids, and which
destroys the receipt's value as a record. Giving the honest answer its own name
converts a lie into a signed statement. That is the whole safety case, and it
is a real one.

Two mechanisms carry it:

1. **A required reason.** Not optional, not defaulted. The operator states the
   ground in their own words and it is stored beside the finding. Free text is
   trivially satisfiable and this design does not pretend otherwise — the point
   is that the receipt names a decision and its stated basis, where today it
   would name a fabricated rebuttal.
2. **A separate count.** `accepted` is never folded into `dispositioned`. A
   reader, a downstream policy, or a future gate can count waivers without
   parsing findings. This is what makes a stricter policy *possible later*
   without inventing one now.

**Rejected: a configured cap** (e.g. max accepted per attempt, in
`.sd-ai-command-pack/review.json`). Three reasons. The codebase can justify no
particular number. The motivating acceptance test needs exactly three, so any
cap below three breaks it and any cap above three is decoration. And the
failure mode is backwards: a cap blocks a legitimate large batch of honest
acceptances while doing nothing about a single dishonest one.

**Rejected: verifying the acceptance against the checkout.** Same reason the
existing grounds do not — a receipt has to be replayable from its own contents.

## Grammar

```text
--local-disposition '<stable-id>=accepted@<reason>'
```

The `@` payload mechanism already exists for `miscited`, so this adds a
vocabulary member rather than a parsing mode. `remainder.partition("@")` splits
on the **first** `@`, so a reason may itself contain `@` and arrives whole.

The reason is subject to the same class of bound as a miscited path:

| bound | value | why |
| --- | --- | --- |
| required | non-empty | an optional reason is not a bound |
| max length | 500 | matches the miscited path bound; keeps the receipt bounded |
| control characters | refused (`ord < 32`) | receipt is JSON read by humans |
| `=` | refused, with its own diagnostic | see below |

`=` has to be refused, and refused *loudly*. `_parse_local_dispositions` splits
the argument with `value.rpartition("=")` — the **last** `=`. A reason
containing one silently moves the split point and the id absorbs
`...=accepted@<reason-prefix>`, so the failure surfaces as an unrelated
"unsupported disposition" complaint about a mangled id. `_reject_local_disposition`
already exists precisely to diagnose this trap for miscited paths; it gains the
matching `accepted` branch. Anything less makes a plain typo unreadable.

## Storage on the finding

```python
finding["disposition"] = "accepted"
finding["dispositionReason"] = reason
```

A distinct key, not a reuse of `dispositionCitation`. Sharing the field would
make `accepted` structurally indistinguishable from `miscited` in the receipt,
which is exactly what the second acceptance criterion forbids.

## Counting and the gate

`_disposition_counts` today returns `(blocking, advisory, dispositioned)` and
folds anything in `LOCAL_DISPOSITION_VALUES` into `dispositioned`. Adding
`accepted` to that set without further change would silently merge it with
rebuttals — the outcome this design exists to prevent. So:

- `LOCAL_DISPOSITION_VALUES` gains `accepted` (it is caller-suppliable).
- **`FINDING_DISPOSITIONS` does *not* gain `accepted`.** An earlier draft of
  this design added it, on the belief that it validates receipt findings. It
  does not. Its only use is `_parse_family_finding` (`:924`), which validates
  `--family-evidence` payloads — a different input path this task does not
  touch. Adding `accepted` there would silently widen the family-evidence
  grammar to a value nothing here designs, tests, or documents, and `:929`
  only bars a non-actionable finding from `outstanding`/`fix`, so an
  `accepted` family finding with `actionable: true` would validate and reach
  the family gate with no defined meaning. Local dispositions are checked
  against `LOCAL_DISPOSITION_VALUES` and nothing else, which is sufficient.
- `_disposition_counts` returns a **4-tuple** `(blocking, advisory,
  dispositioned, accepted)`, testing `accepted` **before** the
  `LOCAL_DISPOSITION_VALUES` membership branch so ordering cannot fold it.
- Both write sites gain the field: the initial receipt build and
  `_redispose_receipt`.
- `_remote_gate` gains `accepted: int = 0`. It does not block — that is the
  point of the task — and it takes a new **first** rung on the eligible
  ladder, ahead of `dispositioned`. See below; this is not a detail.

An accepted finding is *not* advisory. Advisory means the repository's severity
policy released it without anyone looking; accepted means someone looked and
signed. Keeping them in separate integers is what lets a reader tell those
apart, which is requirement 3.

### The eligible reason, which is where this nearly went wrong

`_remote_gate` does not emit a set of counts. It returns a single `reason`
chosen by a priority ladder, under a comment stating its purpose: "Report the
strongest claim the receipt actually supports, so a reader is never told
'clean' about a receipt that was released rather than empty."

```python
if dispositioned: return {"state": "eligible", "reason": "local-findings-dispositioned"}
if advisory:      return {"state": "eligible", "reason": "local-advisory-released"}
return                   {"state": "eligible", "reason": "local-stage-terminal"}
```

An accepted release with no new rung reports `local-advisory-released` or
`local-stage-terminal` — both false, and false in the flattering direction. In
the motivating replay, where four findings are *also* dispositioned, it would
report `local-findings-dispositioned` and the waiver would be invisible to any
reader who consults `remoteGate.reason` alone. That is exactly the silent
acceptance requirement 2 forbids.

So `accepted` takes the **first** rung:

```python
if accepted: return {"state": "eligible", "reason": "local-findings-accepted"}
```

First, not last, and the ladder's own comment is the argument. The rung that
matters most is the weakest release ground, because that is the one carrying
risk. A rebuttal says the finding was not real. An advisory release says policy
did not care. An acceptance says it is real, it stands, and someone signed for
it. Ordering that behind the other two lets the better news mask the worse.

## Compatibility

- **Additive to the receipt.** Existing readers see a new integer and a new
  optional finding key. Nothing is renamed or removed.
- **One trap for readers**, and it is worth writing down: a reader that wants
  "how many findings were dispositioned and therefore do not block" must now
  add `dispositioned + accepted`. Splitting the count is deliberate, but it
  means the old field no longer answers that question on its own.
- **Payload version bump required.** `templates/` is shipped payload and the
  release gate refuses a payload change without a manifest version bump
  relative to `origin/main`.
- **Interacts with `08-24-advisory-classification-per-finding`.** That
  follow-up wants `_disposition_counts` to stop returning bare integers. This
  task widens the tuple from 3 to 4 rather than restructuring, because
  restructuring is that task's scope. The widening is the smaller move and
  leaves it strictly easier, not harder.

## Test strategy

Against `tests/test_review_stage.py`, matching its existing disposition tests:

1. **Release paired with block.** One `high` finding, good citation, true claim.
   Asserted twice in one test: blocking with no disposition, `eligible` with
   `accepted`. Pairing is what proves the release came from the disposition and
   not from a weak gate.
2. **Not an alias.** A test that fails if `accepted` were implemented as
   `rebutted` — assert the receipt's `disposition` string, the presence of
   `dispositionReason`, the absence of `dispositionCitation`, and that the
   `accepted` count moved while `dispositioned` did not.
3. **The bound is enforced.** `accepted` with no `@`, with an empty reason,
   with an over-long reason, with a control character, and with `=` in the
   reason — each raising `ReviewInputError` with a bounded message, and the
   `=` case raising its *own* diagnostic rather than the generic one.

## External evidence

The fifth acceptance criterion — the `sd-github-review` PR #70 replay reaching
`remoteGate: eligible` — runs in another repository and cannot be a unit test
here. It is recorded as external evidence: the replay is run after the pack
ships, its receipt captured, and the result written back to criterion 6 of that
repository's `08-09-review-gate-advisory-convergence`, which is parked waiting
on exactly this.

# Design — a failed provider reaches the gate

## The shared outcome-vocabulary decision

`08-25-bookkeeping-successor-absent-router` is the same defect in a different
branch, so the vocabulary question is settled once here and cited there.

**`outcome` describes what the providers found. It is not a verdict, and no gate
may treat it as one.** The receipt already separates the two ideas and the gate
simply failed to read the second:

| field | question it answers |
|---|---|
| `outcome` | what did the providers report? |
| `confidence.limitations` | did any lane fail to report at all? |
| `remoteGate.state` | may this proceed? |

Every defect in this family comes from a gate consulting `outcome` alone and
inferring a verdict from it. The fix is never to overload `outcome` — that
breaks every consumer that switches on it, and it forces one string to answer
two independent questions. The fix is to make the gate read the second input
that already exists.

## This defect

`_aggregate_outcome` (`:2165`) returns the first match in
`("findings", "failed", "unavailable", "cancelled")`. `findings` wins, so a run
where one provider found something and another died reports `outcome:
"findings"`. `_remote_gate`'s `outcome in TERMINAL_FAILURES` branch (`:2477`)
never runs, and the gate returns plain `eligible`.

The receipt is internally complete and its verdict is wrong: the dead provider
is right there in `confidence.limitations` (`:2679`), computed from the same
attempts (`:2646`), and nothing consults it.

## The change

`_remote_gate` takes a new keyword-only `degraded: bool = False`, and the
terminal-failure branch becomes:

```python
if degraded or outcome in TERMINAL_FAILURES:
```

The two call sites reach the same fact from different places, because they are
in different situations:

- `:2669` builds the receipt. `limitations` is a local (`:2646`), computed from
  the same `attempts` the receipt records, so it passes `degraded=bool(limitations)`.
- `:2381` re-gates a *stored* receipt after applying dispositions. `attempts` and
  `limitations` are not in scope there; the persisted
  `confidence.limitations` is. It reads that.

Still one decision, not two: the second site reads the record the first site
wrote, rather than recomputing it. That is also the correct semantics — re-gating
must preserve the original run's degraded state, not re-derive it from data the
re-gate does not have.

A stored receipt with a missing or malformed `confidence.limitations` is read as
empty. That is not a hole: a run in which *every* provider died still reports
`outcome in TERMINAL_FAILURES` and is caught by the existing half of the branch.
Only the mixed findings-plus-failure case depends on the field, and that case
requires a receipt this same code wrote.

`_aggregate_outcome` is **not** touched. Reordering the tuple was the other
candidate and it is the opposite error: `failed` would dominate `findings`, so a
run that found real problems would report `outcome: "failed"` and the findings
would vanish from the summary. One line, wrong direction.

### Why not a composite outcome

It changes `outcome`'s value space, which is a receipt shape change with digest
consequences, and it asks every existing consumer to learn a new vocabulary in
order to express something two existing fields already express between them.

## Ordering

The branch is inserted where the existing terminal-failure check already sits,
which keeps two existing precedences intact:

- `outstanding` still blocks first. A degraded run with outstanding findings is
  `blocked` for `actionable-local-findings` rather than `local-review-limited`.
  Blocked is blocked; the stronger claim wins and the limitation is still in the
  receipt.
- The family gate still precedes it.

`local_policy == "required"` continues to turn the branch into `blocked` with
`required-local-review-failed`, so a required lane that dies is not merely
limited.

## Blast radius

`degraded` defaults to `False`, so any caller that does not pass it behaves
exactly as today. When every provider succeeds, `limitations` is empty and
`degraded` is `False` — acceptance criterion 4 holds by construction rather than
by test luck.

No receipt field is added, removed, or renamed. `policyDigest` is unaffected,
so cached receipts are not reinterpreted.

## Rollout and rollback

Behaviour-only change to one shipped script: manifest bump plus the four-copy
mirror sync (`make sync` → `make generate` → `fleet-candidate-check.py` →
`make generate`). Rollback is reverting the commit; the parameter is additive
and defaulted.

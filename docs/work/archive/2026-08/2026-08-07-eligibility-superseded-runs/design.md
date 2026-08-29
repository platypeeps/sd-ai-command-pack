# Design: discount superseded check runs in the merge-eligibility probe

Citations are to `templates/scripts/sd-ai-command-pack-pr-eligibility.py` at
this task's start; `scripts/` is its regenerated twin. Symbols, not lines, are
the durable anchor.

## Open questions from the PRD, resolved

### What identity groups rows, and what orders them

The probe's single query is `gh pr view --json ...,statusCheckRollup`
(`query_pr`). `gh` fixes the field selection for that JSON view, so the shape is
not ours to extend without changing transport. Verified against a live rollup
in this repository, a `CheckRun` row carries exactly:

```json
{"__typename":"CheckRun","completedAt":"...","conclusion":"SUCCESS",
 "detailsUrl":"https://github.com/<slug>/actions/runs/31834186847/job/94876658155",
 "name":"CI scope","startedAt":"...","status":"COMPLETED","workflowName":"Tests"}
```

There is no `checkSuite.workflowRun.databaseId` on this selection, so the
PRD's third candidate is unavailable without switching the probe to
`gh api graphql`. That is a transport change for a bug fix and is rejected:
R5 asks for no extra round-trip, and rewriting the query would put every other
consumer of `parse_pr` behind a new failure surface.

**Decision.** Identity is the pair `(workflowName, name)`. Order is `startedAt`,
parsed as ISO-8601. The repository floor is Python 3.10
(`pyproject.toml:5`, and the CI matrix runs 3.10 at
`.github/workflows/tests.yml:420`), and `datetime.fromisoformat` did not accept
a trailing `Z` until 3.11, so the timestamp is normalized with
`value.replace("Z", "+00:00")` first — the idiom already used at
`sd-ai-command-pack-work-loop.py:236` and
`sd-ai-command-pack-review-learnings.py:1130`.
The run ID embedded in `detailsUrl` is deliberately *not* used: parsing a
semantic key out of a display URL couples the verdict to a URL layout GitHub
does not contract, and relying on run-ID monotonicity to mean "newer" is an
assumption about ID allocation, not a documented ordering. `startedAt` is
already in the payload and already means what we need.

Both identity components are normalized before bucketing. `workflowName` is
absent on some non-Actions check runs and normalizes to `""`, which is already
what `parse_checks` reports for it. `name` is different: `parse_checks`
substitutes the placeholder `"unnamed"` for display, and bucketing on a
placeholder would collapse two unrelated nameless rows into one identity. A row
whose `name` is absent or not a string is therefore never bucketed at all — it
can neither be superseded nor supersede anything.

Matrix rows are handled by construction: the PRD's example pair
`test heavy (py${{ matrix.python-version }})` and `test heavy (py3.14)` are
different `name` values, so they are different identities and never collapse
into each other.

### Should `StatusContext` rows collapse the same way

No. A `StatusContext` carries `context` and `state` and no timestamp and no run
identity (`parse_checks`), so the rule cannot be expressed there without
inventing an ordering. Those rows keep today's behaviour exactly. This is
recorded as a scope boundary, not an oversight: the observed defect is a
`CheckRun` defect, and a legacy commit status has no concurrency group to be
superseded by.

### Does GitHub distinguish concurrency-cancelled from operator-cancelled

Not on this selection — `conclusion` is `CANCELLED` either way. R2 is therefore
satisfied by inference from a later sibling, which is the point of the rule:
an operator cancelling the only run leaves no later sibling, so that row keeps
blocking.

## The rule

A `CheckRun` row is **superseded** when all of the following hold:

1. its `conclusion` is `CANCELLED`;
2. another row in the same rollup has the same `(workflowName, name)`; and
3. that sibling's `startedAt` is strictly later than this row's `startedAt`.

A superseded row is excluded from `blocking`. It is never counted as
`successful`.

### Why the rule is restricted to `CANCELLED`

Branch protection evaluates the latest result per context name, so a stricter
reading would discount *any* older row. This design deliberately does not go
there. A superseded run can contain a job that genuinely `FAILURE`d before the
cancellation propagated, and discounting it would let the probe report eligible
on a head where something actually failed. Narrowing to `CANCELLED` cannot let
a real failure through: the observed defect is entirely about rows whose only
content is "this run was replaced".

`STALE` is not included. GitHub emits it for a check run it has itself marked
superseded, so it arguably belongs here under the same sibling guard, but no
rollup in this task's evidence carries one. Parked rather than guessed: add it
when a `STALE` row is actually observed, with the sibling requirement
unchanged.

The cost is a conservative false block in one shape — an older run whose row
`FAILURE`d while the newer run for the same name passed. That shape is not the
reported defect, blocks rather than admits, and is left to a follow-up if it is
ever observed.

### Strictly later, not later-or-equal

Ties do not supersede. Two rows with identical `startedAt` give no evidence of
ordering, and treating one as replaced by the other would be a coin flip that
can only ever loosen the gate.

### Missing versus malformed `startedAt`

The PRD constrains `parse_checks` to keep failing closed and calls a missing
field used by the new rule malformed input. Split by kind, matching how
`parse_checks` already treats `status` and `conclusion`:

- `startedAt` **present but not a string, or unparseable as ISO-8601** —
  malformed. Raise `EligibilityInputError`, exactly as a non-string `status`
  does today.
- `startedAt` **absent or `null`** — no evidence of ordering. The row is not
  superseded and stays blocking. This is the fail-closed direction: it can only
  keep a block, never create eligibility.

Both are evaluated lazily, only for identities that actually contain a
`CANCELLED` row. A rollup with no cancelled row reads no timestamp, so no
existing fixture and no existing caller can start failing on a field the old
code never touched.

## Evidence (R4)

`parse_checks` already emits an `observed` item per row. A superseded row gains
two fields:

```json
{"type": "CheckRun", "name": "CI Result", "status": "COMPLETED",
 "conclusion": "CANCELLED", "superseded": true,
 "supersededBy": {"index": 7, "startedAt": "2026-08-07T18:22:41Z"}}
```

`index` is the 1-based position already used in this function's error messages,
so a reader can find the superseding row in the same `items` array without a
second lookup. That citation is only meaningful because `parse_checks` appends
exactly one `observed` item per input row, in input order, for every row type —
`StatusContext` rows included. The invariant is load-bearing, so a test pins it
with a `StatusContext` sitting ahead of the superseded row.

Non-superseded rows gain nothing; `superseded` is absent rather than `false`,
so the receipt does not grow on the overwhelmingly common shape.

The block diagnosis is unchanged. `blockingCount` and `successfulCount` keep
their meanings and their positions in the receipt.

## What does not change

- The predicate at both merge sites (`blocking_checks != 0`) is untouched. R1
  narrows the population, not the rule.
- `successful_checks == 0` still returns `checks_no_success` at both sites,
  which is what satisfies R3 for free: a superseded row is never counted
  successful, so a rollup whose every row is superseded reaches the merge
  decision with `successful == 0` and is refused by the existing explicit
  reason, not by an empty blocking count.
- One GitHub query per probe on the path this task fixes. The rule is a second
  pass over a list already in memory.

  One secondary effect is worth stating: lowering `blocking` makes the existing
  `mergeStateStatus == "BLOCKED" and blocking_checks == 0 and
  successful_checks > 0` branch (`classify_non_clean_merge_state`) reachable on heads
  that previously fell through, and that branch runs `collect_threads`, a
  second `gh` call. It fires only while diagnosing an already-blocked pull
  request, never on the eligible path, and it produces a better diagnosis than
  the generic block it replaces. R5's no-extra-round-trip test therefore pins
  the eligible (`CLEAN`) path, which is the path the probe takes in the
  reported defect.
- `mergeStateStatus` diagnosis, review-thread collection, and the routed-review
  block are untouched.

## Compatibility

- Receipt schema: additive only. Consumers reading `checks.items` see two new
  optional keys on cancelled-and-replaced rows.
- Behaviour change, and the point of the task: a head that used to report
  `blocked ['checks_blocking']` now reports `eligible` when its only blocking
  rows were superseded cancellations. `sd-ship` Stage 3, `sd-housekeeping`
  eligibility, and `sd-fleet-refresh` `merge-eligibility` all inherit that,
  which is the intended blast radius.
- No consumer edits. The probe ships in the payload; consumers receive it
  through the normal fleet refresh.

## Failure modes considered

- **Every row cancelled, none superseded** (operator cancelled one run): no
  sibling, nothing discounted, still blocked. R2.
- **Every row superseded**: `successful == 0` → `checks_no_success`. R3.
- **Cancelled row whose sibling is also cancelled but later**: the earlier one
  is discounted, the later one still blocks. Correct — the live run's own
  cancellation is unexplained and must be looked at.
- **Cancelled row whose sibling is still `IN_PROGRESS`**: the sibling has a
  later `startedAt`, so the cancelled row is discounted and the in-progress row
  blocks on `status != "COMPLETED"`. The watch coordinator keeps polling, which
  is right.
- **Three generations of the same name**: max-by-`startedAt` per identity, so
  both older cancellations are discounted against the newest sibling.
- **Duplicate names across different workflows**: different `workflowName`,
  different identity, no cross-collapse.

## Rollback

Single commit revert. The rule reads no persisted state and writes none, so a
revert restores the previous verdict on the next probe with no migration.

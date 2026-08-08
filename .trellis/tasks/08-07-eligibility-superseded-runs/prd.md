# Merge eligibility counts superseded workflow runs as blocking

## Goal

Stop the merge-eligibility probe from blocking on check runs that belong to a
workflow run GitHub already superseded, so its verdict agrees with GitHub's own
`mergeStateStatus` instead of contradicting it.

The blocking rule itself is right and stays. What is wrong is the population it
counts: every row the rollup returns, including rows from runs that were
cancelled precisely because a newer run replaced them.

## Problem

> Citations are pinned to the merge commit `4378d37b`.
> `templates/scripts/sd-ai-command-pack-pr-eligibility.py` is 1507 lines and is
> byte-identical to this repository's installed `scripts/` copy, confirmed with
> `diff -q`. A bare `` `:NNN` `` means that file. Each citation names its
> enclosing symbol — re-locate by symbol, not by line, on any other version.

`parse_checks` walks the raw `statusCheckRollup` array and classifies each row
independently (`parse_checks`, `:463-480`):

```python
for index, raw in enumerate(value, start=1):
    ...
    if check_type == "CheckRun":
        status = raw.get("status")
        conclusion = raw.get("conclusion")
        ...
        if status == "COMPLETED" and conclusion == "SUCCESS":
            successful += 1
        elif status != "COMPLETED" or conclusion not in {
            "SKIPPED",
            "NEUTRAL",
        }:
            blocking += 1
```

`CANCELLED` is neither `SUCCESS` nor in the `{SKIPPED, NEUTRAL}` allow-list, so
it increments `blocking`. Both merge paths then refuse on any nonzero count
(`:956-961` and `:1303-1308`, identical shape):

```python
if blocking_checks != 0:
    return finish(
        "blocked",
        ["checks_blocking"],
        f"PR #{pr_number} has non-green checks; skipped auto-merge",
    )
```

Nothing between the query (`:561`, which requests `statusCheckRollup` as one
flat field) and that decision collapses rows by check name or filters by
workflow run. A name that appears twice — once from a superseded run, once from
the run that replaced it — is counted twice, and the superseded copy decides the
verdict.

### Why the rollup contains superseded rows at all

This is not a GitHub anomaly; it is the documented result of a concurrency
group. A repository whose CI cancels superseded in-progress runs on the same
ref — the shape `anomaly-metric-creator` uses, and a common one — will routinely
have a cancelled run and its replacement both attached to the same head. The
rollup reports both.

Branch protection resolves this correctly: it evaluates the latest result per
context name, which is why GitHub reported the pull request mergeable while this
probe reported it blocked.

### Observed on PR #360 (`platypeeps/anomaly-metric-creator`, 2026-08-07)

Marking the pull request ready for review triggered a new CI run, whose
concurrency group cancelled the in-flight run `31227464221`. Both then appeared
in the rollup:

| Check name | superseded run `31227464221` | replacing run |
| --- | --- | --- |
| `CI Result` (required) | `CANCELLED` | `SUCCESS` |
| `test` | `CANCELLED` | `SUCCESS` |
| `quick test` | `CANCELLED` | `SKIPPED` |
| `socket` | `CANCELLED` | `SUCCESS` |
| `Windows collection (advisory)` | `CANCELLED` | `SUCCESS` |

The two verdicts disagreed at the same instant:

```text
$ gh pr view 360 --json mergeStateStatus,mergeable
{"isDraft":false,"mergeStateStatus":"CLEAN","mergeable":"MERGEABLE"}

$ ... sd-ai-command-pack-pr-eligibility.py --dependency-pr-number 360 ...
status blocked | reasons ['checks_blocking'] | retryable False
```

No check had failed. Every check that ran to completion on the current run
passed, including the required `CI Result` context and both `test light
(py3.14)` and `test heavy (py3.14)` under the `full-ci` label.

The only escape was `gh run rerun 31227464221`, which re-ran the superseded run
purely so its rows would stop being cancelled. After it completed, the same
probe returned `status: eligible` with no reason codes, unchanged in every other
respect.

### Blast radius

The probe is not one command's private helper. It is the shared read for:

- `sd-ship` Stage 3, through the watch coordinator, which classifies the result
  into `settled-green` / `settled-blocked`; only `settled-green` continues the
  chain, so this stops a ship at the last stage before merge;
- `sd-housekeeping` eligibility, which recomputes the same result atomically as
  its merge gate; and
- `sd-fleet-refresh` `merge-eligibility`.

All three inherit the false block, and the watch coordinator's own contract
guarantees it will burn its full poll budget first: it keeps polling while any
row is non-`COMPLETED`, and cancelled rows *are* `COMPLETED`, so the loop
settles and only then reports blocked.

The failure is also silently self-inflicted by the pack's own flow. Both events
that add a superseded run here — marking the PR ready for review, and pushing
the finish-work bookkeeping commits — are steps `sd-ship` itself performs, so a
repository with a concurrency group is likeliest to hit this on exactly the runs
the pack drives end to end.

## Requirements

### Functional

- R1: a check run superseded by a later run of the same check name on the same
  head must not contribute to `blocking`.
- R2: a genuinely cancelled check with no successor — an operator cancelling the
  only run — must still block. Cancellation is not evidence of success, and this
  must not become a blanket `CANCELLED` allow-list.
- R3: `successful_checks == 0` must keep its meaning under whatever collapsing
  rule is chosen. A head whose only rows are superseded must not become
  "eligible" by having its blocking rows dropped and nothing left to fail on.
- R4: the observed-checks evidence the probe reports must let a reader see why a
  row was discounted, rather than silently omitting it.

### Non-functional

- R5: no additional GitHub API round-trip per probe. The watch coordinator polls
  every 20 seconds with a ceiling of `timeout-minutes × 3`; the fix must come out
  of the fields the existing single query already returns, or extend that one
  query.

## Constraints

- Do not relax the blocking rule at either merge site. R1 narrows the input
  population, not the predicate.
- `parse_checks` raises `EligibilityInputError` on malformed rows and must keep
  failing closed; a missing field used by the new rule is malformed input, not a
  reason to treat a row as superseded.
- Whatever identity is used for "same check", it must handle the matrix-template
  rows GitHub also returns — the rollup on PR #360 contained both
  `test heavy (py${{ matrix.python-version }})` and `test heavy (py3.14)`.

## Open questions (resolve in design)

- What is the correct supersession key? Candidates: latest `startedAt` /
  `completedAt` per check name, or per `(workflowName, name)`; or the
  `checkSuite.workflowRun.databaseId`, preferring the newest run per name. The
  first needs no query change but is a timestamp comparison; the third is
  explicit about what "superseded" means but must be confirmed available on the
  `statusCheckRollup` selection at `:561` before it can be used.
- Should `StatusContext` rows collapse the same way? They carry no run identity,
  only `context` and `state`, so the same rule may not express there — and the
  current code counts any non-`SUCCESS` state as blocking (`:495-498`).
- Does GitHub distinguish "cancelled by concurrency group" from "cancelled by an
  operator" in any field the query can select? If it does, R2 becomes a direct
  test rather than an inference from a later sibling row.

## Acceptance Criteria

- [ ] A rollup containing a `CANCELLED` row and a later `SUCCESS` row for the
      same check name yields `blocking == 0` and an `eligible` verdict, with the
      PR #360 rollup shape used verbatim as the fixture.
- [ ] A rollup whose only row for a check name is `CANCELLED` still yields a
      `checks_blocking` verdict.
- [ ] A rollup whose every row is superseded does not become eligible: it is
      refused by `checks_no_success` or an equivalent explicit reason, never by
      an empty blocking count alone.
- [ ] The probe's observed-checks evidence marks each discounted row, and a
      reader can tell which row superseded it.
- [ ] Probe count per invocation is unchanged: one GitHub query, asserted in
      test.
- [ ] `parse_checks` still raises `EligibilityInputError` for a row missing any
      field the new rule reads.

## Notes

- Source: shipping `08-06-server-traces-mypy-gate` on PR #360 in
  `platypeeps/anomaly-metric-creator`, 2026-08-07. `sd-ship` Stage 3 settled
  `settled-blocked` after 23 probes and stopped the chain one stage short of
  merge; the merge succeeded unchanged after `gh run rerun 31227464221` cleared
  the superseded rows.
- Distinct from `08-06-review-check-receipt-pinning` and
  `08-07-review-check-stale-cache`, which are the same underlying stale-cached
  `sd-check` defect in `sd-ai-command-pack-review.py`. That one caches a verdict
  too long; this one computes the wrong verdict from live data. The two were hit
  back to back on the same pull request and are easy to conflate.
- Complex enough to need `design.md` and `implement.md` before `task.py start`:
  the supersession key is a real design choice, and R2 and R3 are correctness
  constraints on either side of it.

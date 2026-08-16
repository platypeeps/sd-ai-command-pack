# Re-query a durable receipt that is still in flight

## Goal

Let `sd-review` observe a routed review finishing. Today the coordinator caches
the durable receipt while the dispatch is still in flight and never re-reads it,
so every routed review in a working consumer ends at
`remote-reconciliation-required` no matter how many times the attempt is rerun.

## Background

Found in `platypeeps/sd-github-review` on PR #86, the first pull request to run
against a fully installed durable lane. Reproduced at two heads with two
independent dispatches, so it is not a rare race.

The lane publishes its receipt Check Run when the route step begins, with
`dispatch.phase: "started"`, then rewrites it about three seconds later with
`dispatch.phase: "observed"` and a `completedAt`. Measured twice:
`21:51:30.633Z` to `21:51:34.172Z`, and `22:03:16.347Z` to `22:03:19.403Z`.

`scripts/sd-ai-command-pack-review.py` polls inside that window and keeps what
it finds:

- `:2133` — the receipt is queried only `if state.get("remoteReceipt") is None`,
  so a stored receipt is never refreshed.
- `:2136-2146` — the poll loop breaks on the first non-`None` result, whether or
  not that receipt is terminal.
- `:2153` — `_advance(..., "receipt", remoteReceipt=receipt)` persists it.
- `:2161` — a cached receipt whose `dispatch.phase` is `started` returns
  `indeterminate` with `remote-reconciliation-required`.
- `:2095` — the only branch that re-queries an existing receipt is the
  dispatch-*failure* path (`phase == "reconciliation-required"`), which this
  case never enters.

The result is a wedged attempt rather than a pending one. `sd-review/SKILL.md`
correctly tells callers to rerun the unchanged attempt while a receipt is
delayed; that instruction replays the cache forever.

No supported escape exists, which is worth stating because the obvious one looks
like it should work. A fresh `--artifact-root` does find the receipt —
`logicalDispatchId` is stable across controller state — and then fails
`durable receipt does not contain the current correlation id` (`:1221`), because
the correlation id is per controller state and lives only in the state a fresh
root discards. That failure is correct; it is also a dead end.

## Requirements

- Treat a stored receipt whose dispatch phase is non-terminal the same as a
  missing one: re-query it. The poll loop at `:2136-2146` is the natural place,
  so a receipt that becomes terminal within the existing poll budget is observed
  in the same invocation rather than on a later rerun.
- Non-terminal means `dispatch.phase == "started"` and nothing else.
  `not-started` is what a skipped `route: none` dispatch carries (`:1230-1236`)
  and must keep flowing straight to observation; `acknowledged` and `observed`
  are terminal.
- A dispatch whose `status` is `failed` is terminal-bad. Do not poll it; leave
  `:2161` to report it exactly as it does now.
- Keep the fail-closed behaviour intact. A receipt still non-terminal when the
  poll budget is exhausted must still report `remote-reconciliation-required`.
  This removes a permanent wedge, not the diagnostic.
- A re-query must never dispatch. `_query_receipt` is read-only and must stay on
  the query side of the `route-intent` branch at `:2111`.
- Do not widen receipt matching. `external_id == logicalDispatchId`, the
  correlation-id check, and the multiple-match error are what make a resume
  idempotent.
- A transient re-query returning `None` must not discard a receipt already
  stored.

## Acceptance criteria

- [x] A routed review whose receipt is first seen at `dispatch.phase: "started"`
      and becomes `observed` within the poll budget reaches a terminal state in
      that same invocation.
- [x] The same transition observed across two invocations of the unchanged
      attempt also reaches a terminal state, rather than replaying the cached
      non-terminal receipt.
- [x] A receipt that never becomes terminal still reports
      `remote-reconciliation-required`, and never falls back to a direct request.
- [x] A `route: none` receipt with `phase: "not-started"` still proceeds to
      observation and is not polled as if it were in flight.
- [x] Re-querying triggers no second dispatch for the same
      `logicalDispatchId`.
- [x] Regression coverage drives the real two-write shape the lane produces —
      `started` then `observed` — not a single terminal write.

## Closure

Shipped in PR
[#468](https://github.com/platypeeps/sd-ai-command-pack/pull/468), merged
`2026-08-16T01:02:28Z` into `main` (head `743b84a`, base `bc468b6`; 21 files,
+612/-63). The task record was left `in_progress` past the merge; this section
is the closure the merge should have carried.

Each criterion maps to a named regression test in
`tests/test_review_controller.py`, re-run against the current checkout:

| Criterion | Test | Line |
| --- | --- | --- |
| Settles in one invocation | `test_in_flight_receipt_is_polled_until_it_settles` | `tests/test_review_controller.py:1992` |
| Settles across two invocations | `test_in_flight_receipt_is_refreshed_by_the_next_invocation` | `tests/test_review_controller.py:2034` |
| Exhausted budget still reports | `test_in_flight_receipt_is_refreshed_by_the_next_invocation` (first half) | `tests/test_review_controller.py:2034` |
| `not-started` is not polled | `test_settled_receipt_phases_are_not_polled_again` | `tests/test_review_controller.py:2086` |
| No second dispatch | dispatch count asserted `1` in both in-flight tests | `tests/test_review_controller.py:1992`, `:2034` |
| Two-write shape driven | all four tests write `started` then a terminal phase | `tests/test_review_controller.py:1992-2130` |

```text
$ .venv/bin/python -m unittest tests.test_review_controller
Ran 47 tests in 8.209s
OK
```

The four criterion tests each report `ok` in that run. PR #468 additionally
records that with the fix reverted exactly the two wedge tests fail
(`(3, 'indeterminate') != (0, 'ready')`) while the two guard tests still pass,
which is the evidence that the coverage is load-bearing rather than incidental.

Consumer-side tracking named under Notes stays with
`platypeeps/sd-github-review`; this record closes the pack-side work only.

## Notes

The consumer-side evidence lives in the `platypeeps/sd-github-review`
repository, not this one: its backend spec for the consumer installer, under
the heading "The routed lane works; the client cannot observe it finishing",
plus its own task of the same slug as this one, which is the tracking record on
the consumer side. Until this ships, routed reviews there end at
`remote-reconciliation-required` and the limitation is reported rather than
worked around.

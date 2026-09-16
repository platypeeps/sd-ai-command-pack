# Design — spend cap and meter

## Approach

Two repositories, and the system half lands first. The reservation is a
library concern: the bound is reserved against the month's settled and
reserved rows in one transaction
(`2026-09-05-the-pack-runs-a-team-process-for-one-person/design.md:302-306`),
and only the library holds the transaction. sd:234 slice 8a builds that as
`local-sd-db/sd_db/ledger.py`: `reserve` takes the bound, `claim` and `settle`
close it with the real cost, `lose` records a call that never answered,
`release_orphans` sweeps reservations whose caller died, and `exposure` is the
month's settled plus reserved total the refusal names. The pack consumes those
six names and adds none, reaching them the way every other consumer does:
`library()` and `connect(sd_db, write=True)` in `bin/sd_handoff_rows.py`.
With no `sd_db` on the machine, an uncapped bill is dispatched as today and
a capped bill is refused by name ("no library to hold the reservation"),
fail-closed, in fallthrough and on a direct pick. Every reservation closes, one call per terminal
outcome of `run_provider`: `settle` with the usage the response carries;
`settle` at the bound whenever dispatch was launched and the answer carries
no usable usage, which includes a timeout, a post-send error and a `REFUSED`
raised after `client(...)` was called, because money may have been spent and
the cap counts what it cannot see at the ceiling; `lose` only on a proven
no-send, `NOT_RUN` and the `REFUSED` outcomes returned before the request is
built (preflight, consent, the missing program). The line is the `client`
call in `run_provider`: before it, `lose`; at or after it, `settle`. All of them in a
`finally` of the dispatch in `review`; a process that dies between the two leaves a row
that `release_orphans` sweeps at the next `review` start, before the chain is
built, so `exposure` is settled plus live reservations and a dead one holds
the cap for one run at most. The rejected alternative was a `reserve_call` in
`writes.py`, one function with the transaction inside it; rejected because a
reservation that cannot be released or settled separately leaves an orphan
holding the cap, and because that name has zero hits anywhere today.

The pack half is one call site. `reviewer_chain` and `pick` in
`bin/sd_registry.py` already carry `capped_bills` and the refusal text; the
comment above the parameter says "wiring it is a change to one call site". The
site is `review` in `bin/sd-review`, where the chain is built and where
`--provider` picks one entry. The reservation is taken after every exit
that dispatches nothing, preflight, `--explain`, `--dry-run` and a failed
check, and immediately before each real `run_provider`, one reservation per
attempt, so a fallthrough that tries two entries holds one at a time. The
API changes with it: `capped_bills` becomes `Mapping[str, str]`, bill name
to the exposure line the refusal renders ("$41.20 settled and $9.10 reserved
of $50 this month"), so the chain and the pick carry the month's total
without a second lookup; and a call whose bound would pass the cap while
exposure is still under it is the same outcome, `reserve` refusing with that
line, which `review` turns into a fallthrough entry or the direct-pick
refusal. Before dispatch, the bound is the request's estimated tokens times
`price.in` plus `max_tokens` times `price.out`, each price per million tokens
as `providers.yaml` states them, so the bound in dollars is
`(tokens_in * price.in + max_tokens * price.out) / 1_000_000`. The estimate
is taken over the exact serialized request body, `request_prompt` in
`run_provider` with the schema, material and output contract appended, not
`prompt` alone, and it is byte length divided by three: a margin over the
four-bytes-a-token rule of thumb, because non-ASCII and code-heavy input
tokenize denser. `price` and `max_tokens` are
optional in the registry schema and the price keys are not validated, so
slice 3 refuses by name, fail-closed, at registry read: a `url` entry on a
capped bill that lacks `price.in`, `price.out` or `max_tokens`, or whose
value is not a finite, non-negative number (`max_tokens` a non-negative
integer), is refused naming the entry, the key and the value, the way a
`start` entry on a capped bill is refused today; the same check runs on the
database-merged read, since rows can carry the same keys. That is an assumption, stated as one, and the
cap is best-effort to that extent: the vendor's tokenizer is not consulted,
an over-estimate refuses early rather than late, and a fixture with
non-ASCII input asserts the margin holds against the usage the answer
reports.

The meter is a reader over a recorded answer. `GET
https://www.minimax.io/v1/token_plan/remains` returns the five-hour and weekly
windows as percents (`current_interval_remaining_percent` and
`current_weekly_remaining_percent` per `model_remains` entry); the reader
writes both as `meter` rows, one per window, and fallthrough treats a zero
window as a capped bill. `meter:` is a field of the bill row (`Bill.meter`
in `bin/sd_registry.py`, `bills.minimax` in `providers.yaml`), not of a
provider entry, so the lookup is keyed through the provider's bill. The
value is today an arbitrary string, and a live `GET` with the operator's key
to whatever it names would let an edited registry send the key elsewhere.
So the destination is pinned: the reader accepts exactly the host
`www.minimax.io` and the path `/v1/token_plan/remains`, refuses any other
value naming the value and the pinned pair the way a `url` entry moved to
another host is refused today, follows no redirect, and sends only the
credential named by the `env` of a `url` entry billed to that bill. The
fixture is one recorded answer, taken by the owner with the operator's key,
landed as `tests/fixtures/minimax/token_plan_remains.json` in #1001; no test
calls the endpoint. A metered bill with no row, or whose newest row is older
than the five-hour window, is skipped and refused the same as a zero window,
naming the missing or stale reading: unknown is not uncapped.

## Decisions

- 2026-09-14, owner, decision note 1942: the meter, the cap and the audit are
  this item, not sd:10. Reversed by nothing short of reopening sd:10.
- 2026-09-16, this plan: the system reservation is sd:234 slice 8a's
  `ledger.py`, not a `reserve_call` here. Reversed if 8a lands under another
  shape; then requirement 1 is re-pointed, not rebuilt.
- 2026-09-16, this plan: the token estimate is the serialized request's
  byte length over three, best-effort. Reversed by a measured refusal of a
  call that would have fit, or a dispatched call that passed the cap.
- 2026-09-16, this plan: the meter destination is pinned to one host and
  path, and unknown or stale meter data is capped, not open. Reversed by an
  owner note naming a second metered vendor.
- 2026-09-16, this plan: the `SD_AUTHOR` clauses are cut, the `slice_base` and
  session `authors` clauses stay open. Reversed by an owner note.

## Risks

- The estimate over-refuses near the cap. Accepted: a refused review falls
  through to the next bill, and the run says why.
- Two concurrent calls race the reservation. Mitigated by the one-transaction
  rule in `ledger.py`; the second acceptance criterion is the test.
- The recorded fixture ages. Accepted: it asserts the reader, not the vendor.
- MiniMax is under recovery (`skills/sd-review/SKILL.md`, the recovery
  paragraph), so the meter cannot be exercised live until that clears. The cap
  comes first for that reason.

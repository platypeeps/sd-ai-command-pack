# Design — spend cap and meter

## Approach

Two repositories, and the system half lands first. The reservation is a
library concern: the bound is reserved against the month's settled and
reserved rows in one transaction
(`2026-09-05-the-pack-runs-a-team-process-for-one-person/design.md:302-306`),
and only the library holds the transaction. sd:234 slice 8a built that as
`local-sd-db/sd_db/ledger.py`, landed in `platypeeps/system` #406 at
`4b240d28`, which the pack's CI has pinned since #999. Its six names are a
state machine over `cost` rows, per the module's docstrings and sd:234's prd
(the claim paragraph, "the client claims the reservation in one transaction
just before the request goes on the wire"): `reserve` writes a `reserved`
row for the bound after one `BEGIN IMMEDIATE` check of the month's exposure
against the cap; `claim` moves `reserved` to `sending` in one transaction
just before the request goes on the wire, and refuses a row that is no
longer `reserved`; `settle` moves `sending` to `run` with the actual cost,
once; `lose` moves `sending` to `bound` at the full bound when the response
was lost, because the provider may have finished and billed it;
`release_orphans` deletes a dead owner's `reserved` rows and binds its
`sending` rows, and runs inside every `reserve`; and `exposure` is the
month's `run`, `bound`, `reserved` and `sending` rows as one sum, the total
the refusal names. A `reserved` row whose owner lives is the owner's,
however long: the ledger has no release verb for it, so the pack reserves
only where it can claim in the next statement. The pack consumes those six
names and adds none, reaching them the way every other consumer does:
`library()` and `connect(sd_db, write=True)` in `bin/sd_handoff_rows.py`,
each of which raises `RowsRefusal` for its fault, the missing library and
the connection that fails. On either fault an uncapped bill is dispatched
as today and a capped bill is refused by name, quoting the refusal
("no library to hold the reservation: ..."), fail-closed, in fallthrough
and on a direct pick; the acceptance criteria carry both faults for both
kinds of bill.

The pack's caller of the four transitions is `run_provider` in
`bin/sd-review`, at one point: for a `url` entry, once `request_prompt` is
built and immediately before `client(...)` is called, `reserve` takes the
bound and `claim` follows in the next statement, so the row is `sending`
when the request leaves. Every outcome before that point, `NOT_RUN`, the
`REFUSED` of a refused environment or a refused `review_material`, and a
`start` entry, happens before any row exists and touches the ledger not at
all. After `client(...)` returns, one call in a `finally`: `settle` with
the usage the response carries; `lose` when the answer carries no usable
usage, which is a timeout, a dropped connection, a post-send error, a
`REFUSED` raised after the call and a response without usage fields,
because money may have been spent and the cap counts what it cannot see at
the ceiling. A `reserve` refusal is a `REFUSED` outcome carrying the
exposure line, which fallthrough passes over and a direct pick reports. A
process that dies between `reserve` and `claim` leaves a `reserved` row
the sweep deletes; one that dies after `claim` leaves a `sending` row the
sweep binds; both at the next `reserve` on any bill by any process, and at
`review` start, which calls `release_orphans` once before the chain is
built, so a dead one holds the cap for one run at most. The rejected
alternative was a `reserve_call` in `writes.py`, one function with the
transaction inside it; rejected because a reservation that cannot be
released or settled separately leaves an orphan holding the cap, and
because that name has zero hits anywhere today.

The pack half is two call sites. `reviewer_chain` and `pick` in
`bin/sd_registry.py` already carry `capped_bills` and the refusal text; the
comment above the parameter says "wiring it is a change to one call site".
That site is `review` in `bin/sd-review`, where the chain is built and
where `--provider` picks one entry. The reservation's site is
`run_provider`, as above, and a preflight is no exception:
`provider_preflight` sends its synthetic prompt through `run_provider` and
`client(...)`, a billable request with the entry's `max_tokens`, so it
reserves, claims and settles like any other; only `--explain` and
`--dry-run`, which return before `run_provider`, and a failed check, which
exits before dispatch, touch the ledger not at all. One reservation per
attempt, opened and closed inside `run_provider`, so a fallthrough that
tries two entries holds one row at a time. The API changes with it: `capped_bills` becomes `Mapping[str, str]`, bill name
to the exposure line the refusal renders ("$41.20 settled and $9.10 reserved
of $50 this month"), so the chain and the pick carry the month's total
without a second lookup; and a call whose bound would pass the cap while
exposure is still under it is the same outcome, `reserve` refusing with that
line, which `review` turns into a fallthrough entry or the direct-pick
refusal. Before dispatch, the bound is the request's estimated tokens times
`price.in` plus `max_tokens` times `price.out`, each price per million tokens
as `providers.yaml` states them, so the bound in dollars is
`(tokens_in * price.in + max_tokens * price.out) / 1_000_000`. The estimate
is taken over one named thing, `request_prompt` in `run_provider`: `prompt`
with the schema, material and output contract appended, encoded as UTF-8,
the string handed to `client` and carried as the one message's content.
Not `prompt` alone, and not the JSON envelope `chat_completion` wraps it in,
whose `model`, `max_tokens` and `messages` keys are not tokens the vendor
bills; the tests measure the same string. It is that byte length divided by
three: a margin over the
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
https://www.minimax.io/v1/token_plan/remains` returns one `model_remains`
entry per plan, and the recorded answer carries two, `model_name` `general`
and `video`. The reader selects the one entry whose `model_name` is
`general`, the plan the text model draws from; that is an assumption,
stated as one, and the owner's live call in slice 4 confirms or reverses
it. The selection fails closed: no `general` entry, or more than one, and
the bill is capped naming the count and no row is written. Each of the two
fields, `current_interval_remaining_percent` and
`current_weekly_remaining_percent`, is validated before a row is written:
missing, not a number (a string, a boolean, NaN, an infinity) or outside 0
to 100, and the bill is capped naming the field and the value, and no row
is written for that answer; one edited copy of the recorded fixture per
case is the test. A good answer is written as two `meter` rows, one per
window, for every enabled entry billed to the bill (owner decision
2026-09-17, note 2694; `sample` keys a row by provider), and fallthrough
treats a zero window as a capped bill. `meter:` is
a field of the bill row (`Bill.meter` in `bin/sd_registry.py`,
`bills.minimax` in `providers.yaml`), not of a provider entry, so the
lookup is keyed through the provider's bill. The value is today an
arbitrary string, and a live `GET` with the operator's key to whatever it
names would let an edited registry send the key elsewhere. So the
destination is pinned as one origin and path: the scheme `https`, the host
`www.minimax.io`, no explicit port, and the path `/v1/token_plan/remains`.
Any other value is refused naming the value and the pinned four, the way a
`url` entry moved to another host is refused today; `http://` on the same
host is refused by the rule `refuse_cleartext` applies to a `url` entry
(`source:bin/sd_registry.py::refuse_cleartext`), and a fixture naming that
same-host `http://` value asserts no request is sent; the reader follows no
redirect. The credential is the bill's, not a provider's: a metered bill
names the environment variable holding its key in a `meter_env:` field
beside `meter:` on the bill row (`bills.minimax.meter_env: MINIMAX_API_KEY`),
validated as one name the way an entry's `env` is, and a bill with `meter:`
and no `meter_env:` reads, and is capped at the meter step naming the
missing field (owner decision 2026-09-17, note 2694: a reinstall never
rewrites the operator's `providers.yaml`, so a read-time refusal would
refuse every review after an upgrade until the file was hand-edited). On the
bill row rather than "the `url` entry billed to it" because the registry
lets several entries share one bill, an entry can be disabled or repointed,
and a credential chosen by registry order is a credential chosen by
accident; beside `meter:` rather than inside it because `meter` is a
shipped string the reader compares against the pin, and a map there would
change a shipped field's type for no gain. The order on each `review`
start is fetch, persist, classify: the `GET` runs first, a good answer is
written as the two rows before any window is read, and the classification
reads the rows just written, so a run never classifies on the reading
before its own refresh. A `GET` that fails writes nothing, says so in the
run's output, and the classification reads the newest prior rows, under
the rule below. `--explain` and `--dry-run` send no `GET` and classify on the
stored rows alone (owner decision 2026-09-17, note 2694). The fixture is
one recorded answer, taken by the owner
with the operator's key, landed as
`tests/fixtures/minimax/token_plan_remains.json` in #1001; no test calls
the endpoint. A metered bill with no row, or whose newest row is older
than the five-hour window, is skipped and refused the same as a zero
window, naming the missing or stale reading: unknown is not uncapped.

## Decisions

- 2026-09-14, owner, decision note 1942: the meter, the cap and the audit are
  this item, not sd:10. Reversed by nothing short of reopening sd:10.
- 2026-09-16, this plan: the system reservation is sd:234 slice 8a's
  `ledger.py`, not a `reserve_call` here; 8a landed at system `4b240d28`
  the same day, and the lifecycle above follows its names. Reversed by a
  change to those names; then the lifecycle is re-pointed, not rebuilt.
- 2026-09-16, this plan: the pack reserves and claims in `run_provider`,
  immediately before `client(...)`, and nowhere else, so no `reserved` row
  is ever the pack's to release. Reversed by a release verb in `ledger.py`.
- 2026-09-16, this plan: the token estimate is the serialized request's
  byte length over three, best-effort. Reversed by a measured refusal of a
  call that would have fit, or a dispatched call that passed the cap.
- 2026-09-16, this plan: the meter destination is pinned to one scheme,
  host, port and path, the credential is named on the bill row as
  `meter_env`, the reader selects the `general` entry, and unknown, stale
  or malformed meter data is capped, not open. Reversed by an owner note
  naming a second metered vendor, or by the owner's live call showing the
  text model under another `model_name`.
- 2026-09-16, this plan: the `SD_AUTHOR` clauses are cut, the `slice_base` and
  session `authors` clauses stay open. Reversed by an owner note.
- 2026-09-17, owner, note 2694: `meter:` without `meter_env:` reads and is
  capped at the meter step, not refused at read; `--explain` and `--dry-run`
  send no `GET` and read the stored rows; the rows name every enabled entry
  on the metered bill. Reversed by an owner note.

## Risks

- The estimate over-refuses near the cap. Accepted: a refused review falls
  through to the next bill, and the run says why.
- Two concurrent calls race the reservation. Mitigated by the one-transaction
  rule in `ledger.py`; the second acceptance criterion is the test.
- The recorded fixture ages. Accepted: it asserts the reader, not the vendor.
- MiniMax is under recovery (`skills/sd-review/SKILL.md`, the recovery
  paragraph), so the meter cannot be exercised live until that clears. The cap
  comes first for that reason.

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
six names and adds none. The rejected alternative was a `reserve_call` in
`writes.py`, one function with the transaction inside it; rejected because a
reservation that cannot be released or settled separately leaves an orphan
holding the cap, and because that name has zero hits anywhere today.

The pack half is one call site. `reviewer_chain` and `pick` in
`bin/sd_registry.py` already carry `capped_bills` and the refusal text; the
comment above the parameter says "wiring it is a change to one call site". The
site is `review` in `bin/sd-review`, where the chain is built and where
`--provider` picks one entry. Before dispatch, the bound is the prompt's
estimated tokens plus `max_tokens` at the entry's price, and the estimate is
byte length divided by four. That is an assumption, stated as one: the
library's own tokenizer is not consulted, because the cap is a ceiling on
spend and an over-estimate refuses early rather than late.

The meter is a reader over a recorded answer. `GET
https://www.minimax.io/v1/token_plan/remains` returns the five-hour and weekly
windows as percents; the reader writes both as `meter` rows, one per window,
and fallthrough treats a zero window as a capped bill. The fixture is one
recorded answer, taken by the owner with the operator's key; no test calls the
endpoint.

## Decisions

- 2026-09-14, owner, decision note 1942: the meter, the cap and the audit are
  this item, not sd:10. Reversed by nothing short of reopening sd:10.
- 2026-09-16, this plan: the system reservation is sd:234 slice 8a's
  `ledger.py`, not a `reserve_call` here. Reversed if 8a lands under another
  shape; then requirement 1 is re-pointed, not rebuilt.
- 2026-09-16, this plan: the token estimate is byte length over four.
  Reversed by a measured refusal of a call that would have fit, or a
  dispatched call that passed the cap.
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

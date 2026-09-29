---
title: sd bill cap sets or clears a bill's monthly ceiling
created: 2026-09-28
---
# PRD — sd bill cap

## Problem

The v2 Management mockup offers Cap on a bill, written as "no CLI: sd has no
verb for bill caps (bill.cap_usd_month, moonshot)" (ui-design, verb check of
2026-09-28). The ceiling exists: `providers.yaml` declares `cap_usd_month` per
bill, the registry loader types it (`source:bin/sd_registry.py::Bill`), and the
`bill` table carries the column. Setting one means editing the operator's
`providers.yaml` by hand; `sd providers configure --file` takes enabled flags
and role orders, not caps (its `--help` on 2026-09-28).

Enforcement of the cap is sd:788 (`2026-09-16-spend-cap-and-meter`). This item
is the verb that writes the number; it changes nothing about what a cap does.

## Requirements

1. `sd bill cap <name> <usd> [--json]` sets `cap_usd_month` on one bill and
   prints the bill row; `sd bill cap <name> --clear` removes it.
2. The verb writes the store the registry reads, so `sd providers list --json`
   shows the new cap on the next call with no restart. If the file stays the
   source, the verb edits the operator's file in place and keeps its comments.
3. An unknown bill is refused with the list of bills; a non-positive amount is
   refused.
4. `sd bill list [--json]` prints every bill with its cost basis, cap and the
   month's spend as the ledger sums it, so the cap can be read where it is set.
5. The mockup turns Cap on with the verb as built, and
   `designs/tools/collect-counts.mjs` regenerates `data/commands.js` (ui-design,
   `management.html`).

## Acceptance criteria

- [ ] `sd bill --help` lists `cap` and `list`.
- [ ] After `sd bill cap moonshot 20`, `sd providers list --json` shows
      `cap_usd_month: 20` on that bill; after `--clear`, the field is null.
- [ ] `sd bill cap nosuch 20` exits non-zero and names the bills.
- [ ] A comment in `providers.yaml` survives a cap write, if the file is the
      store.
- [ ] `designs/v2/commands.html` shows no cap declaration marked "no CLI".

## References

- ui-design `products/system/designs/v2/management.html` (`bill.cap`).
- `docs/work/2026-09-16-spend-cap-and-meter/prd.md` (sd:788), enforcement.
- `bin/sd_registry.py`, the loader and its `cap_usd_month` typing.

## Log

- 2026-09-28 created

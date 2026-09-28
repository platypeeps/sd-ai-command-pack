---
title: Snooze a Today or Health row until a time
created: 2026-09-28
---
# PRD — sd today snooze

## Problem

The v2 dashboard mockups (ui-design, `products/system/designs/v2`, verb check of
2026-09-28) offer Snooze on every non-ok Health row and on Today's status mail,
jobs, pull requests and repos. Every one of those declarations is off with the
reason "no CLI verb: sd has no snooze". The mockups write the command as
`sd now snooze <kind>:<id> --until 08:00`. The pack has no `now` group; `sd today`
is the group that owns the page, and it takes `--json` only (checked with
`--help` on 2026-09-28).

Without a verb, a row the operator has already seen stays red until the
underlying fact changes. The dashboard cannot offer "later" without inventing a
store of its own, which the design forbids: the page shows what the tool knows.

Row ids on those pages are `<kind>:<id>`. Kinds seen in the mockups on
2026-09-28: `rs`, `build`, `mcp`, `cred`, `attr`, `gone`, `mwt`, `br`, `dep`
(Health) and `mail`, `job`, `pr`, `ahead` (Today).

## Requirements

1. `sd today snooze <kind>:<id> --until <HH:MM | YYYY-MM-DDTHH:MM>` records a
   snooze for one row and prints the row it changed; `--json` returns the row.
   A bare `HH:MM` means the next such time, local.
2. `sd today snooze <kind>:<id> --clear` removes the snooze. A second `--until`
   replaces the first; neither form needs a prior state to succeed.
3. `sd today --json` carries `snoozed_until` on a snoozed row and leaves it out
   of the attention counts. The plain output lists snoozed rows under one line.
4. The snooze lives in the database, keyed by the row id, so the dashboard and
   the CLI read one store. The `state` table's `kind`, `key`, `resolved_at`
   shape fits; the design decides.
5. A snooze expires by itself. No job runs to clear it.
6. An unknown kind is refused, and the refusal names the kinds Today emits. The
   ids are the ones `sd today --json` prints, so a snooze can be scripted from
   that output.
7. The mockups update from `sd now snooze` to the verb as built, and the off
   reason goes; then `designs/tools/collect-counts.mjs` regenerates
   `data/commands.js` (ui-design, `health.html` and `today.html`).

## Acceptance criteria

- [ ] `sd today snooze --help` lists `--until` and `--clear`.
- [ ] After `sd today snooze job:<id> --until 08:00`, `sd today --json` shows
      `snoozed_until` on that row and the attention count is one lower.
- [ ] After the time passes, the row returns with no command run.
- [ ] `sd today snooze bogus:1 --until 08:00` exits non-zero and names the kinds.
- [ ] `designs/v2/commands.html` shows no snooze declaration with an off reason.

## References

- ui-design `products/system/commands.md`, "Verb check (2026-09-28)".
- ui-design `products/system/designs/v2/health.html` and `today.html`, the
  `snooze` command factories.
- `bin/sd_work.py`, where `sd today` is implemented.

## Log

- 2026-09-28 created

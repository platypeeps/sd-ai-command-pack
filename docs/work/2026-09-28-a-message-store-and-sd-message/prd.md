---
title: A message store, and sd message read and ack
created: 2026-09-28
---
# PRD — a message store and sd message

## Problem

Two v2 mockup pages act on mail. Today's Now ledger lists flagged status mail
with Acknowledge; Briefs lists the daily brief mail with Mark read and Ack.
All four declarations are off with one reason: "no CLI verb: the message store
is not built, so sd has no message group" (ui-design, verb check of 2026-09-28).
The mockups write `sd message ack <id>` and `sd message read <id>`.

Today the pages read Gmail on every load and remember nothing. A brief the
operator read yesterday looks like a brief that arrived this morning. The
intake that exists, `local-mail-intake` in the system repository, records
arrivals as headers in CSV and marks them delivered with `stamp`; that state is
per alias and nothing in `sd` reads it.

## Requirements

1. A message table in the database: one row per message an intake delivers,
   with the source, the external id, the subject, the sender, the received time,
   `delivered_at`, `read_at` and `acked_at`. The external id makes a second
   delivery a no-op. Delivery is the intake's bookkeeping; read and ack are
   the operator's, and nothing but an operator action sets them.
2. `sd message list [--unread] [--source <name>] [--json]` prints the rows.
3. `sd message read <id>` and `sd message ack <id>` stamp the row and print it;
   `--json` returns it. Both are idempotent, and ack implies read.
4. `sd message ack --all --source <name>` acknowledges what one source
   delivered, so a morning's briefs clear with one command.
5. One intake writes rows: `local-mail-intake` adds a row per arrival, and its
   `stamp` verb sets `delivered_at` and nothing else, so a delivered message
   is still unread on Today until the operator reads or acks it. Brief mail
   (`Brief:` subjects) enters through the same intake with its own source
   name.
6. `sd today --json` reads the unread and unacknowledged rows from the store,
   not from Gmail, and the Briefs page reads the same rows.
7. The mockups' declarations turn on with the verbs as built, and
   `designs/tools/collect-counts.mjs` regenerates `data/commands.js` (ui-design,
   `today.html` and `briefs.html`).

Out of scope: sending, replying, labelling or filing mail. The intake keeps
its rule of reading headers only.

## Acceptance criteria

- [ ] `sd message --help` lists `list`, `read` and `ack`.
- [ ] Delivering the same external id twice leaves one row.
- [ ] After `mail-intake.sh stamp`, the stamped rows carry `delivered_at` and
      still list under `sd message list --unread`.
- [ ] `sd message ack <id>` twice prints the same row and exits 0 both times.
- [ ] After an ack, `sd today --json` no longer lists that message.
- [ ] `local-mail-intake` tests still pass `TestNeverSends`.
- [ ] `designs/v2/commands.html` shows no message declaration with an off reason.

## References

- ui-design `products/system/designs/v2/today.html` (`mail.ack`) and
  `briefs.html` (`brief.read`, `brief.ack`).
- system `local-mail-intake/README.md`, "It never sends, replies, files or
  labels" and "Headers, not bodies".
- `bin/sd_work.py`, where `sd today` reads its rows.

## Log

- 2026-09-28 created
- 2026-09-28 review pass 1 (codex, advisory, addressed): `stamp` records
  delivery, not acknowledgment; mapping it to ack would hide new mail before
  the operator saw it. Requirements 1 and 5 separate `delivered_at` from
  `read_at` and `acked_at`.

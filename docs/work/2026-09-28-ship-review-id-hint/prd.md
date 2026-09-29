---
title: sd-ship names the command that allocates a no-item review ID
created: 2026-09-28
branch: docs/ship-review-id-hint
---

# PRD — ship-review-id-hint

## Problem

An itemless `sd-ship prepare` or `sd-ship merge` without `--review-id` refuses
with `review_identity_required`. The message says what is missing, and its
`next_action` says "Use the existing review ID, or explicitly allocate a record
for genuinely new work." It names neither how to find an existing ID nor the
command that allocates one.

The command is `sd-ship review --no-item --create-record --assert-new-work
--json`. It is written only in `skills/sd-ship/SKILL.md`. A caller who reads
the refusal must leave the tool to learn it.

Observed 2026-09-28 in rwbp-songs, on PRs #20 and #21: each itemless merge
cost a failed `merge`, a failed `prepare`, and a search of the skill before
the first working call.

The refusal is raised in two places with the same text:
`bin/sd-ship` (the `review_identity_required` refusal) and
`bin/sd_ship_no_item.py` (`run_no_item`). The second carries no `code` or
`next_action`.

## Requirements

1. The `review_identity_required` refusal's `next_action` names the allocation
   command verbatim: `sd-ship review --no-item --create-record
   --assert-new-work`.
2. It keeps the existing warning: allocating a new record is for genuinely new
   work, never to reset spent passes or discard history.
3. Both raise sites return the same `code`, `boundary`, `state` and
   `next_action`, from one definition.
4. If no command lists existing no-item records, the message says where the ID
   was printed (the `review_id` field of the `--create-record` result), not a
   lookup that does not exist.

## Acceptance

- A test runs itemless `prepare` and `merge` without `--review-id` and asserts
  the refusal's `next_action` contains `--create-record --assert-new-work`.
- A test asserts the two raise sites produce identical workflow fields.
- No change to what is refused; only the message and its fields change.

## Out of scope

- Allocating a record implicitly. The refusal exists so that a missing ID
  never allocates a fresh review budget.

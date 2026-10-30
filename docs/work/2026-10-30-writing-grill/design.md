---
title: A grill the author answers on the Writing page
created: 2026-10-30
item: sd:6700
branch: build/sd-252
---

# Design — writing-grill

The item's row holds status, progress and decisions; this page holds the shape.

## Problem

The only grill is the CLI one (`sd-next`), walked by AskUserQuestion.
The operator asked for a grill on a writing piece that the author answers in the dashboard (note #34636).

## Approach

Add no store, no route and no verb. Reuse three things that exist:

| Step | Reuses | What it does |
| --- | --- | --- |
| Grill | Fix (`POST /api/items/<id>/fix`), body `{"grill": "ask"}` | claude in herdr, in the piece's repository, reads the draft and writes 5 to 10 `question` notes on the piece: claims, audience, the one point, what to cut |
| Answer | Decisions (`POST /api/decisions/answer`) | Details walks the piece's open questions one at a time; each answer is a `decision` note `Ruling on note #N: ...` and resolves the question, as `sd task note --answers` does |
| Apply answers | Fix, body `{"grill": "apply"}` | claude edits the draft to follow each ruling and leaves the edit uncommitted |

`/api/writing` gives each piece `grill`: its open questions (note, text, options) and the count of its rulings.
Apply answers is off while a question is open or before any is answered; the server refuses it the same way.
The questions also list on Decide, since they are question notes.

Pack sd:6699 (Apply review) adds `{"apply": "adversarial"}` to the same Fix route.
The two branches touch the same lines of `fix_session.py`; whichever lands second merges them by hand.

## Acceptance criteria

- Grill on a piece with a draft starts claude in herdr on the grill prompt, in the piece's repository.
- `/api/writing` gives each piece its open questions, with options, and its count of rulings.
- Details shows the first open question; an option or typed answer posts `/api/decisions/answer`.
- Apply answers is off, on the page and the server, while a question is open or before one is answered.
- Grill on an item that is not a piece, or an unknown `grill` value, launches nothing.

## Failure table

| Step | State moved | Failure | Recovery | Test |
| --- | --- | --- | --- | --- |
| Grill | a herdr session; a comment note | herdr down | 503, nothing written | `test_fix_session` refusals |
| Grill | question notes, written by the session | session writes none | Details shows no question; press Grill again | manual |
| Answer | a decision note; the question resolved | stale revision | 409, the page reads again | `test_v2_decisions` |
| Apply answers | an uncommitted draft edit | a question still open | 400, no launch | `TheGrill` |

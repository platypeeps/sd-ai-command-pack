---
title: The ten-pass experiment on the code review point has a pass-log shape before its first pass
created: 2026-09-16
---

# PRD — ten-pass-experiment

## Problem

sd:777 carries sd:10 criterion 7, the ten-pass forward experiment on the code
review point. The criterion stands unchanged at
`2026-09-05-the-pack-runs-a-team-process-for-one-person/prd.md:1352-1358`:
the other vendor reviews the next ten code pull requests, each pass logs
accepted against rejected findings with severities and cost, and a recorded
decision keeps or removes the point. `WORKFLOW.md:139-141` still describes
the experiment. No pass log, no report and no decision exist, and nothing
says what one pass note looks like. Ten passes written ten ways cannot be
summed. The `cost` table that would supply each pass's cost holds 0 rows
today, so the cost field needs a query that is agreed before the first pass.

## Requirements

1. One pass is one plain-text note on sd:777 with the header and the seven
   fields below, in that order, so the report is a sum over ten notes of one
   shape. Each accepted finding's severity is on the note, not only the
   highest, because criterion 7 asks for each.
2. The cost field is copied from the one query below, and the `session`
   field names the row it was copied from. When no row exists, the field is
   the owner's estimate, marked `estimate`, with the reason the runner was
   not used; an unmarked number is a copied one.
3. The passes, the report and the decision are OWNER-ONLY. No lane runs a
   pass, writes a note, or decides. This item's pages fix the shape only.

## Acceptance criteria

- [ ] Ten code PRs have a logged other-vendor pass each, the report is a note
      on this item, and a decision note keeps or removes the code review point.
      A grep of bin/ and skills/ for a percentage that disables a review point
      still returns nothing.
- [ ] Every one of the ten notes carries a cost in USD copied from the query
      by its `session`, or the owner's estimate marked `estimate` with the
      reason the runner was not used. A note with neither is not a logged
      pass and does not count toward ten.

## Pass note template

One note per pass, plain text: a header line `pass N of 10`, then seven
fields, one per line, every field filled or `none`. Severity values are the
review schema's, `source:bin/sd-review::SEVERITIES`: `high`, `medium`,
`low`, `unspecified`; `none` means no finding was accepted.

    pass N of 10
    PR: #<number>
    head sha: <40 hex>
    reviewer entry: <registry name, e.g. codex>
    session: <the runner session identifier, the value of cost.pass; or none>
    findings accepted / rejected: <A> / <R>; accepted: <one severity per accepted finding, e.g. high, low, low>
    highest severity accepted: <high|medium|low|unspecified|none>
    cost in USD: <usd from the query row whose pass equals session; or estimate <usd>, and why the runner was not used>

## Cost query

Read-only. `cost.pass` is the reviewer session's identifier and
`cost.assignment` is the assignment row it ran under (the `run` row that
`sd_db/runner.py` writes: one session is one pass). Run it as
`sqlite3 -readonly -header ~/.local/share/sd/sd.db` and copy `usd` from the
row whose `pass` equals the note's `session`. The note carries that value so
a later reader selects the same row.

    SELECT c.pass, c.timestamp, c.provider, c.source, a.item, a.role, a.status,
           c.tokens_in, c.tokens_out, c.usd
    FROM cost AS c
    JOIN assignment AS a ON a.id = c.assignment
    WHERE a.role = 'reviewer' AND c.source = 'run'
    ORDER BY c.pass, c.timestamp;

Measured 2026-09-16 against the live store, read-only: 0 rows. A pass whose
review ran outside the runner writes no `cost` row; its note carries the
owner's estimate marked as one, with the reason the runner was not used, and
the report keeps estimated and copied costs apart.

## References

- sd:777 body, and sd:10 criterion 7 as cited above.
- `skills/sd-review/SKILL.md:121-123`: MiniMax and Kimi are under recovery,
  and a single-provider `claude-json` review is the temporary mitigation.

## Log

- 2026-09-16 created. Two of the item body's citations moved on main: the
  criterion 7 row is now at
  `2026-09-05-the-pack-runs-a-team-process-for-one-person/implement.md:1850`
  and the 2026-09-07 log entry at
  `2026-09-05-the-pack-runs-a-team-process-for-one-person/prd.md:5167-5198`;
  the claims hold at both.

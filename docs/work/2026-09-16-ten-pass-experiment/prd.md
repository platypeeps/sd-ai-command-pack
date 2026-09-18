---
title: The ten-pass experiment on the code review point has a pass-log shape before its first pass
created: 2026-09-16
item: sd:777
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
summed. The `cost` table that would supply each pass's cost held 0 rows on
2026-09-16, and 0 `run` rows on 2026-09-17, so the cost field needs a query
that is agreed before the first pass.

## Requirements

1. One pass is one plain-text note on sd:777 with the header and the seven
   fields below, in that order, so the report is a sum over ten notes of one
   shape. Each accepted finding's severity is on the note, not only the
   highest, because criterion 7 asks for each.
2. The cost field is copied from the one query below, and the `session`
   field names the row it was copied from. When no row exists, the field is
   the owner's estimate, marked `estimate`, with the reason the runner was
   not used; an unmarked number is a copied one, and a note whose `session`
   is `none` must use the `estimate` form.
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

One note per pass uses a `pass N of 10` header and seven required fields.
A replacement adds `supersedes note: <id>` directly after the header.
`PR`, `head sha` and `reviewer
entry` are never `none`; a note missing one of them is not a logged pass and
does not count toward ten, whatever its cost field says. `none` is allowed
only where a field's own line says so: `session` when no runner row exists,
the accepted severities and the highest severity when no finding was
accepted, and the cost field never.
Severity values are the review schema's, `source:bin/sd-review::SEVERITIES`:
`high`, `medium`, `low`, `unspecified`; `none` means no finding was accepted.

    pass N of 10
    PR: #<number>
    head sha: <40 hex>
    reviewer entry: <registry name, e.g. codex>
    session: <the runner session identifier, the value of cost.pass, the key that selects the cost row; or none when no runner row exists>
    findings accepted / rejected: <A> / <R>; accepted: <one severity per accepted finding, e.g. high, low, low; or none when A is 0>
    highest severity accepted: <high|medium|low|unspecified|none>
    cost in USD: <usd from the query row whose pass equals session; or estimate <usd>, and why the runner was not used; the estimate form is required when session is none>

## Cost query

Read-only. The query joins `cost` to `assignment` on `a.id = c.assignment`,
the assignment row the reviewer session ran under (the `run` row that
`sd_db/runner.py` writes: one session is one pass). It does not join by
`pass`: `cost.pass` is the reviewer session's identifier, selected and
ordered only, and the note's `session` field is what matches it. Run it as
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
the report keeps estimated and copied costs apart, with no combined total
over the ten.

## References

- sd:777 body, and sd:10 criterion 7 as cited above.
- `skills/sd-review/SKILL.md:121-123`: MiniMax and Kimi are under recovery,
  and a single-provider review naming the registry entry whose `reader` is
  `claude-json` is the temporary mitigation. `claude-json` is a reader, not a
  reviewer entry: the entry is `claude` (`providers.yaml`, the `providers`
  map), and that is the name a note's `reviewer entry` field would take.
  Such a review is not a pass of this experiment: the owner named Codex the
  other vendor on 2026-09-17 (`design.md`, Decisions), so only a `codex`
  review counts.

## Log

- 2026-09-16 created. Two of the item body's citations moved on main: the
  criterion 7 row is now at
  `2026-09-05-the-pack-runs-a-team-process-for-one-person/implement.md:1850`
  and the 2026-09-07 log entry at
  `2026-09-05-the-pack-runs-a-team-process-for-one-person/prd.md:5167-5198`;
  the claims hold at both.
- 2026-09-17 lane, sd:777 note 2602's six page findings from #991's
  verification review at 94aab556: `PR`, `head sha` and `reviewer entry` are
  mandatory; the `session` line names the row it selects; the cost query
  prose says the join is on `assignment` and the match is by `pass`;
  `claude-json` is a reader and the entry is `claude`; `design.md`'s reversal
  clause gained a re-record rule; `implement.md` step 4 keeps each cost's
  marker and forbids a combined total. Step 1 ticked (#991 merged as
  e2810a6f). Step 6 re-run at ea32e76a: 34 lines, was 33 at 2eafa78b, none
  disables a review point; the drift is itemised at `implement.md` step 6.
  Cost query re-run 2026-09-17, read-only: 0 rows; the `cost` table holds
  three `meter` rows and no `run` row. Planning review, host lane once: one
  blocking finding, the accepted-severities sub-list had no value at zero
  accepted, fixed on the template line; ten non-blocking, all addressed.
  Copilot round on #1023 at dcc6a954, two findings folded: step 3 names
  the `estimate` form, and the Problem's row count is dated. Verification
  round at c012a736, one finding folded: the re-record rule names the
  counted set, current notes only, a superseded note excluded by id.
- 2026-09-17 owner: the other vendor is Codex. `design.md` records it as a
  decision and drops the risk that summed Codex with a recovered vendor;
  implement step 2's note on sd:777 is still to be written.
- 2026-09-17 owner: the decision note naming Codex is on sd:777, so the
  note the previous entry called still to be written exists; implement step
  2 is ticked.

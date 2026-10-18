---
name: sd-next
description: Use when the operator asks for status or "what next" across all their work: done recently, landing soon, open items and followups, and numbered next steps to pick from.
---

# sd-next

`sd-next` answers "what is done, what lands next, what is open, what do I do now" across every repository.
It is the one home of the operator's status format; other skills and docs point here.
`sd-status` is a different question: where the one repository you stand in stands.

## Steps

1. Run `sd today | head -80`. It is read-only and derives every section from the shared database, the lane and the gate queue.
2. Add what only this session knows:
   - the builders and agents running now, from `ListAgents` where the harness has it, with each one's item and budget;
   - followups and decisions this session raised that no `sd task note` holds yet, each marked "not filed".
3. Answer in the format below, and stop.

## Format

Four sections, in this order, with at most five rows each.
Where a section holds more, end it with "N more in `sd today`".

1. **Done recently**: from `Delivered`. Each row names the item, the PR number and the merge commit, or says "closed" when no PR merged.
2. **Landing soon**: from `Landing now`, `Gate slots` and the running builders. Each row names the item, the repository, the state and the queue position. A failed entry is an open item too.
3. **Open items and followups**: reports needing attention, decisions waiting (with the note id `--answers` takes), open followups, blocked items with whom they wait on, and this session's unfiled followups.
4. **Next steps**: a numbered list the operator picks from by number. Put the recommended step first and mark it. Each step names its item and one action, and a duration ("about 20 minutes") or a delivery time ("by 15:00 MDT"). Draw the steps from decisions waiting, failed lane entries, `Planned` (soonest first) and `Unscheduled` (highest priority first).

Write each time in the machine's local zone with its label; convert UTC first.
Keep each sentence short and plain, in simple tenses. Add no preamble and no closing summary.

## Never

- Never say "none" for a section `sd today` printed as `unknown`; say it is unknown.
- Never list more than five rows in a section; the rest stay in `sd today` and the dashboard.
- Never invent an item number, a PR number or a commit; copy them from the output.
- Never write from here: filing a followup or answering a decision is a separate, named step.

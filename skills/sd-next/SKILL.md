---
name: sd-next
description: 'Use when the operator asks for status, "what next", recommendations, followups or "what do you need from me" across all their work: done recently, landing soon, open items, numbered next steps, then the waiting questions one at a time.'
---

# sd-next

`sd-next` answers "what is done, what lands next, what is open, what do I do now, what do you need from me" across every repository.
It is the one home of the operator's status format; other skills and docs point here.
`sd-status` is a different question: where the one repository you stand in stands.

## Steps

1. Run `sd today | head -120`. It is read-only and derives every section from the shared database, the lane and the gate queue.
2. Collect what only this session knows:
   - the builders and agents running now, from `ListAgents` where the harness has it, with each one's item and budget;
   - this session's open threads: recommendations not acted on, followups and questions no `sd task note` holds yet, and commits or worktrees not landed (`git status`, `git log origin/main..`, `git worktree list`).
3. Answer in the format below.
4. Walk the waiting questions, then stop.

## Format

Use the tables `sd today` prints: a heading `<Section> (<count>)`, a header row, a rule, aligned columns, at most five rows, then `… N more`.
Copy rows from `sd today`; do not rewrite them as prose. Give five sections, in this order:

1. **Done recently**: the `Delivered` table and its `+N closed by hand` line. Its When column is the local time each change landed.
2. **Landing soon**: the `Landing now` table and the gate line, with the running builders added as rows. Position and the time each entry started or was queued come from the table. The lane records no ETA; do not invent one.
3. **Open items and followups**: the `Attention`, `Decisions`, `Blocked` and `Followups` tables, with the `+N review questions wait` line under `Decisions` when `sd today` prints one.
4. **This session**: one table of the threads from step 2, with the columns ID (the item, or `-`), Repo, State (`unfiled`, `filed`, `unlanded` or `running`), Title and When.
5. **Next steps**: a numbered list the operator picks from by number. Put the recommended step first and mark it. Each step names its item with its repo (`system sd:5103`, not a bare `sd:5103`) and one action, and a duration ("about 20 minutes") or a delivery time ("by 15:00 MDT"). Draw the steps from decisions waiting, failed lane entries, `Planned` (soonest first), `Unscheduled` (highest priority first) and this session's threads.

Write each time in the machine's local zone with its label; convert UTC first.
Keep each sentence short and plain, in simple tenses. Add no preamble and no closing summary.

## Waiting questions

After the answer, take the operator through the waiting questions, oldest first: the `Decisions` rows, then this session's unfiled questions.
Skip review questions: `sd today` leaves a review batch's questions out of `Decisions` and counts them in its `+N review questions wait` line, as the operator labels them on the dashboard's Review page.

1. File an unfiled question first: `sd task note N $'<question>\nOption: <a>\nOption: <b>' --kind question`.
2. Ask one question per `AskUserQuestion` call. Give its context in one or two lines, and put your recommended option first, marked "(Recommended)".
3. Record each answer at once: `sd task note N "<ruling>" --kind decision --answers <note>`.
4. Stop when the operator says stop, or when no question waits.

In a run with no operator present, skip this walk; the questions wait on the dashboard.

## Never

- Never say "none" for a section `sd today` printed as `unknown`; say it is unknown.
- Never list more than five rows in a section; the rest stay in `sd today` and the dashboard.
- Never invent an item number, a PR number, a commit or a note id; copy them from the output.
- Never write anything but the question and decision notes of the walk above.

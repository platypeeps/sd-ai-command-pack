# sd-retro: debug retrospective capture

## Problem
Debug retrospectives happen ad hoc (the July guard bug got one informally)
— root causes and gate-miss analysis evaporate instead of becoming
prevention tasks and learnings.

## Goal
`/sd:retro` composes a structured retrospective (what broke, root cause,
why gates missed it), records it as a journal entry via the session
recorder, and proposes consent-gated prevention tasks.

## Requirements
Contract per parent design § sd-retro: evidence gathering from session/
journal/git, fixed retro shape, recorder-based journal entry (`Retro:`
title), prevention proposals never auto-created, no code changes,
mandatory report with journal reference.

## Acceptance Criteria
- [ ] Skill + adapters + manifest wiring installed and tested.
- [ ] Format tests pin the retro shape, recorder usage, and consent gate.
- [ ] Guide + README document it.

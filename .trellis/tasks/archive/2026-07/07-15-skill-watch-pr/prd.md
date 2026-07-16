# sd-watch-pr: PR settle watcher + gated handoff

## Problem
The settle-then-merge pattern (poll checks + reviewer + threads, then run
the housekeeping gate) was hand-rolled five times in the 2026-07-15
session. It is stable, mechanical, and safety-critical enough to deserve a
tested, distributed command.

## Goal
`/sd:watch-pr` watches the current branch's open PR to a settled state and
hands off to the sd-housekeeping gate (or reports blockers), never merging
outside that gate.

## Requirements
Contract as specified in the parent design (07-15-sdlc-skill-expansion
design.md § sd-watch-pr): bounded loop, `timeout-minutes=` and `no-merge`
args, settle definition, blocker reporting, housekeeping as sole merge
authority, mandatory scannable report.

## Acceptance Criteria
- [ ] Skill + 4 adapter surfaces + manifest wiring installed and tested.
- [ ] Format tests pin sections, args, "never merges directly", and the
      housekeeping handoff.
- [ ] Guide + README document it.

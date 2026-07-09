# File Upstream Trellis Issues Implementation Plan

## Execution Order

1. Start only after `07-06-close-fleet-refresh-loop` records the R4
   duplicate-session root-cause decision.
2. Refresh live upstream issue state:
   - `gh issue view 394 --repo mindfold-ai/Trellis`
   - `gh issue view 395 --repo mindfold-ai/Trellis`
   - `gh issue view 396 --repo mindfold-ai/Trellis`
   - `gh issue view 397 --repo mindfold-ai/Trellis`
3. For issue 5, branch by the R4 result:
   - Trellis-owned: sanitize
     `upstream-issue-5-journal-duplicate-session.md`, file it as a GitHub
     issue, and record the URL in the PRD.
   - pack-owned: update the draft and PRD to say issue 5 was rerouted, then
     link the local task or PR that owns the fix.
   - inconclusive: append a dated parked note naming the missing evidence and
     leave issue 5 unfiled.
4. Update superseded pack task PRDs with one-line references:
   - platform registry task references issue #396;
   - housekeeping/recorder robustness task references issues #394 and #395;
   - archive metadata backfill task references issue #397;
   - close fleet task references issue 5 or the local reroute decision.
5. Update this task PRD acceptance criteria with the final issue-5 decision
   and the reference-update evidence.
6. Record the work in the developer journal through the normal finish-work
   path after validation.

## Validation Plan

- Confirm all referenced upstream issues exist with `gh issue view`.
- Run `python3 ./.trellis/scripts/task.py list-archive`.
- Run `git diff --check`.
- If only Trellis task documents change, the local diff and archive-list checks
  are sufficient.
- If the issue-5 decision causes pack-owned code changes, defer to the
  validation plan in `07-06-close-fleet-refresh-loop/implement.md`.

## Documentation And Spec Updates

- The task PRD is the source of truth for filed URLs and reroute decisions.
- Superseded archived PRDs should receive short dated notes with issue URLs,
  not long duplicated issue summaries.
- No README or installed guide changes are expected unless a pack-owned fix
  changes user-visible recorder behavior.

## Review Notes

- Reviewers should verify that issue 5 was not filed before the R4 root-cause
  note existed.
- Reviewers should verify that upstream issue text does not include local-only
  paths or private consumer repo details.
- No upstream Trellis PR should be created by this task.

## Follow-Ups

- If an upstream maintainer replies with a workaround that changes pack
  behavior, create a new pack task before implementing it.
- If issue 5 is rerouted locally, make sure the upstream issue draft remains in
  the task directory as historical evidence but clearly says "not filed".
- If issues #394-#397 close upstream, create a future cleanup task to evaluate
  whether corresponding pack workarounds can shrink or be removed.

# File upstream Trellis issues from deep-review findings

## Goal

Five pack-side workarounds trace to upstream Trellis CLI gaps rather
than pack defects. Per the README "Upstream Path" policy ("hand the
issue to the Trellis source owner"), file the five drafted issues in
this task directory with the Trellis owner (mindfoldhq /
trytrellis.app) and link the filed issue URLs back into the pack tasks
they supersede. None of the pack tasks block on these — they are all
written to fix things pack-side; an upstream fix lets the corresponding
workaround shrink or be removed later.

Issue drafts (ready to copy into the Trellis tracker):

- `upstream-issue-1-add-session-structured-content.md` — add_session
  placeholder auto-commit (supersedes most of the pack recorder
  wrapper).
- `upstream-issue-2-machine-readable-output.md` — `--json` output for
  task/context scripts (kills sentinel-grepping in housekeeping).
- `upstream-issue-3-platform-state-contract.md` — machine-readable
  active-platform state (replaces marker-file tables).
- `upstream-issue-4-task-cli-hygiene.md` — blank descriptions accepted;
  create() moves the current-task pointer during batch creation.
- `upstream-issue-5-journal-duplicate-session.md` — duplicate
  journal session bug report (verified byte-identical bodies).

## Requirements

- R1: Locate the correct upstream tracker (Trellis CLI repo or support
  channel per docs.trytrellis.app) and file issues 1-5, adjusting
  formatting to the tracker's issue template if one exists.
- R2: Do not file issue 5 until its root cause is confirmed to be in
  Trellis-owned code: run the investigation in
  `07-06-close-fleet-refresh-loop` R4 first (the double-write could
  originate in the pack recorder wrapper instead). File it as a pack
  bug there if so.
- R3: Record filed issue URLs in this PRD and add a one-line reference
  in the superseded pack tasks (`07-06-introduce-platform-registry`,
  `07-06-housekeeping-recorder-robustness`,
  `07-06-close-fleet-refresh-loop`,
  `07-06-archive-task-metadata-backfill`) — supersession notes are
  already in those PRDs pointing back here.
- R4: Keep all pack tasks unblocked: no pack task waits on an upstream
  fix landing.

## Acceptance Criteria

- [ ] Issues 1-4 filed upstream with URLs recorded here.
- [ ] Issue 5 either filed upstream with a confirmed Trellis root
  cause, or re-routed to the pack with the draft updated to say so.
- [ ] Superseded pack tasks reference the filed issue URLs.

## Notes

- Origin: 2026-07-06/07 session decision following the deep review.
- The drafts cite pack-repo evidence paths; when filing, keep the
  repro summaries but drop repo-local paths the Trellis owner cannot
  see, or link to this public repo.

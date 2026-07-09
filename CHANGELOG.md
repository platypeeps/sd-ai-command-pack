# Changelog

## 0.7.0 - 2026-07-08

- Added the distributed `sd-work-backlog` command and shared skill for
  sequentially selecting implementation-ready Trellis backlog tasks, completing
  them through the normal `sd-create-pr`/`sd-housekeeping` flow, and recording
  or addressing follow-ups before moving to the next task.

## 0.6.1 - 2026-07-08

- Hardened the `sd-review-pr` wait-for-review step against a remote-review race:
  the completion signal (a reviewer request clearing / a review event) can fire
  before the reviewer's inline review-thread comments are queryable, so an
  immediate thread read can report a false "clean". The skill now waits a short
  settle interval before reading threads and treats the pre-merge unresolved-thread
  re-check (the housekeeping merge guard) as the authoritative clean check, never a
  single post-completion read.

## 0.6.0 - 2026-07-08

- Added the full-check Obsidian KB freshness lane
  (`SD_AI_COMMAND_PACK_FULL_CHECK_KB`) for repos that maintain generated
  `.obsidian-kb/` knowledge folders.
- Made `sd-ai-command-pack-update-spec-kb.py` return exit code 3 when a KB
  refresh is blocked by conflicts that need manual reconciliation.
- Hardened shipped scripts and audits across Bash 3.2 compatibility,
  all-platform install-audit coverage, PR-body scope matching, review-runner
  robustness, recorder/housekeeping behavior, and KB runtime exclusions.
- Added a release guard in full-check so shipped payload changes under
  `templates/**`, the installed usage guide, or `manifest.json` must include a
  manifest version bump.
- Started the release log and tag process at `v0.6.0`; earlier versions remain
  traceable through git history but are not retroactively changelogged here.

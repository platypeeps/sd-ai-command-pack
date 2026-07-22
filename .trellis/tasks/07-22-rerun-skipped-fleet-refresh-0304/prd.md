# Rerun 0.30.4 refresh for skipped fleet checkouts

## Goal

After checkout owners clear the recorded no-touch blockers, rerun sd-fleet-refresh for rwbp-website, se-ai-command-pack, sd-github-review, and anomaly-metric-creator against immutable release 0.30.4.

## Requirements

- Preserve every checkout until its owner resolves the recorded blocker; never
  stash, reset, clean, switch, or overwrite user work as preparation.
- Re-run canonical fleet preflight against immutable tag `v0.30.4` before any
  consumer mutation.
- Limit the resumed rollout to the four skipped consumers and keep manifest
  priority order: `rwbp-website`, `se-ai-command-pack`, `sd-github-review`,
  then `anomaly-metric-creator`.
- Resolve or obtain ownership for the observed blockers:
  - `rwbp-website`: untracked `.obsidian-kb` on `main`;
  - `se-ai-command-pack`: untracked `.obsidian-kb` on
    `codex/review-installed-skills`;
  - `sd-github-review`: unpublished commit `291a9f2` on
    `codex/enforce-housekeeping-finish-work` with no upstream;
  - `anomaly-metric-creator`: untracked `.obsidian-kb` on `main`.
- For each owned clean checkout, run the normal install, expected-platform
  audit, candidate preparation, full check, exact-head review/CI,
  finish-work, housekeeping merge, and post-merge audit gates.
- Re-skip any checkout that remains dirty or ownership-ambiguous, preserving
  the exact reason and opening no refresh PR for it.

## Acceptance Criteria

- [ ] Canonical preflight verifies `v0.30.4` release identity before mutation.
- [ ] Each of the four consumers is either at `0.30.4` or has a new explicit
  no-touch skip reason.
- [ ] Every refreshed consumer is merged only through the exact finish-work
  head and ends clean and synchronized on its default branch.
- [ ] Final fleet status identifies any consumer still stale after the rerun.

## Notes

- Created from timing run `fleet-0.30.4-20260722T191841Z`, which safely skipped
  these four checkouts without mutation.

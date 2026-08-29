---
title: Fix pre-existing preflight failures in sd-github-review planning docs
status: done
created: 2026-08-20
branch: fix/preflight-preexisting-doc-citations
---
# Fix pre-existing preflight failures in sd-github-review planning docs

## Goal

Clear the 11 review-preflight failures that sd-github-review's own Trellis
planning documents carry on a clean default branch, so that repository's
deterministic gate can exit 0 instead of being waved past on a
"pre-existing" disposition at every pack refresh.

## Context

Surfaced by the 0.71.38 fleet rollout (campaign `exec-bit-repair-071380-d`,
consumer `sd-github-review`). They are demonstrably not caused by that
refresh: on the clean base `c376f9c2a4f6e24539206fc11f51720afe2541f8`, with
the refresh stashed, the 0.71.33 checker extracted from tag `v0.71.33`
reports exactly these 11, and the 0.71.38 checker reports the same 11 plus 9
that only its newer bare-filename locator rule sees. Those 9 were repaired at
source inside the refresh branch, so the rollout landed the gate exactly where
it found it — 11 failures, not 20.

Deferred through the fleet finding severity gate as `defer-follow-up`
(`continue-with-follow-ups`, 0 blockers). This task is the follow-up that
disposition promised.

## Requirements

The 11 failures are two distinct defects, and each wants its own judgment:

- **5 personal absolute paths.** In sd-github-review, under
  `.trellis/tasks/`: `07-25-cheap-review-cost-controls/implement.md` line 40,
  `08-09-review-gate-advisory-convergence/implement.md` lines 69 and 242, and
  `08-09-review-gate-advisory-convergence/research/2026-08-20-research.md`
  lines 48 and 49. Each embeds a personal macOS home path. Replace with repo-relative paths or a
  generic placeholder; a machine-specific path in a checked-in doc is wrong for
  every reader who is not on that machine.
- **6 citations of paths the repository does not carry.** Four name a
  `sd-review.yml` under sd-github-review's `.github/`, one a
  `sd-review.config.json` beside it, and one a `sd-ai-command-pack-review-local.py`
  under a `scripts/` directory that a thin consumer does not vendor. Establish for each
  whether it names a file that was never created, one that was renamed or
  removed, or one that lives in another repository — then correct the citation
  to match. Do not silence a citation by deleting it if the claim it supports
  is still load-bearing in that document.

Both groups live in `.trellis/` planning artifacts, several inside archived or
completed tasks. Historical accuracy matters more than a green gate: where a
document records what was true at the time, qualify the citation rather than
rewriting the history it records.

## Acceptance Criteria

- [x] `node ~/.agents/bin/sd-ai-command-pack-review-preflight.mjs` reports 0 failures on a clean sd-github-review default branch.
- [x] No personal absolute path remains in any tracked `.trellis/` document in that repository.
- [x] Every corrected citation resolves, and each one still supports the claim its surrounding prose makes.
- [x] The change lands in sd-github-review, not here; this task tracks the obligation, and closes when that repository's PR merges. Merged as platypeeps/sd-github-review#110, squash `3a53755`; that branch now reports 0 failures and 0 warnings.

---
title: Fix dangling pack-path citations in se-ai-command-pack docs
status: done
created: 2026-08-20
branch: fix/dangling-pack-path-citations
---
# Fix dangling pack-path citations in se-ai-command-pack docs

## Goal

`platypeeps/se-ai-command-pack` fails its local review preflight with 29
dangling path citations. Its own documents cite sd-ai-command-pack *source*
paths -- `scripts/sd-ai-command-pack-*.py`, `.agents/skills/sd-*/SKILL.md`,
`docs/SD_AI_COMMAND_PACK.md` -- which a **thin** consumer does not vendor. The
citations describe real upstream files; they are just not reachable from that
repository.

## Evidence that this is pre-existing

Surfaced by the 0.71.38 fleet refresh (its PR, lane `se-ai-command-pack`) and
proven not to be caused by it, two independent ways:

- With the refresh stashed, the clean base tree still reports 29 failures.
- The 0.71.33 checker, extracted from tag `v0.71.33`, reports the **identical**
  29 failures on that same clean base tree. The version bump neither causes nor
  widens them.

CI never saw it: `.github/workflows/tests.yml:153` resolves the preflight
through the machine pack install, which a GitHub runner does not have, so that
lane reports itself skipped and `main` stays green. The failure is visible only
in a local gate on a machine that has the pack installed.

## Requirements

- Decide, per citation, whether it should name an upstream location (rewrite it
  so it does not read as a repository-relative path) or whether the referenced
  concept has a thin-consumer-reachable equivalent to cite instead.
- Do not weaken the preflight rule to make the failures disappear. The rule is
  correct: a repository-relative path citation that resolves to nothing is a
  dangling citation.
- Concentrated in `.trellis/spec/backend/quality-guidelines.md` (~26 of the 29)
  plus se-ai-command-pack's own `08-10-upstream-pack-workflow-drift` task PRD.

## Acceptance Criteria

- [x] `node <resolved preflight> ` reports 0 failures in a clean
      `se-ai-command-pack` checkout on a machine with the pack installed.
      Merged as platypeeps/se-ai-command-pack#259, squash `4d02baa`; that
      branch now reports 0 failures and 0 warnings. The count was 28 on the
      clean base, not the 29 recorded above -- one had resolved in the
      interim.
- [x] No sd-ai-command-pack rule, allowlist, or extension set was relaxed to
      achieve it. The 25 citations in `quality-guidelines.md` are kept
      byte-identical and carry `[absent:]` markers; an initial attempt to
      repoint them to `~/.agents/...` was reverted because that file's own
      header keeps them verbatim -- the line numbers refer to the
      pre-conversion file, and the surrounding prose calls the target
      "vendored", which the machine install is not.

## Notes

Deferred by the fleet finding severity gate as `continue-with-follow-ups`,
`defer-follow-up`, 0 blockers, during the 0.71.38 rollout. Recorded here rather
than in the consumer so the refresh PR stays inside its managed scope.

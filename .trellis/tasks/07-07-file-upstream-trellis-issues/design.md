# File Upstream Trellis Issues Design

## Overview

This task closes the loop between pack-side workarounds and upstream Trellis
ownership. Issues 1-4 have already been filed in `mindfold-ai/Trellis`; the
remaining work is to resolve issue 5 after the duplicate-session root cause is
known, then make the superseded pack tasks point at the filed upstream issues.

The task must stay issue-focused. It must not create upstream Trellis pull
requests without explicit user approval for that specific PR.

## Proposal

Use `07-06-close-fleet-refresh-loop` R4 as the gate for issue 5. That task owns
the investigation into whether the duplicate Session 29/30 write came from the
pack recorder wrapper or Trellis-owned `add_session.py`.

Once the R4 result exists:

- If Trellis-owned, file or update
  `upstream-issue-5-journal-duplicate-session.md` as a GitHub issue in
  `mindfold-ai/Trellis`. Remove pack-internal notes before filing, preserve the
  reproducible evidence, and avoid local-only paths that the upstream
  maintainer cannot inspect.
- If pack-owned, do not file issue 5 upstream. Update this task's PRD and the
  issue draft to state that the finding was rerouted locally, and link the pack
  task or PR that fixes it.
- If still inconclusive, keep issue 5 unfiled and park the task with the exact
  missing evidence.

After the issue-5 decision, update the pack tasks that contain supersession
notes so they reference the actual filed issue URLs or reroute decision. The
PRD currently names these tasks:

- `07-06-introduce-platform-registry`
- `07-06-housekeeping-recorder-robustness`
- `07-06-close-fleet-refresh-loop`
- `07-06-archive-task-metadata-backfill`

The existing filed URLs are:

- `https://github.com/mindfold-ai/Trellis/issues/394`
- `https://github.com/mindfold-ai/Trellis/issues/395`
- `https://github.com/mindfold-ai/Trellis/issues/396`
- `https://github.com/mindfold-ai/Trellis/issues/397`

## Boundaries And Non-Goals

- Do not file issue 5 until the duplicate-session root cause is confirmed.
- Do not create upstream Trellis pull requests.
- Do not block any pack-side task on upstream action.
- Do not rewrite the already filed issue summaries unless the tracker shows a
  correction is necessary.
- Do not expose private local checkout paths or unrelated consumer repo
  details in upstream issue text.

## Affected Files

- `.trellis/tasks/07-07-file-upstream-trellis-issues/prd.md`
- `.trellis/tasks/07-07-file-upstream-trellis-issues/upstream-issue-5-journal-duplicate-session.md`
- `.trellis/tasks/archive/2026-07/07-06-introduce-platform-registry/prd.md`
- `.trellis/tasks/archive/2026-07/07-06-housekeeping-recorder-robustness/prd.md`
- `.trellis/tasks/07-06-close-fleet-refresh-loop/prd.md`
- `.trellis/tasks/archive/2026-07/07-06-archive-task-metadata-backfill/prd.md`

## Risks And Edge Cases

- Issue 5 may be a pack bug, not an upstream Trellis bug. Filing it upstream
  prematurely would create noise and contradict the task's own guardrail.
- The duplicate may remain unreproduced. In that case, the honest output is a
  parked issue draft with the missing evidence named.
- Existing upstream issues may have moved, been closed, or received maintainer
  guidance. Check live issue state before updating local task references.
- Superseded task PRDs live partly under the archive; edits should be small
  links or dated notes, not outcome rewrites.

## Validation

- Live `gh issue view` evidence for issues #394-#397 before writing final
  references.
- `gh issue view` for issue 5 if filed, or a local reroute/park note if not.
- `python3 ./.trellis/scripts/task.py list-archive` after archived PRD edits.
- `git diff --check`.
- Full local gate only if pack-owned shipped files are changed by a rerouted
  local fix.

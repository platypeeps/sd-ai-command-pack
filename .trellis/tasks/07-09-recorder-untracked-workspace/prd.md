# Fix session recorder for untracked workspaces

## Goal

Make `sd-ai-command-pack-record-session.py` work when
`.trellis/workspace/` is untracked — the normal state for `--local-only`
installs and fresh workspaces — so the 0.8.1 retry-safety fix actually
holds instead of silently reopening the duplicate-session bug it was
written to close.

## Problem

`modified_workspace_journals` runs
`git status --porcelain -z -- .trellis/workspace`
(`scripts/sd-ai-command-pack-record-session.py:87`) without
`-uall` / `--untracked-files=all`. Git's default
`--untracked-files=normal` collapses a fully-untracked directory to a
single `?? .trellis/workspace/` entry, so no per-journal `.md` path is
emitted and the function returns `[]`.

Reproduced end-to-end during the 2026-07-09 deep review with a mock
`add_session.py`: in a repo where `.trellis/workspace/` is untracked
(true for `--local-only`, where `.trellis/` is in `.git/info/exclude`),
`add_session.py` appends the journal, then the wrapper's post-append
discovery finds no journals and prints
`error: expected exactly one modified journal file, found: none`, exit 1.
Because `existing_session_journals()` (the 050237a retry-safety fix) also
depends on `modified_workspace_journals()`, every rerun re-invokes
`add_session.py` and appends *another* duplicate (observed session count
climbing 1→2→3→4). This is exactly the duplicate-entry class 0.8.1 was
released to fix; the fix only works when the workspace is already tracked.

The archived `07-07-file-upstream-trellis-issues` resolution claims
coverage by `test_record_session_wrapper_reuses_uncommitted_retry_entry`
— that test must construct tracked journals, so it misses the untracked
case.

## Requirements

- R1: Journal discovery detects modified/added journals whether
  `.trellis/workspace/` is tracked or untracked (add `-uall` or an
  equivalent enumeration).
- R2: Retry-safety holds in the untracked case: a rerun after a failed
  stage/commit patches the pending journal entry instead of appending a
  duplicate.
- R3: The "expected exactly one modified journal" contract still fires
  correctly for the genuine zero / multiple ambiguous cases; the change
  must not cause unrelated untracked files elsewhere to be misread as
  journals (scope the enumeration to workspace `.md` journals).

## Acceptance Criteria

- [ ] New test: in a temp repo with an untracked `.trellis/workspace/`,
      one record-session run creates exactly one journal entry, and a
      second run after simulated add/commit failure reuses it (final
      count == 1). Reproduces then locks the observed 1→2→3→4 bug.
- [ ] Existing `tests/test_record_session.py` cases still pass.
- [ ] `scripts/` and `templates/scripts/` copies stay byte-identical
      (pack-drift gate green).
- [ ] Shipped-scripts coverage floor (currently 76%) maintained or raised.

## Non-goals

- Reworking `add_session.py` (upstream Trellis) — this is the pack-owned
  wrapper. Broader upstream cleanup is tracked separately under
  `07-09-upstream-trellis-api-cleanup`.

# Trellis upstream: archive auto-commit index-lock retry

## Goal

**Upstream / Trellis-source-owned — NOT shipped by this pack's 0.64.5 release.**
Filed here as a tracking handoff. The fix belongs in the Trellis framework's
`common/task_store.py`, which this repo carries only as a local install copy
(`.trellis/scripts/common/task_store.py`, one copy, not in the pack payload /
`manifest.json`). The pack README "Upstream Path" forbids patching Trellis-owned
runtime copies in this repo; hence this issue is handed to the Trellis source
owner rather than fixed in a pack release.

Origin: during the 0.64.4 pack self-publish, a transient `.git/index.lock`
contention made `_auto_commit_archive`'s final `git commit` return non-zero;
`task.py archive` printed "Archive moved on disk, but git auto-commit did not
complete" and exited 1, stranding the moved task uncommitted. A bare re-run of
`git commit` succeeded, confirming transient lock contention.

## Requirements (retry spec for the Trellis owner)

- In `common/task_store.py::_auto_commit_archive`, wrap ONLY the final `git commit`
  (the single `run_git(["commit", ...])` call) in a bounded retry. Staging
  (`safe_git_add` + `git rm --cached`) is unchanged; the `after_archive` hook
  lifecycle in the caller (`cmd_archive`) is preserved because a successful retry
  still returns True.
- **Retry key (M-3 — index-lock-specific, anchored):** retry ONLY when the commit's
  git stderr contains the substring `index.lock`. The full git message is
  `Unable to create '<path>/index.lock': File exists`; do NOT treat
  `Unable to create` or `File exists` as standalone markers (they match unrelated
  failures). Anchor on `index.lock`.
- Bounded: ≤3 attempts, fixed backoff (e.g. 0.2s, 0.5s) via `time.sleep`. Never
  delete another process's lock.
- **Non-lock / exhaustion contract (M-2 — preserve existing behavior):** a non-lock
  commit failure, and retry exhaustion, must return the SAME value the current code
  returns on commit failure — `not source_was_tracked` (True for a task that was
  never tracked, False otherwise) — NOT a hardcoded `False`. Do not silently change
  this contract; if changed, change it deliberately and update callers/tests.

## Acceptance Criteria (for the upstream change)

- [ ] Transient `index.lock` commit failure retries and succeeds; `after_archive`
  hooks run; only the scoped archive paths are staged (no `git add -A`).
- [ ] Retry triggers ONLY on stderr containing `index.lock`; a non-lock failure
  does not retry and returns `not source_was_tracked` (both tracked + untracked
  cases tested).
- [ ] Retry is bounded ≤3; exhaustion returns `not source_was_tracked` (tested).
- [ ] No behavior change when `session_auto_commit: false`.

## Notes

- This pack's 0.64.5 ships the consumer-safety half only: `fleet-publish.py`
  fails loudly (PublishError + recovery) on a non-zero archive result and attempts
  no rollback (see `08-04-fleet-publish-archive-commit-retry`). That does NOT
  depend on this upstream change.
- Surfaced by adversarial review round 3 (M-1: ownership; M-2: return contract;
  M-3: retry-key breadth).

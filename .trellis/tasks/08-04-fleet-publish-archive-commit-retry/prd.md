# fleet-publish: no retry around task.py archive auto-commit

## Goal

In fleet-publish.py, archive_and_journal() calls task.py archive, whose _auto_commit_archive (common/task_store.py) runs 'git commit' with no retry. During the 0.64.4 self-publish a transient .git/index.lock contention made that commit return non-zero, so task.py printed 'Archive moved on disk, but git auto-commit did not complete' and exited 1; the helper aborted mid-run with the task already moved on disk (H1 committed, archive staged-but-uncommitted), requiring manual recovery. A bare 'git commit' succeeded immediately on retry, confirming it was transient lock contention (likely a background indexer/hook). Fix: wrap the archive auto-commit in a bounded retry-with-backoff on index.lock/commit failure, and/or have fleet-publish detect the half-done archive state and either complete or cleanly roll it back rather than aborting with a stranded move.

## Requirements

- TBD

## Acceptance Criteria

- [ ] TBD

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.

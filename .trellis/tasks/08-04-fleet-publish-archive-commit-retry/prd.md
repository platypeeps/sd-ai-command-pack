# fleet-publish: no retry around task.py archive auto-commit

## Goal

In fleet-publish.py, archive_and_journal() calls task.py archive, whose _auto_commit_archive (common/task_store.py) runs 'git commit' with no retry. During the 0.64.4 self-publish a transient .git/index.lock contention made that commit return non-zero, so task.py printed 'Archive moved on disk, but git auto-commit did not complete' and exited 1; the helper aborted mid-run with the task already moved on disk (H1 committed, archive staged-but-uncommitted), requiring manual recovery. A bare 'git commit' succeeded immediately on retry, confirming it was transient lock contention (likely a background indexer/hook). Chosen fix (see Requirements, revised after 2-round adversarial review): retry ONLY the final commit inside task_store._auto_commit_archive on index-lock-specific stderr (the real fix, reaches the pack + Trellis-updated repos); on a consumer running unpatched task.py, fleet-publish fails loudly with transient-cause + recovery guidance rather than fabricating an incomplete dir-only rollback (cmd_archive also mutates status/children/sessions pre-move — N-1).

## Requirements

Child B of `08-04-0-64-5-followup-hardening`. Full technical design in the
parent `design.md` §B and `implement.md` Phase B.

Revised after adversarial review: the retry lives in **task_store**, not
fleet-publish (completing the commit in fleet-publish would skip `after_archive`
hooks and require an unsafe `git add -A`).

- `task_store._auto_commit_archive` retries ONLY the final `git commit` when its
  git stderr indicates index-lock contention (`index.lock` / `Unable to create` /
  `File exists`); bounded ≤3 attempts, fixed backoff, no lock deletion; existing
  scoped staging and `after_archive` hooks preserved; non-lock failures fail
  closed unchanged.
- `fleet-publish.py archive_and_journal` fails loudly on any non-zero archive
  result: it raises PublishError naming the likely transient git-lock cause and
  the exact recovery (task may be moved + staged but uncommitted; resolve
  `git status` / re-run the fleet action). It attempts NO partial rollback —
  cmd_archive's pre-move status/children/session mutations (task_store.py:473-506)
  make a dir-only rollback incomplete and misleading (N-1). No manual commit, no
  `git add -A`.

## Acceptance Criteria

- [ ] task_store: index-lock stderr triggers a bounded retry that succeeds; hooks
  run; only archive paths staged; non-lock failure returns False without retry;
  ≤3-attempt bound asserted (test).
- [ ] fleet-publish: a non-zero archive result raises PublishError with
  transient-cause + recovery guidance and performs NO rollback mutation (test).
- [ ] `.venv/bin/python -m unittest tests.test_task_store tests.test_fleet_publish`
  green.

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.

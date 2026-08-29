---
title: "fleet-publish: no retry around task.py archive auto-commit"
status: done
created: 2026-08-04
---
# fleet-publish: no retry around task.py archive auto-commit

## Goal

In fleet-publish.py, archive_and_journal() calls task.py archive, whose _auto_commit_archive (common/task_store.py) runs 'git commit' with no retry. During the 0.64.4 self-publish a transient .git/index.lock contention made that commit return non-zero, so task.py printed 'Archive moved on disk, but git auto-commit did not complete' and exited 1; the helper aborted mid-run with the task already moved on disk (H1 committed, archive staged-but-uncommitted), requiring manual recovery. A bare 'git commit' succeeded immediately on retry, confirming it was transient lock contention (likely a background indexer/hook). Scope (revised after 3-round adversarial review): the task_store retry — the real framework fix — is OUT of this pack release (M-1: `common/task_store.py` is Trellis-owned, not shipped by the pack; README forbids patching it here) and is handed to the Trellis source owner as `08-04-trellis-upstream-archive-commit-lock-retry`. This child ships ONLY the pack-owned consumer-safety half: on a consumer running unpatched task.py, fleet-publish fails loudly with transient-cause + recovery guidance rather than fabricating an incomplete dir-only rollback (cmd_archive also mutates status/children/sessions pre-move — N-1).

## Requirements

Child B of `08-04-0-64-5-followup-hardening`. Full technical design in the
parent `design.md` §B and `implement.md` Phase B.

Scope revised after adversarial review round 3 (M-1): the task_store retry (the
framework-level fix) is OUT of this pack release — `common/task_store.py` is a
Trellis-owned runtime copy the pack does not ship (one local copy, not in
`manifest.json`; README "Upstream Path" forbids patching it here). It is handed to
the Trellis source owner as task `08-04-trellis-upstream-archive-commit-lock-retry`
(which carries the M-2 return contract + M-3 `index.lock` anchor). This child now
ships ONLY the pack-owned consumer-safety half:

- `fleet-publish.py archive_and_journal` fails loudly on any non-zero archive
  result: it raises PublishError naming the likely transient git-lock cause and
  the exact recovery (task may be moved + staged but uncommitted; resolve
  `git status` / re-run the fleet action). It attempts NO partial rollback —
  cmd_archive's pre-move status/children/session mutations (task_store.py:473-506)
  make a dir-only rollback incomplete and misleading (N-1). No manual commit, no
  `git add -A`. Independent of the upstream retry.

## Acceptance Criteria

- [ ] fleet-publish: a non-zero archive result raises PublishError with
  transient-cause + recovery guidance and performs NO rollback mutation (test).
- [ ] `.venv/bin/python -m unittest tests.test_fleet_publish` green.
- [ ] task_store retry is NOT in this release; the upstream task exists and carries
  the M-2 return contract + M-3 `index.lock` anchor.

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.

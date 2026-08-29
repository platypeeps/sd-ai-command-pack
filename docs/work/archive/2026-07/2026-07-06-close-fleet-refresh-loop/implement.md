# Close the Fleet Refresh Loop Implementation Plan

## Execution Order

1. Create an evidence ledger in the working notes for the six-consumer fleet.
   Start with the five named repos in the PRD, then search archived PRDs and
   Session 41 for any sixth or remaining consumer repo that must be included.
2. For each consumer repo, gather live state:
   - current default branch and open rollout PRs;
   - installed `sd-ai-command-pack` version from provenance or manifest data;
   - install audit result;
   - GitHub check status for any refresh PR.
3. Close or refresh consumer rollout PRs only when needed. Use the normal
   installer path and PR-only flow for consumer repos. Record the PR URL and
   audit evidence before merging or marking complete.
4. Reconcile the four named review-thread promises:
   - mezmo PR #313 comment 3522276141;
   - anomaly-metric-creator PR #193;
   - rwbp-website PR #85;
   - loadsmith 0.5.15 review threads.
   Reply or resolve only when the linked fix and audit result prove the
   promise is satisfied. If the thread is already obsolete, record why.
5. Update archived PRDs with minimal truth-maintenance edits. Check completed
   acceptance criteria, or add dated notes for moot/superseded items.
6. Investigate duplicate Sessions 29 and 30:
   - diff the two session bodies with headings removed;
   - inspect `scripts/sd-ai-command-pack-record-session.py` for retry or
     double-invocation paths around the `add_session.py` call;
   - inspect `.trellis/scripts/add_session.py` append/index/auto-commit
     behavior for non-idempotent writes;
   - compare Git history around commit `34ea5d8` and the journal commit that
     introduced the duplicate, if available.
7. Decide the duplicate-session owner:
   - pack-owned: patch the recorder and its template twin, add regression
     coverage, and update the upstream issue-5 draft to say it was rerouted;
   - Trellis-owned: leave pack code unchanged, update the issue-5 draft with
     root-cause evidence, and hand off to the upstream issue task;
   - inconclusive: record the investigation and park issue 5 with the missing
     evidence named explicitly.
8. Correct the journal/index only after the owner decision is recorded. Keep
   the correction small and explain whether Session 29 or 30 is retained.
9. Record the final reconciliation in the task PRD and developer journal.

## Validation Plan

- Run each consumer repo's install audit after any refresh.
- Use `gh pr view`, `gh pr checks`, and review-thread queries for PR evidence.
- Run `python3 ./.trellis/scripts/task.py list-archive` after archived task
  metadata or PRD edits.
- Run `git diff --check` after every batch of task/journal edits.
- If pack-owned recorder files change, run focused recorder tests plus:
  `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest discover -s tests`
- If shipped pack files change, run:
  `python3 scripts/sd-ai-command-pack-update-spec-kb.py`
- Finish with:
  `SD_AI_COMMAND_PACK_FULL_CHECK_PRISM=0 SD_AI_COMMAND_PACK_FULL_CHECK_GITO=0 bash scripts/sd-ai-command-pack-full-check.sh`

## Documentation And Spec Updates

- Archived PRDs are the primary documentation surface for this task.
- Update `.trellis/tasks/07-06-close-fleet-refresh-loop/prd.md` with the final
  evidence summary and root-cause note.
- Update `.trellis/tasks/07-07-file-upstream-trellis-issues/prd.md` only if
  issue 5 is filed upstream or rerouted to a pack-owned follow-up.
- If recorder behavior changes, update `docs/SD_AI_COMMAND_PACK.md` and
  `templates/docs/SD_AI_COMMAND_PACK.md` only for user-visible behavior.

## Review Notes

- Reviewers should not treat `.trellis/scripts/add_session.py` changes in a
  consumer repo as durable pack fixes. That file is Trellis-owned runtime.
- Keep evidence links close to the acceptance criteria they satisfy.
- Avoid broad cleanup in archived tasks; the point is accuracy, not rewriting
  history.
- Do not open upstream Trellis pull requests from this task. If an upstream
  code change is needed, write a paste-ready handoff.

## Follow-Ups

- If the duplicate-session root cause is Trellis-owned, continue with
  `07-07-file-upstream-trellis-issues` and file/update issue 5.
- If any consumer repo cannot pass audit because of a new pack defect, create
  or request a focused Trellis task before continuing fleet rollout.
- If the sixth consumer repo cannot be identified from archived evidence, note
  that explicitly in the PRD and complete the known fleet only with user
  confirmation.

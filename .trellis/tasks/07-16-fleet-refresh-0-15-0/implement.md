# Fleet Refresh 0.15.5 Implementation Plan

## Execution Order

1. Verify `v0.15.5` resolves to the release merge commit and the pack checkout
   is clean on `main` matching `origin/main`.
2. Run fleet preflight and capture all six before versions and exact commands.
3. In manifest order, classify each consumer:
   - `at-target`: record and skip;
   - missing clone or dirty tree: record the explicit skip and do not mutate;
   - stale and clean: continue with the refresh transaction.
4. For each stale clean consumer:
   - identify its remote default branch, fetch/prune, switch to it, and pull
     with `--ff-only`;
   - create `codex/refresh-sd-ai-command-pack-0-15-5`;
   - run the preflight-provided install and expected-platform audit commands;
   - inspect the diff for installer-owned files only;
   - run the consumer's documented full-check;
   - commit, push, open the PR, and run the installed review/watch flow;
   - merge only through installed housekeeping;
   - verify clean default-branch state, `0.15.5` provenance, and audit success.
5. Run fleet preflight again and reconcile each PR URL, merge result, audit
   evidence, and final version into this PRD.
6. Mark acceptance criteria, finish/archive the Trellis task, and report the
   mandatory fleet table and follow-ups.

Step 6 remains open because `rwbp-website` is still stale and its checkout has
owner-created untracked Trellis task content. The other five consumer
transactions are complete and verified.

## Stop Conditions

- Dirty consumer checkout: skip that consumer.
- Missing local clone: skip that consumer.
- Install, audit, or full-check failure: do not open a PR; leave the branch and
  report the failure.
- Red CI, unresolved review thread, non-clean merge state, or head mismatch:
  do not merge; report the open PR or blocker.
- Product-code or upstream-Trellis change appears necessary: stop that
  consumer and create a separate consent-gated handoff/task.

## Evidence To Capture

- Preflight before/final versions and classification.
- Consumer branch, commit, PR URL, review rounds, CI result, and merge time.
- Pre-PR and post-merge audit result with expected platforms.
- Final branch, working-tree, remote-head, and provenance state.

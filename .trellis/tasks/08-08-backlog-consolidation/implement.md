# Implement: backlog consolidation

Branch: `chore/backlog-consolidation` off main.

## Steps

1. **Snapshot before-state** (for AC 5): script dumps
   `{dir: {title, priority, parent, children}}` for all 80 active tasks to the
   session scratchpad.
2. **Unlink surviving-parent / dropped-child pairs**:
   - `task.py remove-subtask 07-22-integrate-routed-review-backends 07-25-add-routed-review-operator-ux`
   - `task.py remove-subtask 07-22-integrate-routed-review-backends 07-25-publish-local-review-attestations`
   - `task.py remove-subtask 07-22-streamline-sd-skill-workflows 07-22-validate-sd-workflow-program-integration`
   - `task.py remove-subtask 07-22-streamline-sd-skill-workflows 07-25-add-multi-reviewer-learning-and-effectiveness-analysis`
   - These four are the complete set: a 2026-08-08 host-review scan of every
     active task.json found exactly these surviving-parent → dropped-child
     links; all other links are internal to dropped subtrees. Re-run the scan
     at implement time before deleting.
3. **Absorb sections**: the PRD absorb table has nine rows mapping to seven
   existing survivors plus one new task. Append `## Absorbed: <source>` to
   each of the seven existing survivors, copying the source's unique
   AC/evidence text with the PRD-recorded conflict resolutions applied. The
   two merge-commit rows have no existing survivor: they seed the new
   08-08-merge-commit-policy prd.md instead (step 9).
4. **Deferred-features note**: append to
   `07-22-integrate-routed-review-backends/prd.md`.
5. **Direction note**: append the 2026-08-08 decision to
   `07-22-evaluate-sd-github-review-consolidation/prd.md`: keep-separate
   stands; thin v1 core with v2 governance parked/dropped in that repo;
   remaining open router-contract acceptance items superseded.
6. **Archive**: `task.py archive 07-24-correct-sd-skill-contract-drift
   --no-commit`; same for `07-22-evaluate-sd-github-review-consolidation`.
7. **Drop**: `git rm -r` the 32 directories (leaf-first inside subtrees).
8. **Priority/title/park/rescope edits**: scripted edit of task.json (+ prd.md
   H1 where title changes) per the PRD keep/park tables, AND a
   `## Rescope (2026-08-08)` section appended to every task whose keep-table
   row carries a rescope note (integrate-routed-review-backends contract
   items; task-create-base-branch-seed corrected upstream-fix scope;
   streamline closure-ledger; harden-toolchain R2-only;
   trellis-version-compatibility R5/R6; dispatch-rollout update-deps-only;
   worker-agents park-note; reduce-review-tooling R1/R2/R4).
9. **Create 10 new tasks** via `task.py create --slug`; fill descriptions and
   prd.md problem statements; upstream register copies the nine source prd.md
   files into its `research/`; merge-commit-policy prd.md cites both absorbed
   sources and the session-numbering D3 evidence.
10. **Fill this task's description** in task.json.
11. **Validate** (AC 1–10):
    - `node scripts/sd-ai-command-pack-review-preflight.mjs` → 0 failures
    - topology scan: every parent/children (and legacy subtasks) reference resolves
    - dir count arithmetic; drop-list absence; PARKED prefixes; Absorbed
      sections; Rescope sections present in all named targets (AC 10);
      priority diff vs step-1 snapshot; `git diff --name-only main`
      all under `.trellis/`
12. **Commit + PR** via sd-create-pr flow.

## Validation commands

```bash
node scripts/sd-ai-command-pack-review-preflight.mjs
python3 - <<'EOF'
# topology + priority + count assertions (AC 1,2,5,7) — see step 11
EOF
git diff --name-only main | grep -v '^\.trellis/' | wc -l   # expect 0
```

## Rollback points

- Any step before commit: `git checkout -- .trellis` restores tracked files;
  then remove ONLY the ten new task dirs created by this run (named
  explicitly from step 9's output). Never run a blanket
  `git clean -fd .trellis` — it would delete this task's own untracked
  directory and any unrelated untracked Trellis material.
- After merge: single `git revert`.

## Review gate

Planning adversarial review contract applies before `task.py start` (this
file, prd.md, design.md are the reviewed batch).

# Implement: unblock finalization for the thin-consumers tree

One branch, `fix/thin-parent-status-finalization`, three commits in the
order D3 fixes. No code, no generated artifacts, no consumer contact.

## Recovery source

The corrected parent text already exists, verified, in two commits that
are reachable from closed PR #434 and confirmed present in this checkout
2026-08-12:

- `d386f250` — `08-09-deployment-thin-consumers/prd.md` (+41/-), plus
  the two child files already merged by #436.
- `d3b34c8b` — `08-09-deployment-thin-consumers/design.md` (+23/-) and a
  one-line `prd.md` citation fix.

Recover with `git show <sha>:<path>` per file rather than cherry-picking:
both commits also touch the child files that #436 already landed in
different final form, so a cherry-pick would conflict or regress them.

## Steps

### 1. Branch and flip the parent to `planning`

```bash
git checkout main && git pull --ff-only
git checkout -b fix/thin-parent-status-finalization
```

Edit `.trellis/tasks/08-09-deployment-thin-consumers/task.json`:
`status` `in_progress` → `planning`. Assert `completedAt` and `branch`
are already `null` rather than writing them.

```bash
python3 ./.trellis/scripts/task.py validate \
  .trellis/tasks/08-09-deployment-thin-consumers
python3 -c "import json;d=json.load(open('.trellis/tasks/08-09-deployment-thin-consumers/task.json'));assert (d['status'],d['completedAt'],d['branch'])==('planning',None,None),d"
git commit -- .trellis/tasks/08-09-deployment-thin-consumers/task.json
```

Commit message records D1 and the enumeration behind it.

### 2. Land the parent's doc corrections

Take **both files from `d3b34c8b`**, the later of the two commits. It is
a descendant of `d386f250`, so its `prd.md` already carries that
commit's rewrite plus the archived-path citation fix — verified
2026-08-12, one match each for `Pi retention holds` and for
`archive/2026-08/08-09-thin-machine-installer`. `d386f250` is named in
this plan as where the rewrite was authored, not as something to apply;
restoring from it would regress the citation.

```bash
for f in prd.md design.md; do
  git show "d3b34c8b:.trellis/tasks/08-09-deployment-thin-consumers/$f" \
    > ".trellis/tasks/08-09-deployment-thin-consumers/$f"
done
```

Then add, in `prd.md`, the D5 recurrence note beside the existing
sentence "this task is not the implementation target": that the task
stays `planning` for the program's duration and is started only if it
acquires direct work of its own.

Verify the four PRD-named correction sites are present, by grep and not
by reading:

```bash
grep -n 'Pi retention holds' .trellis/tasks/08-09-deployment-thin-consumers/prd.md
grep -c '08-09-plugin-closure-size\|08-09-machine-status-copy-unavailable\|08-09-codex-home-skills-family' \
  .trellis/tasks/08-09-deployment-thin-consumers/prd.md   # expect 3
grep -rn '"codex", "pi"' .trellis/tasks/08-09-deployment-thin-consumers/   # expect no output
grep -rn '08-09-thin-machine-installer/research' .trellis/tasks/08-09-deployment-thin-consumers/   # expect no output
ls .trellis/tasks/08-09-thin-machine-installer 2>&1   # expect: No such file or directory
ls .trellis/tasks/archive/2026-08/08-09-thin-machine-installer/research/platform-verification.md
```

```bash
make full-check          # expect 0 failure(s)
git add .trellis/tasks/08-09-deployment-thin-consumers && git diff --cached --check
git commit
git push -u origin fix/thin-parent-status-finalization
```

The push is required before step 3: `journal-only-recovery` proves only
already-published work commits.

### 3. Finalization

Capture the base **before** recording anything:

```bash
BASE=$(git rev-parse HEAD)
```

Record the session with the pack wrapper, citing steps 1 and 2's commits.
The summary states plainly that #436's merged work carries no journal
session, that finalization could not run for it, and that this session
does not retroactively cover it — PRD requirement 4 is discharged by
recording the gap, not by citing another branch's commits, which would
fail the per-path rules.

```bash
bash scripts/sd-ai-command-pack-toolchain.sh run-python -- \
  scripts/sd-ai-command-pack-record-session.py --title ... --summary ... \
  --commit "<step1>,<step2>" --change ... --test ... --no-commit
git add -- .trellis/workspace/sdelmas/journal-8.md .trellis/workspace/sdelmas/index.md
git diff --cached --check
git commit -m "chore: record journal" -- \
  .trellis/workspace/sdelmas/journal-8.md .trellis/workspace/sdelmas/index.md
```

```bash
FINISH_WORK_RECEIPT="$(mktemp)"
node scripts/sd-ai-command-pack-review-preflight.mjs \
  final-bundle --mode planning --base "$BASE" --head "$(git rev-parse HEAD)" \
  --json >"$FINISH_WORK_RECEIPT"
```

**This is the gate the whole task exists to pass.** Require
`schemaVersion: 1`, `status: valid`, `reasonCodes == ["planning_bundle_valid"]`,
`evidence.headOid == $(git rev-parse HEAD)`. Any other result stops here
with its reason codes; do not widen the base, do not switch modes, and
do not delete the archive/journal commits.

### 4. Prove both directions

PRD acceptance requires a parent-only branch **and** a child-only branch
each to validate — #435 proved that fixing one does not fix the other.
Step 3 covers the parent-only direction. For the child direction, run
the validator read-only against the merged child-only range that already
exists rather than manufacturing a branch:

```bash
node scripts/sd-ai-command-pack-review-preflight.mjs \
  final-bundle --mode planning \
  --base 8d67ff71 --head 3de90a2b --json
```

That is #435's exact failing range — two children changed, journal
recorded. Before this task it returned
`planning_active_task_outside_closure`; after step 1 the same command
must return `planning_bundle_valid`. The check is falsifiable in the
strongest available sense: it is the recorded failure being re-run, not
a new fixture built to succeed. **Run it before step 1 as well**, to
confirm it still fails for the stated reason; a check that only ever
passes proves nothing.

Why re-running a historical range works, since it is not obvious:
`validatePlanningFinalization` reads the changed task record and the
closure neighbours from the **working tree**, and only the baseline from
the bundle base ref. So the range supplies the delta while step 1's flip
supplies the status the closure check reads. The neighbour it objected
to is `08-09-deployment-thin-consumers/task.json` as it exists on disk.

**Pin the commits first.** `8d67ff71` is an ancestor of `main` (#436
merged it) and is safe. `3de90a2b` is not — it was #435's head, its
branch is deleted, and it is unreferenced locally, so garbage collection
can take it and silently remove this check. GitHub keeps it: verified
2026-08-12, `git ls-remote origin 'refs/pull/435/*'` returns
`3de90a2b26258a40d998e8ad909c67485a56944c refs/pull/435/head`.

```bash
git cat-file -e 8d67ff71 && git cat-file -e 3de90a2b   # if the second fails:
git fetch origin refs/pull/435/head
```

If both routes fail, substitute a throwaway branch changing only
`08-09-thin-migration/design.md` plus a journal commit, and say in the
report that the check was reconstructed rather than replayed.

### 5. Roll out

```bash
gh pr create --body-file <written file>   # never --body
```

Request Copilot, converge its findings, wait for green, then merge
**through `sd-housekeeping`** with the retained receipt:

```bash
bash scripts/sd-ai-command-pack-housekeeping.sh \
  --finish-work-receipt "$FINISH_WORK_RECEIPT" --json
```

That path was unavailable for #434/#435/#436 and its availability here
is the task's real deliverable. If housekeeping still refuses, the fix
is incomplete — report its typed verdict rather than merging by hand.

One known hazard on that path: issue **#432**, "sd-housekeeping blocks
its own merge: pre-merge KB refresh dirties `.gitignore`, tripping the
clean-tree gate". Running the KB refresh before invoking housekeeping,
and committing any resulting `.gitignore` change with the step-2 commit,
avoids meeting it mid-merge. That is a workaround for a filed defect,
not a fix for it.

Delete the receipt file after housekeeping consumes it.

## What this does not do

- The canary conversion. It needs its own per-cohort user authorization
  and mutates three consumer repositories.
- The `completion_successor_history_non_linear` half of the wall, owned
  by `08-09-update-branch-linearity-conflict`.
- Any change to `validatePlanningClosureActiveTasks`. D2 rejects it.

## Rollback

Revert the branch. The status flip is one field and the corrections are
prose; nothing generated, no installer surface, no consumer contact.

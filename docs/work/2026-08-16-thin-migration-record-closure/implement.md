# Implement: closing the thin-migration records

Executes `design.md` in this directory. Records only — no code, no generated
payload, no fleet mutation.

## Step 0 — re-establish the mode precondition

`design.md` rule 4 depends on live repository state that any other session can
change between planning and implementation. Measure it first, not at the merge
gate:

```bash
python3 -c "
import json, glob
bad = []
for p in sorted(glob.glob('.trellis/tasks/*/task.json')):
    with open(p, encoding='utf-8') as fh:
        task = json.load(fh)
    if task.get('status') in ('in_progress', 'review'):
        bad.append((p.split('/')[-2], task['status'], task.get('parent'), task.get('children')))
print(bad or 'none')
"
```

Expect `none`. Any `in_progress` or `review` task that links — as parent or
child — to `08-09-thin-migration` or `08-09-deployment-thin-consumers` trips
`planning_active_task_outside_closure`, and the batch has to be re-scoped
before any edit rather than after. A task in those statuses that is *unlinked*
to either is harmless; check the link, not just the status.

## Step 1 — the grandparent's blocker header

`.trellis/tasks/08-09-deployment-thin-consumers/prd.md`, lines 3–10.

Rewrite the blockquote in the past tense per `design.md` D1: what was blocked,
that AMC has since converted, and that
`docs/fleet/candidate-validation.json` now reports every consumer `passed`.
Keep the 175 figure and the 13-pack-owned-citations detail — they are the
sequencing rationale, and the archived `08-11-pack-layout-aware-guard`
corroborates the measurement.

Re-read the ledger rather than trusting this file for the `passed` claim:

```bash
python3 -c "
import json
d=json.load(open('docs/fleet/candidate-validation.json'))
cs=d.get('consumers') or d.get('results') or []
print(sorted({c.get('status') for c in (cs if isinstance(cs,list) else cs.values())}))
"
```

**Do not** delete the paragraph. A present-tense blocker becomes history; it
does not become absent.

## Step 2 — re-measure each criterion before touching it

`.trellis/tasks/08-09-thin-migration/prd.md`, criteria at `:116`–`:129`.

Work criterion by criterion, gathering evidence *before* deciding whether the
box gets ticked. The `prd.md` table in this task directory is a starting point
and is explicitly not the evidence.

| criterion | how to settle it |
| --- | --- |
| 1 (`:116`) | read the archived `08-10-thin-canary-conversion`'s own recorded evidence for the canary consumer and its CI outcome — not the parent's summary of it |
| 2 (`:119`) | search for a durable record of the revert rehearsal. `git log` the archive for the loadsmith work, and grep the archived task tree and journal for the rehearsal. If nothing durable exists, leave it unticked and record what was searched |
| 3 (`:123`) | AMC's merged conversion removed both surfaces. Evidence lives in another repository, so record it as a repository plus PR or commit reference rather than a `path:line` |
| 4 (`:125`) | do not tick — annotate per Step 3 |
| 5 (`:128`) | read `.github/scripts/prepare-release.py` for the candidate-check invocation and the raise that blocks on failure, and cite the lines you actually read |

Criterion 2 is the one expected to fail this bar. Leaving it unticked with the
search recorded satisfies this task's acceptance criterion; ticking it from
recollection does not, and would reproduce inside this task the exact defect the
task exists to remove.

## Step 3 — annotate criterion 4

Under criterion 4 at `:125`, record that its grep half is satisfied and its gate
half is not, and name `08-10-thin-final-conversion-gate-retirement` requirement
2 as the outstanding work with the unresolved premise: retiring
`validate_consumer` removes the only consumer validator while `--revert-thin`
stays live and documented as the prescribed recovery route.

Do not restate the three options recorded in that task, and do not select one.
Point at it. Duplicating a decision record is how the two copies drift.

## Step 4 — citation sweep

Every `path:line` added across Steps 1–3 must resolve in this checkout — the CI
scope preflight resolves against the local tree, so a consumer-repository path
fails even when it is correct.

```bash
grep -ohE '[A-Za-z0-9_][A-Za-z0-9_./-]*\.(py|sh|mjs|json|md):[0-9]+' \
  .trellis/tasks/08-09-deployment-thin-consumers/prd.md \
  .trellis/tasks/08-09-thin-migration/prd.md \
  .trellis/tasks/08-16-thin-migration-record-closure/*.md \
  | sort -u | while read c; do
    f="${c%:*}"; n="${c##*:}"
    if [ -f "$f" ] && [ "$(wc -l < "$f")" -ge "$n" ]; then echo "OK   $c"
    else echo "FAIL $c"; fi
  done
```

Check for the bare-path shape specifically: a citation that drops its directory
prefix resolves as `FAIL` here only if no same-named file exists at the root, so
also confirm each `OK` line points at the file intended rather than a same-named
one elsewhere.

## Step 5 — confirm no lifecycle drift

```bash
git diff -- '.trellis/tasks/*/task.json'
```

Expect empty. `planning_lifecycle_mutation` requires every changed planning
task to keep `status`, `completedAt`, and `branch` as they were; ticking
criteria is a `prd.md` edit and must not have touched `task.json` at all. A
non-empty diff here means something ran `task.py start` or `set-branch` by
accident.

## Step 6 — finalize

`--mode planning`, per `design.md`. The bundle is the three edited `prd.md`
files, this task's own artifacts, and the journal session with its sibling
index. Require `planning_bundle_valid`.

`make check` before finalization.

## Ordering constraints

- Step 0 before any edit — a re-scope after editing means undoing edits.
- Steps 1, 2, and 3 are independent.
- Steps 4 and 5 after all edits, before finalization.

## Rollback

`git revert`. Nothing outside the task records changes, so a revert restores the
prior records exactly; the only cost is repeating the re-measurement.

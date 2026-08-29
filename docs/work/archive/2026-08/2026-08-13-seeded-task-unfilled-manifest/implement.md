# Implementation plan

Every step edits `templates/scripts/...` or `templates/docs/...` as the source
and propagates before committing. Validation commands run from the source
checkout root.

## Step 0 — branch and falsify the gap

1. `git switch -c task/seeded-task-unfilled-manifest`
2. Bind the task: `task.py set-branch <task-dir> task/seeded-task-unfilled-manifest`
3. Build the failing evidence **before** touching the rule, so the fix is proven
   rather than asserted. Extend `tests/test_bookkeeping_validator.py` with the
   three unfilled shapes from the design table and run them:

   ```bash
   bash scripts/sd-ai-command-pack-toolchain.sh run-python -- \
     -m unittest discover -s tests -p 'test_bookkeeping_validator.py' -v
   ```

   Expect all three to FAIL with `seeded_task_valid`. A test that passes here is
   testing the wrong thing.

Rollback point: nothing shipped yet.

## Step 1 — the unfilled-manifest rule

1. In `templates/scripts/sd-ai-command-pack-review-preflight.mjs`, add the
   file-level counters to `validateBookkeepingTaskContexts` and the sibling
   row-counting helper described in the design.
2. Emit `task_context_unfilled` only when `usableRows === 0` and the file
   emitted no other finding.
3. `make sync`, then confirm source and install copies are identical.
4. Re-run step 0's tests: the three shapes now FAIL the gate (status `invalid`),
   which is the pass condition for the tests.

Validation:

```bash
bash scripts/sd-ai-command-pack-toolchain.sh run-python -- \
  -m unittest discover -s tests -p 'test_bookkeeping_validator.py' -v
bash scripts/sd-ai-command-pack-toolchain.sh run-python -- \
  -m unittest discover -s tests -p 'test_review_preflight.py' -v
```

The second suite is the regression guard for merge time: the lone-`_example`
exemption and the root-task base-branch wording must not move.

Rollback point: revert this commit; 0.71.3 behaviour returns exactly.

## Step 2 — preserve the inline-platform consumer

Add the acceptance-criterion test directly: a seeded task with **no** manifest
files at all still reports `seeded_task_valid`. This is the criterion most
likely to be broken by a careless fix in step 1, and it must be a test rather
than an argument.

## Step 3 — unrecognized command fails loudly

1. Extract the subject composition into an exported
   `bookkeepingResultSubject(result)` with an explicit branch over the known
   commands and a `throw` on anything else; `printBookkeepingResult` calls it.
   The printing function is not exported and writes to the console, so the pure
   function is the only testable seam.
2. Add a test that drives the throw with a synthetic result through the exported
   symbol, using the existing `.mjs` import harness in
   `tests/test_review_preflight.py`. Argv cannot reach this state.
3. Confirm the three real commands still print their existing subjects — the
   0.71.3 receipt test (`PASS seeded-task bookkeeping validation: 1 task(s).`)
   must still pass untouched.

## Step 4 — documentation

1. Edit `templates/docs/SD_AI_COMMAND_PACK.md` with the three statements from
   the design, **and** correct the scaffold passage that currently tells
   operators the scaffold "must be replaced or emptied before the task leaves
   planning". Keep that true for the merge-time lane and state the seeded-task
   lane's opposite rule in the same paragraph. Verify no other copy of the
   sentence survives:

   ```bash
   grep -rn "replaced or emptied" templates/ docs/ plugins/ .agents/ .claude/
   ```
2. `make sync` and `python3 .github/scripts/generate-plugin.py`.
3. Verify the mirrors agree. `templates/` and `docs/` must be byte-identical,
   but the plugin payload is **not** a byte copy: `generate-plugin.py` rewrites
   `scripts/` paths to `~/.agents/bin/`. Count the new sentence across all
   three instead of diffing the payload:

   ```bash
   diff templates/docs/SD_AI_COMMAND_PACK.md docs/SD_AI_COMMAND_PACK.md
   grep -rc "Emptying satisfies those two lanes only" \
     templates/docs/SD_AI_COMMAND_PACK.md docs/SD_AI_COMMAND_PACK.md \
     plugins/sd/machine-payload/docs/SD_AI_COMMAND_PACK.md
   ```

   Do **not** edit `.trellis/workflow.md`; it is vendored Trellis, absent from
   `manifest.json`, and would be overwritten upstream.

## Step 5 — release 0.71.4

1. `manifest.json` to 0.71.4; add the CHANGELOG heading and entries.
2. `python3 .github/scripts/generate-plugin.py`
3. `python3 .github/scripts/prepare-release.py`
4. Regenerate the candidate ledger with **no** consumer filter:

   ```bash
   python3 scripts/sd-ai-command-pack-fleet-candidate-check.py --json
   ```

5. Full local gate plus the release payload gate, which local `sd-check` does
   not contain:

   ```bash
   python3 scripts/sd-ai-command-pack-check.py --json
   bash scripts/sd-ai-command-pack-full-check.sh 2>&1 | grep -i "release version gate"
   ```

   Expect `manifest version 0.71.3 -> 0.71.4`.

## Step 6 — review and finish

1. Push, open the PR, run the `sd-review-pr` loop to convergence.
2. `sd-finish-work`: pre-archive gate, archive, journal, final-bundle receipt,
   final push.
3. Merge; CI auto-tags `v0.71.4` on the `main` push.

## Post-archive handoff (not an acceptance criterion)

Resume campaign `refresh-0.71.3-20260813T163232Z` from fresh preflight evidence
against 0.71.4. Re-verify `rwbp-coordinator`'s checkout before touching it: it
still carries an uncommitted 0.71.3 install on
`chore/sd-ai-command-pack-0.71.3`, and that state must be reconciled — not
assumed — before its lane advances.

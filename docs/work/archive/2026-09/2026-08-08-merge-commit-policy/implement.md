# Implementation plan — one merge-commit policy

Read `design.md` first. The mechanism there is the revised one: a cited
merge's `--cc` paths are **checked against the existing per-path category
rules**, not used as a refusal trigger. An earlier draft refused on non-empty
`--cc` under a new reason code; that draft was wrong and its premise is
corrected in the "Premise correction" section.

## Sequencing against 08-26

`08-26-completion-successor-cc-overrefusal` (PR #563) is correcting the same
false premise in `classifyFirstParentMerge`, and owns the `git merge-tree`
accuracy work and the renaming of the conflict-flavoured artifacts.

**Land 08-26 first.** Two reasons, and the second is the one that bites:

1. Its Direction B is the same shape as this task's revised mechanism, and
   whichever lands second should follow the first's naming rather than invent
   a parallel vocabulary.
2. Its Out of Scope section records that the two `classifyFirstParentMerge`
   call sites have already drifted apart once. Doing this task first would put
   a third variant of the same reasoning in the file.

If 08-26 is still open when this starts, stop and re-plan rather than
duplicating its work.

## Steps

### 1. Red first — the tests that must fail before anything is written

Add to `tests/test_bookkeeping_validator.py`, beside #558's
`make_base_update_repo` helper. Build the fixtures from real merges, not
synthesized ranges — #563's acceptance criteria make the same demand for the
sibling rule, for the same reason.

- `test_planning_recovery_accepts_a_cited_merge_carrying_only_ordinary_paths`
  — journal cites a merge whose combined diff is the version-stamped set
  (`CHANGELOG.md`, `manifest.json`). This is the PR #350 regression and the
  shape the release gate forces; it must validate.
- `test_planning_recovery_accepts_a_cited_merge_with_no_combined_diff`
  — the trivial case: merge contributes nothing.
- `test_planning_recovery_refuses_a_cited_merge_touching_task_paths`
  — combined diff includes `.trellis/tasks/**`; must fail
  `planning_recovery_commit_scope_invalid`, asserting the reason code, not
  only the invalid status.
- `test_planning_recovery_refuses_a_cited_merge_touching_workspace_paths`
  — same for `.trellis/workspace/**`.
- `test_planning_recovery_refuses_a_merge_introducing_a_symlink`
  — the merge's own content sets mode `120000`. This is the test that fails
  if the combined-diff parser drops the mode; without it that regression is
  invisible.
- `test_a_cited_merge_git_auto_merged_is_not_called_a_conflict`
  — the clean auto-merge whose `--cc` is non-empty. Pins the corrected
  premise so it cannot silently regress.
- `test_planning_recovery_still_refuses_an_octopus_merge`
  — >2 parents stays `planning_recovery_commit_non_linear`.

Run and confirm they fail for the intended reason before writing code:

```bash
.venv/bin/python -m unittest tests.test_bookkeeping_validator
```

A test that fails with `bundle_diff_malformed` rather than the reason code
under test is failing for the wrong reason — fix the fixture first.

### 2. The combined-diff parser

New function beside `bookkeepingChangedEntries` in
`templates/scripts/sd-ai-command-pack-review-preflight.mjs`. **Do not extend
the existing regex** — the formats differ (`::`, three modes, three blobs, one
status char per parent) and a regex that accepts both is a regex that accepts
malformed input.

- Parse `git diff-tree --cc -r --raw -z --no-commit-id <oid>`.
- Return the same entry shape the downstream loops consume: `path`, `status`,
  and the **result** mode (the third mode field), so the existing
  executable/symlink/gitlink rejections apply unchanged.
- `oldPath` is null: combined diffs do not carry rename detection. Any
  `D`/`R`/`C` handling keyed on `oldPath` must tolerate that rather than
  assume a pair.
- A malformed record is `bundle_diff_malformed`, `indeterminate` — the same
  failure mode as the two-endpoint parser. Never a pass.

### 3. Relax the parent-count check

At `templates/scripts/sd-ai-command-pack-review-preflight.mjs:3007`:

- accept `parentFields.length === 3` (two parents) alongside the existing 2;
- for that case, source `commitEntries` from the combined-diff parser instead
  of `bookkeepingChangedEntries(parentFields[1], commit.oid)`. The design's
  "second change" section explains why the first-parent diff is wrong here:
  it reports everything the other side brought in, which is not the merge's
  content and would blow the scope rule regardless of policy;
- keep `planning_recovery_commit_non_linear` for >2 parents and for a parents
  read that fails;
- add no new reason code. Out-of-scope merge content fails under the existing
  `planning_recovery_commit_scope_invalid`.

Everything downstream — the task-archive rule, the control-character rule, the
active-task lifecycle rules — runs unchanged over the entries the new parser
returns. That is the point of matching the entry shape.

### 4. Do not touch the recorder

`derive_work_commits` keeps citing merges. Confirm no diff lands in
`templates/scripts/sd-ai-command-pack-record-session.py`. Its workspace-only
filter defect is real and stays open as its own concern; fixing it here would
violate the PRD's "fix recorder OR validator, not both".

### 5. Close D3

`08-06-upstream-add-session-numbering` delegates D3 here. Record in that task
that it resolves by needing no change: under this decision a merge in the
commit table is legal, so the upstream behaviour is correct as it stands.
Edit the delegation note; do not reopen the task.

### 6. Propagate and release

The four copies of `sd-ai-command-pack-review-preflight.mjs` must end
byte-identical. `templates/scripts/` is canonical; `scripts/`,
`plugins/sd/bin/`, and `plugins/sd/machine-payload/scripts/` are generated.

```bash
make sync
make generate            # exits 2 on a stale ledger, having written plugins/sd
.venv/bin/python scripts/sd-ai-command-pack-fleet-candidate-check.py
make generate
```

The two `make generate` runs with the fleet check between them are required,
not belt-and-braces: the first writes the tree the check validates.

Shipped-payload change, so bump all three: `manifest.json`,
`.sd-ai-command-pack/manifest.json`,
`plugins/sd/.claude-plugin/plugin.json`, plus the matching top `CHANGELOG.md`
heading in `## <version> - YYYY-MM-DD` form.

## Validation

```bash
# the tests under change
.venv/bin/python -m unittest tests.test_bookkeeping_validator

# full suite
PYTHON_BIN=".venv/bin/python" bash .github/scripts/run-tests.sh

# four-copy closure -- expect exactly 1
find . -name sd-ai-command-pack-review-preflight.mjs -not -path './.git/*' \
  -print0 | xargs -0 shasum -a 256 | awk '{print $1}' | sort -u | wc -l

# repository gates
make check
```

## The acceptance criterion the unit tests do not close

PRD acceptance criterion 2 is "the merge-main-first-then-record procedure
finalizes **green end-to-end**". Steps 1 through 6 do not demonstrate that:
they prove the validator accepts the shape, which is a different claim from
the procedure completing through `sd-finish-work` and the housekeeping gate.

So the task is not done when the suite is green. Before closing it, run the
prescribed procedure for real on this task's own PR — merge main first, record
the session citing that merge, and take it through the gate rather than around
it. If that route still does not produce a receipt, the remaining obstacle is
evidence for 08-26 or a new task, and it must be recorded rather than worked
around by hand. Hand-editing generated bookkeeping is the failure this task
exists to remove; doing it to close this task would be self-defeating.

Acceptance criterion 4 — both absorbed sources recoverable from git history —
needs no step. It is satisfied by the consolidation commit that created this
task and is verifiable with `git log --follow` over the two absorbed paths.

## Review gates

- After step 1, before step 2: confirm every new test fails, and fails for the
  reason it names.
- After step 3, before step 6: run the unit module alone. Propagating a
  half-working change into four copies makes the diff unreadable.
- Before opening the PR: the four-copy digest must print `1`, and `make check`
  must exit 0.

## Rollback

Steps 2 and 3 are additive within one loop body plus one new function.
Reverting them restores parent-count refusal exactly. No digest or schema
version keys on the planning-recovery verdict — see the design's Rollback
section for what was actually checked. Step 6's version bump reverts with the
code; a released bump does not need clawing back, since the behaviour change
is what the bump describes.

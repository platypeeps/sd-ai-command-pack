# record-session derives merge commits the validator refuses

## Goal

Stop `record-session` from citing merge commits when it derives its own commit
list.

Two outcomes follow, and both matter. On a journal-only planning bundle the
documented invocation stops producing a journal entry the pack's own
final-bundle validator rejects. On every other bundle shape — where that check
never runs — the journal stops recording work against a commit that did not
perform it. The second is the quieter problem and the more durable one.

## Problem

This is the defect 0.64.27 set out to fix, reintroduced through a different
door. `derive_work_commits` says so itself
(`scripts/sd-ai-command-pack-record-session.py:97-101`):

> ``add_session.py`` writes "(No commits - planning session)" whenever no
> hash is supplied, and the pack's own final-bundle validator then rejects
> that session with ``journal_commit_missing`` — two pack surfaces
> disagreeing by default, so the documented invocation produces an artifact
> the documented validator always refuses.

The derivation added to close that gap does not exclude merge commits. On one
bundle shape the validator refuses them; on the others it never looks.

### The derivation includes essentially every merge commit it reaches

The scan is a plain `git log` with no `--no-merges`
(`record-session.py:113-115`):

```python
result = run_git(
    "log", f"--max-count={MAX_DERIVED_COMMIT_SCAN}", "--format=%H", "HEAD"
)
```

Candidates are then filtered on one condition — being confined to the
workspace (`:137-140`):

```python
paths = [line for line in files.stdout.splitlines() if line.strip()]
if paths and all(path.startswith(f"{WORKSPACE}/") for path in paths):
    continue
work.append(full_hash)
```

A commit is skipped only when `paths` is non-empty **and** every path is under
the workspace. A merge commit fails that test on either branch:

- **Clean merge** — `git show --name-only` prints nothing, `paths` is `[]`, so
  `if paths and ...` short-circuits to false and the commit is appended.
- **Combined-diff merge** — `git show` does emit paths when the merge result
  differs from both parents. Those paths are then almost never workspace-only,
  so the commit is appended for the ordinary reason.

Both branches are real in the pack's own history:

```
$ git show --name-only --format= --end-of-options 49c8a39 -- | wc -c   # loadsmith, clean merge
       0
$ git show --name-only --format= --end-of-options fb16862 -- | wc -c   # this repo, combined diff
     267
$ git show --name-only --format= --end-of-options 4cbd80a -- | wc -c   # ordinary commit
      20
```

So the correct statement is not "merges produce no paths" — they sometimes do.
It is that **nothing in the filter is about parenthood at all**, so the only
merge this filter can exclude is one whose combined diff touches the workspace
and nothing else. A fix keyed on path emptiness would therefore miss the
`fb16862` shape; the fix must key on parent count.

### The validator refuses that — but only on one path

`sd-ai-command-pack-review-preflight.mjs:2569-2576` requires a cited commit to
have exactly one parent:

```js
const parentFields = parentResult.stdout.trim().split(/\s+/).filter(Boolean);
if (parentFields.length !== 2 || parentFields[0] !== commit.oid) {
  add(
    'planning_recovery_commit_non_linear',
    session.file,
    `Session ${session.number} commit ${commit.hash} must have exactly one parent`,
  );
```

`git rev-list --parents -n1 49c8a39` returns 3 fields, so the check fails.

That check is narrower than it looks. It sits inside
`validateJournalOnlyPlanningRecovery` (`:2490`), which has exactly one caller
(`:1159`), reached only when the mode is not `completion` **and** the bundle
contains no task entries (`:1152-1159`):

```js
if (options.mode === 'completion') {
  validateCompletionBundle(...);
} else {
  const taskEntries = bookkeepingTaskEntries(entries);
  if (taskEntries.length > 0) {
    validatePlanningBundle(...);
  } else {
    validateJournalOnlyPlanningRecovery(entries, journalSummary, evidence, baseOid, add);
  }
}
```

The `loadsmith` reproduction below was a journal-only planning bundle, which is
why it was caught. **A completion bundle, or a planning bundle that also changes
a task, never runs this check at all.** On those paths a derived merge commit is
written into the journal and silently accepted.

This makes the defect worse than a broken default, not milder. There are two
outcomes rather than one:

- journal-only planning bundle — the run fails and the operator is blocked;
- every other bundle — the journal records work against a merge commit that did
  not perform it, and nothing objects.

The second is a durable wrong attribution in the permanent record, and it is
the more common bundle shape.

### Observed end to end

In `loadsmith`, running the documented form with `--commit` omitted:

```
[sd-record-session] --commit not given; recording 3 unrecorded work commit(s):
49c8a39, 8ee0550, 4cbd80a.
```

`49c8a39` is the merge of PR #207 — already on `origin/main`, not part of the
branch's work, and genuinely unrecorded because the prior PR's journal entry
was written before its own merge commit existed. Validating the resulting
bundle:

```
FAIL planning_recovery_commit_non_linear .trellis/workspace/sdelmas/journal-3.md:
Session 107 commit 49c8a398fb4b048e6f825d38847aad921db5cb55 must have exactly
one parent

Bookkeeping validator: invalid (1 finding(s)).
```

Re-recording with an explicit `--commit 8ee0550,4cbd80a` returned
`valid (0 finding(s))`. Nothing else changed.

### Why this recurs rather than being a one-off

The trigger is structural, not incidental. A merge commit becomes unrecorded
the moment a PR merges, because that PR's journal entry is necessarily written
before the merge commit exists. The next branch cut from the updated default
branch therefore starts with an unrecorded merge commit within scan range. Any
repository that merges via merge commits — `loadsmith` does; the housekeeping
gate reports `merged PR #208 with merge strategy` — is exposed on the next
session recorded after any merge.

Exposed, not guaranteed: the derivation declines outright when git fails, when
no recorded hash exists, when no recorded boundary falls inside
`MAX_DERIVED_COMMIT_SCAN` (200, `:62`), or when more than `MAX_DERIVED_COMMITS`
(25, `:63`) candidates survive. A decline is safe. One further exception is the
filter itself: a merge whose combined diff touches only the workspace is
skipped, as described above — the single shape the current code excludes. The
trap is the ordinary case, where the boundary is a few commits back and the
merge sits inside it.

Squash- and rebase-merging repositories do not produce the parent that trips
the validator, which is likely why this survived the 0.64.27 work.

This repository is itself affected. 28 of the 100 most recent commits on
`origin/main` are merge commits, so `record-session` run here without
`--commit` is subject to the same trap it ships.

### Why the existing tests missed it

Two gaps, both narrow:

- `tests/test_record_session.py` contains no occurrence of the word "merge"
  (`grep -ci merge` returns 0). The two derivation tests
  (`test_derive_work_commits_picks_unrecorded_non_workspace_commits:80` and
  `test_derive_work_commits_declines_when_the_answer_is_not_obvious:136`)
  build linear histories only.
- No test runs the real validator against derived output. The first test's
  docstring names the validator as the reason the derivation exists
  (`:81-85`), but it asserts on the returned commit list, not on whether the
  resulting bundle validates. The defect lives exactly in the gap between
  those two assertions.

## Requirements

- With `--commit` omitted, `record-session` never cites a commit that the
  final-bundle validator would reject as non-linear. The two surfaces must
  agree by default; that agreement is the whole point of the derivation.
- The fix is in the derivation, not in the validator. The validator's
  single-parent rule is correct: a journal entry attributes work to a commit,
  and a merge commit is not where the work happened. Relaxing it would let
  genuinely wrong attributions through.
- Excluding merge commits must not silently drop the work they carry. A merge
  commit brings in its branch's commits; if any of those are themselves
  unrecorded and in scope, the existing conservative-decline behavior applies
  rather than a partial list.
- The existing decline conditions are preserved unchanged: nothing to record,
  git unavailable, no recorded boundary in the scan window, or more candidates
  than one session plausibly covers (`record-session.py:108-112`).

## Acceptance criteria

- [ ] A repository whose history contains an unrecorded merge commit within
      the scan window produces a derived commit list containing no merge
      commit. Tested with a fixture built by an actual `git merge --no-ff`,
      not by a hand-written parent list.
- [ ] The journal entry produced by that derivation passes
      `final-bundle --mode planning` with zero findings, asserted by running
      the real validator against the real fixture rather than by asserting on
      the derived list alone. The defect is the disagreement between the two
      surfaces, so a test that never runs the validator cannot show it fixed.
- [ ] Ordinary single-parent work commits are still derived, with the existing
      workspace-only skip intact — a regression guard proving the fix excludes
      merges rather than everything with no changed paths. Note these are
      currently the *same* branch: an empty `paths` list is why both a merge
      commit and a genuinely-empty commit reach `work.append`, so the fix must
      distinguish them by parent count, not by path emptiness.
- [ ] The behavior is exercised for a repository that merges with merge
      commits *and* one that squash-merges, confirming the fix changes the
      former and leaves the latter's derivation identical.
- [ ] A merge whose combined diff *does* return paths (the `fb16862` shape, not
      only the empty-path `49c8a39` shape) is also excluded. A fix keyed on path
      emptiness passes the other criteria and fails this one.
- [ ] Work introduced *by the merge resolution itself* is derived in full or
      declined — never silently omitted. This is distinct from the side-branch
      criterion below: that work exists in neither parent, so walking past the
      merge cannot recover it. `fb16862` is the concrete case — its parents carry
      pack versions `0.64.25` and `0.64.26` while the merge result is `0.64.27`,
      and the journal records resolving seven version conflicts during it
      (`.trellis/workspace/sdelmas/journal-7.md:710,717`). Simply dropping such a
      merge attributes that work to nothing. Declining is an acceptable outcome
      here; silently shortening the list is not.
- [ ] Unrecorded work reachable only through a merged side branch is either
      derived in full or declined — never silently dropped. This is the
      Requirements clause about not losing the work a merge carries, and no
      other criterion tests it: traversal breaks at the first recorded commit
      before any filtering (`record-session.py:122`), so an implementation could
      omit the merge *and* the side-branch commits and still produce a
      validator-clean partial list.
- [ ] The scan boundary is unchanged by the fix. `--max-count` and any merge
      filter share one `git log` query (`:113-115`), so excluding merges shifts
      which commit is the 200th result. Tested with a history where a merge sits
      inside the window: the same boundary commit is found before and after.
- [ ] The derived list contains no merge commit on a bundle shape that the
      validator never checks — a completion bundle, or a planning bundle that
      also changes a task (`:1152-1159`). Asserted on the derivation itself,
      since no validator finding will appear on these paths. Without this, the
      silent-misattribution half of the Goal goes untested.
- [ ] The change lands in `templates/scripts/sd-ai-command-pack-record-session.py`
      and the root mirror stays byte-identical to it. `templates/**` is the
      source of truth (`AGENTS.md:29-31`) and the tests load the root copy
      (`tests/test_record_session.py:89`), so a root-only fix passes every other
      criterion while shipping the bug.
- [ ] Each existing decline path (`record-session.py:108-112`) still declines,
      verified by test, so the fix does not convert a conservative decline into
      a guess.

## Notes

Reported from `loadsmith` at pack 0.64.27, on the session recording PR #208.

`templates/scripts/sd-ai-command-pack-record-session.py` and the root
`scripts/` mirror are byte-identical as of this filing, so every line number
above applies to both.

Severity is split by bundle shape. On a journal-only planning bundle the
validator catches it every time, and the cost is operator friction: the
documented invocation fails, and the recovery — re-running with an explicit
`--commit` list — requires knowing which derived commit was the merge. On every
other bundle shape the check never runs (`:1152-1159`), the misattribution is
recorded, and nothing surfaces it. The permanent-record case is the more
serious of the two and the reason this is worth fixing rather than documenting.

The one-line form of the fix is `--no-merges` on the `git log` at `:113-115`,
but the acceptance criteria above deliberately do not mandate it; what matters
is that every cited commit has *exactly* one parent, however that is achieved.
Not "no more than one": the check is `parentFields.length !== 2`
(`review-preflight.mjs:2570`), so a zero-parent root commit is rejected too, and
`test_journal_only_recovery_rejects_root_commit`
(`tests/test_bookkeeping_validator.py:2446`) asserts it.

Two traps in that one-liner:

- `--max-count=200` is part of the same query, so `--no-merges` changes *which*
  commit is the 200th result. A boundary previously outside the window can move
  inside it and vice versa, altering the decline behavior the requirements say
  is preserved. Whatever form the fix takes must hold the scan boundary fixed.
- `templates/**` is the source of truth for shipped payloads
  (`AGENTS.md:29-31`), and `templates/scripts/sd-ai-command-pack-record-session.py`
  is the authoritative copy. The root `scripts/` file is a byte-verified mirror,
  and it is the one the existing tests load
  (`tests/test_record_session.py:89`) — so every behavioral test here can pass
  while the shipped template still carries the bug.

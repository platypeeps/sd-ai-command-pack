# Housekeeping is not worktree-aware, so a default branch held elsewhere reports two opaque anomalies and skips cleanup

## Goal

When housekeeping cannot switch to the default branch because another worktree
holds it, carry that diagnosis into the structured result — naming the worktree —
instead of emitting a generic switch failure plus an unexplained second anomaly.

## Problem

`scripts/sd-ai-command-pack-housekeeping.sh:475-480`:

```sh
  if git show-ref --verify --quiet "refs/heads/$DEFAULT_BRANCH"; then
    if git switch "$DEFAULT_BRANCH"; then
      add_action default_branch_switched "switched to $DEFAULT_BRANCH"
    else
      add_anomaly default_branch_switch_failed "failed to switch to $DEFAULT_BRANCH"
    fi
```

`git switch` writes a precise diagnosis to stderr. It is not suppressed — there
is no redirection at `:477`, so an operator watching the terminal sees it — but
it never reaches the structured result, which is what `--json` consumers and the
anomaly list are built from. Reproduced with two worktrees, one holding `main`:

```
$ git -C wt-b switch main
fatal: 'main' is already used by worktree at '.../wt-a'
```

Git names the exact holding path. The anomaly records only
`failed to switch to main`, so the structured result says nothing about the cause
or the remedy even though git had both.

The failure then cascades. Still on the feature branch, the deletion gate
refuses (`:853-854`):

```sh
    add_anomaly branch_switch_incomplete "still on $branch; skipped branch deletion"
```

So one worktree condition produces two anomalies, neither of which names a
worktree, and the branch is left behind. The second anomaly does say deletion was
skipped, so nothing is silent — what is missing is any link between the two, and
any statement of the cause. Refusing to delete from the wrong branch is correct;
reporting it as a free-standing second anomaly is not.

Housekeeping has no worktree awareness anywhere. The only occurrence of the word
in the script is in a comment at `:1000` about recovery artifacts; nothing calls
`git worktree list` on this path.

### Observed

The batch here means the 14 pull requests merged through the housekeeping gate
in one session on 2026-08-08, in the range #358–#379. Every one reported the same
anomaly pair. Two were captured verbatim; this is PR #358's result, and PR #364's
was identical apart from the merge SHA:

```
verdict: blocked ['default_branch_switch_failed', 'branch_switch_incomplete']
actions: ['kb_refreshed', 'remote_refs_refreshed', 'pull_request_eligible', 'pull_request_merged', 'pull_request_merge_confirmed']
anomalies: ['default_branch_switch_failed', 'branch_switch_incomplete']
```

The other twelve were observed during the same session but not captured to a
tracked artifact; treat the two above as the evidence and the rest as
corroboration. Note the shape: every merge action succeeded and the verdict is
still `blocked`.
Every merge completed — the anomalies are post-merge cleanup, not a merge
gate — so the visible effect is a clean merge reported as anomalous, plus
branches left undeleted that a later run has to sweep. A batch of identical
unexplained anomaly pairs also trains an operator to ignore the anomaly list,
which is the more expensive outcome.

`08-07-status-housekeeping-anomaly-disagreement` covers leftover local branches
being treated as a strict anomaly, and `08-07-status-worktree-invisibility`
covers `sd-status` not reporting worktrees. This is the third member of that
family and the only one about housekeeping's switch path.

## Requirements

1. When `git switch` to the default branch fails, carry its stderr into the
   anomaly message, normalized to fit the result contract: collapsed to one line,
   control characters stripped, and truncated to the message limit.
   `validate_event` (`housekeeping-result.py:204-216`) rejects any message
   containing a control character or exceeding `MAX_MESSAGE_LENGTH`, so raw
   multi-line git output would fail validation rather than reach the operator.
2. Detect the worktree-held case specifically — `git worktree list` before the
   switch, or classify the failure after — and emit a distinct reason code
   naming the holding worktree path.
3. The cascading `branch_switch_incomplete` anomaly references the root cause
   rather than standing alone, so an operator reading the anomaly list sees one
   problem instead of two.
4. Behaviour is unchanged when the switch succeeds, and the deletion gate still
   refuses to delete from the wrong branch. This task changes reporting, not
   safety.
5. A worktree-held default branch yields `verdict: clean` when every merge action
   succeeded, with both anomaly codes still present in the result. Incomplete
   post-merge cleanup is worth reporting, not a blocked outcome; `blocked` should
   mean the merge did not happen.

   This is a classifier change, not a message change, and it is larger than one
   code. `sd-ai-command-pack-housekeeping-result.py:255` sets `blocked` when
   *any* `event_codes` or `status_anomalies` are present:

   ```python
   elif eligibility_status == "blocked" or event_codes or status_anomalies:
       outcome = "blocked"
   ```

   `add_anomaly` (`:100-104`) carries only a code and a message with no severity
   field, so the classifier has nothing to discriminate on today. The design must
   introduce that discrimination — a non-blocking anomaly class, or an explicit
   allow-list of codes that do not block — rather than special-casing one code.

6. The dependency on `08-07-status-housekeeping-anomaly-disagreement` is
   resolved before requirement 5 can be met. Housekeeping embeds `sd-status` in
   strict mode (`:1130-1161`) and any embedded status anomaly independently
   forces `blocked`. After a failed switch, `sd-status` reports both the
   unexpected current branch and the leftover local branch
   (`sd-ai-command-pack-status.py:1661-1684`, `:2035-2075`). So requirement 5
   cannot be satisfied while those remain strict anomalies. Either that task
   lands first, or this one absorbs the status-classification change explicitly —
   decide which at design time and record it.

## Acceptance criteria

- A test with two worktrees, one holding the default branch, asserts the anomaly
  message contains the holding worktree path and the captured git stderr
  (requirement 1).
- The same test asserts a distinct reason code is emitted, not
  `default_branch_switch_failed` (requirement 2).
- The same test asserts the `branch_switch_incomplete` message references the
  switch failure rather than standing alone (requirement 3).
- A test asserts `outcome.verdict == "clean"` — the exact value, not merely
  "not blocked", since `failed` and `indeterminate` are also valid verdicts
  (`housekeeping-result.py:47-49`) and would pass a negative assertion — for a
  merge whose every action succeeded, with both anomaly codes still present in
  the result and the expected `outcome.reasonCodes` pinned.
- A test asserts a default-branch switch failure with a cause *other* than a
  holding worktree also carries its git stderr into the anomaly, so requirement 1
  is covered beyond the classified case.
- A test feeds a multi-line, over-length git diagnostic and asserts the resulting
  anomaly message passes `validate_event` — single-line, no control characters,
  within the length limit — and still names the holding worktree.
- A test asserts the single-worktree success path emits
  `default_branch_switched` with no anomaly, unchanged.
- A test asserts branch deletion is still refused while on the wrong branch.
- `bash scripts/sd-ai-command-pack-housekeeping.sh --self-test` passes.
- `make check` passes; `templates/**` updated first with the root mirror
  synchronized (`AGENTS.md:29-33`).

## Out of scope

- Making housekeeping switch anyway — by detaching the holding worktree, forcing
  the checkout, or operating on the branch without checking it out. The refusal
  is correct; only the reporting is wrong.
- Reclassifying leftover-branch anomalies generally
  (`08-07-status-housekeeping-anomaly-disagreement`). Requirement 6 records the
  dependency; it does not adopt that task's scope.
- Teaching `sd-status` to report worktrees (`08-07-status-worktree-invisibility`).

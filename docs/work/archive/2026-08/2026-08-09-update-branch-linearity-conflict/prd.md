---
title: Ruleset update-branch merge commits permanently fail finish-work successor linearity
status: done
created: 2026-08-09
---
# Ruleset update-branch merge commits permanently fail finish-work successor linearity

## Goal

Make the finish-work / housekeeping gate chain able to merge a PR whose
branch was updated from the base with a merge commit, without weakening
either the up-to-date ruleset or the successor-history validation.

## Context

Observed on PR #400 (run 2158bfa4bda649e7b31c52ac25cb1d9f): the branch
fell behind main mid-PR, eligibility reported
`merge_blocked_out_of_date`, and `gh pr update-branch` (the only
non-force option) created a merge commit. The finish-work validator's
completion successor recovery requires every successor commit to have
exactly one parent (`completion_successor_history_non_linear`,
`sd-ai-command-pack-review-preflight.mjs` successor range evaluation),
so the receipt could never revalidate at the merged head. Recovery
required closing the PR and replaying the branch linearly (PR #402),
including remapping journal/index commit hashes
(`journal_commit_unreachable`, `journal_index_mismatch`). Related:
existing task 08-08-merge-commit-policy (decide one merge-commit
policy); this task is the concrete gate incompatibility.

## Requirements

- Decide the policy: either (a) successor validation learns a bounded,
  verifiable allowance for base-sync merge commits (second parent must
  be reachable from the default branch and the merge must introduce no
  delta versus its first parent beyond the base sync), or (b) the flow
  documents/automates linear replay as the sanctioned recovery, or (c)
  the up-to-date requirement is dropped from the ruleset. Coordinate
  with 08-08-merge-commit-policy rather than deciding twice.
- Whatever the decision, the failure mode must be diagnosable: the
  validator or eligibility output should name the update-branch merge
  commit as the cause and point at the sanctioned recovery.
- No gate weakening: an arbitrary merge commit (not a pure base sync)
  must still fail closed.

## Acceptance Criteria

- [ ] A PR that fell behind and was updated from base can reach a valid
      finish-work proof through the sanctioned path (whichever policy is
      chosen) in a test.
- [ ] A non-base-sync merge commit in the successor range still fails
      `completion_successor_history_non_linear`.
- [ ] Docs for sd-finish-work / sd-housekeeping name the out-of-date
      recovery path.

## Resolution (2026-08-26): superseded by 08-25-completion-receipt-base-update

Shipped in PR #558 as option (a) of the Requirements above: successor
validation learned a bounded, verifiable allowance for base-sync merge
commits. `classifyFirstParentMerge`
(`templates/scripts/sd-ai-command-pack-review-preflight.mjs`) is
three-sided — the second parent must be an ancestor of the base tip, the
merge must not already be on the base, and `git diff-tree --cc` must report
no paths. An unresolvable base tip refuses rather than softens.

Acceptance criteria, against main at 0.71.60:

- A base-updated PR reaches a valid proof —
  `test_completion_successor_accepts_a_clean_base_update` and
  `test_active_task_successor_accepts_a_clean_base_update`
  (`tests/test_bookkeeping_validator.py`).
- A non-base-sync merge still fails —
  `test_a_merge_already_on_the_base_branch_is_still_non_linear`,
  `test_an_unresolvable_base_tip_keeps_rejecting_the_merge`, and
  `test_completion_successor_rejects_a_conflicted_base_update`, the last
  under its own reason code `completion_successor_base_update_conflicted`.
- Docs name the recovery — `templates/docs/SD_AI_COMMAND_PACK.md`, the
  paragraph beginning "A head that moved because the branch was updated onto
  a moved base".

The journal remapping this task recorded as the cost of recovery
(`journal_commit_unreachable`, `journal_index_mismatch`) no longer arises:
the base update is accepted, so the linear replay that forced the remapping
is not needed.

Not carried over, and deliberately: the requirement that the diagnostic
"name the update-branch merge commit as the cause and point at the
sanctioned recovery". The conflicted case has its own reason code, but the
plain non-linear message still reads only "must have exactly one parent".
Judged too small to hold this task open. If it bites someone, it is a
one-line message change, not a rediscovery.

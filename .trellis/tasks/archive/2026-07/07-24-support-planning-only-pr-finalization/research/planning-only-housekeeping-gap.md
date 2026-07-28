# Planning-only housekeeping lifecycle evidence

## Current contracts

- `.agents/skills/trellis-finish-work/SKILL.md:50-58` requires archiving the
  current task whenever one exists. It has no planning-session finalization
  branch.
- `.trellis/workflow.md:76` confirms that archive changes lifecycle status to
  `completed` and moves the task, while `task.py finish` only clears the current
  session pointer. Neither operation truthfully represents continued planning.
- `templates/.agents/skills/sd-housekeeping/SKILL.md:24-33` requires SD
  finish-work and an exact-head attestation before an open feature PR may merge.
- `templates/scripts/sd-ai-command-pack-pr-eligibility.py:845-859` verifies only
  that the supplied finish-work OID equals the starting local OID. It cannot
  express or independently prove why that head is a valid finalization.

## Observed PR #244 refusal

On 2026-07-24, PR #244 was open, clean, and mergeable at
`8dc8ca26b6c600d5bac4abe514a432d395c02184`. Required CI was green, Copilot's
second pass produced no new comments, and the sole prior thread was resolved.
The PR contained coordinated Trellis planning artifacts and intentionally left
all implementation tasks in `planning`.

The active session task was
`07-24-add-bookkeeping-only-ci-fast-lane` with status `planning`. Running
canonical housekeeping without a false attestation returned:

- outcome: `blocked`;
- eligibility reason: `finish_work_missing`;
- PR action: skipped auto-merge;
- task state: preserved in `planning`;
- branch action: left local and remote source branches untouched; and
- housekeeping side effects before refusal: refreshed 628 KB copies and fetched
  and pruned `origin`.

Running the current Trellis finish-work flow would have passed the head gate
only by archiving that unfinished implementation task, violating the planning
state and its unchecked acceptance criteria.

## Prior planning PR comparison

PR #225 also described itself as planning-only and kept its new program tasks
in `planning`, but its final head is not a no-archive example. Commit
`ac1d34dc8fd1e20a13946e9a084707552afc62dd` included the completed archive of
`07-22-validate-task-context-before-pr` and a journal record. Its truthful
finish-work evidence came from a separate completed task.

## Design conclusion

The missing state is a valid finalization mode, not a reason to weaken the
merge gate. The command pack can surround unchanged upstream Trellis behavior:
archive and journal for completed work, or journal and preserve task/session
state for a deterministically proven planning-only PR. Both modes need typed,
exact-head evidence that eligibility can independently verify.

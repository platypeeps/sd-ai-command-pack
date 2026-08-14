# review-preflight receipt and repair-string hardening

## Goal

Close the sibling defect that 0.71.4 left behind, and clear three deferred
maintainability findings raised against the same file.

## Origin

Surfaced by Prism during the `rwbp-coordinator` local-checks stage of fleet
campaign `refresh-0.71.4-20260813T212139Z`, reviewing the installed 0.71.4 pack
diff. The finding severity gate classified all four as
`continue-with-follow-ups` with zero blockers, so the campaign proceeded.

## The defect this task exists for

0.71.4 fixed `printBookkeepingResult`, which silently produced an `undefined`
subject for any command outside its inlined chain, by extracting
`bookkeepingResultSubject` and making it throw. That fix covered the **print**
path and missed its sibling on the **reason-code** path:

```js
const validCode = options.command === 'pre-archive'
  ? 'pre_archive_valid'
  : options.command === 'seeded-task'
    ? 'seeded_task_valid'
    : `${options.mode || 'unknown'}_bundle_valid`;
```

A command outside that chain yields `unknown_bundle_valid` — a malformed reason
code emitted as part of a **valid** receipt. That is worse than the print path
it mirrors, because receipts are what downstream eligibility and merge gates
read.

Not reachable through argv today: `parseBookkeepingCli` rejects unknown commands
before this runs. It becomes reachable the moment a subcommand is added to the
parser without updating this chain — which is exactly how the print-path defect
arrived.

## Requirements

1. `validCode` fails loudly on an unrecognized command rather than composing a
   fallback string, matching what `bookkeepingResultSubject` now does.
2. A test drives that failure through an exported seam, since argv cannot.
3. The three existing valid commands keep their exact current reason codes.

## Deferred findings folded into this task

- Repair instructions (for example the `task.py set-base-branch` command) are
  embedded as literal strings and can drift from the scripts they name.
- `checkTrellisPlanningPlaceholders` re-reads each PRD rather than memoizing,
  costing repeated IO on large diffs. Performance only; no result changes.
- Self-citation detection must stay in sync with reference normalization, and
  that coupling is undocumented and untested across path forms (`./`,
  backslash, archive paths).

## Acceptance Criteria

- [ ] An unrecognized command produces a loud failure instead of
      `unknown_bundle_valid`, pinned by a test.
- [ ] `pre-archive`, `seeded-task`, and `final-bundle` receipts are unchanged.
- [ ] Each deferred finding above is either fixed or explicitly closed with a
      recorded reason.

## Notes

Lesson worth keeping: the 0.71.4 fix was scoped to the symptom that was
reported rather than to the defect class. When a fallback branch is removed in
one place, the check is to enumerate every sibling fallback in the same file —
not to fix the one that was named.

# Decide and implement one merge-commit policy

## Problem

Three artifacts prescribed contradictory treatment of merge commits in
session/journal bookkeeping; shipping more than one side produces incoherent
behavior. This task absorbs both dropped tasks and owns the single decision.

**Validator side** (absorbed: 08-07-planning-recovery-rejects-merge-commit):
the `journal-only-recovery` subtype of final-bundle validation requires every
cited work commit to be single-parent; citing a merge commit fails
`planning_recovery_commit_non_linear`. But merge-main-first-then-record is the
prescribed procedure (it prevents session-number collisions, established after
two collisions on 2026-08-06), so the correct procedure guarantees the
failure. Observed shipping PR #350: merge `3ee62194`, record session 315
citing it, validation rejects; workaround was hand-editing generated
bookkeeping.

**Recorder side** (absorbed: 08-07-record-session-merge-commit, the
better-evidenced half): `derive_work_commits`
(`scripts/sd-ai-command-pack-record-session.py:113-140`) scans `git log`
without `--no-merges` and its workspace-only filter passes merge commits on
both branches (clean merge: empty path list short-circuits; combined-diff
merge: paths are almost never workspace-only). So the recorder cites merge
commits the validator refuses on one bundle shape, and mis-attributes work to
non-work commits on every other shape.

**Third voice**: D3 of 08-06-upstream-add-session-numbering also prescribes
merge-commit derivation behavior; its resolution is delegated here by a note
in that task.

## Requirements

1. ONE recorded decision: are merge commits legitimate citable work commits
   (then fix the validator: distinguish what the merge contains, not parent
   count) or not (then fix the recorder: exclude merges from derivation)?
   Fix recorder OR validator, not both.
2. The losing side's diagnostic must name the remedy.
3. Session-numbering D3 is resolved consistently with the decision.

## Acceptance criteria

- [ ] Decision recorded in design.md with the contradiction table.
- [ ] The merge-main-first-then-record procedure finalizes green end-to-end.
- [ ] Regression test reproducing the PR #350 sequence.
- [ ] Full original prd.md content of both absorbed sources recoverable via
      git history (`.trellis/tasks/08-07-planning-recovery-rejects-merge-commit/`,
      `.trellis/tasks/08-07-record-session-merge-commit/`).

## Evidence

PR #350 (2026-08-07); session-number collisions x2 (2026-08-06); recorder code
citations above; 2026-08-08 consolidation review found the three-way
contradiction.

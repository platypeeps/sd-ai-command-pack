# Fleet refresh lanes leave the consumer repomix map stale between releases

## Goal

A fleet refresh lane runs the consumer's `candidatePrepare` commands, which for
repomix-indexed consumers regenerate `docs/repomix-map.md`. Some past lanes did
not, so the map drifted from the tracked tree across several releases and the
next lane that did regenerate it produced a very large diff that the consumer's
own Prism gate flags as an unjustified mass removal — failing a local gate on a
mechanical, correct change.

## Problem

Observed on `rwbp-coordinator` during the 0.71.33 rollout
(campaign `v0-71-33-20260819T035014Z`):

- `bash scripts/update_repomix` produced `14` insertions and `217` deletions in
  `docs/repomix-map.md`.
- Every deleted row was an `.agents/skills/sd-*` entry. Those directories are
  absent from disk and `git ls-files -- '.agents/skills/sd-*'` returns `0`, so
  the map was describing files that had not existed since the thin conversion
  in that consumer's PR #231.
- The intervening 0.71.22 refresh (its PR #234) touched only
  `.github/copilot-instructions.md`, `.sd-ai-command-pack/manifest.json`, and
  `.sd-ai-command-pack/provenance.json` — it never regenerated the map.
- `npm run check:full` therefore exited `1` on a refresh whose payload change
  was correct, with Prism reporting
  "docs/repomix-map.md lines 56-1753 — Missing justification for large-scale repo map and script removals" (paths in Prism output are relative to the consumer checkout, not this repository).

A second, recurring observation from the same gate: newly created Trellis task
directories show up as map rows and Prism reads them as task artifacts added
"without context" (the consumer's generated map, lines 863-873). That one is inherent to
generated output and will repeat on every refresh that seeds a task.

On a second run the same gate produced a different, stronger misreading: it
reported `Removal of SD_AI_COMMAND_PACK.md and related provider config history
doc` at `docs/:1751-1753`. No file is removed by the refresh —
`git diff --diff-filter=D --name-only` is empty — and neither named file exists
on disk or in the index; both went at the thin conversion. The reviewer is
reading generated map rows as the files they name. The findings are also not
stable between runs of the same diff, so a lane cannot rely on dispositioning
one fixed set.

## Requirements

- Determine why a refresh lane can skip `candidatePrepare` and still reach a
  terminal `passed` result, or establish that 0.71.22's lane skipped it for a
  recorded reason.
- Decide where the justification for a mechanical map regeneration belongs so
  the consumer's local gate does not fail on it: the PR body, a changelog entry,
  a Prism allowance, or a smaller regeneration cadence.
- Decide whether the seeded refresh task's own directory should be excluded from
  the generated map, so a lane stops flagging itself.

## Acceptance Criteria

- [ ] The cause of the missed regeneration between 0.71.22 and 0.71.33 is
      identified from lane receipts, not inferred.
- [ ] A refresh lane on a repomix-indexed consumer either passes its local gate
      on a mechanical map regeneration, or fails with a disposition the campaign
      records rather than an operator judging it inline.
- [ ] The recurring seeded-task-directory observation is either suppressed at
      the source or documented as an expected, dispositioned observation.

## Out of scope

- The 0.71.33 rollout itself. That lane dispositioned both observations through
  the fleet finding severity gate as `continue-with-follow-ups` with zero
  blockers, and this task is the follow-up it was required to create.
- Any change to Prism's own thresholds in a consumer repository.

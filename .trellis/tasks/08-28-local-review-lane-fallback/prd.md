# Give the local review stage a lane when codex self-declines

## Goal

Local review should not silently drop to a single lane on the changes this repository makes
most often. The `codex` adapter declines any head that edits an instruction surface it loads,
which on a command-pack repository is routine, leaving `gito` as the only lane and any gito
outage as a total review outage.

## Background

The configured local providers are `codex` (quality tier `deep`) and `gito` (tier `standard`),
both enabled, with `policy.requiredProviders` empty.

`codex` declines with:

```text
the reviewed change edits instruction surfaces codex loads
(.agents/skills/sd-help/references/command-catalog.md), so this lane cannot review it
independently
```

The decline is correct in itself — a reviewer that loads the file under review cannot judge it
independently. The problem is what it leaves behind. `command-catalog.md`, skill bodies, and
their template twins are generated or edited by a large share of this repository's work,
including every release version bump, which regenerates the catalog. On those heads the deep
lane is gone by construction and only `gito` remains.

Because `requiredProviders` is empty, this degrades quietly: the receipt records
`confidence: {"granted": false, "limitations": ["codex:skipped"]}` and the run continues. A
limitation is the correct report, but nothing escalates when the *only* remaining lane then
fails.

## Evidence

Observed on PR #574 (2026-08-28). The head bumped the manifest version, which regenerated
`command-catalog.md` across four trees. `codex` declined; `gito` then hit an upstream credit
limit. Zero lanes produced evidence, and the review could not complete. The head in question
also carried real defects — once gito ran, the reopened review produced three fix commits
(`aa617cd7`, `8fd8305e`, `a0e9f106`) before the remaining findings were accepted as
previously recorded decisions.

## Requirements

- Determine and record which local lanes can review an instruction-surface change without the
  independence problem codex has. At least one option must be viable on such a head.
- When every configured lane declines or is unavailable for structural reasons, the run reports
  that distinctly from "reviewed and found nothing". A zero-lane review must not be able to
  present as a completed review.
- The escalation is proportionate: a single declining lane with another lane healthy stays a
  limitation, as today. Zero usable lanes is the case that changes.
- Whatever fallback is chosen respects the existing decline rule. Do not fix this by having
  codex review surfaces it loads.
- Consider whether `policy.requiredProviders` is the right mechanism, and record why it was or
  was not used. It currently sits empty; making it non-empty has fleet-wide consequences for
  consumers that lack the provider.

## Open question to settle during design

Whether the decline should be narrowed rather than compensated. The current test is whether the
change touches *any* instruction surface codex loads; a narrower test — whether the change
touches a surface that would alter codex's own review behaviour for this diff — might keep the
deep lane on most catalog regenerations, since a version-string bump in a catalog does not
change how the reviewer reasons. This may be the cheaper fix and should be evaluated first.

## Non-goals

- Adding a new external review provider or a new upstream dependency purely as a spare.
- Changing remote routed review, which is a separate stage with its own gate.

## Acceptance Criteria

- [ ] A head that edits only an instruction surface still gets at least one local lane that
      produces evidence.
- [ ] A run in which every lane declines or is unavailable is reported distinctly from a clean
      review, and does not yield a gate state that reads as reviewed.
- [ ] A run with one declining lane and one healthy lane behaves exactly as it does today.
- [ ] The decision on narrowing the decline versus adding a fallback is recorded with its
      reasoning.

## Related

- `.trellis/tasks/08-26-local-provider-failure-masked` — the gito failure that made the
  single-lane exposure visible.

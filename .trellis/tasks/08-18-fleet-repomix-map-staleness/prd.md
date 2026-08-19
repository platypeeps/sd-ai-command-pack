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

## Preferred shape: the repomix map is not tracked code

Operator decision, 2026-08-19. The map and the generator's output are a local
orientation artifact, not source. Untracking the map removes this defect class
rather than patching it: a file that is not in the index cannot drift from the
index, cannot produce a mass-removal diff, and cannot fail a consumer's review
gate on a mechanical regeneration. Every symptom above is downstream of the
decision to commit generated output.

Two repositories already have this shape and neither exhibits the defect:

- `sd-ai-command-pack` itself ships no `docs/repomix-map.md` at all.
- `se-ai-command-pack` generates one and ignores it at `.gitignore:30`, and its
  `repomix.config.json` additionally excludes every pack-managed surface
  (`.claude/**`, `.agents/**`, `.gemini/**`, `.opencode/**`,
  `.sd-ai-command-pack/**`, `.github/prompts/**`, `.obsidian-kb/**`, and more).

The remaining six consumers do not. Surveyed 2026-08-19 by enumerating the
checkouts from `docs/fleet/consumers.json`:

| Consumer | Map tracked | Pack surfaces in map | Generator posture |
| --- | --- | --- | --- |
| se-ai-command-pack | no (`.gitignore:30`) | excluded | `repomix.config.json` ignore list |
| sd-github-review | no map at all | n/a | no repomix |
| hoa-manager | yes | yes | explicitly opts them in by name in `INCLUDE_PATTERNS` |
| mezmo_benchmark | yes | yes | `--no-gitignore --no-dot-ignore`, maps everything |
| rwbp-coordinator | yes | yes | ignores only the artifact, build dirs, secrets |
| loadsmith | yes | yes | ignores only the artifact and the receipt's `docs/` rows |
| rwbp-website | yes | yes | ignores only the artifact |
| anomaly-metric-creator | yes | yes | ignores the artifact and `.trellis/tasks/**` |

The maps are `--no-files` metadata-only, so a pack refresh that only edits file
*contents* never moves them — anomaly-metric-creator's map came back with a zero
diff on 0.71.33. A change to the pack file *set* does move them, and nothing
forces regeneration, so a thin conversion that deletes `.agents/skills/sd-*`
leaves the map lying until some later lane regenerates it. `hoa-manager` is the
most exposed, because it names the pack surfaces in its include list.

### The one real objection, and its remedy

Five of the six map-carrying consumers instruct agents to read the map. Their
root-level AGENTS.md and CLAUDE.md files, and the copilot instructions under
their own `.github/`, reference the generated map path in
rwbp-coordinator (2 references), hoa-manager (3),
anomaly-metric-creator (2), rwbp-website (1), and mezmo_benchmark (1);
loadsmith has none. An untracked map is absent from a fresh clone, a cloud
session, and a remote reviewer's view, so those instructions would point at a
file that is usually not there. Rewriting them belongs in the same change as
the untracking, not after it.

## Requirements

- Untrack `docs/repomix-map.md` in every consumer that tracks it today, and
  exclude the pack-managed surfaces from what the generator indexes, matching
  the `se-ai-command-pack` shape. One pull request per repository; these are
  separate repositories with separate review gates.
- In the same per-repository change, rewrite every agent instruction that tells
  a reader to consult the map so it does not promise a file that a fresh clone
  will not have. Enumerate those references from the filesystem rather than from
  the table above, which is a snapshot.
- Retire the consumer-side gates whose only purpose is defending a tracked map.
  anomaly-metric-creator carries a repomix-map freshness lint under its own
  tools/ directory plus the matching test under its tests/ directory; that
  lint's own docstring says it exists because "nothing regenerates it
  automatically", which untracking resolves at the source. loadsmith reads the
  pack receipt from its review-readiness script under scripts/ for the same
  reason. Enumerate these from each checkout rather than from this list.
- Update this pack's publish path to stop treating the map as work-commit
  content: `DEFAULT_ALLOWED_EXACT` in
  `scripts/sd-ai-command-pack-fleet-publish.py`, the generator ordering, and
  `tests/test_fleet_publish.py`. Leave the `.gitignore` / `.obsidian-kb` half of
  that contract intact — it is unaffected.
- Update `.trellis/spec/tooling/fleet-publish-generated-content.md`, which is
  written around `docs/repomix-map.md` landing in the work commit. The ordering
  rule it establishes still holds for the ignore block; the map is no longer an
  instance of it.
- Determine why a refresh lane can skip `candidatePrepare` and still reach a
  terminal `passed` result, or establish that 0.71.22's lane skipped it for a
  recorded reason. This stays in scope: an untracked map hides the symptom, and
  a lane that silently skips a prepare step is a defect in its own right.

## Acceptance Criteria

- [ ] No consumer tracks `docs/repomix-map.md`. Verified by enumerating the
      checkouts from `docs/fleet/consumers.json` and running `git ls-files
      docs/repomix-map.md` in each, expecting zero output everywhere.
- [ ] No consumer's generated map indexes a pack-managed surface. Verified by
      regenerating each map and grepping it for `.claude/`, `.agents/`,
      `.gemini/`, `.opencode/`, `.github/prompts/`, and `.sd-ai-command-pack/`,
      expecting no directory-structure rows for any of them.
- [ ] No agent instruction file in any consumer directs a reader to a map path
      that a fresh clone does not contain. Verified by grepping each checkout's
      root-level AGENTS.md and CLAUDE.md and its copilot instructions file for
      the generated map path, across the enumerated checkouts.
- [ ] A fleet refresh lane on a formerly map-tracking consumer completes without
      the map appearing in its diff at all.
- [ ] The cause of the missed regeneration between 0.71.22 and 0.71.33 is
      identified from lane receipts, not inferred.
- [ ] This pack's publish path and its generated-content spec no longer claim
      the map belongs in the work commit, and `tests/test_fleet_publish.py`
      passes against the changed behavior.

## Out of scope

- The 0.71.33 rollout itself. That lane dispositioned both observations through
  the fleet finding severity gate as `continue-with-follow-ups` with zero
  blockers, and this task is the follow-up it was required to create.
- Any change to Prism's own thresholds in a consumer repository.
- Excluding pack-installed payload from the Obsidian KB. That is the operator's
  second decision from the same 2026-08-19 review and shares this one's survey,
  but it lands in `scripts/sd-ai-command-pack-update-spec-kb.py`, touches no
  consumer's tracked tree, and is verified differently. It belongs in its own
  task.

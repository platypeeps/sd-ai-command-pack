# Close drift-gate absence blindness and refresh dogfood copies

## Goal

Make the pack's drift/parity safety net catch *missing* artifacts, not
just diverged ones, and bring the pack repo's own installed adapter copies
back in sync with the shipped templates — so the documented
"byte-verified mirrors" guarantee is actually true.

## Problem

Several parity guards pass while the repo is wrong:

- **Missing twins are skipped, not failed.** `test_tracked_pack_targets_match_templates`
  (`tests/test_pack_drift.py:61-62`) does `if not installed.exists(): continue`,
  so only existing twins are byte-compared (floor `compared >= 50`, ~76 of
  342 non-managed targets). Deleting or never-installing a twin never fails
  the drift gate.
- **The pack's own dogfood copies are stale.** Root `.claude/commands/sd/`
  and `.gemini/commands/sd/` have 11 of 13 commands (missing `work-backlog`
  AND `work-designs`); `.opencode/commands/` and `.github/prompts/` are
  missing `work-designs`. Only `.agents/skills/` is current. This session's
  own skill list confirms the absence.
- **Docs claim a guarantee the tests don't enforce.**
  `.github/copilot-instructions.md:3-9` and `AGENTS.md:30-31` state root
  copies are "byte-verified mirrors" of `templates/**`; that is currently
  false, and copilot-instructions also cites a `.zcode/` path that does not
  exist in this repo.
- **templates→manifest completeness is unpinned.** Today 96 tracked
  template sources == 96 manifest sources (verified by hand), but nothing
  fails when an orphan `templates/**` file lands that no manifest entry
  ships. The reverse direction (manifest source exists) *is* tested.
- **Target uniqueness is case-sensitive** (`test_generated_parity.py:733`
  builds a `{file.target}` set) while every consumer runs case-insensitive
  APFS; two targets differing only by case would pass yet collide on
  install.

## Requirements

- R1: For every platform directory that exists at the pack root, the drift
  test requires *all* of that platform's manifest targets to exist and be
  byte-identical to their source — absence is a failure, not a skip.
- R2: Add a completeness assertion: `set(git ls-files templates)` (the
  tracked payload sources) equals `{f.source for f in manifest}`. An orphan
  template or a manifest source with no tracked file fails.
- R3: Add a casefold-uniqueness assertion on manifest targets so
  case-only collisions fail on case-sensitive CI.
- R4: Refresh the pack's own installed copies (`python3 install.py . --force`
  or the release/housekeeping flow) so all root adapters carry all 13
  commands; commit the new files.
- R5: Correct the docs: either enforce presence for all named platforms and
  keep the "byte-verified mirrors" wording, or reword to "existing root
  copies are byte-verified" and remove the non-existent `.zcode` reference
  (`.github/copilot-instructions.md`, `AGENTS.md`).

## Acceptance Criteria

- [ ] Drift test fails when a known twin is deleted from the pack repo
      (add a negative test or manual verification note).
- [ ] Completeness + casefold assertions added and green.
- [ ] All root platform adapters contain all 13 commands; a fresh
      `install.py . --dry-run` reports zero changes afterward.
- [ ] Docs no longer overstate the mirror guarantee and cite no
      non-existent paths.
- [ ] Full suite + full-check pack-drift gates green.

## Non-goals

- Building a generator that derives the four bespoke adapter sets
  (`.claude`/`.gemini`/`.opencode`/`.github`) from the neutral source —
  tracked separately (see the parity discussion in the review); this task
  only closes the *absence* blind spot and re-syncs the copies.

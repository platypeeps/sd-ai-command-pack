# Split sd-review-pr skill into router plus reference steps

## Goal

Cut the per-invocation context cost of the `sd-review-pr` skill by restructuring
its 815-line / 37,244-byte `SKILL.md` into a thin router that loads only the step
detail the current run needs, with the remaining step bodies moved into
on-demand `reference/` files.

Today the whole file loads on every invocation even when the run only needs one
step (for example a step 5 comment sweep on an already-resolved PR). Estimated
saving is roughly 8k tokens per review cycle that does not traverse all eight
steps.

## Background

- Canonical source: `templates/.agents/skills/sd-review-pr/SKILL.md` (815 lines).
- `manifest.json` maps that one source to **12 mirror targets**
  (`.agents`, `.agent`, `.claude`, `.codebuddy`, `.devin`, `.factory`,
  `.kilocode`, `.kiro`, `.pi`, `.qoder`, `.reasonix`, `.trae`).
- The command surfaces (`templates/.commands/sd-review-pr.md`, 46 lines;
  `templates/.github/prompts/sd-review-pr.prompt.md`, 48 lines) are thin
  pointers, **not** copies of the skill body — they are unaffected by the split.
- No skill in this pack currently ships a `reference/` subdirectory
  (0 `manifest.json` entries contain `/reference/`), so this task establishes
  the first progressive-disclosure precedent for the pack.

Current top-level structure of `SKILL.md`:

| Section | Line |
|---|---|
| Standing GitHub authority / Completion boundary / Sandbox-safe tool execution / Structured decisions / Invocation Mode / Safety Rules | 15–137 |
| Step 1: Resolve PR And Local State (incl. Fleet Integration-Only Recheck) | 138–222 |
| Step 1.5: Post-Merge Handoff | 223–247 |
| Step 2: Run Typed Deterministic Check | 248–270 |
| Step 2.5: Disposition First-Review Advisories | 271–302 |
| Step 3: Decide Whether To Trigger Remote Review | 303–406 |
| Step 4: Wait For Review Completion | 407–482 |
| Step 5: Inspect Comments, Prior Threads, And CI | 483–595 |
| Step 6: Reply, Resolve, Fix, Commit, And Push | 596–657 |
| Step 7: Repeat Or Stop | 658–690 |
| Step 7.5: Capture Review Learnings Once | 691–713 |
| Step 8: Finish Work Or Hand Off To The Merge Tail | 714–782 |
| Final Report | 783–815 |

## Requirements

### Functional

- `SKILL.md` retains everything that must be in context for **every** run:
  standing GitHub authority, completion boundary, sandbox-safe tool execution,
  structured decisions, invocation mode, safety rules, the step map, and the
  final-report contract.
- Each step body moves to a `reference/` file the router loads by name at the
  point that step begins.
- Routing instructions are explicit enough that an agent never has to guess
  which reference file a step needs, and never needs to load all of them to
  find one.
- Loop-back steps (step 7 returning to step 2/5) route correctly without
  reloading unrelated step files.
- No behavioral change to the review loop: same gates, same authority scope,
  same stop conditions, same report shape.

### Packaging

- Every new `reference/` file is registered in `manifest.json` across all 12
  skill mirror targets, matching the existing `SKILL.md` target set exactly.
- Mirrors under `.claude/skills/` and the other 11 surfaces regenerate from the
  canonical template; no hand-edited drift.
- Manifest version bumped, release-hygiene surfaces regenerated.

### Constraints

- Do not change the command surfaces unless a step name changes.
- Do not weaken or restate the standing-authority language during the move; it
  is copied verbatim or left in `SKILL.md`.
- Splitting must not fragment a single gate across two files such that an agent
  can act on half a gate.

## Open questions (resolve in design)

- Does the installer (`installer/fileops.py`, `installer/manifest.py`) already
  handle nested subdirectories inside a skill directory, or does adding
  `reference/` require installer changes? Manifest entries are explicit paths,
  so this is likely a no-op, but it is unverified.
- Do `tests/test_generated_parity.py` and `tests/test_surface_generation.py`
  assume one file per skill directory?
- Granularity: one file per step (~12 files × 12 targets = 144 new manifest
  entries) versus grouped phases (for example `reference/steps-1-2.md`,
  `reference/steps-3-4.md`, `reference/steps-5-7.md`, `reference/step-8.md`).
  Fewer files means less manifest churn but coarser loading.

## Acceptance Criteria

- [ ] `templates/.agents/skills/sd-review-pr/SKILL.md` is under 250 lines and
      contains the always-loaded sections plus a step map with explicit
      reference-file routing.
- [ ] Every step body from the table above is present in exactly one
      `reference/` file, with no content dropped — verified by diffing the
      concatenation of router plus reference files against the pre-split body.
- [ ] `manifest.json` registers each new reference file against all 12 skill
      mirror targets; a script or test asserts the target set matches
      `SKILL.md`'s.
- [ ] Manifest version bumped and release-hygiene surfaces regenerated.
- [ ] `make test` passes, including `test_generated_parity`,
      `test_surface_generation`, `test_install_core`, and `test_install_audit`.
- [ ] Mirror sync is clean: regenerating surfaces produces no diff.
- [ ] A dry-run walkthrough of one review cycle confirms the router reaches
      steps 1 through 8 and the step 7 loop-back without ambiguity.

## Notes

- Complex enough to need `design.md` (granularity decision, installer/test
  impact, routing contract) and `implement.md` (ordered split, manifest
  regeneration, verification) before `task.py start`.
- Source of this task: context audit on 2026-08-05, which measured skills at
  9.4k idle tokens and flagged `sd-review-pr` as the largest single skill in
  the pack.

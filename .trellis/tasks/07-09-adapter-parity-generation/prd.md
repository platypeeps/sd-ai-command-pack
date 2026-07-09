# Enforce adapter content parity and generate command fan-out

## Goal

Replace parity-by-convention with parity-by-construction for the per-platform
command adapters. Today four bespoke adapter sets plus a hand-edited 343-entry
manifest are kept in sync by marker-string checks that already let drift
through; this task makes the shared command body single-sourced and pins (or
generates) the rest.

## Problem

PR #74 moved shared command bodies to a neutral source
(`templates/.commands/sd-*.md`, 13 files) that fans out via plain manifest
mapping to 10 "thin" platforms (cursor/antigravity/codebuddy/devin/droid/
kilo/pi/qoder/trae/zcode) with no transformation. Four platforms keep bespoke
hand-maintained sets: `.claude`, `.gemini` (TOML), `.opencode` (md),
`.github` (prompt.md). Problems CONFIRMED in the review:

- **Parity tests check marker strings only.**
  `tests/test_generated_parity.py:830-889`
  (`test_adapters_reference_installed_shared_assets`) asserts anchor phrases
  ("Resolve the `sd-X` skill by name" + one or two strings), not body content;
  gemini descriptions are pinned in a hand-duplicated dict (lines 953-966).
- **Drift already exists.** `templates/.opencode/commands/sd-review-learnings.md`
  differs from the neutral `templates/.commands/sd-review-learnings.md` in
  description and a body sentence — introduced during PR #74 itself, invisible
  to every test. The other 12 opencode files are byte-identical to the neutral
  source.
- **Copilot housekeeping prompt semantically lags the neutral source.**
  `templates/.github/prompts/sd-housekeeping.prompt.md:16-18` lacks the
  neutral source's pre-authorization sentence and expanded ambiguity list
  present in `templates/.commands/sd-housekeeping.md`; Claude/Gemini/OpenCode
  match the neutral text — GitHub is the lone outlier after PR #74.
- **Adding a command is a ~19-file / 26-manifest-entry hand edit.** Commit
  631f1f0 (sd-work-designs) added 26 hand-written manifest entries and still
  missed CHANGELOG + 4 dogfood copies. The 10-platform fan-out is mechanical
  and should be derived from the platform registry, not typed.

This is the architecturally weighty parity item deliberately left out of
`07-09-drift-gate-absence-blindness` (which only closes the *absence* blind
spot).

## Requirements

- R1: Collapse the opencode command set onto the neutral source where it is
  already byte-identical (12/13) — point those manifest entries at
  `templates/.commands/` and delete the near-duplicate files; reconcile the
  one genuinely divergent file (`sd-review-learnings`) by either adopting the
  neutral text or documenting why opencode differs.
- R2: Reconcile the copilot `sd-housekeeping` prompt with the neutral source,
  or add a comment/record explaining the intended platform deviation.
- R3: Add structural parity enforcement for the bespoke sets
  (`.claude`/`.gemini`/`.github`): extract the shared command body and compare
  it to the neutral source, rather than only asserting marker phrases — so a
  future body divergence fails a test.
- R4: Derive the 10 thin-platform fan-out manifest entries for a command from
  the platform registry (which already encodes each platform's directory
  layout), so adding a command does not require hand-writing per-platform
  entries. Add a test that the generated/derived entries match the manifest.

## Acceptance Criteria

- [ ] opencode command set single-sourced from `templates/.commands/` (near-
      duplicates removed); the `sd-review-learnings` divergence resolved.
- [ ] copilot housekeeping prompt reconciled or its deviation recorded.
- [ ] A parity test fails when a bespoke adapter's shared body diverges from
      the neutral source (demonstrated with a temporary edit).
- [ ] Thin-platform manifest entries for a command are registry-derived and
      test-pinned; a scratch "add a command" touches materially fewer files.
- [ ] Full suite + full-check pack-drift/parity gates green; installed output
      byte-identical to pre-change for unaffected platforms.

## Non-goals

- Templating the deep per-platform format differences (Claude frontmatter,
  Gemini TOML) into a single generator — R3 pins the *shared body*, it does
  not unify the wrappers.
- Manifest-section schema work (tracked by
  `07-09-platform-registry-manifest-sections`); R4 derives entries under the
  current flat schema.

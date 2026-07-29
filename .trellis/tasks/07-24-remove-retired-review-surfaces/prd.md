# Remove all retired review and check surfaces

## Goal

Complete the clean cutover by deleting every obsolete review/check/watch skill,
adapter, script, configuration contract, reader, help entry, manifest target,
documentation claim, and generated artifact. Nothing retired remains callable or
executable through an alias, wrapper, fallback, or dormant mode.

## Confirmed Evidence

- The predecessor surface includes `sd-full-check`, `sd-review-local`,
  `sd-review-pr`, and `sd-watch-pr`, plus 79 review/full-check manifest targets,
  generated platform adapters, scripts, environment-variable families, help and
  guide entries, package hooks, tests, and consumer receipts.
- Parent R13-R15, R18, R22, and R29 already require an intentionally
  non-backward-compatible cutover and provenance-aware installed-target removal.
- The user explicitly accepted removal of all legacy/obsolete code and features
  to produce one streamlined experience.

## Dependencies And Boundaries

- Parent: `07-22-integrate-routed-review-backends`.
- Must run only after `07-24-implement-read-only-sd-check`,
  `07-24-implement-unified-routed-sd-review`, and
  `07-24-simplify-review-shipping-composition` have landed and all live callers
  use the successor contracts.
- Provenance-aware uninstall metadata may name retired paths solely to remove
  verified installed copies. Historical archived Trellis records may retain
  evidence. Neither is a callable compatibility surface.
- Coordinates with `07-28-retire-transitional-review-surfaces`, which owns the
  schedule half: pre-registering `RetiredCommandSurface` rows with an explicit
  `removed_version`, the transitional catalog status, and the interim fixes that
  apply while the predecessor still ships. That task names the version; this task
  executes the deletion against it.

## Requirements

- R1: Remove live skills, commands, prompts, workflows, adapters, scripts, and
  registry entries for `sd-full-check`, `sd-review-local`, `sd-review-pr`, and
  `sd-watch-pr` across every supported platform.
- R2: Remove the old full-check/review-local/review-pr environment-variable
  families, package `check:full` hook, shell-string command readers, direct
  Copilot/custom-remote dispatch, reviewer-author matching, and old output/state
  formats. Do not leave ignored readers for migration convenience.
- R3: Remove old help/catalog/examples, README/guide/spec claims, workflow names,
  tests that pin retired behavior, manifest targets, installed receipts,
  provenance entries, and candidate-ledger expectations. Replace only with
  successor documentation and behavioral tests.
- R4: Register every old installed target with the provenance-aware retirement
  mechanism. Refresh deletes unchanged vouched copies, preserves and reports a
  locally modified copy, prunes empty directories, and never records retired
  paths in the new receipt.
- R5: Add a live-surface drift lint with an explicit minimal allowlist for
  archive/history and removal metadata. Comments, fixtures, environment names,
  aliases, redirects, wrappers, hidden flags, and compatibility modes count as
  live legacy when they can influence runtime behavior.
- R6: Remove dead helpers, branches, parsing code, tests, and documentation made
  unreachable by the cutover; do not keep unused abstractions for speculative
  rollback. Rollback installs the last pre-cut release.
- R7: Verify all public callers use only `sd-check`, `sd-review`, `sd-create-pr`,
  `sd-ship`, and `sd-housekeeping` according to their orthogonal authority.

Added 2026-07-28 — audit findings this task owned but did not cover:

- R8 (A-045): Bind R4's registration to the `removed_version` pre-registered by
  `07-28-retire-transitional-review-surfaces`. Do not mint a second version.
  `installer/registry.py:1244-1271` shows every existing `RetiredCommandSurface`
  row carries a `removed_version` and none of the four transitional surfaces do,
  so until that row exists this task has no schedule to execute against and the
  removal cannot be verified as the one that was announced.
- R9 (A-059): Relocate — do not merely delete — the fleet recheck procedure
  embedded at `templates/.agents/skills/sd-review-pr/SKILL.md:196`. It invokes
  `fleet-review-classify.py`, which `scripts/sd-ai-command-pack-install-audit.py:115`
  marks source-only, so those ~22 lines are unreachable in all 11 shipped platform
  copies of the skill (`manifest.json` maps this one source to 11
  `*/skills/sd-review-pr/SKILL.md` targets). Deleting the skill removes the dead copies but loses the procedure: move
  it into the source-only `sd-fleet-refresh` skill first, then delete.
- R10 (A-043): Enumerate the environment-variable families R2 removes and delete
  the lanes they gate in the same change. `Makefile:92` hard-disables the AI
  review lanes with `PRISM=0 GITO=0`, which makes roughly a quarter of
  `scripts/sd-ai-command-pack-full-check.sh` unreachable in this repo's own
  canonical gate: the prism lane at `:296` (~125 lines), the CI-classification
  block at `:935` whose resolver at `:923` targets a `scripts/classify-ci-changes.sh`
  with zero commits in `git log --all`, the package-script block at `:1038` with
  no root package.json, and the legacy `check-review-preflight.mjs` fallback at
  `:978`. Remove
  the `PRISM=0 GITO=0` disabling at the same time so no gate keeps passing by
  never running.
- R11 (A-102, A-114): These two findings die with the script and skill this task
  deletes. Record that explicitly rather than leaving them to be rediscovered —
  the gito filter argv overflow at `full-check.sh:231/:256/:261/:454` (measured at
  142,524 joined bytes, past Linux `MAX_ARG_STRLEN`) and the stale
  `sd-full-check/SKILL.md:32,:104` contract are resolved by deletion, not by a
  fix here. If the removal slips past the announced `removed_version`, their
  interim fixes belong to `07-28-retire-transitional-review-surfaces`, not here.

## Acceptance Criteria

- [ ] Fresh installs and help/catalog discovery expose no retired command or
  identifier on any supported platform.
- [ ] Upgrade from the last pre-cut release removes every unchanged vouched old
  target, preserves/reports a modified old target, and produces a receipt that
  contains only the new surface.
- [ ] Repository-wide live-surface scanning finds no executable old skill,
  adapter, script, environment reader, package hook, direct remote dispatch,
  hidden mode, alias, redirect, or fallback.
- [ ] The installed audit rejects any reintroduced retired target or runtime
  reader; command-surface drift lint fails on stale docs/specs as well as code.
- [ ] Dead-code and manifest/provenance checks confirm obsolete implementation
  branches and tests were deleted rather than skipped or disabled.
- [ ] Focused retirement/upgrade tests, all generated parity checks, candidate
  fleet validation, `make sync`, and `make check` pass.
- [ ] Every retired surface's registry row carries the same `removed_version`
  that was pre-registered before deletion; no row is created without one.
- [ ] The fleet recheck procedure is reachable from the source-only
  `sd-fleet-refresh` skill after the shipped `sd-review-pr` skill is gone.
- [ ] No `PRISM`/`GITO`/full-check environment key survives in the Makefile, in
  any script, or in any generated mirror, and no lane remains that only passes
  because it never executes.

## Out Of Scope

- Backward-compatible aliases, deprecation windows, forwarding scripts, dormant
  readers, or dual old/new operation. Pre-registering a `RetiredCommandSurface`
  row with a `removed_version` is not a deprecation window: it is the existing
  provenance-aware retirement register R4 already requires, and it keeps the
  predecessor no longer working, only announced.
- Deleting historical archived task evidence or the minimal installer removal
  metadata needed for safe cleanup.
- Merging the command-pack and router repositories.

## Notes

- Rollback is release-level reinstall, not legacy code retained in the new
  release.
- 2026-07-28 audit source: `.trellis/audit/report-2026-07-28.md`. This task was
  the nominal owner of five findings — A-045, A-114, A-102, A-059, A-043 — and
  covered none of them, because R1-R7 describe deletion with no removal version,
  no pre-registered retirement rows, no schedule, and no interim behavior. R8-R11
  close that gap; the schedule itself lives in
  `07-28-retire-transitional-review-surfaces`.
- A-059's substance survives deletion: the fleet recheck procedure is real work
  shipped to the wrong audience, so R9 relocates it rather than treating deletion
  as the fix.
- **Scale corrected 2026-07-28.** Confirmed Evidence says "79 review/full-check
  manifest targets"; measured 105 entries across `manifest.json`'s 754 files, of
  which 92 are the four `sd-`-prefixed families (23 each). Recount before sizing.
- **Unrecorded consequence, found 2026-07-28.** `Makefile:94` is
  `check: test lint audit full-check`, and R1 deletes the script that target
  runs. Every acceptance criterion here says "`make check` passes", so the
  replacement composition must be decided before the first deletion commit.
  `design.md` carries the two options.
- **R10 is not separable from R1.** `Makefile:92` hard-disables the prism and gito
  lanes with `SD_AI_COMMAND_PACK_FULL_CHECK_PRISM=0` /
  `SD_AI_COMMAND_PACK_FULL_CHECK_GITO=0`. Removing that disabling without
  deleting the lanes enables code that has never executed in this repo's gate.
- Planning complete 2026-07-28: `design.md` and `implement.md` added.

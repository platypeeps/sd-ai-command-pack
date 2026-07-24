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

## Out Of Scope

- Backward-compatible aliases, deprecation windows, forwarding scripts, dormant
  readers, or dual old/new operation.
- Deleting historical archived task evidence or the minimal installer removal
  metadata needed for safe cleanup.
- Merging the command-pack and router repositories.

## Notes

- Rollback is release-level reinstall, not legacy code retained in the new
  release.

# Name a removal version for the transitional review surfaces

## Goal

Give the remaining transitional review surfaces a forcing function — an
explicit removal version and a machine-readable transitional catalog status —
so successor guarantees actually apply on the main delivery path.

**Scope refresh 2026-07-31.** The original four surfaces are now three:
`sd-watch-pr` was retired at 0.57.0 by `07-24-simplify-review-shipping-composition`
(full `RetiredCommandSurface` row at `installer/registry.py:1315-1322`, skill
deleted, catalog row gone). The composite-orchestrator repoint (R7) also landed:
`.agents/skills/sd-ship/SKILL.md` no longer mentions `sd-review-pr`. Remaining
surfaces: `sd-full-check`, `sd-review-local`, `sd-review-pr`.

## Requirements

- Pre-register `RetiredCommandSurface` rows with an explicit `removed_version` for the three remaining transitional surfaces — `installer/registry.py:1288-1322` shows every existing row carries one (four rows as of 2026-07-31, including the landed `sd-watch-pr` row), and none of these three do.
- Give the machine catalog a transitional / superseded-by status — the three transitional rows read `included in installed pack`, identical to a live command, so sd-help keeps recommending the legacy commands. (2026-07-31 lines: `sd-review-local` at `command-catalog.md:40`, `sd-full-check` at `:43`, `sd-review-pr` at `:54`.)
- ~~Add a current-path decision point to the recommended review loop~~ — **landed via `07-24-simplify-review-shipping-composition` R8** (verified 2026-07-31: `docs/SD_AI_COMMAND_PACK.md:340-346` routes an `sd-ship` chain to publish-and-return and only a standalone invocation to the transitional loop). Verify-only here; do not duplicate.
- Add a CHANGELOG deprecation note, as `CONTRIBUTING.md:156` requires ("Keep deprecated public aliases documented until the removal release ... note the removal in `CHANGELOG.md`").
- Decide the fate of the two parallel orchestration implementations: `review-local.sh` and `review-local.py`. **Decided 2026-07-31:** `review-local.py` is a live dependency of the successor — `scripts/sd-ai-command-pack-review.py:34` binds it as `LOCAL_SCRIPT` (the routed local lane's engine) — so it is *not* covered by the removal version. Only `review-local.sh` (the transitional `sd-review-local` command's standalone orchestrator, which never calls the `.py`) retires with the surfaces.

## Acceptance Criteria

- [x] Every transitional surface has a `removed_version` recorded in the registry.
- [x] `sd-help` reports the transitional status for the legacy commands.
- [x] `make check` passes.

## Notes

- Source: `.trellis/audit/report-2026-07-28.md` — finding A-045 (P2 · L · Plausible · architecture).
- This task covers the *deadline and interim* half. Deletion itself is owned by `07-24-remove-retired-review-surfaces` (R1/R3/R4) and `07-24-simplify-review-shipping-composition` (R5) — coordinate rather than duplicate.
- Ownership decided 2026-07-28: the `sd-ship` Stage 2 repoint belongs to `07-24-simplify-review-shipping-composition` R7, not here. It was removed from the requirement list above because it is not a one-line reference edit — `.agents/skills/sd-ship/SKILL.md:133-136` branches Stage 2 on `defer-finish-work` per `until=` value and `.agents/skills/sd-review/SKILL.md:73` forbids the successor from archiving Trellis work, so the repoint owes a finish-work/Stage 3 design that R7 now carries. **Dependency: the pre-registered `removed_version` this task creates assumes the main delivery path has already moved, so land R7 first.**
- Those tasks are tracked-stale precisely because they name no removal version and add no transitional catalog status.
- README.md:274 calls the surfaces transitional in prose; no removal version exists anywhere in the repo.
- **Disposition decided 2026-07-31 (implement.md final review gate):** this task carries no interim fixes for A-114 (stale sd-full-check SKILL contract), A-102 (gito filter argv overflow), A-059 (dead fleet block in the shipped sd-review-pr skill), or A-043 (unreachable full-check lanes) — its scope is the registry rows, catalog status, and sd-help routing only. All four stay open, **resolved by deletion at 0.62.0** (owned by `07-24-remove-retired-review-surfaces`), not by this task.
- **Citation corrected 2026-07-28.** A-045 attributes the catalog evidence to the `sd-review-pr` row at `command-catalog.md:40`. Line 40 is `sd-review-local`; `sd-review-pr` was at `:55` then. The claim held for both, and the catalog work covered four rows at the time. (Superseded by the 2026-07-31 refresh: three rows, current lines in the requirement above.)
- **R1 is not a free annotation, found 2026-07-28.** `RetiredCommandSurface.source_paths_must_be_absent` defaults to `True`, and `check-command-surface-drift.py:632-646` (cites re-verified 2026-07-31) then reports `retired_identifier_live` for every `installed_target` that still exists. `identifiers` is additionally scanned as text repo-wide (`:508-537`), needing a `CommandSurfaceAllowance` per hit — the already-deleted `sd-review-local-all` needed six. The manifest pass (`:449-462`) needs the flag taught to it — `design.md` and `implement.md` step 4 carry that. Use the `fleet-refresh-consumer-targets` schedule-only shape (`identifiers=()`, `source_paths_must_be_absent=False`); `design.md` carries the reasoning.
- Adding a row does **not** cause install-time deletion: `RETIRED_TARGETS` (`installer/removal.py:65-75` as of 2026-07-31) is a hand-maintained tuple of four named alias groups, not a comprehension over the registry.
- Created from the 2026-07-28 repo audit with explicit user consent via the `audit.followups` decision. Planning complete 2026-07-28: `design.md` and `implement.md` added.
- **Planning refresh 2026-07-31 (work-loop iteration 10).** Blocking prerequisite verified: `grep -n "sd-review-pr" .agents/skills/sd-ship/SKILL.md` returns no hits — R7 landed. Scope is three surfaces (see Goal). The README.md:274 "transitional" prose claim is stale — README no longer says it; the only remaining transitional prose is `docs/SD_AI_COMMAND_PACK.md:344` (the R8 decision point itself). Removal version chosen: **0.62.0** — this task ships at 0.60.0 (minor: catalog semantics + public registry additions), leaving one buffer minor for interleaved work; `07-24-remove-retired-review-surfaces` reuses exactly this number per its R8, and if deletion slips past 0.62.0 the deletion task updates the inert rows rather than minting a second announcement.

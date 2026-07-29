# Name a removal version for the transitional review surfaces

## Goal

Give the four transitional review surfaces a forcing function and stop the composite orchestrator from wiring the predecessor, so successor guarantees actually apply on the main delivery path.

## Requirements

- Pre-register `RetiredCommandSurface` rows with an explicit `removed_version` for the transitional surfaces — `installer/registry.py:1244-1271` shows every existing row carries one, and none of these do.
- Give the machine catalog a transitional / superseded-by status — all four transitional rows read `included in installed pack`, identical to a live command, so sd-help keeps recommending the legacy commands. (`command-catalog.md:40` is `sd-review-local`; `sd-review-pr` is at `:55`.)
- Add a current-path decision point to the recommended review loop (`docs/SD_AI_COMMAND_PACK.md:194`), which today interleaves successor and transitional steps across 18 steps.
- Add a CHANGELOG deprecation note, as `CONTRIBUTING.md:142` requires.
- Decide the fate of the two parallel orchestration implementations: `review-local.sh` (771 lines of bash) and `review-local.py` (2,232 lines).

## Acceptance Criteria

- [ ] Every transitional surface has a `removed_version` recorded in the registry.
- [ ] `sd-help` reports the transitional status for the legacy commands.
- [ ] `make check` passes.

## Notes

- Source: `.trellis/audit/report-2026-07-28.md` — finding A-045 (P2 · L · Plausible · architecture).
- This task covers the *deadline and interim* half. Deletion itself is owned by `07-24-remove-retired-review-surfaces` (R1/R3/R4) and `07-24-simplify-review-shipping-composition` (R5) — coordinate rather than duplicate.
- Ownership decided 2026-07-28: the `sd-ship` Stage 2 repoint belongs to `07-24-simplify-review-shipping-composition` R7, not here. It was removed from the requirement list above because it is not a one-line reference edit — `.agents/skills/sd-ship/SKILL.md:133-136` branches Stage 2 on `defer-finish-work` per `until=` value and `.agents/skills/sd-review/SKILL.md:73` forbids the successor from archiving Trellis work, so the repoint owes a finish-work/Stage 3 design that R7 now carries. **Dependency: the pre-registered `removed_version` this task creates assumes the main delivery path has already moved, so land R7 first.**
- Those tasks are tracked-stale precisely because they name no removal version and add no transitional catalog status.
- README.md:274 calls the surfaces transitional in prose; no removal version exists anywhere in the repo.
- Landing this also resolves A-114 (stale sd-full-check SKILL contract), A-102 (gito filter argv overflow), A-059 (dead fleet block in the shipped sd-review-pr skill) and A-043 (unreachable full-check lanes) if the interim fixes are included; otherwise those remain open until deletion lands.
- **Citation corrected 2026-07-28.** A-045 attributes the catalog evidence to the `sd-review-pr` row at `command-catalog.md:40`. Line 40 is `sd-review-local`; `sd-review-pr` is at `:55`. The claim holds for both, and the catalog work covers four rows, not one.
- **R1 is not a free annotation, found 2026-07-28.** `RetiredCommandSurface.source_paths_must_be_absent` defaults to `True`, and `check-command-surface-drift.py:564-577` then reports `retired_identifier_live` for every `installed_target` that still exists. `identifiers` is additionally scanned as text repo-wide (`:436-468`), needing a `CommandSurfaceAllowance` per hit — the already-deleted `sd-review-local-all` needed six. Use the `fleet-refresh-consumer-targets` schedule-only shape (`identifiers=()`, `source_paths_must_be_absent=False`); `design.md` carries the reasoning.
- Adding a row does **not** cause install-time deletion: `RETIRED_TARGETS` (`installer/removal.py:69-73`) is a hand-maintained tuple of three named aliases, not a comprehension over the registry.
- Created from the 2026-07-28 repo audit with explicit user consent via the `audit.followups` decision. Planning complete 2026-07-28: `design.md` and `implement.md` added.

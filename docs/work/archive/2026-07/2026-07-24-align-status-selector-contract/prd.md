---
title: Align status and housekeeping selector contracts
status: done
created: 2026-07-24
---
# Align status and housekeeping selector contracts

## Goal

Resolve review finding `1.1.1` by removing the obsolete `R-*` selector and
Roadmap-section contract from every live status and housekeeping surface while
preserving untracked roadmap-file items as `F-*` follow-ups.

## Confirmed Evidence

- `templates/.agents/skills/sd-status/SKILL.md:68-81` defines only `F-*` and
  `T-*`, but lines 134-138 still accept an `F/T/R` identifier.
- `templates/.agents/skills/sd-housekeeping/SKILL.md:75-77` still describes the
  delegated result as containing `F/T/R` selectors.
- `07-23-status-untracked-roadmap-items` intentionally removed the separate
  Roadmap section and routed unmatched roadmap-file tasks into Follow-ups.

## Dependencies And Boundaries

- Parent: `07-24-correct-sd-skill-contract-drift`.
- Preserve the current status JSON schema, complete Trellis task inventory,
  read-only behavior, roadmap-source discovery, and deterministic `F-*`/`T-*`
  ordering.
- Do not reintroduce a third category for compatibility.

## Requirements

- R1: Remove `F/T/R`, `R-*`, and separate Roadmap-section claims from every live
  skill, command, prompt, guide, generated adapter, test expectation, and active
  program task that describes current behavior.
- R2: Keep `F-*` for evidence-backed follow-ups, including unmatched task-like
  roadmap-file items, and `T-*` for every valid unarchived Trellis task.
- R3: Treat an incoming `R-*` selection as unsupported current input rather than
  silently translating it, restoring a hidden alias, or guessing a task.
- R4: Update status-to-housekeeping typed handoff documentation so both commands
  describe the same selector and empty-section behavior.
- R5: Add a source-drift test that fails when current surfaces mention the
  retired selector contract outside explicitly archived historical records.
- R6: Synchronize templates, root mirrors, generated adapters, docs, release
  metadata, and candidate evidence through the normal pack workflow.

## Acceptance Criteria

- [x] Local status human and JSON output expose only Follow-ups (`F-*`) and Tasks
  (`T-*`); no Roadmap collection or `R-*` selector exists. Verified, not built:
  `select_items` emits `prefix="T"` once and `prefix="F"` twice, no diff to
  `scripts/sd-ai-command-pack-status.py`.
- [x] Housekeeping relays the same F/T inventory without describing or accepting
  a removed category (`sd-housekeeping/SKILL.md:118` now reads `F/T selectors`).
- [x] Untracked roadmap-file tasks still appear as deduplicated `F-*` follow-ups
  with path/line evidence. Unchanged behavior; regression-guarded by
  `tests/test_status.py` (47 tests OK).
- [x] A later `R-1` request returns a precise unsupported/stale-snapshot result
  and performs no mutation. Wording landed as a generic rejection (any selector
  that is not an `F-*`/`T-*` row of the snapshot is unresolved input, no
  action); the behavioral half is skill prose executed by a host model and is
  not machine-verifiable — the greps prove the instruction is present and
  unambiguous, not that a host follows it.
- [x] Live-surface drift validation finds no obsolete F/T/R wording; archived
  task history may retain historical evidence
  (`tests/test_selector_contract_drift.py`, allowlist over shipped roots).
- [x] Focused status/housekeeping tests, template/root parity, `make sync`, and
  `make check` pass (release-prep gate; evidence in session journal).

## Out Of Scope

- Adding fuzzy roadmap-to-task matching.
- Creating tasks during status.
- Preserving `R-*` through an alias, redirect, compatibility reader, or hidden
  machine-only field.

## Notes

- Historical archived Trellis artifacts are evidence, not live command surface.
- Complex task. Planning complete 2026-07-28: `design.md` and `implement.md` added.
- **All three Confirmed Evidence citations are wrong.** Verified 2026-07-28: the
  `F-*`/`T-*` definitions are at `sd-status/SKILL.md:74-89` (not `:68-81`); the retired
  token is at `sd-status/SKILL.md:140` (not `:134-138`); and
  `sd-housekeeping/SKILL.md:75-77` is the `sd-ai-command-pack-pr-eligibility.py` receipt
  contract (`status`, `reasonCodes`, `checks`, `reviewThreads`, `finishWork`,
  `gh pr merge --match-head-commit`), not a selector claim — the real mention is
  `sd-housekeeping/SKILL.md:118`, about 43 lines away. Implementing from the third
  citation edits an unrelated working contract.
- **AC1 is already satisfied; it is a verification, not a deliverable.**
  `select_items(items, prefix=...)` (`scripts/sd-ai-command-pack-status.py:478-481`) is the
  sole producer of `selectionId` and is called exactly three times — `prefix="T"` at `:559`,
  `prefix="F"` at `:1715` and `:2295`. Grep for the retired prefix across `scripts/`,
  `installer/`, `tests/`, and `.github/scripts/` returns nothing.
  `07-23-status-untracked-roadmap-items` finished the code half; only wording survived.
- **R1 overstates the surface by a wide margin.** A repo-wide sweep across
  `*.md`/`*.py`/`*.sh`/`*.mjs`/`*.toml`/`*.json` finds exactly four live hits:
  `templates/.agents/skills/sd-status/SKILL.md:140`,
  `templates/.agents/skills/sd-housekeeping/SKILL.md:118`, and their two byte-identical
  root mirrors. No command, prompt, guide, generated adapter, doc, or test expectation
  carries it. Every other hit is under `.trellis/` — two archived tasks, the journal, and
  three active PRDs (this one, the parent, and `07-22-streamline-sd-skill-workflows:70`)
  that describe the removal rather than current behavior.
- **R3 and R5 collide as written.** Satisfying R3 by stating that the retired selector is
  unsupported puts it back on a live surface, which R5's own drift test must then flag.
  Resolution: reject generically — the skill enumerates `F-*` and `T-*` and treats anything
  else as unresolved input, never naming the retired prefix. This also covers AC4's
  stale-snapshot half (`F-9` against a three-row report), which no current wording handles.
- **R5's test must be an allowlist over the shipped surface, not an exclusion list.** A
  repo-wide grep minus exclusions would have to exempt three active task PRDs today and
  would break the next time anyone documents this history. Scanning only `templates/`, the
  root mirrors, `docs/`, and generated adapters — never `.trellis/` — is correct by
  construction.
- **Undeclared coordination with `07-28-stop-committing-generated-mirrors`.** That task
  deletes the two mirror files. If it lands first this task edits two files instead of
  four, so the drift test must not hardcode mirror paths.

## Reconciliation note (2026-07-25)

- Two additive tasks now also touch the status surface: `07-25-parallelize-fleet-status`
  (collection concurrency) and `07-24-track-clean-recovery-artifacts` R5 (recovery-receipt
  reporting). This contract fix should land first or independently of both; they carry
  matching coordination notes.

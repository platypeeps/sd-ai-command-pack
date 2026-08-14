# Retire sd-review-pr: port the fleet integration-only review profile into sd-review

> Upstream record: issue #399 documents the user-facing half of this: the
> superseded commands carry no supersession signal at the command choice
> point, and the catalog's "transitional until 0.62.0" horizon expired 30+
> releases ago. Completing this removal is that issue's resolution shape 2;
> close #399 with this task's shipping PR. #399 also lists adjacent
> unmarked-transition instances (`sd-full-check`, `sd-create-pr` naming,
> finish-work/housekeeping seam) — disposition them here or record why not.

## Goal

Delete the `sd-review-pr` command surface and everything that survives only for
it, after moving the one capability it uniquely owns — the fleet
integration-only review profile — into `sd-review`. On completion nothing
retired remains callable, and `sd-fleet-refresh` reviews through the successor.

## Why this is a separate task

Split out of `07-24-remove-retired-review-surfaces` on 2026-08-09 after
adversarial planning review found that `sd-review-pr` is not merely a superseded
alias. It is the sole implementation of a trusted nested contract that a live,
production-path caller depends on:

- `templates/.agents/skills/sd-fleet-refresh/SKILL.md:192` invokes
  `sd-review-pr` with `caller: sd-fleet-refresh`,
  `return-after: review-result`, `defer-finish-work: true`.
- `sd-review-pr/SKILL.md` implements that contract across `:64-79` (trusted
  context block and field validation), `:112` (exact-head eligibility
  reclassification), `:196-209` (classifier invocation and exit handling),
  `:226` (deferral cancellation), and profile-specific behavior at `:251`,
  `:273`, `:345`, `:409`, `:486`, `:641`, `:663`, `:675-677`.
- `sd-review/SKILL.md` implements **none** of it — it accepts only public
  `key=value` controls (`:40`).

Deleting the surface without porting the profile would remove the fleet
integration-only review mechanism outright. That is a behavioral migration, not
a deletion, so it gets its own plan, its own review, and its own PR rather than
riding inside a large cutover diff.

## Scope

`07-24-remove-retired-review-surfaces` (Narrow scope, landing first) deletes the
`sd-full-check` and `sd-review-local` command surfaces and
`sd-ai-command-pack-review-local.sh`. This task owns everything it deliberately
left behind:

1. **Port the integration-only profile** into `sd-review`, including the
   trusted-caller context, `classified-head` validation, classifier invocation,
   `defer-finish-work` semantics, and the `review-result` return shape.
2. **Repoint `sd-fleet-refresh`** to `sd-review` and prove the fleet review
   action still works end to end.
3. **Relocate the Fleet Integration-Only Recheck procedure** (R9 of the parent
   PRD) from `templates/.agents/skills/sd-review-pr/SKILL.md:195-217` into the
   source-only `sd-fleet-refresh` skill before deletion. It invokes
   `fleet-review-classify.py`, which `install-audit.py:119` marks source-only,
   so the block is already unreachable in all 11 shipped copies but is the only
   written record of the procedure. `sd-fleet-refresh` ships in neither
   `plugins/sd/skills/` nor the machine payload (verified 2026-08-09), so the
   relocation creates no new plugin-closure exception.
4. **Delete the `sd-review-pr` surface**: 17 live files, 24 manifest rows, the
   2 short-name command rows, and the generated mirrors.
5. **Delete the two full-check scripts** —
   `sd-ai-command-pack-full-check.sh` (1087 lines) and
   `sd-ai-command-pack-review-full-check.sh` (79 lines), ×4 trees
   (`scripts/`, `templates/scripts/`, `plugins/sd/bin/`,
   `plugins/sd/machine-payload/scripts/`).

   **Corrected 2026-08-09:** these are *not* reachable from `sd-review-pr` —
   `sd-review-pr/SKILL.md:262-263` explicitly forbids falling back to either.
   They land in this task for two independent reasons: `full-check.sh` is the
   repo's own gate (`Makefile:98-101`, `.github/workflows/tests.yml:652-659`),
   so deleting it is inseparable from the `make check` recomposition below; and
   `review-full-check.sh` has **no live caller at all** — already orphaned
   before `07-24`, whose R6 reaches only helpers made unreachable *by* its
   cutover. Both belong to the full-check family, and this task is its single
   owner. Neither deletion depends on `sd-review-pr` being gone, so both could
   be split out again if this task grows too large.
6. **Everything that deletion then unblocks** — this is the bulk of the work
   the Narrow scope deferred:
   - **Relocate `run_pack_source_drift_gates`.** It is a *function inside*
     `full-check.sh`, and `.github/workflows/tests.yml:659` runs
     `bash -c 'source scripts/sd-ai-command-pack-full-check.sh; run_pack_source_drift_gates'`.
     `scripts/sd-ai-command-pack-surface-check.py` models `FULL_CHECK` as a
     graph node (`:463,:524,:530,:531`), requires its text
     (`:587,:593,:596`), and asserts the workflow still calls the function
     (`:600`). The gate must move to a surviving home and all three checkers
     must be repointed **before** deletion.
   - **The `make check` composition** (parent design option A):
     `Makefile:98-101` is `full-check:` plus `check: test lint audit
     full-check`. `make` fails at parse time on a prerequisite whose target is
     gone, so the Makefile edit lands in the same commit as the script.
   - **Remove `SD_AI_COMMAND_PACK_FULL_CHECK_PRISM=0 ..._GITO=0`**
     (`Makefile:99`) together with the lanes it disables — inseparable, because
     removing the disabling without deleting the lanes enables code that has
     never run in this repo's gate.
   - **The `FULL_CHECK` environment family** (24 keys) and the
     `SD_AI_COMMAND_PACK_REVIEW_PR_*` family (7 keys, zero executable readers —
     a skill-text contract pinned by
     `tests/test_review_scope.py:1638-1648,1724`).
   - **`tests/test_full_check.py`** (1621 lines) and
     **`tests/test_review_full_check.py`** (254 lines).
   - **The plugin dependency-closure allowlist**:
     `installer/references.py:216` (`PLUGIN_CLOSURE_ALLOWLIST`) and `:222`
     (`MACHINE_CLOSURE_ALLOWLIST`), both keyed on
     `skills/sd-review-pr/SKILL.md → fleet-review-classify.py`, plus the parity
     assertion in `tests/test_generate_plugin.py`. This subsumes task
     `08-09-review-pr-fleet-classifier-ref` — close it as resolved-by-removal.
   - **Audit findings A-102 and A-114**, which die with `full-check.sh` and the
     `sd-full-check` contract: the gito filter argv overflow at
     `full-check.sh:231,:256,:261,:454` (measured 142,524 joined bytes, past
     Linux `MAX_ARG_STRLEN`) and the stale contract text. Mark both
     `resolved-by-removal` in `.trellis/audit/ledger.md` in the deletion commit.

## Requirements

- R1: `sd-review` accepts the integration-only profile with the same trusted
  context fields, validation strictness, and return shape `sd-review-pr`
  implements today. No public argument surface gains these keys.
- R2: `sd-fleet-refresh`'s `review` action invokes `sd-review` and its
  integration-only path is exercised, not merely re-worded.
- R3: The recheck procedure is reachable from `sd-fleet-refresh` before any
  deletion, and its script reference resolves.
- R4: No `sd-review-pr` identifier, adapter, prompt, manifest row, receipt, or
  provenance entry survives on any platform; the `review-pr-command` registry
  row flips from schedule-only to enforcing with `identifiers` populated,
  `source_paths_must_be_absent=True`, and `removed_version` unchanged.
- R5: `RETIRED_TARGETS` gains the `sd-review-pr` command family **and** the two
  deleted script paths — `command_installed_targets()` returns command paths
  only and no `scripts/` path, so a row alone leaves consumer script copies
  undeletable forever.
- R6: `make check` has a working composition and no lane passes only because it
  never runs.
- R7: The dependency-closure allowlist is empty and the generator passes
  `--check` on a regenerated tree.
- R8: A live-surface drift lint with a minimal, individually justified
  allowlist confirms the absence.

## Acceptance Criteria

- [ ] `sd-fleet-refresh` completes an integration-only review through
      `sd-review` against a real PR head, with the classifier consulted and the
      `review-result` return honored.
- [ ] Fresh installs and help/catalog discovery expose no `sd-review-pr`
      identifier on any supported platform.
- [ ] Upgrade from the prior release removes every unchanged vouched
      `sd-review-pr` target **and** the two deleted scripts; a locally modified
      copy is preserved and reported; the new receipt contains neither.
- [ ] `run_pack_source_drift_gates` runs green from its new home; `tests.yml`
      and `surface-check.py` reference only that home.
- [ ] `make check` passes with the new composition and no `PRISM=0`/`GITO=0`
      disabling survives anywhere.
- [ ] The plugin closure allowlist is empty; `generate-plugin.py --check`
      passes; `tests/test_generate_plugin.py` asserts the empty set.
- [ ] Command-surface drift lint is green with every allowance carrying a
      reason naming why the reference is historical.
- [ ] A-102 and A-114 are marked `resolved-by-removal` in the audit ledger in
      the deletion commit.

## Dependencies

- **`07-24-remove-retired-review-surfaces` lands first.** It removes the
  `sd-full-check` and `sd-review-local` command surfaces; this task removes the
  scripts and gates that were still reachable through `sd-review-pr`. It also
  reassigns the `review-pr-command` registry row's `owner_task` to this task and
  leaves the row schedule-only (`identifiers=()`,
  `source_paths_must_be_absent=False`, `removed_version="0.62.0"`), so this task
  inherits a row already pointing at it.
- Subsumes `08-09-review-pr-fleet-classifier-ref` (close as
  resolved-by-removal, do not implement separately).

## Out Of Scope

- Backward-compatible aliases, deprecation windows, forwarding scripts, or dual
  old/new operation. Rollback is installing the last pre-cut release.
- Renaming the successor's internal `sd-review-local-stage` /
  `sd-review-local-policy` receipt identifiers — a receipt-schema change filed
  separately.

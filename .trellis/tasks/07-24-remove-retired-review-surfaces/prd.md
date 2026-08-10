# Remove the retired sd-full-check and sd-review-local surfaces

## Goal

Delete the `sd-full-check` and `sd-review-local` command surfaces and
`sd-ai-command-pack-review-local.sh` — every skill, command, prompt, workflow,
adapter, manifest target, installed receipt, help/catalog entry, documentation
claim, test, and environment reader that belongs to them. Nothing retired
remains callable or executable through an alias, wrapper, fallback, or dormant
reader.

## Scope: Narrow (decided 2026-08-09)

The original scope covered three surfaces. Adversarial planning review found
that `sd-review-pr` is not a superseded alias but the sole implementation of a
trusted nested contract used by a live caller
(`templates/.agents/skills/sd-fleet-refresh/SKILL.md:192`), which `sd-review`
does not implement. Removing it is a behavioral migration, not a deletion, so it
moved to **`08-09-retire-review-pr-surface`** (P1, blocked on this task).

Two scripts also survive, and — corrected in adversarial review round 3 — not
because `sd-review-pr` calls them. `sd-review-pr/SKILL.md:262-263` is a
**prohibition** ("Do not … fall back to `sd-ai-command-pack-full-check.sh` or
`sd-ai-command-pack-review-full-check.sh`"), which an earlier draft read as an
invocation. The real reasons:

- **`full-check.sh` is this repo's own gate** — `Makefile:98-101`
  (`check: test lint audit full-check`) and `.github/workflows/tests.yml:652-659`.
  Deleting it means recomposing `make check`, which stays out of scope here by
  decision. The `PRISM=0/GITO=0` disabling, the `run_pack_source_drift_gates`
  relocation, the `FULL_CHECK` env family, and `tests/test_full_check.py` all
  travel with that decision.
- **`review-full-check.sh` is already orphaned** — no live caller before this
  task, so R6 does not reach it. Deferred to the full-check family's owner along
  with `tests/test_review_full_check.py`.

Both are recorded in `08-09-retire-review-pr-surface`, not silently dropped. See
`design.md` for the full survivor list.

## Confirmed Evidence

Measured 2026-08-09 against the shipped `0.64.35` tree
(`research/retired-surface-inventory.md`; enumerated from `manifest.json`, not
from a hand-written list).

| item | count |
|---|---|
| `sd-full-check` manifest rows | 24 |
| `sd-review-local` manifest rows | 24 |
| short-name command rows (`full-check.md/.toml`, `review-local.md/.toml`) | 4 |
| `review-local.sh` script row | 1 |
| **manifest rows deleted** | **53** |
| live files (17 per surface) | 34 |
| `review-local.sh` copies (`scripts/`, `templates/scripts/`, `plugins/sd/bin/`, `plugins/sd/machine-payload/scripts/`) | 4 |

Superseded figures, recorded so they are not re-derived: this PRD's original
"79", the 2026-07-28 count of 105, and the research file's 83 (which counted two
rows that must survive).

- **`sd-watch-pr` is already gone**: 0 live files, 0 manifest rows, an enforcing
  registry row since 0.57.0.
- **No package hook exists.** `package.json` declares no `scripts` block; the
  `check:full` string is an invocation *inside* `review-full-check.sh:74` of a
  hook a consumer repo might define. That script survives, so R2's package-hook
  clause moves to `08-09-retire-review-pr-surface`.
- **`scripts/sd-ai-command-pack-review-local.py` must survive** despite its
  name: it is `sd-review`'s local-review stage
  (`sd-ai-command-pack-review.py:37,:718,:720` — `LOCAL_SCRIPT`, hard-fails when
  absent). Only its `.sh` sibling is deleted.
- **`full-check.sh:166,:170,:174,:178` read four retired
  `SD_AI_COMMAND_PACK_REVIEW_LOCAL_GITO_*` keys as fallbacks.** The script
  survives; those readers are exactly what R2 forbids and die here (R10).
- Surviving executables that name the two retired surfaces need refactoring
  rather than deletion; see the table in `design.md`.
- Parent R13-R15, R18, R22, and R29 already require an intentionally
  non-backward-compatible cutover and provenance-aware installed-target removal.
- The user explicitly accepted removal of all legacy/obsolete code and features
  to produce one streamlined experience.

## Dependencies And Boundaries

- Parent: `07-22-integrate-routed-review-backends`.
- Runs after `07-24-implement-read-only-sd-check`,
  `07-24-implement-unified-routed-sd-review`, and
  `07-24-simplify-review-shipping-composition` (all archived).
- **Blocks `08-09-retire-review-pr-surface`**, which removes the third surface
  and the scripts and gates reachable through it.
- Provenance-aware uninstall metadata may name retired paths solely to remove
  verified installed copies. Historical archived Trellis records may retain
  evidence. Neither is a callable compatibility surface.
- `07-28-retire-transitional-review-surfaces` owned the schedule half
  (pre-registered `RetiredCommandSurface` rows with an explicit
  `removed_version`, transitional catalog status). It is archived; this task
  executes the deletion against the schedule it set and does not set a new one.

## Requirements

- R1: Remove live skills, commands, prompts, workflows, adapters, scripts, and
  registry entries for `sd-full-check` and `sd-review-local` across every
  supported platform.
- R2: Remove the `SD_AI_COMMAND_PACK_REVIEW_LOCAL_*` environment family, shell
  string command readers, and old output/state formats belonging to these two
  surfaces. Do not leave ignored readers for migration convenience — including
  the four `REVIEW_LOCAL_GITO_*` fallbacks inside the surviving `full-check.sh`.
- R3: Remove old help/catalog/examples, README/guide/spec claims, workflow
  names, tests that pin retired behavior, manifest targets, installed receipts,
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
  `sd-review-pr` remains a live surface until `08-09-retire-review-pr-surface`
  lands; a surviving reference to it is not a violation of this requirement.
- R8 (A-045): Bind R4's registration to the already pre-registered
  `removed_version="0.62.0"`. Do not mint a second version. The rows exist at
  `installer/registry.py:1387-1410`; design D1 resolves the version slip.
- R10 (A-043, rescoped): Delete the `SD_AI_COMMAND_PACK_REVIEW_LOCAL_*` family
  and any lane it gated in the same change. The `PRISM=0`/`GITO=0` disabling in
  `Makefile:99` gates `full-check.sh` lanes and moves to
  `08-09-retire-review-pr-surface` with that script — removing the disabling
  while the lanes still ship would enable code that has never run in this
  repo's gate.
- R11 (A-102, A-114, rescoped): Both findings live in `full-check.sh` and the
  `sd-full-check` **contract text**, and only the latter dies here. Do **not**
  mark either resolved in this task. Re-own both to
  `08-09-retire-review-pr-surface` in `.trellis/audit/ledger.md`, since
  `07-28-retire-transitional-review-surfaces` (the originally named fallback
  owner) is archived.

R9 (A-059, relocate the fleet recheck procedure out of `sd-review-pr/SKILL.md`)
moves in full to `08-09-retire-review-pr-surface`: that skill is not deleted
here, so nothing is lost yet.

## Acceptance Criteria

- [ ] Fresh installs and help/catalog discovery expose no `sd-full-check` or
  `sd-review-local` identifier on any supported platform.
- [ ] Upgrade from the last pre-cut release removes every unchanged vouched old
  target **including consumer copies of `sd-ai-command-pack-review-local.sh`**,
  preserves/reports a modified old target, and produces a receipt containing
  only the new surface.
- [ ] Repository-wide live-surface scanning finds no executable retired skill,
  adapter, script, environment reader, hidden mode, alias, redirect, or
  fallback — and no `SD_AI_COMMAND_PACK_REVIEW_LOCAL_*` reader survives inside
  `full-check.sh`.
- [ ] Reintroduction is caught, with each half assigned to the check that can
  actually enforce it:
  - a retired **target** reappearing in a consumer install is reported by the
    installed audit's `unlisted-pack-like` detection
    (`install-audit.py:563,:644`) — it is no longer a manifest row, so it has no
    vouched place to be. `install-audit.py` has **zero** references to
    `RETIRED_TARGETS` and does not check retired identifiers inside vouched
    files; do not claim otherwise, and do not extend it here.
  - a retired **identifier or environment reader** reappearing in the source
    repository is caught by the command-surface drift lint, which fails on
    stale docs and specs as well as code — and only if the row's
    `configuration_keys` are populated (design D2).
- [ ] Dead-code and manifest/provenance checks confirm obsolete implementation
  branches and tests were deleted rather than skipped or disabled.
- [ ] Focused retirement/upgrade tests, all generated parity checks, candidate
  fleet validation, `make sync`, and `make check` pass.
- [ ] Both flipped registry rows carry the pre-registered
  `removed_version="0.62.0"`; no new version value appears anywhere.
- [ ] `tests/test_review_controller.py`, `tests/test_review_stage.py`,
  `tests/test_verdict_vocabulary.py`, and `tests/test_git_invocation_boundary.py`
  pass unchanged — the negative control proving `review-local.py` survived.
- [ ] A-102 and A-114 are re-owned to `08-09-retire-review-pr-surface` in the
  audit ledger, neither closed nor left silently ownerless.

## Deliberate residue

Two `sd-review-local`-shaped identifiers survive on purpose:

- `scripts/sd-ai-command-pack-review-local.py` emits
  `"command": "sd-review-local-stage"` (`:2177,:2192,:2202,:2301,:2313`);
- `scripts/sd-ai-command-pack-review.py:950` emits provider id
  `sd-review-local-policy`.

Both belong to the **successor's** local-review stage, not to the retired
`sd-review-local` command. Renaming them changes a consumer-visible receipt
schema — a different kind of change from deleting a command surface — and is
filed as a follow-up. The drift lint will not flag them: its token boundary
rejects hyphen-suffixed matches (`check-command-surface-drift.py:271`). **Any
absence check written for this task must use the same boundary semantics**, or
it will fail on residue that is intended.

## Out Of Scope

- The `sd-review-pr` surface, `full-check.sh`, `review-full-check.sh`, the
  `FULL_CHECK` and `REVIEW_PR` env families, the `Makefile` `check`
  recomposition, `run_pack_source_drift_gates`, the plugin closure allowlist,
  and `tests/test_full_check.py` / `tests/test_review_full_check.py` — all owned
  by `08-09-retire-review-pr-surface`.
- Backward-compatible aliases, deprecation windows, forwarding scripts, dormant
  readers, or dual old/new operation. A pre-registered `RetiredCommandSurface`
  row is not a deprecation window: the predecessor no longer works, it was only
  announced.
- Deleting historical archived task evidence or the minimal installer removal
  metadata needed for safe cleanup.
- Renaming the successor's internal `sd-review-local-stage` /
  `sd-review-local-policy` receipt identifiers.
- Merging the command-pack and router repositories.

## Notes

- Rollback is release-level reinstall, not legacy code retained in the new
  release.
- 2026-07-28 audit source: `.trellis/audit/report-2026-07-28.md`. This task was
  the nominal owner of five findings — A-045, A-114, A-102, A-059, A-043 — and
  covered none of them. R8/R10/R11 close what belongs to the narrow scope;
  A-059 and the A-043 remainder move with `sd-review-pr`.
- Planning complete 2026-07-28; replanned 2026-08-09 against `0.64.35`;
  rescoped to Narrow 2026-08-09 after adversarial planning review (two Codex
  rounds plus a host round, 18 verified concerns, one blocking).
- Research: `research/retired-surface-inventory.md` (live-artifact inventory,
  deletion-vs-refactor classification) and
  `research/removal-mechanism-precedent.md` (the `sd-watch-pr` 0.57.0 flip, end
  to end). Decisions D1-D8 are in `design.md`.
- The diff may still approach the remote reviewer's 20,000-line refusal
  threshold; `design.md` D8 sequences the cutover as separate commits inside one
  PR, bounded by the payload release gate's per-head requirements.

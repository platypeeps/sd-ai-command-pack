---
title: Reduce review tooling process spawns
status: planning
parked: 2026-09-01 bulk-park (D2)
created: 2026-07-25
---
# Reduce review tooling process spawns

> **R1/R2/R4 are resolved-by-removal (decided 2026-08-21).** Those requirements
> memoize base-ref discovery and export it readonly *inside*
> `scripts/sd-ai-command-pack-full-check.sh`, a file that
> `08-21-retire-full-check-family` deletes across all four trees. Optimizing a
> file scheduled for deletion is wasted work, and landing the optimization
> first would simply be discarded. Mark R1/R2/R4 resolved-by-removal when that
> task lands.
>
> **The surviving scope is the `review-preflight.mjs` work**, which is
> unaffected by the deletion. Re-scope this task to that remainder before
> starting it, and re-measure the acceptance criteria that currently quantify
> spawn reduction "in both full-check and review-preflight" against
> review-preflight alone.


## Goal

The per-change review path stops paying redundant process spawns: review-preflight
computes changed-paths and base-refs once per run, and review-scope answers 378 membership
tests with one process instead of ~1500 forks (full-check pays review-scope twice).

## Origin

SE-pack repo audit 2026-07-25 (se-ai-command-pack ledger A-029 + A-030, both P3/S).
Related in-repo finding: this repo's own ledger A-024 (preflight recomputes documentation
file list) — same class; fix together. SE-side bundle task retired in favor of this.

## Requirements

Original scope (2026-07-25):

- R1: `scripts/sd-ai-command-pack-review-preflight.mjs`: memoize defaultReviewBaseRef() and
  currentChangedPaths() (~:2040; call sites ~:485/:598/:935/:1281) in per-run module
  caches reset in runReviewPreflight(), alongside the existing readTextCache pattern —
  and fold in the A-024 documentation-list recomputation while there.
- R2: `scripts/sd-ai-command-pack-review-scope.sh` (~:127, :259-273): load
  installed-targets.txt once into an associative array (or one grep -Fxf pass); drop
  per-file command-substitution subshells.

Added 2026-07-28 — findings this task already owned but did not cover:

- R3 (A-104): Replace the per-commit git loops in the same preflight file with batched
  passes. The two loops are not the same shape and do not take the same fix:
  - `review-preflight.mjs:1284` walks a contiguous range, spawning `rev-list` plus
    `log` per commit, bounded at 50. One `git rev-list --format='%H %P %s'` over the
    range, parsed once, replaces it — the file already uses that batched idiom for
    `ls-tree` at `:1918`.
  - `:1818` walks journal-resolved commits that are **not** necessarily one contiguous
    range, bounded at 100, and per commit checks ancestry (`merge-base`), parents,
    changed entries, and regular-path filtering. `rev-list --format` alone does not
    supply ancestry or changed entries, so this loop needs separate batching per
    evidence class (one `merge-base --is-ancestor` sweep or a single
    `rev-list --ancestry-path`, one metadata batch over the explicit commit list, one
    diff/tree batch) with fixtures containing noncontiguous commits.
  Measured at ~8.8 ms per spawn these cost ~0.9 s and ~2.6 s against a 0.75 s
  whole-preflight baseline. R1's two memoizations do not touch either loop. Specify the
  bounded spawn budget and the result contract before implementing.
- R4 (A-107): Resolve base-ref discovery once in `main` in
  `scripts/sd-ai-command-pack-full-check.sh` and export it readonly. `:192` uses
  uncached command substitutions and five call sites recompute it (`:408`, `:410`,
  `:439`, `:609`, `:909`); each hop spawns `symbolic-ref` and `rev-parse` per candidate
  via `shell-lib.sh:253`. Same concept as R1, different file — full-check.sh was not in
  the original file list.

## Acceptance Criteria

- [ ] Identical classification output on a fixture diff.
- [ ] Measurable spawn reduction on a 378-target pack-refresh diff, in both full-check
      passes.
- [ ] R3: a bookkeeping-validation fixture over a 50-commit and a 100-commit range issues
      one `rev-list` per range rather than per commit, with unchanged validation results.
- [ ] R4: base-ref discovery runs once per full-check invocation; all five call sites read
      the resolved variable.
- [ ] Changelog + version; fleet rollout via normal refresh.

## Notes

- 2026-07-28 audit source: `.trellis/audit/report-2026-07-28.md` — findings A-104 and
  A-107, both P2/P3 · S/M · Plausible in the performance dimension.
- Complex task. Planning complete 2026-07-28: `design.md` and `implement.md` added.
- **R1's line numbers match neither function.** Measured 2026-07-28 against
  `review-preflight.mjs` (4,547 lines): `defaultReviewBaseRef()` is defined at `:3816`
  (not `~:2040`) and called at `:3843`, `:3851`, `:3865`; `currentChangedPaths()` is
  defined at `:4053` and called at `:2094`, `:2207`, `:2279`, `:2877`, `:3277`. None of
  the cited call sites (`~:485/:598/:935/:1281`) lands on either — and there are eight
  call sites, not four.
- **A-024 is already fixed; drop it from R1 as work and keep it as the template.**
  `.trellis/audit/ledger.md:432` reads `status: fixed` ("fixed in 0.13.1 via
  `07-15-p3-polish-batch`"), and `documentationGuardFilesCache` exists at `:16`, resets at
  `:180`, and memoizes at `:3715-3737`. Its own evidence lines (`:759-777`, `:327`, `:352`,
  `:1200`) no longer resolve.
- **R1's reset instruction is half the reset the caches need.** There are two entry points:
  `runReviewPreflight` (`:174`, clears at `:180-181`) and `runBookkeepingValidator`
  (`:536`, clears at `:539`). The validator works from explicit base/head oids and can run
  in the same process as a preflight, so a memoized base ref or changed-path list leaks
  into it. Reset in both.
- **R2's ~1500 forks are command substitutions, not greps.** `normalize_repo_path`
  (`:66-69`) is pure shell but is invoked through `$( )` at `:88`, `:118`, `:132`, `:143`,
  and `:156`; the loop at `:259-275` reaches up to four per changed file, so 378 × 4 ≈ 1512.
  The membership grep at `:127` fires at most once per file (≤378, fewer because the `case`
  at `:121-124` short-circuits). Fixing only the grep leaves ~1500 subshells standing while
  the Goal's wording reads as satisfied. R2's second clause is the load-bearing one.
- **"full-check pays review-scope twice" is true, but the second payment is nested inside
  review-preflight.** `full-check.sh:1034` runs the script directly (`:457-465`);
  `full-check.sh:977` runs review-preflight, which spawns it again in advisory mode at
  `review-preflight.mjs:3396`. `full-check.sh:1035` is `pr-body-scope.py`, a different
  script. The nested pass is skipped when `SD_AI_COMMAND_PACK_SCOPE_CHECK` is falsey
  (`:3388-3390`), so any measurement must pin that variable.
- **R4 cites a call site that does not exist and misses that there are two base refs.**
  `:408` (in both the PRD and `ledger.md:1919`) contains no base-ref call — the hit is
  `:410`. Actual `full_check_base_ref` call sites: `:203`, `:208`, `:410`, `:609`, `:909`;
  `:439` calls `full_check_gito_base_ref` (`:199`), a separate function keyed on a separate
  env var that falls back at `:203`. "Export it readonly", singular, would collapse the two
  and change what `gito review --vs` compares against. Memoize each on first call below the
  `configured_review_base_ref` check — `readonly` in `main` is a re-assignment error, since
  the helpers are reachable earlier and tests source the script more than once.
- **R3 is correctly derived and already corrects the ledger — keep it that way.** Loop A at
  `:1283` is bounded by `MAX_BOOKKEEPING_SUCCESSOR_COMMITS = 50` (`:33`); loop B at `:1819`
  by `MAX_BOOKKEEPING_RECOVERY_COMMITS = 100` (`:29`, enforced at `:1793`) with four spawn
  classes per commit. `ledger.md:1873`'s `fix:` field prescribes a single `rev-list` for
  both, which cannot work for loop B. Additional constraint not in R3: both loops
  `continue` on first failure, so batching must reconstruct the short-circuit precedence or
  one bad commit starts emitting several findings instead of one.
- Ledger notes for A-104 and A-107 recorded this task as owner while its requirements
  named neither code path; R3/R4 close that gap.
- A-101 (`sd-check` worktree re-hashing) and A-105 (`pr-body-scope` classifier scans)
  were briefly added here on 2026-07-28 and then split out to
  `07-28-reduce-review-hashing-and-classifier-cost`. They are hashing and matching
  cost, not spawn cost, and widened this task past its title. No shared code, so the
  two tasks can land in either order.

## Rescope (2026-08-08)

R1/R2/R4 only; R3 is dropped (its batching target shipped in v0.64.11).

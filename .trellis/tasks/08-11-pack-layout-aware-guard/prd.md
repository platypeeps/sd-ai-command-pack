# Ship a layout-aware review guard so consumers stop reimplementing one

Child of `08-09-thin-migration`. Pack-side only: this task changes nothing
outside `sd-ai-command-pack`.

## Why

The fleet-wide thin-conversion sizing taken on 2026-08-11 (against the
pre-0.70.0 resweep, `<scratchpad>/resweep/*.json`) found **510 conversion
blockers across 8 consumers**. They are not evenly spread, and they are not
mostly prose:

| category | blockers |
|---|---|
| test assertions | 166 |
| guard scripts | 164 |
| prose | 115 |
| CI/config | 37 |
| platform declarations | 22 |
| **total** | **510** |

Per consumer:

| consumer | blockers |
|---|---|
| anomaly-metric-creator | 207 |
| rwbp-website | 68 |
| loadsmith | 56 |
| rwbp-coordinator | 52 |
| mezmo_benchmark | 47 |
| hoa-manager | 37 |
| se-ai-command-pack | 27 |
| sd-github-review | 16 |

The concentration is the finding. **Five consumers each independently
reimplemented the same pack-layout guard**, under five different names:

Each lives in its own consumer repository, under that repository's own
scripts directory. None of these paths exists in this repository:

- `rwbp-coordinator` — `check-review-churn.mjs` (36 of its 52 blockers)
- `rwbp-website` — `review-guard.mjs` plus its test (43 of 68)
- `mezmo_benchmark` — `check-review-preflight.mjs`
- `hoa-manager` — `check_review_readiness.sh`
- `anomaly-metric-creator` — `check-review-cycle-patterns.py`

Each one hardcodes the fat layout it was written against, which is why each
one blocks its own consumer's conversion. Together with the test assertions
that pin those scripts' output, **330 of the 510 blockers (65%) are consumer
code asserting a pack layout the pack itself should own**.

Converting eight consumers without fixing this means editing five bespoke
guards and their tests, five times, by hand — and leaving five copies to
drift again on the next layout change.

## Goal

Ship one pack-owned review guard that resolves the pack layout at runtime
instead of hardcoding it, so a consumer deletes its bespoke script rather
than porting it. A consumer must get the same guard behavior in fat mode and
thin mode with no consumer-side conditional.

## Requirements

1. The guard resolves pack-owned paths through the same resolution the rest
   of the installed pack uses — machine install under `~/.agents` when the
   consumer is thin, vendored paths when it is fat — and never hardcodes
   either.
2. It covers the behavior the five bespoke scripts actually implement. Read
   all five before designing the surface; do not assume they are the same
   check with different names. Record what each one does that the others do
   not, and decide explicitly whether that behavior ships, is dropped, or
   stays consumer-local.
3. It installs through the existing consumer install path, so adopting it is
   an install plus a delete rather than a new integration.
4. Its own tests live in the pack. A consumer adopting it should not need to
   re-derive the assertions its deleted test file held.
5. Deleting a bespoke guard is measurable: the resweep blocker count for that
   consumer drops by the number of blockers that guard and its tests carried.

## Acceptance criteria

- [ ] All five bespoke guards read and their behavior tabulated, with each
      difference marked ship / drop / consumer-local and a reason.
- [ ] One pack-shipped guard exists, resolving layout at runtime, with pack
      tests covering the shipped behaviors from the table.
- [ ] `make check` and `make release-prep` pass.
- [ ] A thin-mode and a fat-mode invocation of the guard are both exercised
      by tests, proving no consumer-side conditional is needed.
- [ ] The fleet resweep is re-run and the projected blocker reduction is
      recorded per consumer, measured rather than estimated.

## Out of scope

Touching any consumer repository. Deleting the bespoke guards is the
conversion cohorts' work (`08-10-thin-canary-conversion`,
`08-10-thin-post-canary-conversion`) and requires the per-cohort user
authorization those tasks already document. This task ships the replacement
so that work is a delete instead of five ports.

## Evidence

- Sizing method and per-consumer breakdown: this PRD's tables, taken from the
  pre-0.70.0 resweep on 2026-08-11.
- 0.70.0's `fix(fleet): measure pack defects after the rewrite` corrected the
  resweep to run after install on a committed clone, which lowered blocker
  counts on five consumers. The numbers above predate that correction and are
  therefore an upper bound; re-measure before acting on an exact figure.

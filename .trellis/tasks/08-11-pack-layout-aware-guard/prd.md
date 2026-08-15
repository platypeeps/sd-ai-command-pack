# Ship a layout-aware review guard so consumers stop reimplementing one

Standalone, pack-side only: this task changes nothing outside
`sd-ai-command-pack`.

It belongs to the thin-migration program by subject — the migration task
and, above it, the thin-deployment umbrella task — and is deliberately not
linked as a child of either. The umbrella is `in_progress`, so declaring
the link would drag an active task into the planning closure of every
branch that files work under that program, which the finalization gate
correctly refuses. Naming those tasks by their exact IDs here would create
the same link, so this reference stays descriptive; the migration task's
own child map is where the formal link belongs once the umbrella is no
longer active.

Ordered before the conversion cohorts without gating them: converting
without this guard is possible, only five times more hand work with five
copies left to drift again.

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
scripts directory. None of these paths exists in this repository.

**Corrected 2026-08-14.** The list below was re-enumerated from the consumer
checkouts named by `docs/fleet/consumers.json` `pathHint`. The original filing
had the right *set* of five filenames but shuffled four of the five consumer
attributions, and it missed `loadsmith` entirely while naming
`anomaly-metric-creator` for a script that lives in `mezmo_benchmark`. Three of
the five original consumer/path pairs do not exist on disk. Sizes are
`wc -l`:

| consumer | bespoke guard | lines |
|---|---|---|
| `rwbp-coordinator` | `scripts/check-review-churn.mjs` (+ `.test.mjs`, 20) | 762 |
| `loadsmith` | `scripts/check_review_readiness.sh` | 1139 |
| `hoa-manager` | `scripts/check-review-preflight.mjs` (+ `.test.mjs`, 589) | 902 |
| `rwbp-website` | `scripts/review-guard.mjs` | 2466 |
| `mezmo_benchmark` | `scripts/check-review-cycle-patterns.py` | 812 |

`rwbp-website` has no test file beside its guard, contrary to the original
filing's "plus its test".

Two further files match the guard naming but are **dispatchers, not guards**,
and must not be counted as bespoke reimplementations:

- `loadsmith/scripts/check-review-preflight.mjs` (25 lines) — `spawnSync`s
  `check_review_readiness.sh --full-gate --skip-build`.
- `anomaly-metric-creator/scripts/check-review-preflight.mjs` (31 lines) —
  runs four `tools/check_*.py` guards plus the pack's own
  `sd-ai-command-pack-pr-body-scope.py`.

So `anomaly-metric-creator`, the consumer with the *most* blockers, owns no
bespoke layout guard at all. Its blockers come from somewhere else.

**Re-measured 2026-08-14** with `sd-ai-command-pack-thin-resweep.py`:
**175 blockers, not 207** — the 0.70.0 correction this PRD's Evidence section
predicted. `verdict: blocked`, `worktreeClean: true`. Every one is a reference
to a hardcoded `scripts/sd-ai-command-pack-*` literal, and 18 distinct pack
paths account for all 175. They are the same defect as the five guards, spread
across contract guards, their tests, and instruction prose instead of
concentrated in one file. Design D3b adds the `--resolve` query that puts them
in reach; the per-consumer figures live there rather than being restated
here.

Each one hardcodes the fat layout it was written against, which is why each
one blocks its own consumer's conversion. Together with the test assertions
that pin those scripts' output, **330 of the 510 blockers (65%) are consumer
code asserting a pack layout the pack itself should own**. That 65% figure
inherits the mis-attribution corrected above and the pre-0.70.0 measurement
error already noted under Evidence; treat it as an upper bound on an upper
bound until the resweep is re-run.

**The pack already owns a runtime-resolving classifier.**
`is_copied_review_scope_path` (`templates/scripts/sd-ai-command-pack-review-scope.sh:130`)
answers the shared question these five guards each re-answer — is this changed
path vendored pack payload or authored source — and it already resolves at
runtime rather than hardcoding, by matching against
`.sd-ai-command-pack/installed-targets.txt` (overridable via
`SD_AI_COMMAND_PACK_TARGETS_FILE`). Two consumers already know this:
`hoa-manager/scripts/check-review-preflight.mjs:70` comments that its matcher
"Mirrors the pack's own matcher at scripts/sd-ai-command-pack-review-scope.sh:170",
and `rwbp-website/scripts/review-guard.mjs:6` already imports
`runReviewPreflight` from the pack's shipped preflight.

This reframes the goal. The missing piece is not a new guard; it is that the
existing classifier is reachable only from shell, and that its receipt-based
resolution has not been proven under thin mode, where the consumer keeps
neither `scripts/sd-ai-command-pack-*` nor, necessarily, the receipt in the
same place. Design must start from extending what ships, and justify any new
surface against that.

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
   of the installed pack uses — the machine install when the consumer is thin,
   vendored paths when it is fat — and never hardcodes either.

   Filed as "machine install under `~/.agents`". Corrected 2026-08-14: that is
   where the *payload* lands, but the thin **receipt** the guard must read is
   under `resolve_state_root()`
   (`templates/scripts/sd_ai_command_pack_lib.py:248-292`), measured live as
   `~/.local/state/sd-ai-command-pack` and reachable through a five-rung ladder
   that `SD_AI_COMMAND_PACK_STATE_HOME` and `XDG_STATE_HOME` can move. A guard
   that expanded `~/.agents` would skip four of those five rungs. See design
   D4a; the requirement is the runtime resolution, and the literal path in the
   original wording was wrong.
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

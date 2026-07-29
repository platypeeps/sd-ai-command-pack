# Design — remove all retired review and check surfaces

## Scope boundary

Deletion only. The removal **version** and the transitional catalog status belong
to `07-28-retire-transitional-review-surfaces`; the `sd-ship` repoint and the
review-loop decision point belong to `07-24-simplify-review-shipping-composition`.
This task executes against a schedule it does not set (R8).

## Measured scale

The PRD's Confirmed Evidence says "79 review/full-check manifest targets".
Measured 2026-07-28 against `manifest.json` (754 files total):

| token | entries |
|---|---|
| `sd-full-check` | 23 |
| `sd-review-local` | 23 |
| `sd-review-pr` | 23 |
| `sd-watch-pr` | 23 |
| short-name adapters (`full-check`, `review-local`, `review-pr`, `watch-pr`) | 13 |

**105 entries, not 79** — and the four `sd-`-prefixed families alone are 92. The
plan is not wrong, but any sizing done against 79 is short by about a third.
Recount before estimating.

`sd-review-pr/SKILL.md` alone fans out to **11** platform targets, confirming the
R9 reasoning.

## The gate eats itself

`Makefile:91-94`:

```make
full-check:
	SD_AI_COMMAND_PACK_FULL_CHECK_PRISM=0 SD_AI_COMMAND_PACK_FULL_CHECK_GITO=0 bash scripts/sd-ai-command-pack-full-check.sh

check: test lint audit full-check
```

R1 deletes `full-check.sh`. `make check` depends on `full-check`. So the moment
R1 lands, the repo's own canonical gate — and the acceptance criterion "`make
check` passes" — refers to a target that cannot run.

**The PRD does not say what `make check` becomes.** It must, before any deletion
starts. Two shapes:

- **A — `check: test lint audit`.** Honest: the AI review lanes were already
  hard-disabled by `PRISM=0 GITO=0` (`Makefile:91-92`), so nothing measurable is
  lost.
- **B — `check: test lint audit sd-check`.** Routes the local gate through the
  successor. Larger, and couples this task to `sd-check`'s CLI surface.

**Decided 2026-07-28: A.** B would put a new coupling into the same commit that
deletes four command families, making any gate failure ambiguous between the two
causes; route `check` through `sd-check` as a separate follow-up if wanted. Land
the Makefile change **in the same commit** as the deletion — `make` fails at
parse time on a prerequisite that no longer exists, so a split leaves no working
gate at all.

## Deletion order is forced by three dependencies

1. **R9 relocation before R1 deletion.** The Fleet Integration-Only Recheck at
   `templates/.agents/skills/sd-review-pr/SKILL.md:196` invokes
   `fleet-review-classify.py`, which `install-audit.py:112-118` lists as
   source-only. The procedure is therefore dead in all 11 shipped copies but is
   still the only written record of how integration-only recheck works. Move it
   into the source-only `sd-fleet-refresh` skill **first**; deleting first loses
   it.
2. **Registry rows flip, not appear.** `07-28-retire-transitional-review-surfaces`
   leaves four schedule-only rows (`identifiers=()`,
   `source_paths_must_be_absent=False`). This task populates `identifiers`, flips
   the flag to `True`, and adds the targets to `RETIRED_TARGETS`
   (`installer/removal.py:69-73` — a hand-maintained tuple, so this is an explicit
   edit, not automatic). Only then does uninstall reach the old copies.
3. **Allowances arrive with the flip, not after.** Once `identifiers` is
   populated, `check-command-surface-drift.py:436-468` flags every remaining text
   occurrence. CHANGELOG entries, the README migration note, and retirement
   fixtures all need a `CommandSurfaceAllowance` — the already-deleted
   `sd-review-local-all` needed six (`installer/registry.py:1284-1313`). Expect
   more here, and expect the drift lint to be red for exactly as long as it takes
   to enumerate them. That redness is the lint working.

## R5's real difficulty

"Live-surface drift lint with an explicit minimal allowlist" is the mechanism
that makes this cutover verifiable, and it already exists — R5 is mostly
*configuring* `check-command-surface-drift.py`, not building something. The hard
part is the word **minimal**: every allowance is a permanent exception, and the
easy failure mode is adding one per red line until the lint is green and
meaningless. Each allowance needs a `reason` that names why the reference is
historical rather than live, matching the existing rows' style.

## R10's trap

`Makefile:92` hard-disables the prism and gito lanes. Deleting the lanes and
removing the disabling are one change **only because the script is being deleted
outright**. If R1 slips and R10 is attempted alone, removing `PRISM=0 GITO=0`
turns on lanes that have never run in this repo's gate — a large, untested
behavior change disguised as cleanup. R10 is not separable from R1.

## Rollback

R6 is explicit: rollback is installing the last pre-cut release, not retaining
legacy code. That makes the ordering above the actual safety mechanism — there is
no in-release undo. Consequently:

- R9's relocation must be verified *before* deletion, not after.
- The Makefile decision must be made before the first deletion commit.
- The uninstall path (R4) must be proven on a real prior-release install, not
  only in fixtures, because a wrong `recorded_hash` silently preserves files
  instead of removing them and the receipt then looks clean.

## Compatibility

Intentionally non-backward-compatible (parent R13-R15, R18, R22, R29; user
accepted). The only compatibility obligations that survive are: a modified old
target is preserved and reported rather than deleted, and no retired path appears
in the new receipt.

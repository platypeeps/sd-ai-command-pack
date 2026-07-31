# Design — name a removal version for the transitional review surfaces

## Scope boundary

This task owns the **deadline and the interim**. Deletion belongs to
`07-24-remove-retired-review-surfaces` (R1/R3/R4, bound to this task's version by
its R8); the `sd-ship` Stage 2 repoint and the review-loop decision point belong
to `07-24-simplify-review-shipping-composition` (R7/R8).

The surfaces are `sd-full-check`, `sd-review-local`, and `sd-review-pr`.
(Originally four: `sd-watch-pr` was already retired at 0.57.0 by
`07-24-simplify-review-shipping-composition` — full registry row at
`installer/registry.py:1315-1322`, skill and catalog row deleted. Verified
2026-07-31.)

Successor mapping (2026-07-31, from the shipped catalog and
`docs/SD_AI_COMMAND_PACK.md:906`): `sd-review-local` and `sd-review-pr` are
superseded by `sd-review` (routed local/remote lanes); `sd-full-check` is
superseded by `sd-check` (deterministic verification gate).

## The registry row is not a free annotation

`RetiredCommandSurface` (`installer/registry.py:1271-1279` as of 2026-07-31)
is:

```python
id: str
identifiers: tuple[str, ...]
installed_targets: tuple[str, ...]
removed_version: str
owner_task: str
source_paths_must_be_absent: bool = True
configuration_keys: tuple[str, ...] = ()
```

Two of those fields have teeth, and R1 as written trips both.

**1. `source_paths_must_be_absent` defaults to `True`.**
`check-command-surface-drift.py:632-646` (line cites re-verified 2026-07-31)
walks every retirement with that flag set and emits `retired_identifier_live`
— *"retired installed target exists in the source checkout"* — for each
`installed_target` that still exists. All three surfaces still ship. A naive
row therefore turns the drift gate red on the very files the row is meant to
schedule.

**2. `identifiers` is scanned as text repo-wide.**
`check-command-surface-drift.py:508-537` searches every text file for each
retired identifier token and emits `retired_identifier_live` — *"retired
identifier appears in live content"* — unless a `CommandSurfaceAllowance`
matches. The `sd-review-local-all` precedent needed **six** allowances for a
command that was already deleted (`installer/registry.py:1288-1297` as of
2026-07-31). A still-shipping command appears in the catalog, README, the
guide, its own skill, eleven platform adapters, and the manifest.

### The precedent that already solves this — with one gap

`fleet-refresh-consumer-targets` (`installer/registry.py:1298-1307` as of
2026-07-31) is exactly a schedule-only row: `identifiers=()` and
`source_paths_must_be_absent=False`. It records a `removed_version` and an
`owner_task` and asserts nothing about presence.

**Gap found in adversarial review 2026-07-31 (Codex lane, verified in code):**
the drift lint's manifest pass (`check-command-surface-drift.py:449-462`)
intersects every retirement's `installed_targets` with live `manifest.json`
targets and emits `retired_identifier_live` **without consulting
`source_paths_must_be_absent`**. Only the source-checkout pass (`:632-646`,
flag consulted at `:633`) respects the flag. The fleet-refresh precedent never trips this because its
source-only targets are absent from the live manifest; our three commands
ship, so naive rows produce ~25 findings per command. And rows cannot simply
drop `installed_targets`: `validate_command_surface_registry`
(`installer/registry.py:1409`, all-empty check at `:1443-1448`) rejects a row
whose identifiers, installed targets, and configuration keys are all empty.

**Decision: teach the manifest pass the same flag semantics.** Skip
retirements with `source_paths_must_be_absent=False` in the manifest
intersection, exactly as the source-checkout pass already does — the flag's
meaning is "this retirement does not yet assert absence", and the manifest
pass is an absence assertion. Dev-side checker change plus a unit test
(schedule-only row whose targets are live in the manifest must stay clean;
enforcing row must still flag). This keeps the canonical
`RetiredCommandSurface` structure as the single retirement-metadata source.

**Recommendation: pre-register schedule-only rows in that shape** — empty
`identifiers`, `source_paths_must_be_absent=False` — and let
`07-24-remove-retired-review-surfaces` populate `identifiers` and flip the flag
to `True` in the same change that deletes the files. That splits the row's two
jobs (announce vs. enforce) along the same seam the two tasks already split on.

### One correction to a fear this raises

Adding a row does **not** make `install.py` delete the surface. `RETIRED_TARGETS`
(`installer/removal.py:62-75` as of 2026-07-31) enumerates four retirement ids
by hand (review-local-all, the fleet-refresh source-only targets, work-designs,
watch-pr) and derives each group's targets from that registry row via
`retired_surface_targets(id)` — it is not a comprehension over all of
`RETIRED_COMMAND_SURFACES`. A new row is inert at install time until someone
enumerates its id there. Worth stating because the opposite assumption would
make this task look dangerous when it is not.

The derivation cuts the other way too (adversarial review round 2): once the
deletion task enumerates these ids, everything in `installed_targets` becomes a
consumer-repo removal candidate. So `installed_targets` may only ever carry
**consumer-install paths** (manifest targets), never manifest *sources* — a
`templates/scripts/…` source path listed there would mark a consumer-owned
file of that name for deletion, unconditionally under `--force`.

The same fact is the reason the `source_paths_must_be_absent=False` precedent is
safe to copy here: the fleet-refresh freeze came from that row being wired into
`RETIRED_TARGETS` **and** excluded from the manifest, not from the flag itself.

## Citation correction

A-045 cites `command-catalog.md:40` as "the sd-review-pr row". Line 40 is
**`sd-review-local`**; `sd-review-pr` was at `:55` when this was corrected on
2026-07-28. The underlying claim survives — both rows read `included in
installed pack`, identical to a live command — but the line attribution is
wrong, and the catalog work covered **four** rows then. (As of 2026-07-31 it
covers three — `sd-watch-pr`'s row is gone — and `sd-review-pr` sits at `:54`;
current lines are in the PRD requirements.)

## What "transitional status" has to mean mechanically

`sd-help` reads the catalog table. Today the availability column carries one of
two literals (`included in installed pack` / `source-checkout-only`, from
`.github/scripts/generate-command-surfaces.py:353-357` keyed on
`SOURCE_ONLY_COMMAND_NAMES`). R2 needs a value that is machine-distinguishable,
not prose in the description cell — otherwise `sd-help` still recommends the
legacy command and the acceptance criterion is unverifiable. Decide between:

- a new status literal (`transitional — superseded by sd-review`), or
- a fourth column (`superseded_by`).

**Decided 2026-07-31: the status literal** (refined in adversarial review the
same day). The column already encodes availability states as literals; the
third literal **keeps the availability fact** — a transitional command still
ships — and appends the schedule:

```
included in installed pack — transitional until <version>; use <successor>
```

Replacing the `included in installed pack` prefix wholesale would make the
column lie about availability (Codex concern, accepted); the combined form
stays machine-distinguishable by the `transitional until` marker and stays
true for every reader that only checks the shipping prefix.

**The `<version>` is not a second copy of the number.** The generator derives
it from the registry row's `removed_version` — single source of truth, no
literal `0.62.0` in the generator (Codex concern, accepted). Mechanically: add
`SUPERSEDED_COMMANDS: dict[name, (successor_name, retirement_id)]` next to
`SOURCE_ONLY_COMMAND_NAMES` in `installer/registry.py`, validated the same
way (every key and successor a known command name, every retirement id
present in `RETIRED_COMMAND_SURFACES`), and branch the generator's
availability expression on it, reading the version off the referenced row.
Either way the catalog is generated into eleven skill roots, so this is a
generator change plus `make sync`, not a hand edit. `sd-help`'s SKILL.md also
needs one instruction: when a catalog row is transitional, recommend the
named successor instead. `tests/test_help_command.py` asserts availability
literals for other rows (`:573-574`); add the transitional-row assertions
there.

## Sequencing

`07-24-simplify-review-shipping-composition` R7 lands **first**. Pre-registering
a removal version while the main delivery path still runs `sd-review-pr`
announces a date for something nothing has migrated off. The PRD already records
this dependency; it is a hard ordering constraint, not a preference.
**Satisfied 2026-07-31:** that task is archived and
`grep -n "sd-review-pr" .agents/skills/sd-ship/SKILL.md` returns nothing.

## The two-implementations question (R5)

`review-local.sh` and `review-local.py` both orchestrate local providers, but
they are not two copies of one surface. **Resolved 2026-07-31 (recorded in the
PRD):** `scripts/sd-ai-command-pack-review.py:34` binds `review-local.py` as
`LOCAL_SCRIPT` — it is the successor's local-lane engine and survives the
retirement. `review-local.sh` never invokes the `.py`; it is the transitional
`sd-review-local` command's standalone orchestrator and retires with the
surface. The removal version therefore commits to deleting the bash
orchestrator and the three command surfaces, not 3,003 lines.

## Compatibility

Nothing about consumer behavior changes here. The predecessor keeps working
exactly as today; it merely acquires an announced end date and a catalog status.
That is the whole point of splitting this from the deletion task.

## Rollout and rollback

Each piece is independently revertable: registry rows, catalog status, CHANGELOG
note. The one irreversible act is publishing a version number consumers will
plan against — so the number must be chosen with the deletion task's actual
readiness in mind, not optimistically.

## Risk

The failure mode is announcing a version that then slips. If it slips, the
interim fixes A-114, A-102, A-059 and A-043 stop being "resolved by deletion" and
become live defects shipping past their own announced end date — which is why the
PRD makes those conditional on the removal actually landing.

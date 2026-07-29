# Design — name a removal version for the transitional review surfaces

## Scope boundary

This task owns the **deadline and the interim**. Deletion belongs to
`07-24-remove-retired-review-surfaces` (R1/R3/R4, bound to this task's version by
its R8); the `sd-ship` Stage 2 repoint and the review-loop decision point belong
to `07-24-simplify-review-shipping-composition` (R7/R8).

The four surfaces are `sd-full-check`, `sd-review-local`, `sd-review-pr`, and
`sd-watch-pr`.

## The registry row is not a free annotation

`RetiredCommandSurface` (`installer/registry.py:1227-1234`) is:

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
`check-command-surface-drift.py:564-577` walks every retirement with that flag
set and emits `retired_identifier_live` — *"retired installed target exists in
the source checkout"* — for each `installed_target` that still exists. All four
surfaces still ship. A naive row therefore turns the drift gate red on the very
files the row is meant to schedule.

**2. `identifiers` is scanned as text repo-wide.**
`check-command-surface-drift.py:436-468` searches every text file for each
retired identifier token and emits `retired_identifier_live` — *"retired
identifier appears in live content"* — unless a `CommandSurfaceAllowance`
matches. The `sd-review-local-all` precedent needed **six** allowances for a
command that was already deleted (`installer/registry.py:1284-1313`). A
still-shipping command appears in the catalog, README, the guide, its own skill,
eleven platform adapters, and the manifest.

### The precedent that already solves this

`fleet-refresh-consumer-targets` (`installer/registry.py:1253-1263`) is exactly
a schedule-only row: `identifiers=()` and `source_paths_must_be_absent=False`.
It records a `removed_version` and an `owner_task` and asserts nothing about
presence.

**Recommendation: pre-register schedule-only rows in that shape** — empty
`identifiers`, `source_paths_must_be_absent=False` — and let
`07-24-remove-retired-review-surfaces` populate `identifiers` and flip the flag
to `True` in the same change that deletes the files. That splits the row's two
jobs (announce vs. enforce) along the same seam the two tasks already split on.

### One correction to a fear this raises

Adding a row does **not** make `install.py` delete the surface. `RETIRED_TARGETS`
(`installer/removal.py:69-73`) is a hand-maintained tuple of three named aliases,
not a comprehension over `RETIRED_COMMAND_SURFACES`. A new row is inert at
install time until someone adds it there. Worth stating because the opposite
assumption would make this task look dangerous when it is not.

The same fact is the reason the `source_paths_must_be_absent=False` precedent is
safe to copy here: the fleet-refresh freeze came from that row being wired into
`RETIRED_TARGETS` **and** excluded from the manifest, not from the flag itself.

## Citation correction

A-045 cites `command-catalog.md:40` as "the sd-review-pr row". Line 40 is
**`sd-review-local`**; `sd-review-pr` is at `:55`. The underlying claim survives —
both rows read `included in installed pack`, identical to a live command — but
the line attribution is wrong and the catalog work covers **four** rows, not one.

## What "transitional status" has to mean mechanically

`sd-help` reads the catalog table. Today the status column carries exactly one
value for every command. R2 needs a value that is machine-distinguishable, not
prose in the description cell — otherwise `sd-help` still recommends the legacy
command and the acceptance criterion is unverifiable. Decide between:

- a new status literal (`transitional — superseded by sd-review`), or
- a fourth column (`superseded_by`).

A column is cleaner for a machine reader; a status literal is a smaller diff.
Either way the catalog is generated into eleven skill roots, so this is a
generator change plus `make sync`, not a hand edit.

## Sequencing

`07-24-simplify-review-shipping-composition` R7 lands **first**. Pre-registering
a removal version while the main delivery path still runs `sd-review-pr`
announces a date for something nothing has migrated off. The PRD already records
this dependency; it is a hard ordering constraint, not a preference.

## The two-implementations question (R5)

`review-local.sh` (771 lines) and `review-local.py` (2,232 lines) do the same
provider orchestration in two languages. This task does not have to *resolve*
that — but it must record a decision, because the removal version applies to both
and "we will delete 3,003 lines by version X" is a materially different
commitment from "we will delete the bash one."

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

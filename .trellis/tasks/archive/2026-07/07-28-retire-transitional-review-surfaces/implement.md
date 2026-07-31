# Implementation — name a removal version for the transitional review surfaces

## Blocking prerequisite

`07-24-simplify-review-shipping-composition` R7 (the `sd-ship` Stage 2 repoint)
must land first. Verify, do not assume:

```bash
grep -n "sd-review-pr" .agents/skills/sd-ship/SKILL.md
```

**Gate:** no Stage 2 hit. If Stage 2 still calls `sd-review-pr`, stop — announcing
a removal version for a surface the main delivery path still uses schedules a
break rather than a retirement.

**Verified 2026-07-31: no hits; the task is archived. Gate passes.**

## Order

1. **Pick the version.** Coordinate with `07-24-remove-retired-review-surfaces`
   on when deletion can realistically land, and record the reasoning in the task.
   **Gate:** one number, agreed by both tasks. `remove-retired-review-surfaces`
   R8 forbids minting a second one.
   **Chosen 2026-07-31: `0.62.0`** (this task ships at 0.60.0; one buffer minor;
   reasoning in the PRD notes — if deletion slips, the deletion task updates the
   inert rows rather than minting a second announcement).

2. **Decide the `review-local.sh` / `review-local.py` fate** (PRD R5).
   **Decided 2026-07-31, recorded in PRD and design:** `review-local.py` is the
   successor's local-lane engine (`review.py:34` `LOCAL_SCRIPT`) and survives;
   only `review-local.sh` retires with the surfaces.
   **Gate:** decided before the rows are written — it changes what
   `installed_targets` lists. Satisfied.

3. **Add three schedule-only `RetiredCommandSurface` rows** at the end of
   `RETIRED_COMMAND_SURFACES` (`installer/registry.py:1288-1322`), one each for
   `sd-full-check`, `sd-review-local`, `sd-review-pr`, in the
   `fleet-refresh-consumer-targets` shape:

   ```python
   identifiers=(),
   installed_targets=command_installed_targets("<name>", "<short>"),
   source_paths_must_be_absent=False,
   removed_version="0.62.0",
   owner_task="07-24-remove-retired-review-surfaces",
   ```

   `installed_targets` is required — `validate_command_surface_registry`
   (`installer/registry.py:1409`, all-empty check at `:1443-1448`) rejects a
   row where identifiers, installed targets, and configuration keys are all
   empty ("describes no surface"). Shorts: `full-check`, `review-local`, `review-pr`. Targets of a
   still-live command are safe: validation checks target path safety and
   *identifier* liveness only, and the `fleet-refresh-consumer-targets` row
   already coexists with its live source-only command.

   Footprint boundary (adversarial review 2026-07-31, tightened round 2):
   `command_installed_targets` returns command skill/adapter targets only —
   never scripts; the schedule-only rows therefore carry the adapter footprint
   and nothing else. The deletion task appends only
   `scripts/sd-ai-command-pack-review-local.sh` — the manifest **target** — to
   `installed_targets` when it populates `identifiers` and flips the flag. Its
   `templates/scripts/` twin is that target's manifest **source**
   (`manifest.json`: `source: templates/scripts/…`, `target: scripts/…`) and
   must never be listed: `RETIRED_TARGETS` derives from row
   `installed_targets` via `retired_surface_targets(id)`
   (`installer/removal.py:62-75`), and removal candidates are consumer-repo
   paths — listing a source path marks a consumer-owned `templates/scripts/`
   file for deletion (unconditional under `--force`). The twin is deleted as
   source cleanup in the same deletion commit instead — recorded in that
   task's implement.md.

   (`sd-watch-pr` needs no row — it already has a full retirement row at
   `:1315-1322`, landed at 0.57.0.) `identifiers` and the flag are populated by
   the deletion task, not here.
   **Gate:** the drift lint must stay green *after step 4 lands with it*. If it
   still reports `retired_identifier_live` then, the row is asserting absence
   for a surface that still ships — re-read `design.md` before adding
   allowances to paper over it.

4. **Teach the drift lint's manifest pass the schedule-only flag** (found in
   adversarial review; reasoning in `design.md`). The manifest pass
   (`check-command-surface-drift.py:449-462`) intersects retirement
   `installed_targets` with live `manifest.json` targets unconditionally;
   without this change the three rows from step 3 produce
   `retired_identifier_live` for every shipped target. Skip retirements with
   `source_paths_must_be_absent=False` there, mirroring the source-checkout
   pass (`:632-646`, flag at `:633`). Add unit coverage in the checker's existing test module:
   a schedule-only row whose targets are live in the manifest stays clean; an
   enforcing (`True`) row still flags.
   **Gate:** step 3's rows + this change together leave
   `python3 .github/scripts/check-command-surface-drift.py` green with **zero**
   new `CommandSurfaceAllowance` entries.

5. **Do not add these rows to `RETIRED_TARGETS`** (`installer/removal.py:62-75`
   as of 2026-07-31 — four alias groups whose targets are **derived from the
   registry rows** via `retired_surface_targets(id)`; only the ids are
   hand-enumerated). That tuple drives install-time deletion; enumerating the
   new ids there deletes surfaces that are still supposed to work.
   **Gate:** `installer/removal.py` unchanged in this task's diff.

6. **Add the catalog status.** Implement the combined literal decided in
   `design.md`:
   `included in installed pack — transitional until <version>; use <successor>`
   — availability fact preserved, `<version>` **derived from the registry
   row's `removed_version`** (no literal `0.62.0` in the generator). Add
   `SUPERSEDED_COMMANDS: dict[name, (successor_name, retirement_id)]` in
   `installer/registry.py` (validated like `SOURCE_ONLY_COMMAND_NAMES`: known
   names, known successors, retirement ids present), branch
   `.github/scripts/generate-command-surfaces.py:353-357` on it, and add the
   sd-help SKILL.md instruction to recommend the named successor for
   transitional rows. The catalog is fanned out to eleven skill roots, so this
   is a generator change plus `make sync`. Three rows change: `sd-review-local`
   (`:40`), `sd-full-check` (`:43`), `sd-review-pr` (`:54`). Successors:
   `sd-review`, `sd-check`, `sd-review` respectively. Extend
   `tests/test_help_command.py` (availability literals asserted at `:573-574`)
   with the transitional-row assertions.
   **Coverage requirement (adversarial review round 2):** `installer/*` sits on
   a 100% coverage gate (`Makefile` — `coverage report
   --include="install.py,installer/*" --fail-under=100`), so every validation
   branch of the new `SUPERSEDED_COMMANDS` check needs a negative test:
   unknown command name, unknown successor name, and retirement id absent from
   `RETIRED_COMMAND_SURFACES`. Follow the retirement-schema negative cases at
   `tests/test_help_command.py:246`.

7. **Add the CHANGELOG deprecation note** — `CONTRIBUTING.md:156-157` requires
   deprecated public aliases stay documented until the removal release and that
   the removal be noted in `CHANGELOG.md`.

8. **Confirm the review-loop decision point is covered elsewhere.**
   Owned by `07-24-simplify-review-shipping-composition` R8.
   **Verified landed 2026-07-31:** `docs/SD_AI_COMMAND_PACK.md:340-346` routes
   an `sd-ship` chain to publish-and-return; only a standalone invocation
   reaches the transitional loop. Nothing to edit here.

9. `make sync`.

10. **Release step** (adversarial review: `CONTRIBUTING.md:95-110` — bump the
    manifest whenever shipped payload changes; the catalog rows and sd-help
    SKILL.md ship). Bump `manifest.json` to `0.60.0`, add the `0.60.0`
    CHANGELOG heading carrying the deprecation note from step 7, and run
    `make release-prep`. The Release payload gate CI job fails the PR
    otherwise.

## Validation

The decisive check — `sd-help` must report the transitional status rather than
recommending the legacy command:

```bash
.venv/bin/python -m unittest tests.test_help_command -v
```

Drift lint must stay green with the new rows present:

```bash
python3 .github/scripts/check-command-surface-drift.py
```

Confirm every registry row carries a version (count assignment sites only, not
the dataclass field or its reader):

```bash
grep -c 'removed_version="' installer/registry.py
```

Expect 7 (4 existing rows as of 2026-07-31 + 3 new).

```bash
make sync && make check
```

## Review gates

- Before step 3: the version number is agreed with the deletion task, not chosen
  unilaterally.
- After steps 3–4 (they land together): drift lint green **without** new
  `CommandSurfaceAllowance` entries. Needing allowances means the rows were
  written in the wrong shape.
- After step 5: `git diff --stat installer/removal.py` is empty.
- After step 10: `make release-prep` green; manifest version and CHANGELOG
  heading both read `0.60.0`.
- Before completion: the four interim findings (A-114, A-102, A-059, A-043) are
  each explicitly marked either "resolved by deletion at `<version>`" or "interim
  fix required here". Leaving them implicit is how they get rediscovered.

## Rollback

Plain revert. Nothing installed changes, no consumer behavior changes, and the
rows are inert at install time — the only cost of reverting is having published
a version number and withdrawn it.

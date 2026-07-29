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

## Order

1. **Pick the version.** Coordinate with `07-24-remove-retired-review-surfaces`
   on when deletion can realistically land, and record the reasoning in the task.
   **Gate:** one number, agreed by both tasks. `remove-retired-review-surfaces`
   R8 forbids minting a second one.

2. **Decide the `review-local.sh` / `review-local.py` fate** (PRD R5). Both are
   covered by the version; 771 + 2,232 lines. Write the decision down.
   **Gate:** decided before the rows are written — it changes what
   `installed_targets` lists.

3. **Add four schedule-only `RetiredCommandSurface` rows** after
   `installer/registry.py:1268`, one each for `sd-full-check`, `sd-review-local`,
   `sd-review-pr`, `sd-watch-pr`, in the `fleet-refresh-consumer-targets` shape:

   ```python
   identifiers=(),
   source_paths_must_be_absent=False,
   removed_version="<agreed>",
   owner_task="07-24-remove-retired-review-surfaces",
   ```

   `identifiers` and the flag are populated by the deletion task, not here.
   **Gate:** the drift lint must stay green. If it reports
   `retired_identifier_live`, the row is asserting absence for a surface that
   still ships — re-read `design.md` before adding allowances to paper over it.

4. **Do not add these rows to `RETIRED_TARGETS`** (`installer/removal.py:69-73`).
   That tuple drives install-time deletion; adding them there deletes surfaces
   that are still supposed to work.
   **Gate:** `installer/removal.py` unchanged in this task's diff.

5. **Add the catalog status.** Implement the machine-readable transitional /
   superseded-by field chosen in `design.md`, teach `sd-help` to read it, and
   regenerate. The catalog is fanned out to eleven skill roots
   (`SHARED_SKILL_REFERENCES`), so this is a generator change plus `make sync`.
   Four rows change: `sd-full-check`, `sd-review-local` (`:40`), `sd-review-pr`
   (`:55`), `sd-watch-pr`.

6. **Add the CHANGELOG deprecation note** — `CONTRIBUTING.md:142-143` requires
   deprecated public aliases stay documented until the removal release and that
   the removal be noted in `CHANGELOG.md`.

7. **Confirm the review-loop decision point is covered elsewhere.**
   `docs/SD_AI_COMMAND_PACK.md:194` is owned by
   `07-24-simplify-review-shipping-composition` R8. If R8 has landed, verify;
   if not, do not duplicate the edit here — record the dependency.

8. `make sync`.

## Validation

The decisive check — `sd-help` must report the transitional status rather than
recommending the legacy command:

```bash
python3 -m pytest tests/test_help_command.py -q
```

Drift lint must stay green with the new rows present:

```bash
python3 .github/scripts/check-command-surface-drift.py
```

Confirm every registry row carries a version:

```bash
grep -c "removed_version" installer/registry.py
```

Expect 7 (3 existing + 4 new).

```bash
make sync && make check
```

## Review gates

- Before step 3: the version number is agreed with the deletion task, not chosen
  unilaterally.
- After step 3: drift lint green **without** new `CommandSurfaceAllowance`
  entries. Needing allowances means the rows were written in the wrong shape.
- After step 4: `git diff --stat installer/removal.py` is empty.
- Before completion: the four interim findings (A-114, A-102, A-059, A-043) are
  each explicitly marked either "resolved by deletion at `<version>`" or "interim
  fix required here". Leaving them implicit is how they get rediscovered.

## Rollback

Plain revert. Nothing installed changes, no consumer behavior changes, and the
rows are inert at install time — the only cost of reverting is having published
a version number and withdrawn it.

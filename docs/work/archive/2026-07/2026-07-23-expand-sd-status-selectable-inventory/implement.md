# Selectable sd-status inventory implementation plan

## Implementation steps

1. Add focused failing tests in `tests/test_status.py` for deterministic task
   and roadmap classification, selection IDs, empty sections, follow-up kinds,
   human rendering, malformed/symlink exclusions, and read-only behavior.
2. Extend the template collector's Trellis record and sorting helpers, then add
   the complete `tasks` and open-root `roadmap` views without changing the
   existing lifecycle arrays.
3. Add normalized follow-up candidate construction and F-prefixed local
   rendering. Preserve existing anomaly and next-step compatibility behavior
   while removing task-backed work from the follow-up category.
4. Add F-prefixed fleet follow-up rendering while keeping fleet task detail in
   nested JSON/local reports and retaining the bounded rollout table.
5. Update the canonical `sd-status` skill and distributed guide to require the
   F/T/R final-response shape, exact `none` behavior, report-local selector
   semantics, and canonical Trellis ownership.
6. Update adapter/status contract tests and the frontend adapter spec where the
   new behavior is an executable project convention.
7. Bump the pack minor version and top changelog heading, run `make sync`, and
   review every generated/dogfood change for scope and byte parity.
8. Run focused tests and static checks, then regenerate exact-payload fleet
   candidate evidence after the payload is final.
9. Run `make check`, review the final diff, update acceptance criteria with
   validation evidence, and commit the task-scoped change.

## Validation commands

```bash
PYTHONPYCACHEPREFIX=/private/tmp/sd-status-selectable-pycache \
  .venv/bin/python -m unittest \
    tests.test_status tests.test_sdlc_commands tests.test_generated_parity \
    tests.test_housekeeping

.venv/bin/ruff check \
  templates/scripts/sd-ai-command-pack-status.py \
  scripts/sd-ai-command-pack-status.py \
  tests/test_status.py

make sync

bash scripts/sd-ai-command-pack-toolchain.sh run-python -- \
  scripts/sd-ai-command-pack-fleet-candidate-check.py

make check
```

## Review gates

- Confirm no status path writes to Git, GitHub, Trellis, work-loop, or profile
  state.
- Confirm the same task cannot receive two T IDs or two R IDs in one report.
- Confirm all active-root tasks are present in T rows and only open root tasks
  are present in R rows.
- Confirm `none` is visible in each empty human category.
- Confirm housekeeping strict mode still returns the same success/failure
  status and required anomaly evidence.
- Confirm template/root byte parity and payload-bound candidate evidence.

## Rollback points

- Before the version bump, the collector/skill/test changes can be reverted as
  one additive feature set.
- After the version bump, revert manifest, changelog, payload, generated files,
  docs, and candidate ledger together; do not publish a partial rollback.

## Start gate

Do not run `task.py start` or edit implementation files until the user reviews
and approves `prd.md`, `design.md`, and this implementation plan.

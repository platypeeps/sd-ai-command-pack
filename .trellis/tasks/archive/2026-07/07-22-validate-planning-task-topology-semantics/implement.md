# Implementation plan: planning task topology semantics

## Activation

1. After explicit implementation approval, validate this task, start it through
   Trellis, and load the backend quality contract for the implementation phase.
2. Confirm the branch and task metadata still describe a `main`-based source
   change before editing shipped payload.

## Test-first semantic coverage

3. Extend `tests/test_review_preflight.py` with helper and executable fixtures
   that reject a deferred child with an unrelated inherited feature base.
4. Add positive fixtures for a child using the parent's durable base and a
   child intentionally stacked on the parent's active branch.
5. Add changed-parent fixtures that:
   - reject a child omitted from `prd.md` when `task.json` changes;
   - reject prose-only removal when only `prd.md` changes;
   - require exact child-ID token boundaries;
   - accept child references outside a prescribed heading; and
   - fail closed for missing, symlinked, non-regular, or oversized PRDs.
6. Retain explicit coverage that unchanged legacy prose, archived PRDs,
   standalone tasks, assigned-branch tasks, and existing valid stacks remain
   outside the new rejection boundary.

## Canonical implementation

7. In `templates/scripts/sd-ai-command-pack-review-preflight.mjs`, add one
   semantic topology check adjacent to the structural task metadata check.
8. Reuse changed-path discovery, active/archive task lookup, bounded file reads,
   and result caps. Add only small pure helpers for parent-relative base
   validation and exact child-ID matching where they improve test clarity.
9. Keep missing or unsafe linked parent records owned by the existing
   reciprocal metadata diagnostics so the new check does not duplicate errors.
10. Update `.trellis/spec/backend/quality-guidelines.md` with the changed-scope
    contract, good/base/bad cases, failure matrix, and required regression
    coverage.

## Payload and release synchronization

11. Bump `manifest.json` from `0.30.8` to `0.31.0` and add the matching
    `2026-07-22` top entry to `CHANGELOG.md` because the preflight gains a new
    consumer-visible rejection rule.
12. Run `make sync` only after the template, tests, spec, and release identity
    are final; verify the root preflight mirror is byte-identical to the
    template.
13. Regenerate the full exact-payload fleet candidate ledger with:

    ```bash
    bash scripts/sd-ai-command-pack-toolchain.sh run-python -- \
      scripts/sd-ai-command-pack-fleet-candidate-check.py
    ```

    Do not substitute a partial consumer run for the committed ledger.

## Validation

14. Run focused syntax and behavior checks:

    ```bash
    node --check templates/scripts/sd-ai-command-pack-review-preflight.mjs
    .venv/bin/pytest -q tests/test_review_preflight.py
    cmp templates/scripts/sd-ai-command-pack-review-preflight.mjs \
      scripts/sd-ai-command-pack-review-preflight.mjs
    ```

15. Verify the generated ledger against the final payload:

    ```bash
    bash scripts/sd-ai-command-pack-toolchain.sh run-python -- \
      scripts/sd-ai-command-pack-fleet-candidate-check.py --check-ledger
    ```

16. Run `make check`, review the authored/generated diff, and use the normal
    update-spec, review, finish-work, and PR lifecycle. Do not bypass a failed
    semantic check or fleet candidate result.

## Stop points

- Stop and report if current metadata cannot express an intended stack without
  rejecting a known-valid workflow; expanding the schema is a separate design
  decision.
- Stop before release publication if the full-fleet candidate run cannot
  validate the exact synchronized payload.
- Any Trellis-owned creation-default improvement remains a separate handoff and
  requires explicit approval for an upstream Trellis PR.

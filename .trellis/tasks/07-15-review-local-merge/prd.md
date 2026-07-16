# Merge sd-review-local-all into sd-review-local (all=)

## Problem
Two commands differ only by the script's --full-codebase flag; duplicate
skill/docs/manifest surface (~25 entries).

## Goal
One sd-review-local with an `all` argument; -all removed everywhere;
consumer refreshes delete the orphaned installed files.

## Requirements
Parent design § 2 is binding: skill content merge, COMMAND_NAMES removal +
regeneration, installer legacy-removal wiring with a test, docs/lists
merge, changelog removal notice with replacement invocation.

## Acceptance Criteria
- [ ] `sd-review-local all` documents/executes the full-codebase loop.
- [ ] No sd-review-local-all references remain in manifest/templates/docs/
      test expectation lists (historical changelog/journals exempt).
- [ ] Removal test: stale -all files deleted on refresh; audit clean.

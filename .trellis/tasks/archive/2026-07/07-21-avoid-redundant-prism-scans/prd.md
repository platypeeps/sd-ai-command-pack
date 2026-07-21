# Avoid redundant Prism scans in full-check

## Goal

Reduce the cost and cycle time of the full-check Prism lane by avoiding a
committed-range review when the same run is already reviewing in-flight local
work, while preserving coverage of distinct staged and unstaged changes and all
existing required/optional failure behavior.

## Background

- GitHub issue #203 reports that `run_prism_reviews` can invoke Prism for
  unstaged changes, staged changes, and the merge-base-to-HEAD range in one
  full-check run.
- Prism exposes separate `unstaged`, `staged`, and revision-range review
  targets; it does not expose a single combined committed-plus-index-plus-worktree
  diff target.
- The shipped `sd-review-local` runner already uses local-first precedence:
  local changes suppress the branch-diff fallback, while a clean working tree
  selects the committed branch diff.
- `templates/scripts/sd-ai-command-pack-full-check.sh` is authoritative and
  the root script is a synchronized installed mirror.

## Requirements

- Full-check must select one review scope per invocation:
  - if tracked unstaged or staged changes exist, review the non-empty local Git
    layers and do not also review the committed branch range;
  - otherwise, review the merge-base-to-HEAD range when it is non-empty.
- Preserve separate staged and unstaged Prism calls when both layers are
  non-empty; they represent different Git diffs and neither may be silently
  omitted.
- Preserve `SD_AI_COMMAND_PACK_FULL_CHECK_PRISM=0`, `auto`, and `required`
  availability and exit-code behavior.
- Preserve merge-base diagnostics for the clean-tree branch-review path.
- Keep the template/root runtime mirrors and consumer-facing documentation
  synchronized.
- Publish the shipped runtime change through the normal pack version,
  changelog, provenance, and fleet candidate-validation process.
- Add focused regression coverage for mixed committed/staged/unstaged state,
  clean-tree committed state, and unchanged required/optional handling.

## Acceptance Criteria

- [x] A branch with committed work plus staged and unstaged changes invokes
      Prism for staged and unstaged changes only, never the committed range.
- [x] A clean working tree with committed branch work invokes exactly one Prism
      range review.
- [x] A local-only staged or unstaged state invokes only its corresponding
      Prism review target.
- [x] Prism-disabled, unavailable, required, and provider-error behavior remains
      unchanged.
- [x] The full-check template and root mirror remain byte-identical.
- [x] Focused tests and `make check` pass on the final payload.
- [x] All configured fleet candidates validate against the final payload.

## Out of Scope

- Combining staged and unstaged diffs through temporary commits, index
  mutation, or a new Prism feature.
- Changing `sd-review-local`, Gito targeting, full-codebase review, or Prism's
  provider/model behavior.
- Expanding full-check's current handling of untracked files.

## Notes

- Origin: [platypeeps/sd-ai-command-pack#203](https://github.com/platypeeps/sd-ai-command-pack/issues/203).
- Proposed decision: align full-check with the established local-first
  `sd-review-local` scope contract instead of adding a cache or content-digest
  deduplication layer.
- Validation: `tests.test_full_check` passed 34 tests; `make check` passed the
  complete repository gate; the candidate ledger records all seven configured
  fleet consumers passing against pack version `0.25.5`.

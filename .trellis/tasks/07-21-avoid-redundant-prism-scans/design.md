# Design: Local-first Prism scope selection in full-check

## Architecture and Boundaries

The change stays inside the full-check Prism orchestrator. The authoritative
runtime is `templates/scripts/sd-ai-command-pack-full-check.sh`; `make sync`
updates the root installed mirror. Prism argument construction and exit-status
handling remain unchanged.

## Scope Selection Contract

`run_prism_reviews` first detects tracked local diffs:

1. Record whether the working tree has unstaged changes.
2. Record whether the index has staged changes.
3. If either local layer is non-empty, run Prism once for each non-empty layer
   and return without resolving or reviewing the committed branch range.
4. If both local layers are empty, resolve the merge base and review the
   non-empty merge-base-to-HEAD range.

This produces at most two Prism calls for a dirty tree and exactly one for a
clean feature branch. Staged and unstaged calls are retained because Git defines
them against different snapshots; dropping either would lose review coverage.

## Compatibility

- No environment variable or CLI contract changes.
- `run_prism_command` continues to own optional-versus-required provider
  failures, so scope selection cannot weaken the gate.
- Merge-base failure/no-diff warnings remain available when branch review is
  the selected scope.
- Repositories relying on the old three-scan behavior receive fewer paid Prism
  calls but no new failure modes.

## Trade-offs

- Committed branch work is deferred until the working tree is clean. This
  matches the existing `sd-review-local` contract and favors the operator's
  newest in-flight state during iteration.
- A digest/cache system could deduplicate individual hunks across all three
  targets, but would add persistent state, invalidation rules, and provider
  coupling without improving the clean-tree final review.
- A temporary combined diff would require index or commit manipulation and is
  rejected as unsafe for a verification command.

## Operational and Rollback Considerations

The behavior is shell-only and stateless. Rollback restores the prior
`run_prism_reviews` ordering. Tests use a stub Prism executable and isolated Git
repositories so no provider calls or credentials are required.

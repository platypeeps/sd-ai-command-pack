# Design: recurring review-learning signal clustering

## Data flow

Retain GitHub collection and `PullRequestComment` normalization. Insert a pure
analysis layer between collection and Markdown rendering:

1. Partition current actionable comments from historical comments.
2. Normalize a historical finding signature from bounded body text, path
   family, and repository-owned category rules.
3. Aggregate exact signatures, then group signatures under stable categories.
4. Rank actionable rows and historical clusters separately.
5. Render bounded evidence summaries and category-derived preventive actions.

## Determinism and safety

- Category rules are an ordered constant table with stable identifiers.
- Normalization removes volatile line numbers and repeated whitespace without
  erasing security-sensitive distinctions such as path family or failure mode.
- Each cluster retains counts and original URLs; no evidence is invented.
- Caps apply to clusters, signatures, PR identifiers, paths, and example links.
- All remote text continues through existing Markdown and control-character
  sanitization.

## Compatibility

CLI selectors and GitHub pagination remain unchanged. The renderer continues
to own only the managed block and preserves human-curated content. Existing
consumers that inspect headings retain `Local Pattern Findings`,
`Recent Copilot Review Signals`, and `Suggested Preventive Actions`; the signal
section gains explicit actionable and clustered subsections.

## Verification

Use synthetic comment fixtures for duplicates, related-but-distinct findings,
current versus historical state, Markdown-sensitive paths, shuffled input,
large windows, and idempotent updates. Add a captured multi-PR fixture that
reproduces the PR #206 terminology cluster without requiring live GitHub.

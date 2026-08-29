# Design

## Decision

Keep `PullRequestComment.markdown_item()` as the canonical renderer for remote
GitHub provenance. Its code-spanned path is readable, escapes untrusted managed
markers, and remains stable across refreshes. Use a fence longer than any
backtick run in a path so Markdown-sensitive remote filenames cannot break out
of that code span. Change the documentation-path preflight so it does not
interpret content inside the complete managed `sd-review-learnings` block as
claims about files in the current checkout.

This addresses both sources of false positives: the rendered review-path label
and path-like code spans copied from review-comment bodies. Changing only the
path label would leave comment-body snippets exposed, while exempting the
entire `docs/review-learnings.md` file would also disable useful checks in its
human-authored sections.

## Boundary

Add a small exported preflight helper that masks complete managed blocks only
for `docs/review-learnings.md`. Replace every non-newline character in a
matched block with spaces so references outside the block retain their original
line numbers. An absent or incomplete marker pair is not masked; malformed
content therefore remains visible to the normal validator instead of widening
the exemption.

The generic path extractor and resolver remain unchanged. Other documentation,
including human-authored content before and after the managed block, continues
to use the existing local path contract.

## Safety

- Preserve renderer-side neutralization of managed-block markers in paths,
  bodies, and URLs.
- Do not make GitHub review paths conditional on current checkout contents.
- Do not weaken documentation path checks outside a complete generated block.
- Keep `templates/**` canonical and synchronize the root script twin.
- Regenerate the managed snapshot with the unchanged renderer after the
  preflight exemption is covered, removing the temporary plain-text bridge.

## Verification

Focused tests will prove that:

- missing paths in generated path labels and comment bodies are ignored;
- missing paths in human-authored content surrounding the block still fail;
- line numbers after a masked block remain accurate;
- incomplete marker pairs are not exempted;
- Markdown-sensitive and managed-marker review data remains neutralized; and
- template/root parity and the canonical pack checks pass.

Because the preflight script is shipped, the change requires a patch version,
matching changelog entry, refreshed generated knowledge, and normal release
validation.

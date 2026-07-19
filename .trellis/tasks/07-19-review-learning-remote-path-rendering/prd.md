# Render remote review paths without local path validation

## Goal

Prevent generated review-learning snapshots from treating historical GitHub review paths as current local documentation references, with renderer regression coverage and normal shipped-payload release handling.

## Background

Running `sd-review-learnings --github-days 2 --update` after the 0.21.4 fleet
rollout captured historical Copilot comments whose remote PR paths no longer
exist in the current checkout or deliberately demonstrate invalid paths. The
renderer wraps every remote path in a Markdown code span, and comment bodies
can contain their own path-like code spans. The general documentation-path
preflight therefore interprets remote provenance as claims that those paths
exist in the current checkout and fails the canonical gate.

## Requirements

- Treat paths and path-like snippets copied from GitHub review threads as
  remote provenance, not current local documentation references.
- Keep remote paths readable while safely escaping untrusted Markdown and
  managed-block marker content.
- Preserve current versus historical thread classification and PR links.
- Add focused renderer coverage for missing, archived, and Markdown-sensitive
  review paths.
- Verify an updated `docs/review-learnings.md` containing missing historical
  paths in both labels and comment bodies passes documentation-path preflight
  without weakening checks for normal documentation code spans and links.
- Update the canonical template and installed mirror together.
- Follow manifest version, changelog, release, and fleet-refresh rules because
  the renderer is shipped to consumers.

## Acceptance Criteria

- [x] Generated remote review-path labels do not enter the local path-reference
      validator.
- [x] Ordinary missing local paths in documentation still fail preflight.
- [x] Managed-marker and Markdown-injection protections remain covered.
- [x] Template parity, focused tests, and the canonical source check pass.
- [x] The shipped change is versioned and released through the normal process.

## Out Of Scope

- Rewriting or summarizing historical Copilot comment meaning.
- Weakening path validation outside the managed review-learning snapshot.
- Creating a pull request in the upstream Trellis repository.

## Results

- The review preflight now masks only complete managed review-learning blocks
  during local path extraction and preserves newlines for accurate diagnostics.
- Human-authored references around the block and incomplete marker pairs remain
  in the normal local path check.
- Remote paths containing backticks use a longer Markdown code-span fence while
  the existing managed-marker neutralization remains in force.
- The managed snapshot was regenerated with the canonical renderer from 25
  recent PRs and 58 Copilot comments.
- Release `0.21.5` passed focused tests, the full canonical check, and disposable
  candidate validation for all seven configured consumers.

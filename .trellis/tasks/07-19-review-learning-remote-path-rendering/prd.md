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

- [ ] Generated remote review-path labels do not enter the local path-reference
      validator.
- [ ] Ordinary missing local paths in documentation still fail preflight.
- [ ] Managed-marker and Markdown-injection protections remain covered.
- [ ] Template parity, focused tests, and the canonical source check pass.
- [ ] The shipped change is versioned and released through the normal process.

## Out Of Scope

- Rewriting or summarizing historical Copilot comment meaning.
- Weakening path validation outside the managed review-learning snapshot.
- Creating a pull request in the upstream Trellis repository.

# Implementation Plan

1. Add a managed review-learning block masker to the canonical review-preflight
   template. Preserve newlines and apply it only before extracting local path
   references from `docs/review-learnings.md`.
2. Synchronize `scripts/sd-ai-command-pack-review-preflight.mjs` from the
   canonical template.
3. Extend exported-helper tests for complete, incomplete, and line-preserving
   masking behavior.
4. Add an installed-repo preflight regression containing a missing remote path
   label and a missing path-like comment-body span inside the managed block,
   plus a missing human-authored path outside it.
5. Extend renderer tests with missing, archived, Markdown-sensitive, and
   managed-marker inputs so the stable rendering and injection protections are
   explicit.
6. Regenerate `docs/review-learnings.md` through the pack script so the managed
   block again matches the renderer contract.
7. Bump the manifest patch version and add the matching top changelog entry.
8. Run focused review-preflight and review-learning tests, template parity,
   the repository KB refresh, release gates, and the canonical full check.

## Rollback

Reverting the masker and its tests restores the prior strict interpretation.
No persistent data migration is involved; regenerated documentation can be
refreshed again with the renderer.

# README audience split: consumer content first, maintainer content grouped

## Goal

Make the README serve a consumer (installing/using the pack) without wading
through maintainer-only material. Group the maintainer sections at the end under
a single "Maintaining" umbrella, keeping consumer content (Overview, Commands,
Configuration, Install, Supported Adapters) up front. Pure reorganization — no
information loss and no change to any test-pinned string.

## Problem

The README interleaves audiences: the consumer path (Overview → Commands →
Configuration → Install → Supported Adapters) is split by ~190 lines of
maintainer-only sections — Verify, Releasing, Fleet Rollout, Direct-to-main
Chore Commits, Upstream Path — so an installer scrolls past release/CI machinery
that does not concern them (docs-review finding 4).

## Requirements

- R1: Move the maintainer sections (Verify, Releasing, Fleet Rollout,
  Direct-to-main Chore Commits, Upstream Path) to the end of the README, after
  the consumer sections, grouped under a single top-level "## Maintaining" (or
  similar) heading. Consumer sections (Overview, Commands, Configuration Quick
  Reference, Install, Supported Adapters) remain in reading order up front.
  License stays last.
- R2: This is a REORDER, not a rewrite: move whole sections verbatim. Do not
  delete or reword content, and preserve every existing cross-reference/anchor
  (update any in-page `#anchor` links whose target heading moved).
- R3: Preserve all strings the test suite pins. `tests/test_generated_parity.py`
  asserts ~23 exact README substrings (e.g. `make setup`, `make check`,
  `[CONTRIBUTING.md](CONTRIBUTING.md)`, the smoke-test/SANDBOX_TMP block, the
  coverage commands). Every one must still be present. Run
  `python3 -m unittest tests.test_generated_parity` (via .venv) after the reorg.

## Constraints

- README.md only — not shipped payload (not in `templates/`, not watched by the
  release gate), so NO manifest version bump.
- `make test` (esp. `test_generated_parity`), `make lint`, and `make full-check`
  stay green; the review-preflight doc-path checker
  (`node scripts/sd-ai-command-pack-review-preflight.mjs`) passes (no broken
  in-page or file links).

## Acceptance Criteria

- [ ] Consumer sections precede maintainer sections; maintainer sections grouped
      under one "Maintaining" umbrella near the end; License last.
- [ ] All ~23 pinned README strings still present (`test_generated_parity` green).
- [ ] No content deleted or reworded (a `git diff` shows moves, not rewrites);
      any moved-heading anchors updated; review-preflight passes.
- [ ] `make test` / `make lint` / `make full-check` green; no version bump.

## Non-goals

- Rewriting or further trimming section content (Batch C already deduped);
  moving maintainer content into CONTRIBUTING.md (keep it in-README under the
  umbrella, with the existing CONTRIBUTING pointer intact).

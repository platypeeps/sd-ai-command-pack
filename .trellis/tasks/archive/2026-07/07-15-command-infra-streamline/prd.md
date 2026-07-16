# Command infrastructure streamline (0.13.0)

## Problem

Adding one command costs 1 skill + 1 neutral body + 3 hand-authored bespoke
adapters + ~25 hand-written manifest entries + parity-list insertions; the
manifest is now 534 hand-maintained entries growing 25 per command. Audit
findings A-034 (adapter transform rules live in tests, not a generator) and
A-009/A-012 (parallel structures synced by convention) describe the cost.
Separately, sd-review-local and sd-review-local-all differ only by a script
flag, and the publish→merge endgame spans four commands with no one-command
path.

## Goal

One 0.13.0 release with three deliverables: (1) generate bespoke command
adapters and registry-derived manifest entries from a single command list;
(2) merge sd-review-local-all into sd-review-local behind an `all` argument
with clean consumer migration; (3) add sd-ship, a composite orchestrator
chaining create-pr → review-pr → watch-pr → housekeeping with stop-points.

## Requirements

- R1. Generation is dev-side tooling (no new shipped scripts): a generator
  under .github/scripts/ + a Makefile target + a drift test asserting the
  committed surfaces match regeneration. Generated files stay committed.
- R2. The command list becomes a single registry-owned source of truth;
  adding a command = skill + neutral body + one list entry.
- R3. Hand-authored bespoke bodies that intentionally diverge (the parity
  exemption set) remain hand-authored via an explicit generator override
  list; the parity tests keep verifying them.
- R4. A one-time canonical manifest regeneration (reordering) is accepted;
  semantic protection comes from existing set/uniqueness/install tests.
- R5. sd-review-local absorbs the full-codebase mode as `all`; the -all
  command's targets are removed from the manifest AND wired into the
  installer's legacy-removal mechanism so consumer refreshes delete the
  orphaned files; docs and tests updated; changelog states the removal.
- R6. sd-ship adds no new gate logic: every stage's own gates remain
  authoritative; `until=pr|review|merge` stop-points (default merge) plus
  pass-through of stage arguments; zero new env vars.
- R7. All existing gates stay green; one version bump 0.11.0→…→0.13.0 with
  a CHANGELOG entry covering all three deliverables.

## Acceptance Criteria

- [ ] A1. `make generate` reproduces every committed generated surface
  byte-identically; the drift test fails on any hand-edit to them.
- [ ] A2. Adding a test command to the list (in a scratch check) yields
  complete adapters + manifest entries with no other edits.
- [ ] A3. sd-review-local-all is gone from manifest/docs/lists; its
  installed files are removed on consumer refresh (removal-mechanism test);
  `sd-review-local all` covers the full-codebase loop.
- [ ] A4. sd-ship ships with the full adapter surface via the generator and
  passes format-drift tests pinning stop-points and gate deference.
- [ ] A5. make test + make full-check green; 0.13.0 + CHANGELOG.

## Out of scope

- Trellis-owned (trellis-*) adapter surfaces.
- Deriving non-command manifest entries (scripts/configs/docs stay static).
- Fleet rollout of 0.13.0.

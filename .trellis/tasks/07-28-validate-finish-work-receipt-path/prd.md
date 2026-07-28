# Validate finish-work receipt paths at CLI boundary

## Goal

Reject missing, unreadable, non-regular, or unsafe finish-work receipt paths before housekeeping performs external work, while preserving authoritative downstream revalidation.

## Background

- `sd-ai-command-pack-housekeeping.sh` currently rejects an empty or
  option-shaped `--finish-work-receipt` value but accepts missing files,
  directories, symlinks, and unreadable paths until downstream processing.
- Delayed rejection makes operator diagnostics less precise and can occur only
  after the workflow has begun KB refresh or remote inspection.
- The eligibility evaluator already performs authoritative receipt parsing and
  exact-head revalidation; an early filesystem check must not replace or weaken
  that gate.
- `templates/scripts/sd-ai-command-pack-housekeeping.sh` is the shipped source
  of truth; the root script is its byte-verified mirror.

## Requirements

- Validate the receipt path after argument parsing and before KB refresh,
  network access, Git mutation, or merge eligibility work.
- Require an existing readable regular file. Reject directories, missing
  paths, non-regular files, and symlinks with stable bounded diagnostics and the
  documented usage/error exit code.
- Do not echo secrets, control characters, or uncontrolled host-specific path
  material in diagnostics.
- Preserve independent receipt parsing, schema validation, exact-head
  recomputation, and equality comparison in the eligibility evaluator; the
  early check is diagnostic hardening, not eligibility proof.
- Preserve fail-closed behavior if the file changes or disappears after the
  early check.
- Update the template first, keep the root script byte-identical, and document
  the accepted path contract.

## Acceptance Criteria

- [ ] A readable regular receipt reaches the existing eligibility evaluator.
- [ ] Missing, directory, symlink, non-regular, and unreadable fixtures fail
  before KB refresh, fetch, merge, or branch cleanup.
- [ ] Failure diagnostics are stable and bounded, return the documented error
  code, and expose no unsafe raw value.
- [ ] Replacement or disappearance after the early check still fails in the
  authoritative downstream validator and cannot reach merge.
- [ ] Existing exact-head receipt, dependency-PR, dry-run, and self-test paths
  remain compatible.
- [ ] Template/root parity, focused housekeeping tests, and `make check` pass.

## Out of Scope

- Parsing or trusting receipt JSON in shell code.
- Relaxing the independent eligibility evaluator or exact-head merge gates.
- General temporary-file or recovery-artifact lifecycle changes.

## Notes

- Source finding: `platypeeps/people-profiles` PR #3 review thread on
  `sd-ai-command-pack-housekeeping.sh`, observed 2026-07-27 UTC.
- Keep this task separate from `track-clean-recovery-artifacts`, which owns
  stash/worktree artifact receipts rather than finish-work evidence input.

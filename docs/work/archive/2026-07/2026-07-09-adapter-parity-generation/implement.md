# Enforce Adapter Content Parity And Generate Command Fan-Out Implementation Plan

## Execution Order

1. Diff OpenCode command templates against neutral command templates and choose
   the `sd-review-learnings` resolution.
2. Update manifest entries for byte-identical OpenCode commands to use neutral
   sources, then remove obsolete duplicate files.
3. Add shared-body extraction helpers for Claude, Gemini, GitHub, and OpenCode
   where needed.
4. Add registry-derived expected thin-platform command-entry assertions.
5. Reconcile GitHub housekeeping prompt text or record the intended deviation.
6. Run install/dry-run parity checks and refresh root dogfood copies if needed.

## Validation Plan

Run `python3 -m unittest tests.test_generated_parity tests.test_pack_drift` and
the full-check pack-drift lane. Add a temporary body-drift fixture in a test or
commented verification note to prove the new parity assertion fails when a
bespoke body changes.

## Documentation And Spec Updates

Update the existing adapter guideline spec, or create a command-surface spec
only if the implementation adds that new spec file. The spec should say the
neutral source owns shared body text and the registry owns thin fan-out
expectations.

## Review Notes

Reviewers should confirm installed output remains byte-identical for platforms
whose behavior is not intentionally changed.

## Follow-Ups

If registry-derived manifest generation becomes large, split generator tooling
into a new task rather than expanding this one beyond parity enforcement.

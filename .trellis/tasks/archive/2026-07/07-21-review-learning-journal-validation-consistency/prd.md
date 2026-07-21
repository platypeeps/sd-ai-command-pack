# Enforce journal validation consistency

## Goal

Prevent Software Delivery review completion from recording internally
contradictory Trellis journal sessions, and fail deterministically when a
completed session claims validation while retaining Trellis' default
"validation not recorded" Testing text.

## Background

RWBP Coordinator PR #167 exposed the gap: Session 66 said the full quality
gate was verified in its Summary, while Testing still said validation was not
recorded. Copilot caught the contradiction after the deterministic preflight
had passed.

The upstream pack already ships
`scripts/sd-ai-command-pack-record-session.py`, and `sd-finish-work` requires
that wrapper when journal recording begins. The wrapper supplies concrete
change/test lines and refuses placeholder output. However, standalone
`sd-review-pr` Step 8 currently reads and invokes `trellis-finish-work`
directly, bypassing `sd-finish-work` and therefore bypassing the safe recorder.

The review preflight already validates completed journal placeholders,
journal/index commit parity, and append-only history. It does not recognize the
newer Trellis fallback text as contradictory when the same session positively
claims tests or a quality gate passed.

## Requirements

- Extend the shipped review preflight to reject a completed Trellis journal
  session when both conditions hold:
  - Summary or Main Changes contains a recognized positive validation claim;
  - Testing retains either supported default fallback form:
    `Validation was not recorded for this session.` or
    `Validation not recorded for this session.`
- Keep the contradiction rule narrow: completed planning/no-validation
  sessions, incomplete sessions, explicit failure/skip statements, and
  sessions with concrete Testing evidence must not fail.
- Report the journal path, exact Testing line, session number, and corrective
  action in the failure.
- Change non-deferred `sd-review-pr` lifecycle ownership to resolve and execute
  `sd-finish-work`, which remains responsible for delegating to Trellis and
  using `sd-ai-command-pack-record-session.py` at the journal step.
- Preserve existing `defer-finish-work`, already-merged housekeeping,
  finish-work commit pushing, and final PR-state refresh behavior.
- Update template sources first and synchronize all dogfood/generated mirrors.
- Add focused regression coverage for preflight detection, false-positive
  boundaries, and review-to-finish-work routing.
- Publish as a compatible patch release with changelog, documentation,
  manifest, provenance, and fleet-candidate validation kept consistent.

## Out of Scope

- Changing Trellis' `add_session.py` defaults or opening an upstream Trellis
  pull request.
- Rejecting every completed session that legitimately records no validation.
- Changing remote-review triggering, CI convergence, merge, or housekeeping
  policy.
- Rewriting historical journal entries in consumer repositories.

## Acceptance Criteria

- [ ] A completed session that claims a passed gate/test in Summary or Main
      Changes and retains a supported default Testing fallback fails preflight
      with a line-specific diagnostic.
- [ ] Focused tests prove planning-only, incomplete, explicitly failed/skipped,
      and concretely tested sessions remain accepted.
- [ ] Standalone/non-deferred `sd-review-pr` resolves and uses
      `sd-finish-work`; deferred flows retain their existing owner and wording.
- [ ] `sd-finish-work` remains the single wrapper that invokes Trellis
      finish-work and records journals through the pack recorder.
- [ ] Template/root/generated parity tests pass after synchronization.
- [ ] The patch release metadata, changelog, docs, candidate ledger, and full
      `make check` gate pass.

## Notes

- Parent: `07-21-review-learning-preventive-actions`.
- Consumer evidence: RWBP Coordinator PR #167, Session 66 review thread.

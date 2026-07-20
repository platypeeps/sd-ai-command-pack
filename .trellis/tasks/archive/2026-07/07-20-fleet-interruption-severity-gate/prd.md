# Enforce fleet interruption severity policy

## Goal

Prevent low-risk hardening, documentation, diagnostics, style, and unrelated
consumer findings from unnecessarily stopping an otherwise healthy fleet
rollout.

## Background

- The fleet guide already limits rollout interruptions to correctness,
  security, installation or audit, and compatibility defects.
- The 0.23.11 corrective chain treated some test-only, changelog, diagnostic,
  and observability findings as reasons for fresh review or release work.
- Remote-review findings must still be verified and addressed; classification
  determines timing, not whether feedback is ignored.

## Requirements

- Define documented finding classes with two outcomes:
  `block-corrective-release` and `defer-follow-up`.
- Treat verified correctness, security, install or audit, and compatibility
  defects as blockers. Treat low-risk hardening, style, test implementation,
  documentation wording, diagnostic quality, and unrelated consumer findings
  as follow-ups unless evidence shows higher impact.
- Require a short evidence-backed rationale for every classification and allow
  the operator to override it explicitly.
- Reply to and resolve verified review threads according to their disposition;
  deferred does not mean silently ignored.
- Detect exact duplicate reviewer findings so they share one disposition and
  do not produce duplicate corrective work.
- Include blocker and deferred-finding summaries in fleet status and final
  reports.
- Update fleet documentation, relevant skills/templates, and regression tests.

## Acceptance Criteria

- [ ] A correctness, security, install/audit, or compatibility fixture stops
      the rollout before another consumer merge.
- [ ] Test-only, documentation-only, low-risk diagnostic, and unrelated
      findings produce follow-ups without forcing a new patch release.
- [ ] Duplicate findings do not create duplicate tasks or version bumps.
- [ ] Every disposition includes evidence and remains operator-overridable.
- [ ] Existing unresolved threads still block housekeeping until replied to and
      resolved or otherwise settled by policy.
- [ ] Tests exercise each class, escalation from follow-up to blocker, and the
      operator override.

## Out of Scope

- Automatically dismissing remote-review feedback.
- Reducing the source repository's correctness or security bar.

## Notes

- Add `design.md` and `implement.md` before starting implementation.

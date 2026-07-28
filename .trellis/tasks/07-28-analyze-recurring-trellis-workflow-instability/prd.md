# Analyze recurring Trellis workflow instability

## Goal

Review recent Trellis-backed sessions across repositories, identify recurring status and journaling recovery failures, determine root causes and fixes, and map findings to existing sd-ai-command-pack tasks.

## Requirements

- Review the 2026-07-14 through 2026-07-28 session inventory for every
  indexed checkout whose resolved repository root contains `.trellis/`.
- Separate workflow defects from expected fail-closed gates, stale installed
  pack versions, sandbox/filesystem restrictions, and ordinary GitHub review
  settlement.
- Identify repeated lifecycle and journaling failure classes with concrete
  repository, session, PR, reason-code, or task evidence.
- Verify which mitigations are already shipped in the current command pack
  and which remain only as planned Trellis tasks.
- Map every recommended fix to one existing task when ownership is already
  clear; identify uncovered gaps without creating duplicate tasks.
- Keep the review read-only outside this task directory and do not modify
  consumer repositories or upstream Trellis.

## Acceptance Criteria

- [x] Recent indexed sessions are inventoried across every physical Trellis
      repository, with aliases deduplicated and coverage limits disclosed.
- [x] Recurring failures are grouped by root cause rather than counted from
      repeated transcript text.
- [x] Shipped mitigations are verified against current source and focused
      tests.
- [x] Consumer pack and Trellis versions are compared to identify rollout
      skew.
- [x] Remaining work is mapped to active tasks and uncovered gaps are called
      out explicitly.
- [x] A durable research report records evidence, conclusions, and the
      recommended implementation order.

## Notes

- Findings: `research/recent-trellis-workflow-instability.md`.
- New-session handoff and finding-to-task ownership map: `handoff.md`.
- Accepted remediation tasks:
  - `07-28-stabilize-self-hosted-delivery-lifecycle`
  - `07-28-route-housekeeping-by-pr-lifecycle-state`
  - `07-28-standardize-environment-blocked-recovery-evidence`
  - `07-28-roll-out-stabilized-pack-release-to-fleet`
- Accepted upstream Trellis planning tasks:
  - `07-28-harden-add-session-retry-convergence`
  - `07-28-restore-install-safe-opencode-mem-reader`
- OpenCode session storage is not indexable by Trellis 0.6.7; the report does
  not claim OpenCode coverage. Upstream restoration is now tracked by the
  second task above.

# Add per-job dispatch protocol to sd-fix-ci

Parent: `.trellis/tasks/07-25-agent-artifacts` (Tier 1 pilot). Settled inputs: parent
`design.md` section 1 and `research/cross-platform-agent-support.md`.

## Goal

Pilot the SD dispatch pattern in sd-fix-ci: one read-only sub-agent per failing CI job,
each consuming only that job's failure logs in isolation and returning a typed triage
result, so the parent context stops absorbing every job's full log output.

## Requirements

- R1: Dispatch section modeled on the sd-audit-repo protocol (the house template):
  capability-first phrasing, "on sub-agent dispatch platforms run per-job triage in
  parallel; on inline platforms classify jobs sequentially in one context" fallback.
- R2: Worker contract: input = one failing job's identity + its `--log-failed` output +
  the change context; output = classification (`real-code | flake | infra |
  stale-baseline`), evidence quotes, and a suggested fix or rerun disposition. Workers are
  read-only; fixes are applied by the parent.
- R3: Checkout-trust preflight classification is restated in every dispatch prompt;
  structured answers cannot override safety gates; untrusted/indeterminate handling
  unchanged from the current command.
- R4: Parent owns job IDs, result assembly, fix application, rerun, and the final report;
  report contract unchanged.
- R5: Inline platforms produce the same outcome as today (no scope change).

## Acceptance Criteria

- [ ] sd-fix-ci canonical body carries the dispatch section; `make generate` byte-stable
      across all platform adapters; catalog regenerated.
- [ ] Worker result contract documented in the command body; classifications unchanged.
- [ ] Trust restatement present in the dispatch protocol text.
- [ ] Version bump + dated changelog entry per repo rules.

## Dependencies / order

- Independent of Tier 2 tasks (works with host built-in sub-agents).
- 07-25-dispatch-rollout MUST wait for this pilot. Informs the later sd-ci-triager named
  agent (07-25-worker-agents).

## Notes

- Lightweight-to-medium; PRD + short design note likely sufficient.

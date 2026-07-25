# PARKED: Add Review Effectiveness Command

> Status: BLOCKED (external) — do not `task.py start`. Requires: stable paired-review and trusted-adjudication projections from sd-github-review. Marked 2026-07-25; see Dependencies.

## Goal

Add read-only `sd-review-effectiveness` reporting so users can evaluate
parallel reviewers' correctness, marginal value, reliability, latency, and
cost without automatically changing configuration.

## Requirements

- Compare reviewers directly only within the same repository, PR, parent plan,
  exact head, lane, and relevant configuration period.
- Consume explicit trusted correctness/relationship/resolution evidence.
  Preserve unresolved when trust is missing or disputed.
- Report completion/failure/timeout/ambiguity/deferral; adjudication coverage;
  accepted/invalid/duplicate/superseded counts; conditional precision;
  overlap; unique valid findings; marginal unique accepted findings; cost and
  latency per completed/adjudicated/accepted/unique-accepted result; and
  provider-diversity resilience.
- Never claim recall without an independent ground-truth defect set.
- Separate correctness, complementarity, redundancy, resilience, cost, and
  latency rather than collapsing them into one score.
- Segment by lane, risk/path family, configuration digest, model/prompt/policy
  period, and bounded time window.
- Require configurable minimum paired sample, trusted adjudication coverage,
  and evidence freshness before recommendations.
- Emit deterministic schema-versioned JSON plus concise human/Markdown output;
  remain advisory and read-only.

## Acceptance Criteria

- [ ] Same-head paired fixtures distinguish valid, invalid, duplicate,
      superseded, unresolved, overlapping, and unique findings.
- [ ] A noisy reviewer with invalid findings cannot outrank a quieter reviewer
      through raw volume.
- [ ] Duplicate valid findings receive overlap credit but no duplicate
      marginal-value credit.
- [ ] Missing/stale/truncated/mixed-head/disputed evidence produces
      `insufficient-evidence` with numerator, denominator, limitations, and
      evidence needed.
- [ ] Reliability/resilience remains distinct from correctness and marginal
      finding value.
- [ ] One/two/many-reviewer, cheap/deep, Copilot-only, and generic candidate
      fixtures are deterministic and provider-neutral.
- [ ] The command makes no learning update, configuration mutation, stage,
      commit, push, review request, or external write.

## Dependencies

- Parent `07-25-add-multi-reviewer-learning-and-effectiveness-analysis`.
- Stable paired review and trusted adjudication projections from
  `platypeeps/sd-github-review`.

## Out of Scope

- Automatic reviewer/model changes, adaptive fan-out, complete-recall claims,
  or finding adjudication.

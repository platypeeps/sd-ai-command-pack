# Roll out sd-ai-command-pack 0.55.2 across the fleet

## Goal

Deliver the immutable `sd-ai-command-pack` 0.55.2 release to every eligible
consumer in the configured fleet through the deterministic campaign
controller, including review, merge, and post-merge verification.

## Background

- Release `v0.55.2` resolves to
  `02554f8f72481325777acc8cf9ec1313f553ba30` locally and on `origin`.
- The current source checkout has the same commit and manifest version
  `0.55.2`.
- The user approved task creation and a merge-capable full-fleet rollout.
- Campaign ID: `fleet-v0-55-2-20260727T135308Z`.
- Timing run ID: `fleet-v0-55-2-20260727T135308Z`.
- Corrective child task:
  `07-27-correct-fleet-merge-finalization-head-epoch` owns the released-pack
  head-epoch blocker discovered at the first consumer merge.

## Requirements

- Treat `docs/fleet/consumers.json`, the candidate ledger, release tag, and
  controller actions as authoritative.
- Process the full configured fleet in controller-issued canary and bounded
  wave order with integration-only review when the exact refresh qualifies.
- Create and activate one dedicated lightweight Trellis task in each eligible
  clean consumer before installation; do not repurpose unrelated work.
- Skip dirty, missing, externally owned, or already-at-target consumers using
  the controller's normalized result without stashing, resetting, cleaning,
  cloning, or broadening scope.
- Execute eligible consumer refresh commits, pushes, PRs, configured reviews,
  finding remediation, lifecycle merges, and post-merge audits without
  additional approval, as authorized by `sd-fleet-refresh`.
- Record every issued action exactly once with its release, consumer, head,
  PR, and bounded result evidence; preserve mandatory private timing evidence.
- Stop new mutations for a verified pack-owned blocker, ambiguous side effect,
  invalid controller state, or unsafe ownership condition.

## Campaign Outcome

- Controller campaign `fleet-v0-55-2-20260727T135308Z` completed with a valid
  ledger and complete timing evidence.
- Merged and post-merge audited: `rwbp-coordinator` PR #180, `loadsmith` PR
  #172, `hoa-manager` PR #186, and `se-ai-command-pack` PR #108.
- Ownership-skipped without mutation: `rwbp-website` (active PR #179 and task),
  `mezmo_benchmark` (active dirty 0.55.0 stream), and
  `anomaly-metric-creator` (active automation PR #306 for 0.55.1).
- `sd-github-review` PR #28 reached exact head
  `92f855080e5ccb668f2d93a4567e0800c80b8291` with its Windows UTF-8 stdin
  review finding fixed and resolved, then parked as `retry-exhausted` after the
  second legitimate head advance. Child task
  `07-27-complete-sd-github-review-rollout-after-retry-exhaustion` owns the
  required fresh controller-authorized continuation.
- The finding severity gate classified all three review observations as
  non-blocking hardening. Their follow-ups are captured in
  `07-27-align-review-scope-gemini-settings`,
  `07-27-align-review-preflight-claude-hooks`, and
  `07-27-upstream-claude-statusline-utf8-stdin-fix`.

## Acceptance Criteria

- [x] Controller planning and source preflight validate immutable release
      `0.55.2`, the full-fleet ledger, fleet policy, and checkout identities.
- [x] Every selected consumer reaches a terminal controller outcome with no
      unrecorded issued action.
- [x] Every merged refreshed consumer passes install audit, repository checks, review
      convergence, exact-head merge eligibility, managed housekeeping, and
      post-merge installed-version/audit verification.
- [ ] The parked `sd-github-review` lane completes exact-head re-review,
      eligibility, housekeeping merge, and post-merge audit through a fresh
      controller-authorized attempt.
- [x] At-target or ownership-skipped consumers have explicit evidence and are
      not mutated.
- [x] Controller `validate` and final `status` pass, and the complete timing
      report accounts for all selected consumers.
- [x] The final report itemizes campaign, fleet, scheduling, findings, timing,
      and follow-ups, explicitly using `none` for empty categories.

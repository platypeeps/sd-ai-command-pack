# PARKED: Complete sd-github-review 0.55.2 rollout after retry exhaustion

## Goal

Complete the `sd-github-review` consumer lane after the bounded fleet controller
parked its second legitimate PR-head advance as `retry-exhausted`.

## Requirements

- Keep the lane parked until a new controller-authorized rollout attempt owns
  the existing checkout and PR #28.
- Start from published head
  `92f855080e5ccb668f2d93a4567e0800c80b8291`; do not replay the completed
  install, task archive, journal, review remediation, or old controller action.
- Retain and revalidate
  `/private/tmp/fleet-v0-55-2-sd-finish-work-28-successor.json` only while its
  exact repository, branch, lineage, and head evidence remain unchanged.
- Request and require a materialized remote review for the current exact head,
  settle late inline threads, and rerun merge eligibility without rerunning the
  already completed review-learnings scan for PR #28.
- Invoke housekeeping only from a fresh controller-issued merge action, then
  run the immutable 0.55.2 post-merge audit and verify a clean synchronized
  default branch.
- Preserve the completed campaign
  `fleet-v0-55-2-20260727T135308Z` as immutable evidence; never edit its private
  controller state to reopen the exhausted lane.

## Completed Campaign Evidence

- Merged and post-merge audited: `rwbp-coordinator` PR #180, `loadsmith` PR
  #172, `hoa-manager` PR #186, and `se-ai-command-pack` PR #108.
- Ownership-skipped without mutation: `rwbp-website` (active PR #179 and task),
  `mezmo_benchmark` (active dirty 0.55.0 stream), and
  `anomaly-metric-creator` (active automation PR #306 for 0.55.1).
- The completed controller ledger validates and its complete timing report
  accounts for all eight selected consumers.
- Review findings were classified as non-blocking hardening and captured in
  `07-27-align-review-scope-gemini-settings`,
  `07-27-align-review-preflight-claude-hooks`, and
  `07-27-upstream-claude-statusline-utf8-stdin-fix`.

## Acceptance Criteria

- [ ] A new controller-authorized action is bound to the unchanged PR #28 head,
      or the task records the safe replacement head and why it changed.
- [ ] The exact merge head has materialized remote-review evidence, green
      required checks, and zero unresolved review threads.
- [ ] Housekeeping consumes a valid exact-head completion receipt and merges
      PR #28 without bypassing the controller or retry bound.
- [ ] The immutable 0.55.2 audit passes for all 174 managed targets on the
      synchronized default branch, and the refresh branch is removed.

## Notes

- Trigger: explicitly start a fresh fleet/controller attempt after reviewing
  the completed campaign's `retry-exhausted` receipt.
- PR #28 already contains the verified Windows UTF-8 stdin remediation at
  `92f855080e5ccb668f2d93a4567e0800c80b8291`.

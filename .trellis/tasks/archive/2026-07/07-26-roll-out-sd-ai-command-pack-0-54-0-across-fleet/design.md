# Fleet rollout 0.54.0 design

## Overview

The source checkout coordinates an eight-consumer operational campaign without
becoming the authority for lane state. The versioned controller owns campaign
transitions and issues bounded actions; existing repository-local commands own
installation, checks, review, watch, housekeeping, and post-merge audit.

## Authorities and boundaries

| Boundary | Authority |
| --- | --- |
| Release and payload identity | `v0.54.0`, `origin`, source preflight, candidate ledger |
| Fleet membership and scheduling | `docs/fleet/consumers.json` |
| Campaign actions and receipts | fleet controller private state |
| Stage timing | fleet timing helper private state |
| Consumer mutation | one controller-issued lane in its configured checkout |
| Review profile | source review classifier plus `sd-review-pr` |
| Merge | controller-issued consumer `sd-housekeeping` action |
| Final evidence | controller validate/status and complete timing report |

The source repository records only this Trellis task and its session evidence.
Private campaign and timing state stays outside repositories. Consumer lanes
may change only installer-managed payload, receipts/provenance, and declared
deterministic preparation output.

## Data flow

1. Fetch the exact release tag, create one safe campaign ID and timing run ID,
   and plan the controller campaign for all manifest consumers.
2. Initialize timing, request the controller's preflight action, execute the
   source preflight, and record its normalized receipt.
3. Repeatedly request controller actions. For every action, validate its
   consumer, attempt, timeout, and side-effect boundary; execute it once through
   the documented owner; record timing and one controller receipt.
4. After PR publication, overlap reviewer and CI timing. Review may run the
   proven integration-only profile or fall back to remote review. Findings pass
   through the severity classifier before watch or merge.
5. The controller releases at most one merge action in manifest order. The
   consumer housekeeping gate proves exact head and cleans the merged lane.
6. Post-merge verification proves target provenance, install audit, default
   branch cleanliness, and refresh-branch cleanup before the lane terminates.
7. Controller validation/status and the complete timing report produce the
   final campaign record.

## Scheduling

- Canary cohort: `rwbp-coordinator`, then `loadsmith`, then `hoa-manager`.
- Post-canary cohort: `rwbp-website`, `mezmo_benchmark`,
  `se-ai-command-pack`, and `sd-github-review`, with at most two active lanes.
- Final cohort: `anomaly-metric-creator` alone.
- Review and CI waits may overlap within a lane. Consumer writes never overlap
  within one checkout, and merges remain serialized.

## Failure and recovery

- Dirty, missing, divergent, or live-owned checkout: record the controller's
  bounded ownership result; do not repair or broaden scope.
- Ambiguous review classification: select normal remote review, not failure.
- Pack-owned blocking finding: record `review-finding --pack-blocker`, pause
  new starts and merges, and retain the campaign for a corrective release.
- Issued action with uncertain side effect or controller/timing error: stop,
  use controller `resume`, and load the controller recovery procedure. Never
  replay the action from chat history.
- Consumer-local deferred finding: reply and resolve when allowed, create or
  reuse its follow-up task, then record the normalized non-blocking result.

## Compatibility and rollback

The campaign never rewrites `v0.54.0` and never force-rolls consumers back.
Before PR publication, an invalid lane remains local for inspection. After PR
publication, recovery follows the PR and controller state. A released-pack
defect requires a new corrective pack release and resume of this campaign.

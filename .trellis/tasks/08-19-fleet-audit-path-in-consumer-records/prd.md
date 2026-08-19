# Correct the fleet install-audit path cited in consumer task records

## Goal

Five consumers refreshed in campaign `v0-71-33-20260819T095717Z` carry a task
PRD acceptance criterion and a journal testing note that cite
`scripts/sd-ai-command-pack-install-audit.py` as if it were a path inside the
consumer. Every one of those consumers is a thin install, so no such file
exists there. Correct the five records and close the source of the mistake in
this pack's own documentation.

## Background

`docs/FLEET_ROLLOUT.md` step 3 instructs the operator to run

```
python3 scripts/sd-ai-command-pack-install-audit.py --repo <repo> ...
```

That relative path is correct, because the step runs **from the pack source
checkout** with `--repo` pointed at the consumer. The surrounding prose does not
say so, and the command was transcribed into each consumer's own task record,
where the same relative path resolves to nothing.

GitHub Copilot independently flagged this on both open refresh pull requests
(`platypeeps/rwbp-website#252`, `answerbook/mezmo_benchmark#514`), citing
`.sd-ai-command-pack/installed-targets.txt` as evidence that the path is not an
installed target. The finding is correct.

The installed payload is unaffected: the audit itself ran from the pack source
checkout against each consumer and passed with `31 targets checked` and matching
vouched hashes on all five. This is a defect in the durable record of how the
work was verified, not in the verification.

## Requirements

- Correct the acceptance criterion in the `08-19-sd-ai-command-pack-0-71-33`
  PRD that each consumer keeps under its own `.trellis/tasks/archive/2026-08/`
  directory, so it describes the audit as running from the sd-ai-command-pack
  source checkout with `--repo` pointed at that repository, with no
  consumer-relative path.
- Correct the matching `[OK]` testing note in each consumer's journal entry the
  same way. Keep the recorded result (`31 targets checked`, provenance 0.71.33,
  vouched hashes match) unchanged — it is accurate.
- Fix `docs/FLEET_ROLLOUT.md` step 3 so the command's working directory is
  explicit, and the next operator cannot transcribe it into a consumer record
  the same way.
- Fix the stale work-commit citation in `rwbp-website`. Its journal entry and
  `.trellis/workspace/sdelmas/index.md` both cite
  `7ab13689c95030c58372cbe14f01cee0f06d3481`, which is not the commit that
  merged: the branch was rebased onto the prep fix in `platypeeps/rwbp-website#253`,
  and the work commit became `662d9500b1445e5762093a926fa513a86a609515`.
- Land one pull request per affected repository. These are separate repositories
  with separate review gates; do not attempt a single cross-repo change.

## Affected repositories

| Consumer | Checkout | Refresh PR |
| --- | --- | --- |
| rwbp-coordinator | `~/repos/rwbp/rwbp-coordinator` | #246 |
| loadsmith | `~/repos/platypeeps/loadsmith` | #240 |
| hoa-manager | `~/repos/platypeeps/hoa-manager` | #273 |
| rwbp-website | `~/repos/rwbp/rwbp-website` | #252 (also needs the commit-hash fix) |
| mezmo_benchmark | `~/repos/mezmo/mezmo_benchmark` | #514 |

All five refresh pull requests are already merged, so each correction is an
ordinary content change on that repository's default branch, not a
post-archive-review-successor on the refresh branch.

## Why this was deferred rather than fixed in the refresh PRs

The two open lanes had already spent the fleet controller's head-republication
budget: `PR_HEAD_REPUBLICATION_STAGES` allows a `pr-head-advanced` rewind only
while `attempt < 2`, and `_next_stage_attempt` only ever increments, so a third
published head would have driven both lanes to terminal `retry-exhausted` for a
documentation-wording change. Fixing two of the five consumers mid-campaign
would also have left the fleet's task records inconsistent. The finding was
answered and its review threads resolved on both pull requests with a
`defer-follow-up` disposition pointing at this task.

## Acceptance Criteria

- [ ] No consumer's archived 0.71.33 task PRD or journal entry cites an
  install-audit path that does not resolve in that consumer. Verified by
  enumerating the task directories from the filesystem and grepping each for
  `scripts/sd-ai-command-pack-install-audit.py`, expecting zero hits across all
  five.
- [ ] `docs/FLEET_ROLLOUT.md` step 3 states the working directory the command
  runs from.
- [ ] `rwbp-website` cites `662d9500b1445e5762093a926fa513a86a609515` as the
  0.71.33 refresh work commit in both its journal entry and its workspace index,
  with no remaining reference to the pre-rebase hash.
- [ ] Each affected repository's own default-branch gate passes on the change.

# Roll out sd-ai-command-pack 0.8.6 to the fleet

## Goal

Use docs/fleet/consumers.json and scripts/sd-ai-command-pack-fleet-preflight.py to refresh all six consumers to 0.8.6 via PRs, verify post-install audit completeness with explicit expected platforms, confirm hoa-manager and rwbp-coordinator regain .claude/commands/sd/work-backlog.md, and add a superseding/correction note to the archived 07-06 close-fleet-refresh-loop PRD for hoa-manager.

## Requirements

- R1: Run `python3 scripts/sd-ai-command-pack-fleet-preflight.py` on current
  `main` and use its target version, path hints, and platform sets as the
  source of truth for the rollout.
- R2: For each `refresh-needed` consumer, create a PR-only branch, run the
  printed `python3 install.py <repo> --force --platform ...` command from the
  pack checkout, and run the printed install-audit command with every
  `--expected-platform` from the fleet manifest.
- R3: Do not open duplicate or empty refresh PRs for repos already at target.
  If a repo is reported `at-target`, record the evidence and skip it.
- R4: Confirm all six consumers end on provenance version 0.8.6 and their
  install audits pass after merge:
  anomaly-metric-creator, hoa-manager, loadsmith, rwbp-coordinator,
  rwbp-website, and answerbook/mezmo_benchmark.
- R5: Explicitly verify the two previously broken consumers, hoa-manager and
  rwbp-coordinator, have `.claude/commands/sd/work-backlog.md` present on disk,
  listed in `.sd-ai-command-pack/installed-targets.txt`, and represented in
  provenance.
- R6: Add a superseding correction note to the archived
  `07-06-close-fleet-refresh-loop` PRD explaining that hoa-manager is a real
  sixth consumer in the current fleet inventory.

## Acceptance Criteria

- [x] Fleet preflight output captured before rollout and shows no duplicate
      at-target work.
- [x] Six consumer PRs are created or skipped with evidence; every opened PR is
      merged green.
- [x] Post-merge provenance in all six consumers reads `0.8.6`.
- [x] Post-merge audit passes in all six consumers with explicit
      `--expected-platform` arguments from `docs/fleet/consumers.json`.
- [x] hoa-manager and rwbp-coordinator contain the Claude work-backlog command
      on disk, in receipts, and in provenance.
- [x] Archived close-fleet-refresh-loop PRD has a dated superseding note for
      the six-consumer inventory correction.
- [x] A final ledger lists each repo, PR number, merge state, installed version,
      audit result, and any anomalies.

## Notes

- Follow-up from archived task `07-09-fleet-refresh-081-completeness`: PR #88
  completed the pack-side manifest/preflight/audit tooling, but the actual
  fleet rollout acceptance criteria remain open here.
- The initial rollout target was 0.8.5. Consumer CI exposed two pack-owned
  blockers, so this task now rolls forward to 0.8.6 instead of merging the
  flawed 0.8.5 consumer payload.

## Final Ledger - 2026-07-10

Fleet preflight now reports all six consumers `at-target` for
`sd-ai-command-pack` 0.8.6 with no duplicate work:

- `platypeeps/anomaly-metric-creator`: PR
  [#232](https://github.com/platypeeps/anomaly-metric-creator/pull/232)
  merged 2026-07-10T01:12:49Z as
  `7597cb3b49b61102b3dcb6d8799dc4b378d0c7e8`; audit passed for
  `claude`, `gemini`, `github`, and `opencode` with 87 targets and
  provenance version 0.8.6.
- `platypeeps/hoa-manager`: PR
  [#102](https://github.com/platypeeps/hoa-manager/pull/102) merged
  2026-07-10T01:12:51Z as
  `66586ac196810d090e9b1f7c2907d88c4c43f4c1`; audit passed for
  `claude`, `gemini`, `github`, and `opencode` with 87 targets and
  provenance version 0.8.6. `.claude/commands/sd/work-backlog.md` is present,
  listed in `.sd-ai-command-pack/installed-targets.txt`, and vouched in
  `.sd-ai-command-pack/provenance.json`.
- `platypeeps/loadsmith`: PR
  [#68](https://github.com/platypeeps/loadsmith/pull/68) merged
  2026-07-10T01:12:50Z as
  `6b9412ce6374edb54c755bd66f15d132fe3986e0`; audit passed for
  `claude`, `gemini`, `github`, and `opencode` with 87 targets and
  provenance version 0.8.6. Non-blocking warning: generated
  `docs/repomix-map.md` still contains legacy command names
  `sd-refresh-specs`, `trellis-full-check`, `trellis-housekeeping`, and
  `trellis-review-pr`.
- `answerbook/mezmo_benchmark`: PR
  [#341](https://github.com/answerbook/mezmo_benchmark/pull/341) merged
  2026-07-10T01:12:49Z as
  `b3369f623a89b606cfa6dedb61d902ff9bc535b0`; audit passed for
  `claude`, `gemini`, `github`, and `opencode` with 87 targets and
  provenance version 0.8.6. Repo-local follow-up fixes in the PR updated the
  review-cycle guard/checklist and full-check test fixture for the new shared
  shell library.
- `platypeeps/rwbp-coordinator`: PR
  [#102](https://github.com/platypeeps/rwbp-coordinator/pull/102) merged
  2026-07-10T01:12:51Z as
  `37d3f6592fe77b1860ef6dd2c09e17564c1bdd17`; audit passed for
  `claude`, `cursor`, `gemini`, `github`, and `opencode` with 100 targets and
  provenance version 0.8.6. `.claude/commands/sd/work-backlog.md` is present,
  listed in `.sd-ai-command-pack/installed-targets.txt`, and vouched in
  `.sd-ai-command-pack/provenance.json`. Non-blocking warning: the
  rwbp-coordinator repo-owned review-churn checker still references
  `TRELLIS_REVIEW_PR_PACK.md`.
- `platypeeps/rwbp-website`: PR
  [#114](https://github.com/platypeeps/rwbp-website/pull/114) merged
  2026-07-10T01:12:53Z as
  `7c3d33c556b9f4c2985cfd3e2e859629e57a69ee`; audit passed for
  `claude`, `gemini`, `github`, and `opencode` with 87 targets and
  provenance version 0.8.6.

Post-merge local cleanup completed for all six consumers: each checkout is on
`main`, matches `origin/main`, and the local/remote rollout branch was removed.
The two audit warnings are existing repo-local legacy references, not installed
payload drift; they remain covered by `07-09-review-nits-cleanup`.

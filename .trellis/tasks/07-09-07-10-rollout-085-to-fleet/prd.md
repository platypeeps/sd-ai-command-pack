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

- [ ] Fleet preflight output captured before rollout and shows no duplicate
      at-target work.
- [ ] Six consumer PRs are created or skipped with evidence; every opened PR is
      merged green.
- [ ] Post-merge provenance in all six consumers reads `0.8.6`.
- [ ] Post-merge audit passes in all six consumers with explicit
      `--expected-platform` arguments from `docs/fleet/consumers.json`.
- [ ] hoa-manager and rwbp-coordinator contain the Claude work-backlog command
      on disk, in receipts, and in provenance.
- [ ] Archived close-fleet-refresh-loop PRD has a dated superseding note for
      the six-consumer inventory correction.
- [ ] A final ledger lists each repo, PR number, merge state, installed version,
      audit result, and any anomalies.

## Notes

- Follow-up from archived task `07-09-fleet-refresh-081-completeness`: PR #88
  completed the pack-side manifest/preflight/audit tooling, but the actual
  fleet rollout acceptance criteria remain open here.
- The initial rollout target was 0.8.5. Consumer CI exposed two pack-owned
  blockers, so this task now rolls forward to 0.8.6 instead of merging the
  flawed 0.8.5 consumer payload.

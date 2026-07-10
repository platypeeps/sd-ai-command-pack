# Roll Out sd-ai-command-pack 0.8.6 To The Fleet Implementation Plan

1. Run `python3 scripts/sd-ai-command-pack-fleet-preflight.py` on pack `main`
   and capture the output as the starting ledger.
2. For each `refresh-needed` repo, create a consumer branch, run the printed
   install command, run the printed audit command, then use that repo's normal
   SD create/review/housekeeping flow.
3. Skip any `at-target` repo and record the evidence instead of creating an
   empty PR.
4. After each merge, pull the consumer default branch and re-run the audit with
   the same explicit expected platforms.
5. In hoa-manager and rwbp-coordinator, additionally verify
   `.claude/commands/sd/work-backlog.md` exists, appears in
   `.sd-ai-command-pack/installed-targets.txt`, and has a provenance hash.
6. Add a dated superseding note to the archived close-fleet-refresh-loop PRD
   correcting the fleet inventory to include hoa-manager.
7. Update this task's PRD/check notes with the final ledger, then archive when
   every repo has evidence.

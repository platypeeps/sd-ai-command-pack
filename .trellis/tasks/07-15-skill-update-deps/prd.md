# sd-update-deps: dependency PR batch triage

## Problem
Four dependabot PRs in the 2026-07-15 session took multiple manual
decision rounds each; the audit added npm Dependabot coverage, growing
future volume.

## Goal
`/sd:update-deps` classifies open dependency-bot PRs and merges the safe
class through housekeeping-equivalent gates, sequentially, parking the
rest with recommendations.

## Requirements
Contract per parent design § sd-update-deps: auto-class = patch/minor
dev-deps + Actions SHA bumps + security patches; `include-runtime-minor`
flag; majors always manual; sequential merges with re-verification after
each (dependabot rebase races); `dry-run`; mandatory classification-table
report.

## Acceptance Criteria
- [ ] Skill + adapters + manifest wiring installed and tested.
- [ ] Format tests pin the auto-merge class definition, "majors always
      manual", and sequential-merge rule.
- [ ] Guide + README document it.

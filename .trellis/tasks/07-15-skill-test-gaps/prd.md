# sd-test-gaps: coverage-driven test authoring

## Problem
The audit found per-file coverage holes the aggregate floor hides
(fleet-preflight 62%, review-learnings 69%); the coverage-gate-per-file
task will make such gaps visible repo-wide, and there is no remediation
loop to close them.

## Goal
`/sd:test-gaps` ranks the worst-covered shipped files and writes targeted
tests for the top N through the normal implement/check flow.

## Requirements
Contract per parent design § sd-test-gaps: baseline coverage run first
(abort if red), per-file ranking, `file=` and `max-gaps=` (default 3)
args, tests/fixtures only (never product code), never lowers floors,
before/after report.

## Acceptance Criteria
- [ ] Skill + adapters + manifest wiring installed and tested.
- [ ] Format tests pin tests-only safety, baseline-abort, and the
      before/after report shape.
- [ ] Guide + README document it.

# sd-fix-ci: red-CI triage and fix loop

## Problem
Red CI triage (fetch logs, classify, fix or rerun) is frequent and manual;
the July guard bug left main CI red for days before a human noticed.

## Goal
`/sd:fix-ci` classifies failing checks (real / flake / infra /
stale-baseline), fixes real failures through the normal gated flow, reruns
flakes boundedly, and reports the rest.

## Requirements
Contract per parent design § sd-fix-ci: PR-branch default + `main` arg,
job→local-target mapping for repro, fix branch + PR for main failures
(never direct non-chore push), `max-reruns=` bounded (default 1), no
force-push / guard bypass / test-skipping, mandatory report with per-job
classification.

## Acceptance Criteria
- [ ] Skill + adapters + manifest wiring installed and tested.
- [ ] Format tests pin the classification set, bounded reruns, and the
      never-skip-tests safety rule.
- [ ] Guide + README document it.

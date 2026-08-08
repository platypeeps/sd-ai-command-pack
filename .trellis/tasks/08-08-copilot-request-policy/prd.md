# Single Copilot request owner fleet-wide

## Problem

Copilot premium requests are the real review cost (measured 2.07 reviews/PR
over 30 PRs on this repo; GitHub Actions on public repos bill $0 — billing
API `total_ms: 0`). Today THREE independent surfaces request Copilot reviews:

1. Repo-level automatic Copilot review ruleset (on the 8 fleet repos).
2. The pack's sd-review-pr skill direct path:
   `gh pr edit --add-reviewer @copilot` (`.agents/skills/sd-review-pr/SKILL.md:308-391`
   + template twin).
3. The sd-github-review router's request-copilot capability — the only path
   with duplicate-suppression and a durable head-bound receipt.

Overlap means duplicate premium requests per PR and no single place to apply
policy (e.g., skip bookkeeping-only PRs).

## Requirements

1. The router owns Copilot dispatch fleet-wide.
2. Delete the pack skill's direct `gh pr edit --add-reviewer @copilot` path
   (+ template twin); the skill delegates to the router lane.
3. Any remaining request logic gates on the bookkeeping/docs classification CI
   already computes — no Copilot request for bookkeeping-lane PRs.
4. Operator pass switches OFF the repo-level automatic Copilot review ruleset
   on all 8 fleet repos (enumerate from docs/fleet/consumers.json).
5. Depends on the sd-github-review durable-lane rollout (descriptor installed
   fleet-wide); sequence after it or gate per-repo.

## Acceptance criteria

- [ ] Repo-wide grep for `--add-reviewer @copilot` (aside from history) = 0.
- [ ] One Copilot review per PR head observed on a smoke PR (no duplicates).
- [ ] Ruleset state change recorded per repo (8 rows).
- [ ] Bookkeeping-lane PR triggers zero Copilot requests.

## Evidence

2026-08-08 cost audit: 2.07 reviews/PR; two independent code paths confirmed
(skill grep + router capability gates in review.py:765-850).

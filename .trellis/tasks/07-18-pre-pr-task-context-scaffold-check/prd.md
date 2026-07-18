# Detect task context scaffolds before PR creation

## Goal

Detect generated `_example` rows in changed Trellis task context before a pull
request is created, while continuing to allow untouched planning scaffolds.

## Requirements

- Extend the shared review preflight task-context check to inspect changed
  `implement.jsonl` and `check.jsonl` files when their task status is
  `in_progress`, `completed`, or archived.
- Keep `planning` task scaffolds valid so task creation and requirements work
  do not fail the preflight prematurely.
- Preserve the existing diff scope, JSONL parsing, symlink safety, malformed
  `task.json` diagnostics, and sibling-context behavior when `task.json`
  changes.
- Report the exact file and line for every own-property `_example` seed row,
  with grounded replacement-or-removal guidance.
- Keep the canonical template and installed script synchronized, update the
  public contract documentation, and follow shipped-payload release rules.
- Add focused regression coverage for planning, in-progress, completed, and
  archived task states.

## Acceptance Criteria

- [x] A changed `in_progress` task with `_example` context fails review
  preflight before PR creation.
- [x] A changed `planning` task with the same generated scaffolds still passes.
- [x] Replacing or removing the in-progress scaffolds makes preflight pass.
- [x] Existing completed, archived, malformed-status, nested-property, and
  symlink behavior remains covered and passing.
- [x] Template parity, release metadata, candidate evidence, focused tests,
  and the canonical repository checks pass.

## Follow-Up Adjustment

- [x] Local and JSON status report the repository's Git stash count.
- [x] Fleet status includes each available repository's stash count.
- [x] Saved stashes remain informational and do not make a clean repository
  unhealthy; unavailable stash inventory is reported explicitly.
- [x] Focused status tests and canonical repository checks pass.

## Copilot Churn Follow-Up

- [x] GitHub review-learning scans cover the complete UTC window by default,
  expose explicit truncation, and support direct PR selection.
- [x] Review preflight warns on added boundary-sensitive behavior, large
  authored-source surfaces, and changes spanning multiple Trellis tasks.
- [x] The PR review skill dispositions those warnings before remote review and
  attempts one PR-scoped learning pass only after the overall cycle completes.
- [x] The ship composite preserves that single owner and does not repeat the
  learning pass in a later stage.
- [x] Focused tests, template parity, public docs, specs, fleet candidate
  evidence, and canonical checks pass.

### First-Review Advisory Disposition

- The risk sweep triggered all five conservative categories because this task
  changes both the analyzer and its own categorization rules. Focused tests
  cover malformed GraphQL payloads, exact pagination/cutoff behavior, explicit
  truncation, missing or terminated Git processes, path/symlink boundaries,
  interpreter-global cleanup, and stable risk-category extraction. Digest
  behavior is classification-only; no integrity or hashing contract changed.
- The authored-source warning covers the combined task-context, status, and
  review-churn release work already tracked in this single task. The changes
  form one pre-PR reliability release and passed all seven fleet candidates;
  no second Trellis task directory is present in the diff.

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.

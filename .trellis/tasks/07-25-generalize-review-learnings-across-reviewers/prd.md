# PARKED: Generalize Review Learnings Across Reviewers

> Status: BLOCKED (external) — do not `task.py start`. Requires: stable learning projection from sd-github-review 07-25-publish-finding-adjudication-evidence. Marked 2026-07-25; see Dependencies.

## Goal

Keep `sd-review-learnings` focused on recurring feedback and preventive
repository guidance while replacing Copilot-only collection with generic,
disposition-aware evidence from every configured reviewer.

## Requirements

- Replace Copilot-specific internal collection/window types with
  reviewer-neutral structures while preserving semantically valid public scan,
  update, dry-run, JSON, containment, and atomic-write behavior.
- Use normalized receipts to attribute shared bot publications to reviewer,
  slot, candidate, provider/model, lane, plan, exact head, and configuration.
- Keep unresolved current findings individually actionable.
- Deduplicate one underlying issue across parallel reviewers before recurrence
  clustering; preserve all contributing reviewer identities.
- Permit trusted valid findings to support durable guidance. Exclude invalid
  findings; treat superseded findings as historical; never promote uncertain,
  disputed, or operational-only evidence as correctness.
- Preserve existing task-metadata, boundary-validation,
  contract/documentation, generated-surface, reviewer/test-harness, and
  fallback families unless evidence requires a new family.
- Report source/trust coverage, missing reviewers, unidentified publishers,
  stale/mixed-head exclusions, and truncation.
- Never rank reviewers, calculate model value, write adjudication, or
  automatically modify source guidance outside the existing explicit managed
  block update.

## Acceptance Criteria

- [ ] Copilot, native, PR-Agent, future generic, shared-bot, and unidentified
      publisher fixtures preserve correct provenance.
- [ ] Repeated duplicate reports create one underlying recurrence event and do
      not inflate preventive-action thresholds.
- [ ] Invalid evidence cannot enter guidance; unresolved current findings stay
      visible without being mislabeled as trusted lessons.
- [ ] Existing Copilot-only fixtures and scan/update/planning behavior remain
      compatible where semantics are unchanged.
- [ ] The managed block remains bounded, deterministic, atomically updated only
      through explicit update mode, and never contains secrets/raw output.
- [ ] Output does not rank reviewers or present recurrence as correctness.

## Dependencies

- Parent `07-25-add-multi-reviewer-learning-and-effectiveness-analysis`.
- Stable learning projection from
  `platypeeps/sd-github-review:07-25-publish-finding-adjudication-evidence`.

## Out of Scope

- Finding adjudication, effectiveness scoring, reviewer configuration, or
  automatic adoption of preventive guidance.

## Cross-program coordination (2026-07-25 review)

- This task's collection rework supersedes the per-PR gh GraphQL N+1 in
  `scripts/sd-ai-command-pack-review-learnings.py:1174` (SE-pack audit finding A-028).
  A tactical batching task exists (`07-25-batch-review-learnings-github`) for use ONLY if
  this task stays blocked and current runs hurt; when this task starts, mark the tactical
  task superseded (or fold its fixture work in).

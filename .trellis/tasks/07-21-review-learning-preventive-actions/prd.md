# Implement preventive actions from review learnings

## Goal

Turn repeated recent review findings into deterministic local guards and higher-signal review-learning output without duplicating protections already present.

## Background

The 2026-07-21 review-learning refresh inspected 40 pull requests updated in
the prior two days and captured 67 Copilot comments in
`docs/review-learnings.md`. Most comments describe already-fixed defects, so
the useful follow-up is to prevent recurrence rather than reopen historical
implementation work.

Two rendered recommendations already have concrete repository protections and
do not need duplicate tasks:

- `.github/copilot-instructions.md` already directs reviewers to focus on
  current, non-outdated unresolved findings.
- `scripts/sd-ai-command-pack-review-scope.sh` and review preflight already
  classify copied/generated payloads as integration and sync-contract surfaces.

## Requirements

- Deliver the preventive work through the four linked child tasks:
  - `review-learning-task-metadata-integrity`
  - `review-learning-boundary-contract-matrix`
  - `review-learning-signal-clustering`
  - `review-learning-journal-validation-consistency`
- Keep each child independently implementable, reviewable, and verifiable.
- Preserve template/root parity for every shipped script, skill, prompt, or
  instruction changed by a child.
- Prefer deterministic local guards and focused regression tests over broader
  reviewer prose.
- Do not recreate tasks for historical comments whose owning pull requests
  already fixed the defect.
- Keep the refreshed `docs/review-learnings.md` evidence in the delivery stream
  that creates these tasks.

## Out of Scope

- Reopening or rewriting merged historical pull requests.
- Creating one task per review comment.
- Upstream Trellis changes already represented by parked `upstream-*` tasks.
- Replacing Copilot or other remote review with local heuristics.

## Acceptance Criteria

- [ ] All four child tasks have converged PRDs, technical designs, and
      implementation plans with evidence-backed acceptance criteria.
- [ ] Existing current-thread and generated-surface protections are cited as
      covered rather than duplicated.
- [ ] Each child identifies its deterministic validation and template/source
      synchronization obligations.
- [ ] No child is activated automatically; implementation begins only after a
      separate user decision.
- [ ] Trellis task validation and the repository full-check pass for the
      planning-only change set.

## Notes

- Parent task only; implementation belongs to its independently verifiable
  children.

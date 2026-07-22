# Cluster recurring review-learning signals

## Goal

Deduplicate and cluster recent review comments into bounded evidence-backed signals and concrete preventive-action candidates.

## Background

The 2026-07-21 two-day scan rendered 67 individual comments from 40 PRs. Five
comments on PR #206 describe the same tracked-diff terminology issue across
different documentation surfaces, while larger families repeat task-metadata,
boundary-validation, and work-loop evidence concerns. Listing every historical
comment preserves evidence but obscures frequency and makes the suggested
actions generic rather than decision-ready.

Current, non-outdated unresolved comments must remain individually visible.
Only historical signals may be collapsed into clusters.

## Requirements

- Classify review comments into deterministic, repository-owned signal
  categories using normalized text and path-family evidence. Do not use an LLM
  or nondeterministic external service.
- Preserve every current, non-outdated unresolved comment as an individual
  actionable row before historical clusters.
- Deduplicate historical comments that share a normalized finding signature,
  while retaining total count, affected PRs, path families, time bounds, and a
  bounded set of example links.
- Cluster related historical signatures into stable categories such as task
  metadata, boundary validation, contract/documentation drift, generated
  surfaces, and reviewer/test harness quality.
- Render clusters in deterministic priority order using current actionability,
  recurrence count, recency, then stable lexical keys.
- Bound managed-block output independently of the number of PRs in the selected
  window, and state when examples or clusters were truncated.
- Derive suggested preventive actions from detected categories and recurrence
  thresholds. Do not emit generic actions for categories absent from the scan.
- Preserve `--github-days`, repeated `--github-pr`, `--github-limit`,
  `--dry-run`, `--update`, custom target, Markdown escaping, and managed-block
  replacement behavior.
- Keep canonical/template script parity and update user-facing skill/docs text
  for the clustered output contract.

## Out of Scope

- Automatically creating Trellis tasks from scan output.
- Hiding or auto-resolving current actionable review feedback.
- Semantic embeddings, paid inference, or cross-repository taxonomy services.
- Reclassifying GitHub thread resolution or outdated state locally.

## Acceptance Criteria

- [ ] Five equivalent wording comments render as one historical signature or
      cluster with count and bounded examples, not five unprioritized bullets.
- [ ] Current unresolved comments remain individually visible and rank ahead of
      historical clusters.
- [ ] Cluster ordering and identifiers are deterministic across repeated runs
      with equivalent input ordering.
- [ ] Output remains bounded for a large complete time window and explicitly
      reports truncation.
- [ ] Suggested actions correspond only to detected recurring categories and
      include evidence counts.
- [ ] Dry-run is mutation-free; update remains idempotent and preserves human
      content outside the managed block.
- [ ] Focused tests, template parity, install audit, and full-check pass.

## Notes

- Evidence source: `docs/review-learnings.md`, refreshed 2026-07-21.

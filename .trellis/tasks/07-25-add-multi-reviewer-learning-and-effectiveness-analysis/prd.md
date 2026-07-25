# PARKED: Add Multi-Reviewer Learning And Effectiveness Analysis

> Status: BLOCKED (external) — do not `task.py start`. Requires: sd-github-review 07-25-configurable-parallel-reviewers + 07-25-establish-trusted-finding-adjudication contracts. Marked 2026-07-25; see Dependencies.

## Goal

Use one privacy-bounded reviewer-evidence contract to generalize recurring
review learnings across all configured reviewers and separately evaluate
parallel-review correctness, complementarity, reliability, latency, and cost.

## Requirements

- Share one versioned normalization layer for repository, PR, exact head, lane,
  plan/attempt, slot, candidate, handler, provider/model, configuration digest,
  finding identity/category, operational outcome, adjudication evidence,
  limitations, and observation time.
- Keep `sd-review-learnings` focused on recurring valid feedback and durable
  repository guidance. It must not rank reviewers or own adjudication.
- Add separate read-only `sd-review-effectiveness` for paired reviewer/model
  evaluation. It must not update learning files or configuration.
- Consume trusted adjudication from `sd-github-review`; never infer
  correctness from thread resolution, comment deletion, agreement, author
  identity, or a later code change alone.
- Treat missing, uncertain, disputed, stale, mixed-head, truncated, or
  incompatible evidence as reduced coverage or `insufficient-evidence`.
- Support variable-length cheap/deep reviewer sets generically without
  hard-coding Copilot, Kimi, Qwen, providers, models, or exactly two reviewers.
- Keep raw prompts, diffs, source, credentials, unrestricted provider output,
  and unnecessary finding text outside normalized evidence and reports.
- Keep both children read-only by default and advisory. Neither stages,
  commits, pushes, requests reviews, or changes routing/model/budget policy.

## Acceptance Criteria

- [ ] Both children consume one normalized reviewer/adjudication evidence
      schema and expose source coverage, exclusions, freshness, and truncation.
- [ ] Recurrence cannot be presented as correctness, and effectiveness cannot
      mutate the learning managed block.
- [ ] Invalid findings never become preventive guidance; duplicate findings
      count as one underlying issue while preserving reviewer attribution.
- [ ] Reviewer/model recommendations require configured paired-sample,
      adjudication-coverage, and trust thresholds.
- [ ] Copilot-only, migrated single-reviewer, and variable-length parallel
      plans remain analyzable without active legacy dispatch interpretation.
- [ ] Templates, generated surfaces, manifest/provenance, help/docs, install
      lifecycle, changelog/release ledger, focused tests, `make check`, and
      fleet validation pass.

## Dependencies

- `platypeeps/sd-github-review` tasks
  `07-25-configurable-parallel-reviewers` and
  `07-25-establish-trusted-finding-adjudication`.

## Out of Scope

- Automatic adjudication, reviewer/model configuration changes, adaptive
  reviewer counts, or claims of complete defect recall.

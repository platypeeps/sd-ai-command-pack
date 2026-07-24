# Add a bookkeeping-only CI fast lane

## Goal

Reduce redundant GitHub Actions cost and merge latency when finish-work adds
only Trellis task/archive/journal bookkeeping to an already-green pull request,
while preserving a required `CI Result` for the exact current head and failing
closed whenever the cheaper path cannot be proven safe.

## Confirmed Evidence

- `.github/workflows/tests.yml` runs on every pull-request head and has no PR
  path filter. A new head therefore starts the three-job unit-test matrix,
  lint, security, release-payload, and aggregate lanes even when only Trellis
  bookkeeping changed.
- `sd-review-pr` and the merge-through housekeeping tail run finish-work, then
  push any archive and journal commits and wait for checks on that new head.
- PR #243 ran the full workflow successfully for code head `9978866`, then ran
  it again for journal-only successor `c0525b3`. That successor changed only
  `.trellis/workspace/sdelmas/index.md` and `journal-5.md`.
- The normal finish-work path already creates its bookkeeping commits locally
  and performs one push after the archive and journal steps. GitHub Actions
  evaluates the pushed head, so collapsing those local commits into one commit
  would not materially reduce CI by itself.
- The routed-review program permits a separate exact-head `none` or skipped
  review receipt for a verified bookkeeping successor. That contract concerns
  AI-review evidence only; it does not optimize or replace this repository's
  required CI check.
- The `main` trigger currently ignores `.trellis/workspace/**` but not
  `.trellis/tasks/**`, so direct task-bookkeeping pushes can still run the full
  suite.

## Dependencies And Boundaries

- Parent: `07-22-streamline-sd-skill-workflows`.
- Depends on `07-24-validate-finish-work-bookkeeping-before-push` publishing
  the canonical task/archive/journal validator. This task reuses that helper in
  CI and does not create a CI-only metadata policy.
- This task is the CI counterpart to the bookkeeping-successor behavior in
  `07-22-integrate-routed-review-backends`; it must not mint, reuse, or weaken a
  routed-review receipt.
- The final program integration task must exercise the resulting exact-head CI
  behavior together with review and housekeeping gates.
- Keep the implementation local to `sd-ai-command-pack`. Fleet-wide workflow
  rollout and changes to upstream Trellis are separate, consent-gated work.

## Requirements

- R1: Keep the workflow triggered for every pull-request head and preserve the
  branch-protection context named `CI Result`. Never use broad PR-level
  `paths-ignore` or allow a required check to remain absent, skipped, or tied
  only to an older head.
- R2: Add a deterministic, machine-readable scope decision before expensive
  jobs run. Its output must include a schema version, `full` or `bookkeeping`
  mode, exact before/after commit identities, a stable reason code, and the
  prior-run evidence used for a bookkeeping decision.
- R3: Permit `bookkeeping` mode only for a pull-request `synchronize` event or
  an eligible direct `main` push whose event-supplied prior head is available,
  is an ancestor of the current head through a linear non-merge update, and has
  a successful `Tests`/`CI Result` run associated with the same pull request or
  protected branch. This may cover multiple locally-created bookkeeping
  commits delivered by one push.
- R4: Require the complete prior-head-to-current-head delta to be limited to
  `.trellis/tasks/**` and `.trellis/workspace/**`. Inspect names using
  NUL-safe Git output and no rename inference so task archive moves are checked
  as bounded deletes and additions. Reject symlinks, submodules, executable-bit
  changes, merge commits, path escapes, unavailable objects, and any workflow,
  script, configuration, source, test, dependency, manifest, or payload change.
- R5: Treat a previously successful bookkeeping run as valid prior-head
  evidence only when it was itself associated with the same PR/ref. This
  supports a safe chain of exact-head bookkeeping deltas without reusing an
  older check as the current result.
- R6: In bookkeeping mode, run a small validation lane that includes
  `git diff --check`, task JSON/schema/status and parent-child topology checks,
  supported active/archive layout checks, journal/index consistency, and
  placeholder detection. Consume the canonical finish-work bookkeeping
  validator and its stable reason codes instead of creating a second
  validator.
- R7: Skip the unit-test matrix, lint, security, and release-payload jobs only
  after R2-R6 succeed. Known ambiguity, missing or unsuccessful prior evidence,
  an API lookup problem, force-push/non-ancestor history, or a mixed delta must
  select `full`; an invalid bookkeeping artifact or classifier execution defect
  must fail the exact-head `CI Result`, never report success.
- R8: Make `CI Result` validate mode-specific job outcomes explicitly. Full
  mode requires every existing expensive lane; bookkeeping mode requires the
  classifier and bookkeeping validations and requires expensive lanes to be
  skipped. An impossible or inconsistent job-result combination fails closed.
- R9: Keep the classifier and evidence lookup read-only, noninteractive, and
  minimally permissioned. Do not use `pull_request_target`, expose secrets, or
  execute a changed checkout-owned helper before the delta that would justify
  the fast path has been bounded.
- R10: Apply the same bounded decision to direct `main` bookkeeping pushes.
  Actual PR merge commits, squash/rebase merges containing product or pack
  changes, release-bearing commits, and any non-bookkeeping push continue to
  run full CI and preserve auto-tag behavior.
- R11: Preserve at most one pushed finish-work successor per finalization
  attempt. Do not force archive and journal data into one Git commit solely for
  CI optimization; change commit batching only if implementation evidence
  finds an additional push that the current skills do not already prevent.
- R12: Emit a concise workflow summary showing the selected mode, reason,
  before/after heads, prior evidence, validations executed, expensive jobs
  avoided, and fallback reason. Do not claim cost savings when full mode ran.

## Acceptance Criteria

- [ ] A fixture matching PR #243—green code head followed by one pushed linear
  archive/journal-only delta—selects bookkeeping mode and reports a successful
  `CI Result` for the new exact head without starting unit, lint, security, or
  release-payload jobs.
- [ ] Journal-only, task-metadata-only, task-archive, and combined
  archive-plus-journal successors pass focused positive tests, including more
  than one bookkeeping commit in a single push.
- [ ] Changed source/workflow/configuration paths, mixed deltas, executable or
  symlink entries, merge commits, malformed SHAs, missing objects,
  non-ancestor/force-push histories, first/opened PR heads, and prior checks
  from another PR/ref all select full CI or fail safely as specified.
- [ ] Malformed task JSON, invalid task topology/layout, inconsistent journal
  index state, placeholders, or whitespace errors fail the bookkeeping lane
  and therefore fail the exact current-head aggregate check.
- [ ] Full code-change PRs retain the existing matrix, coverage, lint,
  security, release-payload, concurrency, and branch-protection behavior.
- [ ] Direct `main` task/journal bookkeeping uses the cheap validated path,
  while real merge and release commits still run full CI and auto-tag only
  after the full aggregate succeeds.
- [ ] Tests prove mode-specific aggregate handling cannot turn a failed,
  cancelled, or unexpectedly skipped lane into success.
- [ ] The finish-work/review/housekeeping contract still performs no more than
  one push after producing the final bookkeeping head in one finalization
  attempt.
- [ ] Focused classifier/workflow tests, workflow security checks,
  `git diff --check`, and `make check` pass; a real PR finish-work successor is
  used as an end-to-end dogfood check when repository policy permits.

## Out Of Scope

- Skipping the current-head required check entirely or trusting only an older
  commit's branch-protection result.
- Broad path ignores for pull requests, unvalidated metadata-only success, or
  weakening exact-head review, unresolved-thread, finish-work, or merge gates.
- Replacing the routed-review successor receipt or treating CI success as AI
  review evidence.
- Avoiding the post-merge full run for a real code/release merge.
- Publishing a generic fleet workflow, modifying consumer repositories, or
  changing upstream Trellis lifecycle behavior.

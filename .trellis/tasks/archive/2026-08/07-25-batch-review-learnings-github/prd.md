# Batch review-learnings GitHub fetches (tactical)

## Goal

`sd-review-learnings` stops making one gh GraphQL subprocess per PR (~30-45 serial spawns
per documented `--github-days 2 --update` run at current merge cadence) by batching PR
numbers into aliased GraphQL queries (15-25 per request).

## Origin

SE-pack repo audit 2026-07-25 (se-ai-command-pack ledger A-028, P2/M). Defect lives in
this repo's source; the SE-side task was retired in favor of this one.

## IMPORTANT — check before starting

`07-25-generalize-review-learnings-across-reviewers` replaces the Copilot-specific
collection path with normalized receipts/projections and will likely DELETE the code this
task optimizes. This task is the tactical fix for current pain only:

- If the generalization is expected to land soon, SKIP this task (mark superseded).
- If it stays blocked on sd-github-review contracts and learnings runs hurt now, do this
  minimal batching without restructuring types (keep the diff small to discard later).

## Requirements

- `scripts/sd-ai-command-pack-review-learnings.py`: batch the per-PR loop at `:2043` via
  GraphQL field aliases or a single search query; preserve parsed output, timeouts, and
  per-batch errors. (The PRD originally cited `~:1174-1193`, which is `_signal_category`,
  a pure string classifier that makes no network call — see Notes.)
- **Aliased batching widens the failure domain from one PR to the whole batch, so the
  partial-failure contract is a requirement, not an implementation detail.** GraphQL
  returns `200` with a partial `data` plus an `errors` array; `_run_gh_json` (`:1908-1909`)
  only decodes JSON and would treat that as success. Specify, before coding:
  - a batch response carrying `errors` yields per-PR outcomes, not one blanket failure —
    PRs with present data are used, PRs whose alias resolved to `null` are marked failed
    and are individually retried or reported;
  - the `truncated` flag currently computed per PR at `:2073-2074` stays per PR under
    batching;
  - output ordering is the input PR order, not GraphQL alias order;
  - a batch size that keeps the query inside GitHub's node/cost limits, stated as a number
    with the reasoning, so a large fleet does not fail wholesale on cost.
- Keep the existing pagination: the PR-list query at `:1938-1964` already pages 100 at a
  time through `endCursor` (`:1963`, `:2003`) and is not what this task changes.

## Acceptance Criteria

- [x] A run over N PRs makes at most ceil(N/batch) gh calls; identical learnings output on
      a fixture window. Batched via `_review_thread_connections` /
      `_batch_review_threads` (`GITHUB_REVIEW_THREAD_BATCH_SIZE = 20`);
      `tests/test_review_learnings.py::test_review_threads_are_fetched_in_one_batched_call`
      asserts N=3 collapses to one gh call in requested order, and the partial-failure,
      whole-batch-failure, and per-PR-truncation tests pin the widened-failure contract.
- [x] Changelog + version; note in the generalization task that the collection code moved.
      `0.64.10 → 0.64.11` (CHANGELOG.md); note added to
      `07-25-generalize-review-learnings-across-reviewers/prd.md` recording the new
      `_copilot_comments_for_prs` / `_review_thread_connections` /
      `_batch_review_threads` / `_single_pr_review_threads` boundaries.

## Notes

- Lightweight task; PRD-only is appropriate. Classified 2026-07-28: the task's own
  standing instruction is to keep the diff small enough to discard when
  `07-25-generalize-review-learnings-across-reviewers` deletes this code path. Writing a
  `design.md` for a change that is explicitly disposable — and may be marked superseded
  before it starts — is the wrong artifact. Re-check the supersession question above
  first; if the generalization is landing, close this task instead of planning it.
- **The cited line range is wrong.** `~:1174-1193` in
  `scripts/sd-ai-command-pack-review-learnings.py` is `_signal_category`, a pure string
  classifier with no network call. The real per-PR fan-out is the `for pr in prs:` loop at
  `:2043`, which calls `_run_gh_json` at `:2048` with a `pullRequest(number:$number)`
  query (`:2020`) — one `gh` subprocess per PR. That is the site to batch.
- **The PR-list query is already batched; do not "fix" it.** The separate query at
  `:1938-1964` pages 100 pull requests per request through `endCursor` (`:1963`, `:2003`).
  Only the per-PR review-thread query is one-at-a-time.
- Per-PR truncation is currently reported through the `truncated` flag set at `:2073-2074`
  when a PR's `reviewThreads` has `hasNextPage`. Aliased batching must keep that per-PR,
  not collapse it to one flag for the whole batch.

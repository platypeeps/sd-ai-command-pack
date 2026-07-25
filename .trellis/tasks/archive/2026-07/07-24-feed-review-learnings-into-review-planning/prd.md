# Feed review learnings into review planning

## Goal

Give each review attempt a bounded current summary of recent defect families
without requiring a documentation update, remote provider call, or extra
bookkeeping commit.

## Confirmed Evidence

- `docs/review-learnings.md` was last refreshed on 2026-07-21, before the high
  churn PRs #234-#243.
- A current read-only scan inspected 38 PRs and 114 Copilot comments and found
  material boundary, generated-surface, contract, task-metadata, and test
  harness signals not present in that checked-in snapshot.
- The scanner's JSON scan result reports counts and write state but does not
  currently expose the bounded historical clusters already rendered by its
  Markdown preview.
- Updating the tracked learning document after every PR would itself create
  bookkeeping heads and CI work, undermining the cost goal.

## Dependencies And Boundaries

- Parent: `07-24-implement-unified-routed-sd-review`.
- `07-24-converge-review-finding-families` consumes the typed family summary.
- Reuse `sd-ai-command-pack-review-learnings.py`; do not create a second GitHub
  comment scanner or classification vocabulary.
- Planning and review consumption are read-only with respect to tracked files,
  Git, and GitHub. Explicit `sd-review-learnings --update` remains the only
  tracked-document update path.

## Requirements

- R1: Extend the scanner's versioned JSON report with bounded normalized
  clusters: family ID/label, comment and signature counts, PR/time bounds, path
  families, representative signatures, truncation metadata, and limitations.
  Do not include full raw comment bodies in the review-planning payload.
- R2: Run the bounded scan once per review attempt when GitHub evidence is
  available, then reuse its exact receipt within that attempt. Enforce maximum
  PR/comment/page limits, timeouts, and explicit incomplete/truncated states.
- R3: Feed only the categories relevant to the intended changed path families
  into the local review plan as risk questions or sibling-matrix inputs. The
  signal is advisory evidence, not proof of a defect or test coverage.
- R4: Do not invoke a review provider, mutate GitHub, update the tracked
  learning document, stage, commit, push, or refresh generated knowledge while
  collecting or consuming the summary.
- R5: On authentication, rate-limit, network, malformed-payload, or unavailable
  history, continue only according to parent review policy with a visible stale
  or unavailable limitation and zero positive confidence from historical
  learning.
- R6: Permit an ignored user-local cache only within the parent review artifact
  store, keyed by repository identity and observed GitHub watermark, with
  version, timestamp, bounded lifetime, atomic replacement, and private
  permissions. Cache absence or corruption falls back to a fresh bounded read
  or a visible unavailable state; it never changes `sd-check` read-only rules.
- R7: Keep periodic durable curation separate. Provide an explicit report that
  tells maintainers when the tracked snapshot is stale, but do not update it
  automatically during ordinary review.
- R8: Human output derives from the typed report and discloses evidence age,
  truncation, unavailable platforms, and whether live or cached data was used.

## Acceptance Criteria

- [x] JSON scan mode exposes the same bounded clusters and truncation facts as
  Markdown rendering without writing the target file.
- [x] A changed state-controller fixture receives relevant boundary/history
  prompts; unrelated documentation-only changes do not load the full history.
- [x] One review attempt performs at most one bounded GitHub learning scan and
  reuses its exact receipt across local and remote stages.
- [x] Stale cache, unavailable GitHub, rate limit, malformed comments, and
  truncated pagination remain visible and grant no positive confidence.
- [x] Ordinary review produces no tracked learning-document diff or additional
  commit; explicit update mode remains atomic and separately authorized.
- [x] Focused scanner/report/cache/review-consumption tests, generated parity,
  `make sync`, and `make check` pass.

## Out Of Scope

- Sending historical review comments to remote providers.
- Automatically changing product code or tests from a historical signal.
- Updating `docs/review-learnings.md` after every PR.

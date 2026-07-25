# Implementation Plan: Front-load local review before remote PR review

## Preconditions

- [x] The parent routed-review PRD/design now defines `local=auto` as a
  policy-selected provider set rather than exactly one provider; reverify that
  contract remains aligned before implementation starts.
- [x] Confirm `07-24-implement-read-only-sd-check` has published the typed
  deterministic result consumed by the controller.
- [x] Confirm the external router capability/receipt contract used by the
  parent unified-review task is available and reviewed.
- [x] Confirm `07-24-feed-review-learnings-into-review-planning` has published
  the bounded finding-family evidence shape.

## Implementation Sequence

1. **Provider-plan contract**
   - Add the versioned risk classifier and provider-plan schema to the new
     review configuration owned by the unified `sd-review` work.
   - Encode explicit, first-substantive, ambiguous, low-risk successor,
     high-risk successor, repeated-family, and bookkeeping-successor decisions.
   - Validate configuration, data-handling constraints, deterministic ordering,
     and cost/quality metadata without shell-string commands.

2. **Concurrent local dispatcher**
   - Extract only reusable Prism/Gito adapter behavior from the legacy runner
     into the successor controller.
   - Launch selected provider argv concurrently with isolated attempt IDs,
     timeouts, cancellation state, stdout/stderr, and artifact directories.
   - Persist terminal attempt results atomically and make resume idempotent.

3. **Finding normalization and batching**
   - Normalize provider outcomes and findings while retaining source evidence.
   - Deduplicate overlapping findings, attach bounded review-learning families,
     and verify candidates before disposition.
   - Integrate the parent `fix=auto|ask|none` policy and enforce at most one
     focused pre-remote fix commit per clean-up batch.

4. **Exact-scope receipt and reuse**
   - Implement the aggregate local receipt with canonical `branch_delta`
     target, provider plan, versions, configuration/policy digests, outcomes,
     dispositions, and local artifact references.
   - Reuse a pre-publication receipt in PR scope only for an exact match.
   - Invalidate on base/head/content/provider/configuration/policy changes and
     represent proven bookkeeping successors with the parent stable skip.

5. **Unified-review state-machine integration**
   - Place provider planning/execution after router capability preflight and
     `sd-check`, and before any remote route request.
   - Block remote routing on non-terminal or actionable local results.
   - Re-enter `sd-check` and local planning after every code-changing local or
     remote fix, using current-head evidence only.
   - Send only the allow-listed aggregate summary to `sd-github-review`.

6. **Shipping-composition contract**
   - Publish a reusable branch-review entrypoint and receipt-consumption
     contract for `07-24-simplify-review-shipping-composition`.
   - Prove `sd-ship` can review before initial publication and that PR creation
     alone does not trigger duplicate local billing.
   - Keep `sd-create-pr` publication-only as required by the parent design.

7. **Reporting and telemetry**
   - Report provider-plan reasons, run/reuse status, concurrent attempts,
     outcome/disposition counts, costs, latency, fix batches, exact head,
     remote rounds, and limitations.
   - Do not calculate hypothetical avoided rounds; retain enough measured data
     for before/after comparison.

8. **Generated surfaces and retirement handoff**
   - Update template sources first and run `make sync` for installed mirrors.
   - Update help, examples, manifest/audit expectations, and candidate ledger
     through the parent unified-command work.
   - Hand legacy target removal to `07-24-remove-retired-review-surfaces`; add
     no wrapper, alias, or environment compatibility path.

## Validation

- [ ] Add focused tests for risk classification and provider-plan selection.
- [ ] Add a concurrency fixture proving Prism and Gito overlap in execution and
  cannot overwrite each other's artifacts.
- [ ] Add state-machine fixtures for findings, batching, cancellation, resume,
  partial failure, and remote-dispatch blocking.
- [ ] Add exact-match/mismatch matrices for branch-to-PR receipt reuse and
  successor-head invalidation.
- [ ] Add failure fixtures for missing, failed, timed-out, rate-limited, and
  cancelled providers with optional and required local policy.
- [ ] Exercise repeated-family input and verified bookkeeping-successor skips.
- [ ] Run relevant existing review and surface tests, including
  `python3 -m unittest tests.test_review_local tests.test_sdlc_commands tests.test_surface_generation`.
- [ ] Run `make sync` and inspect generated parity.
- [ ] Run `make check`.
- [ ] Exercise one pilot PR and record measured local attempts, pre-remote
  findings, fix batches, Copilot rounds, latency, and limitations.

## Risk And Rollback Points

- Provider concurrency can duplicate paid calls if attempt persistence is not
  written before launch; fail closed when durable identity cannot be created.
- Branch-to-PR reuse can grant stale confidence if target canonicalization is
  incomplete; require every exact-match field and test base-branch movement.
- Automatic finding fixes can broaden scope; preserve the parent structured
  decision boundary and focused staging rules.
- Do not merge a partial cutover that leaves both legacy and successor remote
  paths callable. Roll back the entire unified-review release instead.

## Delivered Internal Contract

- Added the non-public exact-scope local-review stage used by the future
  unified controller. It provides deterministic risk/provider planning,
  concurrent isolated Prism/Gito attempts, native structured-output parsing,
  normalized findings, exact-match receipt reuse, and explicit optional versus
  required remote-gate outcomes without dispatching a remote reviewer.
- Kept the existing public review commands unchanged. Wiring this stage into
  `sd-review`, composing it into `sd-ship`, and retiring the legacy surfaces
  remain owned by the parent and sibling tasks named in the PRD.
- Exercised real Prism/Gito review rounds while implementing the stage. Those
  rounds exposed and drove fixes for native-report false-clean handling,
  process-tree cleanup, option-safe Git refs, lossy path serialization,
  bounded provider fields, and deterministic multi-provider aggregation.
- Dispositioned two non-actionable review candidates with repository evidence:
  the candidate ledger timestamp preceded the live UTC observation, and
  Trellis-generated `task.json` files conventionally omit a trailing newline.

## Before `task.py start`

- [ ] Complete the PRD convergence pass after any user review changes.
- [ ] Read this task's PRD and design top to bottom and reconcile them with the
  parent and sibling task artifacts.
- [ ] Obtain explicit user approval to start implementation.

# Recent Trellis workflow instability review

## Scope and method

- Window: 2026-07-14 through 2026-07-28.
- Inventory: 329 indexed Claude/Codex sessions across 12 cwd identities that
  resolve to 11 physical repositories containing `.trellis/`.
- Repositories: `sd-ai-command-pack`, `people-profiles`, `rwbp-coordinator`,
  `anomaly-metric-creator`, `rwbp-website`, `mezmo_benchmark`, `hoa-manager`,
  `sd-github-review`, `se-ai-command-pack`, `loadsmith`, and upstream
  `Trellis`.
- `anomaly-metric-creator` appeared under both its canonical path and a legacy
  symlink and was treated as one repository.
- Evidence pass: session-level searches for finish-work, final-bundle,
  pre-archive, journal, placeholder, lock, recovery, and filesystem failures;
  focused context extraction for representative sessions; review of current
  and archived task contracts; live no-network version/status collection; and
  focused runtime tests.
- Coverage limit: OpenCode session indexing is unavailable in the installed
  Trellis build. Upstream task `07-28-restore-install-safe-opencode-mem-reader`
  now owns that gap. Not every indexed session invoked a Trellis lifecycle;
  the inventory was used as the population and only grounded lifecycle
  evidence was classified as a finding.

## Executive conclusion

The instability is real, but `sd-status` is mostly the detector rather than
the cause. The expensive loops happen because finalization crosses several
non-atomic epochs: task validation/archive, journal recording, push, exact-head
CI/review, merge, and cleanup. A failure or review fix between those epochs can
leave Git, the active-task pointer, the archive, journal, retained receipt, PR
head, and work-loop ledger individually valid but mutually inconsistent.
Status then correctly reports the inconsistency, and the operator must enter a
special recovery path.

Three additional factors amplify the effect:

1. Consumer installations are not at one pack version, so newly shipped
   recovery behavior is uneven across repositories.
2. Trellis-owned `add_session.py` now accepts structured session sections, but
   still renders `(see git log)` for commit subjects and does not converge a
   retry after append/index success followed by auto-commit failure. The pack
   wrapper repairs both gaps for current consumers, while direct calls and old
   installs expose the underlying producer mismatch.
3. Managed filesystem restrictions frequently block `.git`, user-local lock,
   cache, or linked-KB writes. These are environmental failures, but earlier
   guidance sometimes presents them like repository corruption and encourages
   repeated broad reruns.

## Findings

### F1. Completion is a multi-epoch protocol, not one transaction

Evidence:

- `loadsmith` and other consumers merged delivery PRs while the Trellis task
  remained `in_progress`, requiring a protected-main bookkeeping recovery PR.
- `sd-ai-command-pack` PR #243 reran full CI after a journal-only successor.
- Planning PR #244 was mergeable but canonical housekeeping blocked with
  `finish_work_missing` because truthful completion would have archived tasks
  intended to remain in planning.
- PR #253 archived and journaled correctly, then review fixes advanced the PR
  head; housekeeping could no longer prove finish-work at the new exact head.
- `rwbp-coordinator` PR #187 archived a task before merge while its PRD still
  represented post-archive merge/cleanup work as unchecked completion criteria.

Root cause:

- `sd-finish-work` and `sd-housekeeping` intentionally split archive/journal
  ownership from merge/cleanup ownership. The split is sound for safety, but
  the protocol previously lacked typed successor modes and a single explicit
  representation for post-archive obligations.

Already shipped:

- `07-24-validate-finish-work-bookkeeping-before-push` (pack 0.51.0).
- `07-25-support-journal-only-finalization-recovery` (pack 0.53.0).
- `07-25-support-post-archive-review-finalization` (pack 0.54.0).
- `07-24-add-bookkeeping-only-ci-fast-lane` (merged through PR #271).

Remaining tasks:

- `07-24-support-planning-only-pr-finalization` (P1) is the central unfinished
  state-machine task.
- `07-28-clarify-completion-housekeeping-obligations` defines truthful
  pre-archive versus post-archive ownership.
- `07-28-enforce-pre-archive-acceptance-readiness` enforces that contract.
- `07-28-decide-housekeeping-result-schema-compatibility` and
  `07-28-validate-finish-work-receipt-path` harden the typed handoff.
- `07-22-validate-sd-workflow-program-integration` should supply the final
  end-to-end matrix.

### F2. Journal recording has a producer/validator impedance mismatch

Evidence:

- Trellis `add_session.py` historically emitted `(Add details)` and
  `(Add test results)`; GitHub issue #394 removed those section placeholders.
  Current source still emits `(see git log)` for every commit subject, while
  pack recording resolves it before publication.
- The original workflow required a fill-and-amend cycle six times in one week
  and twice briefly published placeholder or wrong-hash content.
- Sessions 29 and 30 in this repository were duplicated when a retry followed
  a successful append but failed pack-owned staging/commit.
- `sd-github-review` exposed the related `_example` producer/validator mismatch
  in generated task JSONL.

Root cause:

- Trellis owns the low-level task/journal producer, while this pack owns a
  stricter publication validator. Compatibility wrappers must infer and repair
  generated content after the producer writes it.

Already shipped:

- Upstream GitHub issue #394 and archived task `07-22-script-qol-batch` added
  structured session-section flags and removed the two section placeholders.
- `07-04-record-session-wrapper` added one-shot structured recording, placeholder
  removal, hash validation, and a manual fallback.
- PR #77 made retry recording idempotent by reusing the pending matching
  journal entry rather than appending a duplicate.
- `07-17-archived-task-jsonl-placeholder-preflight` and
  `07-20-planning-task-placeholder-gate` reject changed scaffold rows.

Remaining tasks:

- No additional pack task is needed for placeholder or duplicate-session
  prevention unless a current-version reproducer is found.
- Upstream Trellis task `07-28-harden-add-session-retry-convergence` owns
  accurate commit subjects plus retry convergence across journal append, index
  update, and auto-commit. Upstream changes remain separately consent-gated.

### F3. Cleanup-only runs can report merge eligibility anomalies that do not
apply to cleanup

Evidence:

- In `rwbp-website` session
  `019f864b-c166-7a61-93b8-692be8b71c94`, cleanup of an already-merged PR #181
  deleted the proven branch but still surfaced the pre-cleanup
  `finish_work_missing` eligibility result as an anomaly. A second run from
  `main` was needed to produce a typed clean result.

Root cause:

- When invoked from an already-merged feature branch, housekeeping can evaluate
  open-PR eligibility before its merged-branch cleanup path establishes that no
  merge is possible or required. The cleanup succeeds, but the irrelevant
  anomaly contaminates the result.

Accepted task and fix:

- `07-28-route-housekeeping-by-pr-lifecycle-state` owns the gap. Resolve the
  branch's PR lifecycle state before merge eligibility. Skip
  finish-work eligibility entirely for a GitHub-confirmed merged PR, then run
  only exact-head deletion proof, default-branch synchronization, and final
  status. Add a regression asserting one cleanup invocation returns clean.

### F4. Work-loop persistence is useful but recovery ownership is fragmented

Evidence:

- HOA and AMC sessions hit user-local lock permission failures and paused or
  stale loop state.
- Terminal runs historically remained red after the task and PR were completed
  outside the loop, causing status to keep recommending reconciliation.
- Concurrent stale-lock recovery can still delete a competitor's newly created
  lock.

Already shipped:

- `07-20-terminal-work-loop-reconciliation` added a verified terminal
  reconciliation record.
- `07-20-stale-terminal-lock-guidance` made explicit recovery guidance
  actionable.

Remaining tasks:

- `07-25-fix-work-loop-lock-race` owns the remaining concurrency defect.
- `07-25-backlog-selector-blocked-markers` improves machine-visible blocked
  ordering.
- `07-24-track-clean-recovery-artifacts` covers owned stashes/worktrees, not
  work-loop lock correctness.

### F5. Environment restrictions are repeatedly misread as workflow defects

Evidence:

- Recent sessions across almost every consumer contain `Operation not
  permitted` failures involving `.git/index.lock`, `.git/FETCH_HEAD`,
  user-local loop state, package caches, `.agents`, or linked `.obsidian-kb`
  targets.
- The canonical operation generally succeeded when rerun with the same scope
  and the required filesystem authority or a task-scoped cache.

Root cause:

- The workflow spans repository files, Git metadata, user-local state, external
  KB symlinks, and tool caches, which do not share one sandbox boundary.
- Generic failure text does not always classify the owning boundary or provide
  the smallest safe retry.

Existing tasks:

- Completed `07-24-standardize-sandbox-safe-tool-cache-routing` owns the common
  external cache environment.
- `07-25-user-scope-toolchain-caches` adds per-user ownership and permission
  hardening to those caches.
- `07-24-track-clean-recovery-artifacts` covers recovery artifact ownership,
  not Git metadata, KB, or user-local state permissions.
- `07-25-harden-toolchain-failure-paths` is narrowly scoped to GraphQL
  pagination and atomic-write descriptor ownership; it does not own this
  cross-command classification problem.

Accepted task and improvement:

- `07-28-standardize-environment-blocked-recovery-evidence` owns the gap.
  Standardize typed `environment_blocked` results across recorder,
  finish-work, housekeeping, work-loop, KB, and Git metadata operations, with
  an exact retry command and mutation checkpoint.

### F6. Version skew makes historical and current behavior look inconsistent

Live installed state on 2026-07-28:

| Repository | Pack | Trellis |
| --- | ---: | ---: |
| sd-ai-command-pack | 0.55.5 | 0.6.7 |
| people-profiles | 0.55.0 | 0.6.7 |
| rwbp-coordinator | 0.55.2 | 0.6.7 |
| anomaly-metric-creator | 0.55.5 | 0.6.7 |
| rwbp-website | 0.55.0 | 0.6.7 |
| mezmo_benchmark | 0.55.4 | 0.6.7 |
| hoa-manager | 0.55.2 | 0.6.7 |
| sd-github-review | 0.55.2 | 0.6.7 |
| se-ai-command-pack | 0.55.2 | 0.6.7 |
| loadsmith | 0.55.2 | 0.6.7 |
| upstream Trellis source | not installed | 0.6.2 |

Implication:

- The core journal-only and post-archive recovery modes exist in every listed
  consumer because they shipped in 0.53.0/0.54.0.
- Consumers below 0.55.4 lack the archive-move rewrite fix and consumers below
  0.55.5 lack the Gemini settings classification fix. A fleet refresh to
  0.55.5 removes this avoidable skew; it will not by itself implement the
  unfinished planning-only lifecycle.
- Decision updated after review: do not roll out 0.55.5 merely to normalize
  evidence. Accept the temporary skew, complete the pack-owned fixes and final
  integration, publish a stabilized successor release, then use
  `07-28-roll-out-stabilized-pack-release-to-fleet` for one fleet deployment.

### F7. The upstream Trellis source checkout bypasses pack lifecycle guards

Evidence:

- Live status for the local upstream Trellis source checkout reports Trellis
  0.6.2 with no command pack installed.
- Task `07-24-fix-task-context-jsonl-warning-syntax` has
  `status: completed` and `completedAt: 2026-07-24` but still resides directly
  below `.trellis/tasks/` with no branch, commit, or PR identity.

Impact:

- The source checkout can reproduce the completed-but-unarchived state that
  consumer pack pre-archive and housekeeping guards are intended to prevent.
- This is an upstream-repository bookkeeping issue, not evidence that current
  consumer `sd-status` mutated state.

Ownership:

- No task in this command pack should silently modify or publish upstream
  Trellis. Reconciliation and any producer-side invariant belong in the
  Trellis checkout and require the user's separate upstream-PR consent.

## What is not the main cause

- Local `sd-status` completed in roughly one to two seconds with cached refs in
  the observed runs. Its complete 51-task output is verbose by design, but it
  is not the source of journal recovery.
- GitHub review settlement and transient CI infrastructure failures add wall
  time but do not explain task/journal contradictions.
- Journal rotation is implemented in Trellis 0.6.7: `add_session.py` creates a
  new journal before an append would exceed the configured line limit.

## Recommended order

Execute `07-28-stabilize-self-hosted-delivery-lifecycle` as one branch, PR, and
merge. Within that delivery boundary:

1. Settle completion obligations and result-schema compatibility.
2. Implement planning-only finalization, receipt-path validation, and
   PR-lifecycle housekeeping routing.
3. Enforce truthful pre-archive acceptance readiness.
4. Implement user-cache ownership, the work-loop lock race, blocked markers,
   and recovery-artifact ownership.
5. Add typed environment-blocked evidence across the corrected owners.
6. Run the bounded cumulative self-hosting matrix and release preparation,
   then finalize all included tasks together and merge once.

Feed the stability evidence into `07-22-validate-sd-workflow-program-integration`
for later program closure. Publish a stabilized successor release after the
single merge, then execute `07-28-roll-out-stabilized-pack-release-to-fleet`.

Reconcile the completed-but-unarchived Trellis task and work on
`07-28-harden-add-session-retry-convergence` and
`07-28-restore-install-safe-opencode-mem-reader` locally in a separate lane.
They do not block the pack sequence unless final integration proves that no
safe local mitigation exists. Any upstream PR remains separately consent-gated.

## Verification

- `trellis mem` project/list/search/context used for indexed-session inventory
  and representative dialogue recovery.
- Current and archived task contracts inspected directly.
- Live no-network status/version collection completed for all 11 physical
  repositories.
- Focused command-pack contract suite passed: 124 tests covering recorder,
  bookkeeping validator, PR eligibility, housekeeping, and bookkeeping CI.

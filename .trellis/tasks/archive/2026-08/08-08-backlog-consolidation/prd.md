# Consolidate the Trellis backlog and execute phase-0 simplifications

## Problem

The active backlog holds 79 planning tasks. A five-agent deep review (session
2026-08-08) found:

- The same defect filed two and three times from separate live sessions
  (review-cache, housekeeping-verdict, manifest-lane, doc-path-check pairs).
- One three-way contradiction: `08-07-planning-recovery-rejects-merge-commit`
  says the validator wrongly rejects merge commits; `08-07-record-session-merge-commit`
  and D3 of `08-06-upstream-add-session-numbering` say the recorder wrongly
  derives them. Shipping both sides produces incoherent behavior.
- One direct conflict: `08-05-split-sd-review-pr-skill` restructures a skill
  that `07-24-remove-retired-review-surfaces` deletes.
- A nine-task review-operator group (07-25-*: five operator-UX tasks, three
  effectiveness tasks, one attestation task, across two parent branches)
  blocked on sd-github-review v2 contracts that do not exist in that repo's
  runtime (9,390 of its 13,136 src LOC is unreachable from its Action
  entrypoint). `07-22-evaluate-sd-github-review-consolidation` had already
  decided keep-separate; the 2026-08-08 owner-approved direction, recorded by
  this task and not by any prior artifact, is: thin working v1 core, v2
  governance parked/dropped in that repo's own consolidation, minimal durable
  lane shipped to the fleet (descriptor install, durable workflow, fresh pins).
- Nine pure upstream-Trellis handoff parks occupying nine task directories.
- Cost work misaimed: GitHub Actions spend on this public repo is $0 (billing
  API: `total_ms: 0` on all sampled runs). Real costs are Copilot premium
  requests (measured 2.07 reviews/PR over 30 PRs), merge latency, and private
  fleet consumers where Actions minutes do bill (macOS leg would be 73% of
  billable minutes).
- Priorities do not reflect the owner's directive: correctness first, then
  review/CI cost, with fleet-wide consistency ("one path") as a principle.

## Goals

1. One authoritative disposition for every active task: keep, absorb, drop,
   park, or archive-as-shipped. No duplicate or contradictory tasks remain.
2. Priorities reordered: correctness P1 wave, then cost P2 wave, features after.
3. Ten new tasks capture the review's genuinely new work items (parallel
   work-backlog, Copilot request policy, CI lane cost, fleet one-path,
   merge-commit policy decision, upstream register, fleet machinery diet,
   phase-0 dead-surface cleanup, Trellis upgrade, relocated review-coordinator
   env-isolation defect).
4. This task's PR touches only `.trellis/**` (bookkeeping-lane eligible).
   Code and doc cleanups are delegated to the new phase-0 task.

## Non-goals

- No code, docs, template, or manifest changes in this PR.
- No implementation of any consolidated task.
- No changes to sd-github-review or the Trellis fork in this PR; their sibling
  consolidations are separate efforts executed in those repos (see Notes).

## Disposition table

### Drop — absorbed into a survivor (delete directory; survivor prd.md gains an "Absorbed" section with the unique evidence/AC)

| Dropped | Survivor | Carry over |
|---|---|---|
| 08-06-review-check-receipt-pinning | 08-07-review-check-stale-cache | PR #338/#339 fail/repair/re-invoke/pass sequence as regression evidence only. Policy conflict resolved here: the source's cached-pass-reuse AC is superseded by the survivor's recompute contract — recompute wins (correctness over reuse) |
| 08-08-housekeeping-worktree-held-default-branch | 08-07-status-housekeeping-anomaly-disagreement | exact-verdict `clean` assertion AC; 14-PR session evidence |
| 08-07-preflight-manifest-lane-zero-inspected | 08-08-manifest-reference-existence | zero-inspected-cannot-pass AC, plus an explicit open question the survivor's design must answer: source demands invalid manifests outside the change set be reachable; survivor is currently diff-scoped by declared non-goal. Unresolved scope conflict, not a duplicate claim |
| 08-06-preflight-bare-filename-references | 08-08-preflight-absent-path-prose | eligibility-expansion requirement carried as an explicit phase-2 requirement, sequenced strictly after the survivor's absent-path escape hatch lands (the tasks are complementary: escape hatch first, widening second) |
| 08-08-codex-lane-consent-gate | 08-07-default-local-review-lanes | full consent-not-capability gating acceptance set (10 acceptance bullets covering both the planning-review and local-review lanes) |
| 07-29-resolve-evidence-run-id-through-api | 07-28-consolidate-ci-fast-lane-trust-stack | note: moot if stack retired; decide retain/retire first |
| 08-07-planning-recovery-rejects-merge-commit | NEW 08-08-merge-commit-policy | validator-side evidence |
| 08-07-record-session-merge-commit | NEW 08-08-merge-commit-policy | recorder-side evidence (better-evidenced half) |
| 08-08-task-create-description-required | 08-06-task-create-base-branch-seed | description-refusal AC; survivor retitled |

### Drop — rejected (delete directory; rationale recorded here and in the PR)

| Task | Reason |
|---|---|
| 07-22-validate-sd-workflow-program-integration | Oversized validation program (21 cross-lifecycle scenarios, 28 named task dependencies plus an external repo) that re-verifies behavior individual tasks and CI already gate; disproportionate to the KISS direction. Note: it does specify executable scenarios — the drop is on proportionality, not "no behavior" |
| 08-07-codex-review-round-budget | Raising rounds 3→5 increases review spend, against the cost directive |
| 08-05-split-sd-review-pr-skill | Restructures a skill 07-24-remove-retired-review-surfaces deletes |
| 07-28-add-dependency-vulnerability-scan | Own evidence: zero third-party runtime deps; dependabot already covers pip/actions; adds CI lane |
| 07-09-actionlint-workflow-linting | Trigger condition never fired across two evaluations |
| 07-25-add-routed-review-operator-ux (+4 children: budget, configuration, data, finding-adjudication ops) | Blocked on sd-github-review v2 contracts now parked/dropped in that repo; ~19 planned subcommands of scope creep |
| 07-25-add-multi-reviewer-learning-and-effectiveness-analysis (+2 children: effectiveness command, generalize learnings) | Same parked/dropped v2 dependency; generalize would delete batching that shipped in v0.64.11 |
| 07-25-publish-local-review-attestations | Blocked on the same parked/dropped v2 dependency; ceremony not correctness |

A deferred-features note listing the operator-UX/effectiveness/attestation ideas
is added to `07-22-integrate-routed-review-backends/prd.md` so the ideas are
recoverable if the v2 governance direction is ever revived.

### Drop — absorbed into NEW 08-08-upstream-handoff-register

07-09-upstream-trellis-opencode-context-exec-hardening,
07-16-upstream-trellis-hook-shell-semantics,
07-27-upstream-claude-statusline-utf8-stdin-fix,
07-27-upstream-trellis-subagent-context-read-hardening,
07-30-upstream-task-start-branch-recording,
08-04-trellis-upstream-archive-commit-lock-retry,
07-09-upstream-issue-closure-cleanup, 07-09-upstream-platform-state,
07-09-upstream-trellis-api-cleanup (last three form the register's
"post-upgrade uptake evaluation" section — originally gated on 0.6.8 reaching
the fleet, now evaluated as part of 08-08-trellis-upgrade to 0.6.14). Each becomes one register entry preserving its
handoff text (original prd.md content copied into the register task's
`research/` directory). The untested compensating-write-path gap noted in
07-30-upstream-task-start-branch-recording is carried as its own register entry
flagged "pack-local test gap".

### Archive as completed (work or decision genuinely shipped)

- 07-24-correct-sd-skill-contract-drift — all three children archived.
- 07-22-evaluate-sd-github-review-consolidation — its keep-separate decision is
  recorded; its remaining open router-contract acceptance items are superseded
  by the 2026-08-08 owner-approved thin-core direction (v2 governance
  parked/dropped in that repo; minimal durable lane shipped instead). A note
  recording that direction and the supersession is appended to its prd.md
  before archive, so the archive record is honest about what completed versus
  what was overtaken.

### Keep with priority/title edits

| Task | Change |
|---|---|
| 08-07-ci-preflight-full-mode-gap | P2→P1 |
| 08-07-review-check-stale-cache | P2→P1; +Absorbed section |
| 08-07-status-worktree-invisibility | P2→P1 (prerequisite of housekeeping fix) |
| 08-07-status-housekeeping-anomaly-disagreement | P2→P1; +Absorbed section |
| 08-08-developer-identity-not-in-worktrees | P2→P1 |
| 07-22-integrate-routed-review-backends | P1→P2; rescope: program closes when 07-24-remove-retired-review-surfaces lands, plus the two pack-side contract items from the 2026-08-08 collaboration review (accept supportedContractMajors from the descriptor; emit riskClass + changed-path count in the v1 request so the pack classifies and the router prices); +deferred-features note |
| 07-22-streamline-sd-skill-workflows | P1→P3; closure ledger only, no new rounds |
| 08-08-preflight-absent-path-prose | Retitle: drop "and main is red because of it" (verified green 2026-08-08); +Absorbed section |
| 08-06-task-create-base-branch-seed | Retitle: "Harden task.py create: base-branch seed and description requirement"; +Absorbed section; rescope note: upstream Trellis ≥0.6.8 (delivered by 08-08-trellis-upgrade) resolves the repo default branch at create time, but still falls back to the checked-out branch with only a warning when resolution fails — so this task retains its deterministic-gate requirement (reject wrong root-task base_branch values) as pack-local work, plus post-upgrade verification, plus tracking the upstream empty-description fix filed in the Trellis fork |
| 08-07-preflight-planning-branch-gap | P2→P3 (inert until full-mode gap closes) |
| 08-07-review-learnings-unqueried-absence-claim | P2→P3 |
| 08-07-claude-trellis-skill-resolution | P2→P3 |
| 07-28-split-payload-behavior-digest | P2→P3 |
| 07-25-harden-toolchain-failure-paths | Rescope note: R1 already satisfied; R2 only |
| 07-09-trellis-version-compatibility | P3; rescope note: R5/R6 pin fix live, R1–R4 parked |
| 07-25-dispatch-rollout | Park; rescope note: sd-update-deps piece only; R4 dropped per its own notes |
| 07-25-worker-agents | Park note corrected (blocker archived; parked by choice) |

### Park (PARKED: title prefix added where missing; no other edits)

08-06-session-followups, 08-07-sd-submit-pack-task,
08-07-plugin-review-provider-lanes, 08-07-local-finding-rebuttal-channel,
08-07-task-context-manifests-never-curated, 08-07-upstream-task-rename,
08-07-plan-only-payload-shape, 07-25-agent-artifacts.

### Keep unchanged

08-07-work-loop-start-discards-stopped-ledger (P1),
08-06-fleet-provider-config-propagation (P1),
07-24-remove-retired-review-surfaces (P1),
07-28-consolidate-ci-fast-lane-trust-stack, 07-28-stop-committing-generated-mirrors,
08-07-default-local-review-lanes, 08-06-local-provider-empty-scope,
08-07-ship-resume-kb-gap, 08-07-eligibility-superseded-runs,
08-08-pr-eligibility-stale-blocked-review, 08-08-shell-coverage-lane-failures,
08-08-manifest-reference-existence, 07-28-skill-untrusted-content-boundary,
08-06-upstream-add-session-numbering (D3 resolution delegated to
08-08-merge-commit-policy via note), 08-07-provenance-concurrent-session-collision,
07-30-recover-bookkeeping-repair-sessions,
07-26-resolve-v0-54-0-static-analysis-hygiene-findings,
08-07-distributed-gitignore-python-cache, 08-07-preflight-base-diagnosis,
07-25-reduce-review-tooling-spawns (rescope note: R1/R2/R4 only, R3 dropped).

### New tasks (ten, created in this PR, status planning)

| Slug | Priority | One-line scope |
|---|---|---|
| 08-08-trellis-upgrade | P1 | Upgrade vendored Trellis 0.6.7 → 0.6.14. Verified clean: pack's .trellis/scripts is byte-identical to the 0.6.7 release templates, so this is a file swap, not a merge. Delivers the base-branch seed fix and statusline UTF-8 fix for free, plus journal merge=union and machine-readable task.py --json output; adopt --json in wrappers that currently parse console prose |
| 08-08-phase0-dead-surface-cleanup | P2 | Delete review-full-check.sh (+template twin, registry/doc/test refs), remove duplicate installed manifest receipt if nothing reads it, fix four doc contradictions (sd-watch-pr ×3 sites, kcov count, fleet-scripts template carve-out) |
| 08-08-merge-commit-policy | P2 | One decision resolving the planning-recovery vs record-session vs session-numbering-D3 contradiction; then fix recorder or validator, not both |
| 08-08-copilot-request-policy | P2 | Single Copilot request owner fleet-wide: the router owns Copilot dispatch (only path with duplicate-suppression and a durable head-bound receipt). Delete the pack skill's direct `gh pr edit --add-reviewer @copilot` path (+template twin); gate any remaining request logic on the bookkeeping/docs classification CI already computes; operator pass to switch off the repo-level automatic Copilot review ruleset on all 8 fleet repos |
| 08-08-ci-lane-cost | P2 | tests.yml: widen bookkeeping allowlist to docs/ + top-level *.md (allowlist stays inside the byte-identical-classifier trust model; never .github/ or scripts/); shell-coverage to nightly/main-only with kcov cache; macOS leg to main-only; skip full re-run on merge to main while keeping the first-push-full rule |
| 08-08-review-coordinator-env-isolation | P2 | Relocated from sd-github-review's backlog (08-05-fix-review-coordinator-env-isolation there): the pack's review coordinator env-isolation defect, filed in the wrong repo; operators have hand-waived the resulting red gate twice |
| 08-08-parallel-work-backlog | P2 | sd-work-backlog --workers N: N concurrent workers in isolated worktrees, conflict-safe task claiming; prerequisites: work-loop ledger fix, provenance collision, developer identity in worktrees, session numbering, worktree inventory |
| 08-08-fleet-one-path | P2 | One canonical Trellis+pack+GitHub+workflow path across the 8 fleet consumers; normalize per-consumer checks/prepares in consumers.json; private-repo Actions cost guidance (macOS multiplier); Copilot policy propagation |
| 08-08-upstream-handoff-register | P3 | Active register of the nine absorbed upstream-Trellis items: each entry resolves to a filed task in the Trellis fork repo (~/repos/ai/Trellis), an upgrade-delivered fix (statusline UTF-8, base-branch seed), or a deliberately kept pack workaround (the two items inside the fork's runtime-hardening audit) |
| 08-08-fleet-machinery-diet | P3 | Retire fleet-timing.py (1,268 lines of schedule estimation for 8 repos); simplify cohort/wave planning toward a sequential list |

## Acceptance criteria

All checks enumerate from the filesystem, not from this document.

1. `node scripts/sd-ai-command-pack-review-preflight.mjs` on the branch reports
   0 failures; a scripted scan over every remaining task.json finds no
   `parent`/`children` entry naming a removed directory (`children` is the
   live field; `subtasks` is scanned too for safety).
2. Every directory in the three drop lists is absent from `.trellis/tasks/`.
   Active task-dir count equals the table arithmetic (79 − 32 dropped − 2
   archived + 10 new + this task = 56), verified by `ls`.
3. Every existing-task survivor named in the absorb table contains an
   `## Absorbed` section naming its source task; the two merge-commit rows are
   satisfied by the new 08-08-merge-commit-policy prd.md citing both sources.
4. The two archived tasks are under `.trellis/tasks/archive/2026-08/` with
   status completed.
5. Every priority/title edit in the keep table is reflected in that task's
   task.json (scripted before/after diff, not eyeballed).
6. All ten new task dirs exist with non-empty description in task.json and a
   prd.md whose problem statement cites this review's evidence.
7. Every task in the park list has a title starting with `PARKED:`.
8. The PR diff touches only paths under `.trellis/`.
9. This task's task.json description is non-empty (pre-archive gate).
10. Every rescope note named in the keep table is present in its target task's
    prd.md as a `## Rescope (2026-08-08)` section (scripted grep across the
    named targets, not eyeballed), including the two contract items on
    07-22-integrate-routed-review-backends and the corrected base-branch
    rescope on 08-06-task-create-base-branch-seed.

## Evidence

Five-agent review, session 2026-08-08: task-analysis agents (07-*, 08-*),
CI/Copilot cost audit (billing API verified $0 Actions on public repo; 2.07
Copilot reviews/PR over 30 PRs; fast lane fired 6 of 59 runs), KISS audit
(3.23 MB committed self-duplication across 231 groups; 173,615 bytes of
drift-proof machinery), sd-github-review scan (zero deployments, pilot stale
two weeks; direction set to thin v1 core with v2 governance parked/dropped).
Preflight on main verified green 2026-08-08:
`Review preflight: 0 failure(s), 0 warning(s)`.

## Notes

- `task.py archive` force-sets status=completed, so it is reserved for the two
  genuinely shipped tasks; drops are directory deletions whose content Git
  history preserves.
- Known pre-existing condition, out of scope: install-audit reports drift on
  seven installed mirrors against pack 0.64.25 content (the installed pack is
  three patch versions behind the source's 0.64.28). This predates the task,
  is untouched by a `.trellis`-only diff, and is the standing F-1 refresh
  follow-up; it may keep the unified sd-review repository receipt `blocked`
  until the pack is refreshed.
- Owner directives (2026-08-08 session): correctness first, then cost
  efficiency around GitHub Actions and Copilot reviews; KISS throughout; fleet
  repos as consistent as possible ("one path"); parallel work-backlog feature
  requested; sd-github-review not assumed to be the review solution (scan
  confirmed the doubt; direction set to thin v1 core, v2 governance
  parked/dropped, minimal durable lane shipped); cross-repo consistency:
  collaboration between the pack, sd-github-review, and the Trellis framework
  must be seamless — fix upstream where pack workarounds are brittle.
- Sibling efforts, out of this PR's diff but part of the same 2026-08-08
  direction: (a) sd-github-review consolidation in that repo (keep 2, park 16,
  drop 20 of its 38 tasks; new tasks: release v0.3.0 with enforced pin
  freshness, installer ships the discovery descriptor + durable sd-review.yml
  lane and moves the published descriptor off the discovery path, fleet
  rollout with per-repo smoke PRs); (b) Trellis fork updates in
  ~/repos/ai/Trellis (close 4 landed, rescope 4 partially landed, relocate 5
  pack-owned track-* stubs, update 2, create 4 targeted fixes: create-time
  empty-description rejection, .developer worktree provisioning, archive
  index.lock retry, task.py rename); (c) collaboration contract: router owns
  Copilot dispatch, contract surface frozen at schemaVersion 1 + contractMajor
  1 + Check Run "sd-github-review/receipt", pack accepts
  supportedContractMajors and emits riskClass (folded into
  07-22-integrate-routed-review-backends rescope).

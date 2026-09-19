---
title: Reduce workflow overhead without weakening delivery gates
created: 2026-09-18
branch: docs/sd-1021-closeout
item: sd:1021
---

# PRD — workflow-efficiency

## Problem

The workflow audit found repeated checks, late refusals, and manual shipping steps for a single operator.
The staged policy changes reduce reviewer calls but do not resolve these execution gaps.
Installation and machine settings also remain separate from staged source changes.

## Requirements

1. Provide cheap readiness checks before expensive tests or reviews.
   Report tool, authentication, reviewer, consent, runtime-approval, and scope-limit conditions without provider or quota calls.
   Report unavailable runtime-approval evidence as unknown; never imply that pack consent grants runtime permission.
2. Fix runner check reuse before extending reuse to interactive review and shipping.
   Bind evidence to exact tracked, staged, and untracked inputs, configuration, check commands, and runtime identity.
   Changed inputs, missing evidence, and unverifiable identity must invalidate reuse.
   Changed or untracked inputs invalidate legacy receipts.
   Interactive reuse requires explicit opt-in and a clean committed checkout.
   Unknown dependencies disable reuse.
3. Support itemless prepare, merge, and reconciliation through the existing stable review record.
   Preserve review acceptance, ownership, exact-head checks, and delivery receipts without inventing a work item.
   Use canonical repository identity for cross-clone manual-merge guards.
   Build on the merged `sd:1006` foundation; preserve its row, separate acceptance criteria, and locked worktrees.
   Coordinate overlapping shipping edits and rebase onto newer merged dependencies before editing overlapping modules.
   Repeat concurrency checks before phase 3 edits and before integration; stop for conflicting work instead of overwriting it.
4. Preserve existing protection, ownership, review, approval, and CI checks without a new exception.
   Merge-authorization redesign belongs to a user-owned future design, outside this batch.
   Existing separately authorized manual delivery remains unchanged where the ship gate refuses.
5. Add actionable typed state to existing command and API data.
   Distinguish retryable failures, operator decisions, policy blockers, and successful completion.
   Name the next supported action through additive fields; preserve existing status, error, and exit-code meanings.
   Adapt runner or dashboard consumers only when necessary; do not redesign the dashboard.
6. Keep the existing review payload limit.
   Produce an advisory complete path-and-byte inventory and split-branch plan for oversized changes.
   Name dependency boundaries and cross-branch concerns without executing review partitions or aggregating approval.
   The advisory plan never counts as a completed review.
7. Shorten the review and shipping skill entrypoints through conditional references.
   Preserve safety gates, stop conditions, ownership, authorization boundaries, and necessary evidence.
   Apply STE-Concise without deleting actionable failures or caveats.
   Update `WORKFLOW.md`, `README.md`, and `AGENTS.md` for the remaining changes without relaxing existing authorization statements.
   Keep canonical Claude `disable-model-invocation: true` markers for commands.
   Adapt production Codex renders to supported metadata that preserves explicit-only invocation.
   Use `agents/openai.yaml` with `policy.allow_implicit_invocation: false`; preserve unrelated metadata.
8. Test reviewer isolation with synthetic fixtures only.
   Report actual OS confinement, file-read access, and instruction sources separately through reproducible probes.
   Unsupported or failed confinement remains a named blocker, never an isolation pass.
   Keep the external ten-pass experiment, `sd:777`, cancelled; do not restart it under this work.
9. Add strict installation verification using existing receipts, command resolution, and safe smoke checks.
   Return failure for drift or failed checks; distinguish staged, merged, installed, and verified states.
   Preserve the previous serving commit, receipt, rendered surfaces, and matching library runtime before activation.
10. Coordinate reviewer configuration across pack, system controls, and the installed machine.
    Rank only Codex then Claude for automatic review; retain enabled MiniMax and Baseten for explicit task selection.
    Preserve every other provider, enabled/disabled state and reason, spending cap, and author order, including Kimi and exo.
    Do not enable disabled providers during migration.
    Support unranked reviewer-capable providers in system controls before migrating the machine registry.
    Remove only automatic Copilot requests from in-scope repository settings.
    Preserve the system repository's stronger no-Copilot restriction and unrelated settings.
    The approved machine-wide change targets the Copilot-requesting `PostToolUse` Bash hook in `/Users/sven/.claude/settings.json`.
    Remove its automatic Copilot request instructions globally; preserve the push detector and unrelated permissions.
    Do not edit repository `.githooks`.
    The user approved these source, registry, global hook, and GitHub ruleset changes, then deferred merge-authorization redesign.
    Preserve scoped backups and read-back verification for each configuration change.
    Capture the actual machine registry before migration; never substitute the seed YAML as its baseline.
    Back up `/Users/sven/.local/share/sd/providers.yaml` and affected `provider` and `bill` rows at a new migration checkpoint.
    Record the effective inventory, configuration hash, and current revision; reject stale writes.
11. Add conditional post-merge closeout through a ship-skill reference, not a cleanup executable.
    Use existing reconciliation, fetch-prune, review acknowledgment, and GitHub thread reads, replies, and resolution.
    Preserve `sd-receive-review`'s no-post boundary; `sd-ship` owns authorized thread actions.
    Before destructive cleanup, inventory exact task-owned targets with full commit SHAs and stash OIDs, then verify recovery.
    Obtain one consolidated user approval and recheck unchanged targets before deletion.
    Preserve active, locked, dirty, unrelated, primary, and serving worktrees, unique commits/stashes, and shared dependencies.
    Never clear all stashes or force-remove worktrees.
    Give review findings evidence-backed dispositions or verified successors; leave unresolved findings open.
    Do not request Copilot automatically.
    Keep durable follow-ups local unless destination-specific external issue authority exists.

## Dependency evidence

On 2026-09-18, `sd:1006` remained `in_progress`; `sd store item 1006 --json` returned decision note 2786.
Its foundation merged as `c5cd8fe1` through PR #1050; its additional tests merged as `99ca6fde` through PR #1061.
Both commits are ancestors of this worktree's base, `73ea391d`.
The locked worktree `agent-a539046d3d46c5816` had empty status and diff output during this check.
The remaining `sd:1006` acceptance work is separate; this task does not alter its row or claim its acceptance.

The 2026-09-18 machine read from `bin/sd providers list --json` contains disabled Kimi and exo entries.
Both carry reason `Disabled by sven`; the seed YAML is not this machine's inventory.
That read returned configuration SHA256 `d9a8740446d97aa000bd5e50b0525392843fb2c88259b5b1a6b1b5e2748ca6ed`.
Its revision was `181fbc974f161ee0849deeae0873be2324fc6092ef210492fd8d7d79690bb5c1`.
Capture a fresh baseline at the migration checkpoint; these dated values do not authorize a later stale write.

## Delivery sequence

| Phase | Work | Dependency |
|---|---|---|
| 1 | Readiness, typed states, runner reuse correctness | Record baseline behavior and failing regression cases. |
| 2 | Safe interactive reuse, oversized split plans, isolation probes | Phase 1 evidence identity and refusal semantics. |
| 3 | Itemless shipping with unchanged authorization gates | Merged `sd:1006` foundation and concurrency checks before editing and integration. |
| 4 | Concise skills and strict installation verification | Implemented command behavior and receipt contract. |
| 5 | System controls, machine migration, Copilot settings | Compatible controls, scoped backups, passing native checks, and read-back verification. |

## Acceptance criteria

Checked criteria have recorded evidence or an explicitly accepted historical evidence exception, as qualified below.
AC5 and AC14 contain the two accepted exceptions; neither claims that missing historical checks ran.

- [x] `python -m unittest tests.test_sd_review_readiness` passes with zero failures and zero provider or quota calls.
- [x] `python -m unittest tests.test_sd_workflow_state` passes with zero failures.
      Additive fields preserve existing status, error, and exit-code contracts and existing consumer parsing.
      Cases distinguish retryable failure, operator decision, policy blocker, and completion, each with the next supported action.
- [x] `python -m unittest tests.test_sd_review_receipts` passes with zero failures.
      Dirty, staged, untracked, configuration, command, and runtime changes invalidate otherwise reusable evidence.
      Legacy receipts fail reuse when inputs change or untracked inputs exist.
      Interactive reuse requires explicit opt-in and a clean committed checkout; unknown dependencies disable reuse.
- [x] `python -m unittest tests.test_sd_ship_no_item tests.test_sd_ship_remote` passes with zero failures.
      Cross-clone identity, conflicting assignments, stale heads, missing CI, and missing review acceptance retain their refusals.
      Existing protection, ownership, and approval checks remain unchanged; this batch adds no bypass or machine grant.
- [x] AC5 — accepted historical evidence exception, not an executed-check claim.
      Original criterion: before phase 3 edits and integration, record concurrent worktree, assignment, branch, and `sd:1006` row checks.
      Resolve overlaps before proceeding; incorporate newer merged dependencies without altering locked worktrees or the `sd:1006` row.
      Dependency ancestry and one clean locked worktree are recorded; the required phase-boundary snapshots were not located.
      The user accepted this recording gap on 2026-09-19; current ownership and preservation gates remain unchanged.
- [x] `python -m unittest tests.test_sd_review_oversize` passes with zero failures and preserves the existing byte limit.
      The advisory inventory covers every changed path and byte; split plans identify dependency boundaries.
      The planner executes no review partitions and produces no aggregate approval or complete-review status.
- [x] `python -m unittest tests.test_sd_review_isolation` passes with zero failures and makes no external review calls.
      Probe results separate OS confinement, file-read access, and instruction sources.
      Unsupported or failed confinement remains a named blocker; it cannot produce an isolation pass.
- [x] `python -m unittest tests.test_sd_install` passes with zero failures.
      Strict status fails on receipt drift, incorrect command resolution, or failed smoke checks.
      Production-render metadata tests preserve explicit-only invocation on actual Codex output and retain canonical Claude markers.
- [x] `python -m unittest tests.test_rule_registry tests.test_doc_citations` passes with zero failures after entrypoint extraction.
- [x] `python -m unittest tests.test_skill_frontmatter tests.test_workflow_policy` passes with zero failures.
      Canonical Claude markers remain required; current policy prose matches the remaining implementation and unchanged authorization gates.
- [x] `bin/sd-docs-lint` reports `clean`; referenced safety instructions remain reachable.
- [x] `python bin/sd_install.py --user --home "$scratch_home"` produces real Codex renders in an isolated scratch home.
      Run the official validator against those actual renders, never filtered test copies.
      The commands below each report `Skill is valid!`.
      C-29 records both passes contemporaneously; the raw validator transcript was not located.

      ```bash
      python /Users/sven/.codex/skills/.system/skill-creator/scripts/quick_validate.py "$scratch_home/.codex/skills/sd-review"
      python /Users/sven/.codex/skills/.system/skill-creator/scripts/quick_validate.py "$scratch_home/.codex/skills/sd-ship"
      ```

- [x] `make check` passes in the pack worktree with zero failed groups and the existing installer coverage floor.
- [x] AC14 — system tests passed; the user accepted the historical prompt-preflight evidence gap on 2026-09-19.
      Original criterion: `./local-sd-db/sd-db.sh test` passes in the system worktree with zero failures.
      Discover the documented `local-agent-prompt` test and preflight before editing that component.
      Record their exact commands and results; any failure blocks migration.
      Recorded results: library 1,407 tests passed; prompt 18 tests passed.
      Pre-edit discovery timing and preview execution remain unverified, not passed.
- [x] Read back the effective reviewer order as Codex then Claude after migration.
      Verify explicit MiniMax/Baseten eligibility without sending payloads or reading remote quota meters.
      Compare the full provider inventory, enabled/disabled reasons, caps, and author order against the captured machine checkpoint.
      Preserve every checkpoint entry and state, including Kimi and exo when present; never derive expectations from seed YAML.
- [x] The migration checkpoint contains the registry file, affected provider/bill rows, configuration hash, and current revision.
      Backup read-back matches the captured machine baseline before any migration write.
      Scoped rollback restores only affected rows with an optimistic current-revision check; conflicting concurrent changes stop restoration.
- [x] Back up `/Users/sven/.claude/settings.json` and read back the exact scoped hook diff.
      Automatic request instructions are absent globally; the push detector, system no-Copilot restriction, and unrelated permissions remain unchanged.
      Repository `.githooks` remains unchanged.
- [x] Read back affected GitHub settings after scoped changes.
      Automatic Copilot requests are absent; unrelated rules and the system no-Copilot restriction remain unchanged.
- [x] Strict installation verification passes against the intended serving checkout after installation.
      Source checks alone cannot satisfy this criterion.
- [x] Restoration fixtures verify the prior serving commit, receipt, rendered surfaces, and matching library runtime.
      After any real rollback, repeat strict status, command-resolution, and safe smoke checks against those restored identities.
- [x] `python -m unittest tests.test_sd_ship_skill tests.test_sd_review_ack tests.test_sd_review_ack_carried tests.test_sd_status` passes with zero failures.
      Closeout tests cover exact-target approval, recovery, concurrent changes, protected work, and evidence-backed review dispositions.
      Existing documentation and rule gates pass for the conditional reference; no cleanup executable or automatic Copilot request appears.

## Acceptance evidence — 2026-09-19

Pack implementation merged through PR #1070 as `c2e47eb596b199eeee70bb93379b5424de35e05d`.
System implementation merged through PR #451 as `55c4d69168cfa873d57bf063275e2f1a22c5a8e6`.
The pack merge was a slice; whole-item delivery requires a later verified `Delivers: sd:1021` merge.
These records establish implementation acceptance, not review clearance for another head.

| Criteria | Recorded evidence |
|---|---|
| AC1–4, AC6–11, AC13, AC21 | `/private/tmp/sd-pack-review-fixes-fullgate.DwG057/REPORT.md` and `unittest-output.log`: every named shard exited 0. Exact head `ee9fb82b` passed 3,308 tests in 166.499 seconds; installer coverage remained 100%. Documentation lint reported `clean`. |
| AC5 | The user accepted the missing historical phase-boundary snapshots. Dependency evidence remains above; no new check proves historical timing. |
| AC12 | C-29 records both actual scratch-render validator passes. The raw transcript remains unavailable. |
| AC14 | `/private/tmp/sd-system-fix-verification.1rHhIY/REPORT.md` records passing library and prompt suites. The user accepted only the missing pre-edit prompt evidence. |
| AC15–16 | `/private/tmp/sd-workflow-policy.wgpIrs/reviewer-migration.uVDl7s/migration-plan.json` records checkpoint identities, preservation, and scoped recovery instructions. Codex then Claude remain automatic; MiniMax/Baseten require explicit selection. All six provider states remain preserved. |
| AC17–18 | `/private/tmp/sd-workflow-policy.wgpIrs/configuration-changes.json` records exact hook and repository-ruleset read-back. Personal Copilot settings were outside this scope. |
| AC19 | `/Users/sven/.local/share/sd/runtime-backups/workflow-policy-20260919T140005Z/activation-result.json` records strict installer verification: 260 checks, zero failures. Its earlier service limitation remains preserved. |
| AC20 | `/private/tmp/sd-restoration-rehearsal.MwidYw/artifacts/result.json` records matching source, receipt, renders, and runtime. Sixteen command checks and three smoke checks passed. This was a fixture, not a live rollback. |

Item note 2949 records later dashboard health: `ok:true`, `code_changed:false` at `2026-09-19T18:41:36Z`.
It does not rewrite the earlier activation receipt or prove continuing health.
Two fresh desktop skill inventories each returned 40 enabled SD skills and zero errors.
The user confirmed discovery through `@sd-ship`; installation did not create `/sd-*` aliases.
The diagnostic remains at `/private/tmp/sd-codex-discovery.GQcUBZ/DIAGNOSIS.md`.

Approved cleanup removed two backed-up worktrees and their exact local branches without forced removal.
Recovery remains under `/Users/sven/.local/share/sd/runtime-backups/workflow-policy-20260919T140005Z/closeout/candidate-pairs-aqb6p6h_`.
Its `removal-completion.json` reports `verified`; all four recovery archive hashes matched during independent read-back.
Primary checkouts, six dirty worktrees, the archive branch, unrelated work, and shared runtimes remained preserved.
Follow-ups `sd:1024` and `sd:1025` remain separate planning items.

Decision note 2951 records the user's acceptance of AC5 and AC14 after approval of the docs-only closeout PR.
This acceptance changes no executable checks, reviewer policy, CI, ownership, protection, or merge authorization.
It is not a claim that missing checks ran or that this closeout has already merged.

## Scope and rollback

The blast radius includes installed commands, reviewer dispatch, runner reuse, required dashboard adapters, policy documents, and repository review automation.
Preserve the existing staged policy changes and all unrelated work in both primary checkouts.
Use isolated worktrees for implementation; do not alter the original dirty system checkout.
Back up enumerated machine and GitHub settings before changing them, then verify each write by read-back.
The migration checkpoint includes `/Users/sven/.local/share/sd/providers.yaml`, affected `provider` and `bill` rows, and effective configuration identity.
Rollback restores only those backed-up settings or discards only newly created isolated worktrees after preserving their work.
Restore only migration-affected provider/bill rows using optimistic current-revision checks; stop if concurrent changes conflict.
Never restore the whole database over other work.
Before activation, record the serving checkout's exact commit and library revision; back up its receipt and installed rendered surfaces.
Include existing command-link targets and the matching library runtime in the rollback manifest.
Restore that exact serving commit through a preserved checkout, without resetting dirty or concurrent worktrees.
Restore the enumerated receipt, rendered surfaces, command links, and matching library runtime from the preactivation backup.
Read back their identities and rerun strict installation status, command-resolution checks, and safe smoke checks after restoration.
Do not delete unrelated files, rewrite history, or weaken execution approval boundaries.
No release tag, upstream Trellis PR, or external isolation experiment belongs to this scope.
Merge-authorization redesign is deferred to the user-owned future design; this batch implements neither bypass capability nor grants.
The user authorized publication, merge, and activation through existing gates.
Destructive closeout still requires the exact-target approval described in requirement 11.

## References

- User request, 2026-09-18: "address partial and open items" from the workflow audit.
- [Coding-to-release audit and recommendations](../../coding-to-release.md).
- [Merged no-item foundation and separate acceptance scope](../2026-09-17-no-item-review-acceptance/prd.md): `sd:1006`, decision note 2786.
- Follow the sd-ai-command-pack checkout's [.claude/rules/sd-operator-defaults.md](../../../.claude/rules/sd-operator-defaults.md).
- Applicable documentation rules: R13-D1, R13-D2, R13-D3.

## Review

Host planning findings below are addressed in this PRD, not claimed as implemented.
Host registered `sd:1021` in planning status.
Claude planning passes 1 through 3 closed the original scope; pass 4 reviewed the later closeout extension.
Host probes 8–11 passed for both scopes. Host accepted pass 4 dispositions for planning only; no independent clean approval is claimed.
Requirements 1–10 retain their implementation approval.
Requirement 11 is approved for implementation after host read-back; no unresolved planning blocker remains for that extension.

The merge-authorization redesign that C-4 and C-6 both touch is deferred by the
user. That deferral is recorded here and not in either row's verdict cell,
because it is not what either row decided: both concerns are addressed by
requirement 4 keeping the existing gates and adding no exception and no grant
mechanism. `bin/sd-status` reads a ledger row's last cell and ranks
`source:bin/sd-status::OPEN_WORDS` above `source:bin/sd-status::CLOSED_WORDS`,
so a `deferred` beside an `addressed` in one cell reports the row open. That is
the reader working: the cell did carry both. `source:bin/sd-status::_verdict_cell`
records the same collision reaching an archived C-11 from a narrative column,
which is why the last cell is what it reads; a cell holding both words is the
case that fix cannot reach, and the page is where it is answered.

| Finding | Severity | Disposition |
|---|---|---|
| C-1: Interactive reuse needs explicit scope and fail-closed identity. | Blocking | Addressed: explicit opt-in, clean committed checkout, legacy invalidation, and unknown-dependency refusal. |
| C-2: Review partition execution exceeds the bounded oversized-review change. | Blocking | Addressed: advisory inventory and split-branch plan only; no execution or aggregate approval. |
| C-3: Synthetic success cannot establish unsupported isolation guarantees. | Blocking | Addressed: separate measured boundaries and retain unsupported or failed confinement as blockers; `sd:777` stays cancelled. |
| C-4: A PR must not authorize its own protection exception. | Blocking | Addressed: requirement 4 preserves the existing gates and adds no exception. |
| C-5: Typed state must not expand into dashboard redesign. | Nonblocking | Addressed: additive command/API state with only necessary consumer adapters. |

### Claude planning pass 1

Source: `/private/tmp/sd-workflow-policy.wgpIrs/planning-review-1.json`, reviewed on 2026-09-18.
The author prepared these dispositions and is not neutral about shipping this work.
Lane severities below retain the review's values; response dispositions address the plan only.

| ID | Strongest finding | Lane / severity | Response | Evidence |
|---|---|---|---|---|
| C-6 | Default-branch content alone cannot independently authorize bypassing protection. | blocking / high | addressed | Requirement 4 retains the existing authorization gates and adds no grant mechanism. |
| C-7 | Unknown collaborator access could silently satisfy the sole-writer precondition. | blocking / medium | addressed | The proposed exception was removed; requirement 4 preserves existing ownership checks. |
| C-8 | Migration can discard other providers or leave them automatically selected. | blocking / medium | addressed | Requirement 10 and inventory acceptance preserve every provider and state. Automatic inclusion already contradicted: "Rank only Codex then Claude for automatic review". |
| C-9 | An unnamed global hook change can affect unrelated repositories or edit the wrong hook. | blocking / medium | addressed | Requirement 10 names the machine-wide settings hook and preserves its detector. Hook backup/read-back criteria exclude repository `.githooks`. |
| C-10 | Concurrent unmerged `sd:1006` edits can conflict with this task and claim the same acceptance. | blocking / medium | rebutted | On 2026-09-18, ancestry checks returned "c5cd8fe1 is ancestor of 73ea391d" and "99ca6fde is ancestor of 73ea391d". The inspected locked worktree was clean. Requirement 3 now names the dependency and preserves its separate acceptance. |
| C-11 | Settings-only rollback cannot restore activated commands or their library runtime. | advisory / low | addressed | Scope and rollback names the prior serving commit, receipt, rendered surfaces, command links, and matching runtime. Restoration requires read-back and smoke checks. |
| C-12 | Unnamed safety and documentation checks cannot establish acceptance. | advisory / low | addressed | Acceptance now names oversized/isolation modules, rule/citation suites, `bin/sd-docs-lint`, and discovered skill validation commands. |

These responses address the plan only; they do not claim implementation or independent approval.

### Claude planning pass 2

Source: `/private/tmp/sd-workflow-policy.wgpIrs/planning-review-2.json`, reviewed on 2026-09-18.
The author prepared these dispositions and is not neutral about shipping this work.
The user approved deferring merge-authorization redesign and applying existing-workflow fixes first.

| ID | Strongest finding | Lane / severity | Response | Evidence |
|---|---|---|---|---|
| C-13 | The proposed exception leaves waived protection conditions undefined. | blocking / high | addressed | Requirement 4 removes the exception and preserves existing protection and authorization checks. |
| C-14 | Automation can write the proposed grant and thereby authorize its own bypass. | blocking / high | addressed | The grant design and associated implementation criteria were removed. The user owns any future redesign. |
| C-15 | The proposed policy contradicts shipped authorization guarantees. | blocking / medium | addressed | Requirement 4 preserves those guarantees. Requirement 7 includes policy-document updates for only the remaining changes. |
| C-16 | Seed inventory makes exo absent and Kimi's disabled state undefined, so migration preservation cannot be verified. | blocking / medium | rebutted | Machine read-back returned `kimi: enabled=false` and `exo: enabled=false`. Dependency evidence records its configuration hash and revision. Acceptance now binds preservation to a captured machine checkpoint, not seed YAML. |
| C-17 | No explicit provider-file and database-row backup supports migration rollback. | blocking / medium | addressed | Requirement 10, acceptance, and rollback name the registry file and affected provider/bill rows. A new checkpoint and optimistic scoped restoration preserve concurrent work. |
| C-18 | Typed state can break existing consumers without a named compatibility test. | blocking / medium | addressed | `tests.test_sd_workflow_state` must preserve old status/error/exit contracts and parsing. It covers all state kinds and the next action. |
| C-19 | A clean-worktree snapshot cannot exclude future concurrent shipping edits. | advisory / low | addressed | Requirement 3 and acceptance require fresh concurrency checks before phase 3 edits and integration. Locked worktrees and the separate `sd:1006` row remain untouched. |

Closing state: disposed. Scope verification continued in pass 3; raw review reports remain unchanged.

### Claude planning pass 3

Source: `/private/tmp/sd-workflow-policy.wgpIrs/planning-review-3.json`, reviewed on 2026-09-18.
Claude completed one review; the deterministic gate passed with exit 0 in 147.118 seconds.
The raw report remains `blocking`. The author prepared these dispositions and is not neutral about shipping this work.

| ID | Strongest finding | Lane / severity | Response | Evidence |
|---|---|---|---|---|
| C-20 | A false cancellation claim could delete an active owner experiment. | blocking / high | rebutted | `sd store item 777 --json`, note 2775: "External provider reviews are cancelled" and "Resume only with explicit authorization." The [current status and amendment](../2026-09-16-ten-pass-experiment/implement.md) agree. The row remains `blocked`; its item and history stay intact. |
| C-21 | Platform adaptation could silently break byte-parity architecture and leave contradictory tests. | blocking / high | rebutted | Requirement 7 explicitly says "Adapt production Codex renders"; installer acceptance separately requires production metadata tests. Body-and-invocation-policy parity deliberately replaces cross-platform byte parity. |
| C-22 | Unsupported invocation metadata could silently enable side-effecting commands. | blocking / medium | rebutted | [Official OpenAI documentation](https://developers.openai.com/es-419/docs/build-skills), fetched 2026-09-18, documents `policy.allow_implicit_invocation: false` with explicit `$skill` invocation. Bundled `skill-creator/references/openai_yaml.md` agrees. Production metadata tests are separate from `quick_validate`. |
| C-23 | Fake argv assertions cannot prove real OS confinement without provider execution. | blocking / medium | rebutted | `codex sandbox --help` states "Run commands within a Codex-provided sandbox" and accepts arbitrary `COMMAND` plus sandbox-state controls. Local synthetic canaries need no model call; protocol fixtures remain separate. |
| C-24 | An unpinned local validator could become an irreproducible mandatory CI gate. | advisory / low | addressed | This validator is a machine-local activation check, not a new mandatory CI dependency. Its observed SHA256 is `ee6dba90f44d37171c5a6edb8095979c54919ff6822c1a907afca2e78c48738c`. Missing or changed validators are reported, never silently passed; portable metadata regressions remain repository tests. |

C-21's implementation covers production renders, parity tests, current-architecture/README updates, and Codex-only generated companions.
C-22's tests must reject unsupported or conflicting metadata; runtime enforcement remains unverified until direct host observation.
C-23's observed `sandbox_apply: Operation not permitted` remains a blocker, not an isolation pass.
Closing state: disposed. Requirements and acceptance remain unchanged; no completed implementation or independent clean approval is claimed.
Host reread closure SHA256 `00e94dda66bcff85c0a40b39a60907335bb0bb810f8cb724baf8e8dd72bb11cb` and confirmed probes 8–11 passed.
Requirements 1–10 were approved through existing gates at this closure; the later requirement 11 extension received pass 4.

### Closeout extension — Claude planning pass 4

Source: `/private/tmp/sd-workflow-policy.wgpIrs/planning-review-4.json`, reviewed on 2026-09-18.
Claude completed one review; the deterministic gate passed with exit 0 in 162.846 seconds.
The raw report remains `blocking`. The author prepared these dispositions and is not neutral about shipping this work.

| ID | Strongest finding | Lane / severity | Response | Evidence |
|---|---|---|---|---|
| C-25 | Earlier approval could authorize destructive closeout that no review covered. | blocking / high | rebutted | Pass 3 closed requirements 1–10 before requirement 11 existed. The extension expressly awaited review; pass 4 now covers it. Exact-target approval and recovery still precede destructive action. |
| C-26 | Mixed-vendor authorship can leave no eligible automatic reviewer. | blocking / high | rebutted | This is the user's intentional stop condition, not automatic third-provider consent. `TheReviewerChain.test_unranked_reviewers_never_enter_automatic_fallback` asserts mixed OpenAI/Anthropic authorship yields `[]`; that test passed. A third provider requires a new explicit task request. |
| C-27 | Repository and global configuration changes share one inseparable approval and rollback. | blocking / medium | rebutted | Separate acceptance and backups already distinguish them. `configuration-changes.json` records one hook and two repository-only rulesets, each with verified preimages and individual rollback. No organization-wide ruleset changed. |
| C-28 | Adapting metadata leaves rendered body divergence undetectable. | blocking / medium | rebutted | C-21 states body/policy parity, and acceptance names `tests.test_sd_install`. In `work-install`, `RendererParityTests.test_every_surface_preserves_body_and_invocation_policy` and `CodexMetadataTests.test_all_real_commands_and_trials_preserve_policy_and_other_bytes` both passed. They compare every non-marker byte with the source. |
| C-29 | The local validator makes portable acceptance irreproducible. | blocking / medium | rebutted | C-24 limits it to this authorized machine's activation diagnostic and records its hash and missing/change failure behavior. Real `sd-review` and `sd-ship` renders in `/private/tmp/sd-installer-validation.5T7C0u` each returned `Skill is valid!`. This is not an all-surfaces claim; portable metadata regressions remain repository tests. |
| C-30 | Interactive reuse replaces a safe runner identity with an unbounded, unsafe input guess. | blocking / medium | rebutted | The host reports a nine-case pre-fix reproduction; baseline `73ea391d`'s `recorded_check` lacks a dirty-state guard. Requirement 2 permits interactive reuse only on clean committed checkouts. `work-review`'s `sd_check_receipts.check_binding` and `dependency_files` enforce the declared local-only closure. |

C-30's binding includes Git status, HEAD/tree, recursive declared dependencies, configuration, tools, and interpreter identity before and after checking.
Its dirty-state, dependency/runtime-change, and changed-during-check regression methods passed: three tests in 1.907 seconds.
The declaration does not prove arbitrary hermeticity; tests establish invalidation only within the supported closure.
This provisional worktree evidence is not a merged or activated runtime result; the user approved retaining interactive caching.
C-27's independently readable backups are under `/private/tmp/sd-workflow-policy.wgpIrs/configuration-backup.ePTJkC`.
Closing state: disposed. Host read-back is complete and accepts these evidence-based dispositions for planning only.
Requirement 11 has implementation approval through existing gates; requirements and acceptance remain unchanged.
This evidence-only closure starts no additional automatic planning review and authorizes no destructive cleanup.

## Log

- 2026-09-18: Created from the approved audit scope. Source and configuration changes remain distinct acceptance steps.
- 2026-09-18: Addressed host planning findings C-1 through C-5 and recorded source-plus-configuration approval.
- 2026-09-18: Disposed Claude planning findings C-6 through C-12; preserved severity and separated policy capability from activation.
- 2026-09-18: User deferred merge-authorization redesign after source-plus-configuration approval; existing-workflow fixes remain approved.
- 2026-09-18: Disposed C-13 through C-19 and corrected validation to use actual Codex renders with explicit-invocation metadata.
- 2026-09-18: Canonical validation returned `Unexpected key(s) in SKILL.md frontmatter: disable-model-invocation`; production-render validation remains an implementation criterion.
- 2026-09-18: Disposed C-20 through C-24 against primary evidence; preserved the raw blocking report and unchanged implementation scope.
- 2026-09-18: Host verified the closing record and probes 8–11, then approved implementation with no open planning blockers.
- 2026-09-18: User added bounded post-merge closeout and authorized publication, merge, and activation through existing gates.
  Requirement 11 awaits planning review; existing implementation remains approved.
- 2026-09-18: Pass 4 reviewed the closeout extension; C-25 through C-30 received evidence-backed dispositions pending host read-back.
- 2026-09-18: Host reread PRD `15643ac5c1e5778dbb3d8a098d43e3d58a7354b6a1f06f60baeffba62273e848`, accepted planning dispositions, and approved requirement 11 implementation.
  Probes 8–11 passed; the cache decision was pending at that closure and runtime evidence remained provisional.
- 2026-09-18: User approved retaining interactive caching and a broader refactor; requirement 2 and acceptance criteria remain unchanged.
  The original review suite, 2430-line boundary, function limits, coverage guards, and final `make check` must still pass.
- 2026-09-18: Preserve `docs/documentation-truth-archive`; switch the serving checkout to updated `main` only after PR merges and fresh concurrency checks.
  Requirement 11 implementation approval remains active. These authority records start no additional automatic planning review.
- 2026-09-18: User approved documenting the final measured review-lane size increase with written rationale, replacing the earlier 2430-line boundary.
  Functional tests, complexity limits, ownership controls, and review gates remain unchanged.
  This closes the pending choice and starts no additional automatic planning review.
- 2026-09-18: User selected "Authorize manual merges after all checks" for this pack/system batch through a separate manual operator path.
  Exact-head Claude review, CI, ownership checks, dependent-PR query, and thread dispositions must complete first.
  Host read-back returned 404 for both classic `main` protection endpoints.
  Active rules were pack `deletion`/`non_fast_forward` only and system `[]`.
  The existing `sd-ship` merge refusal remains; no gate, protection, or merge-authorization design changes are authorized.
  This scoped approval closes the pending delivery decision; requirements and acceptance remain unchanged.
- 2026-09-19: User said "Approve these five shipping-policy files": replace `skills/sd-ship/SKILL.md` and add four files under `skills/sd-ship/references/`.
  The additions are `adjudication.md`, `delivery.md`, `post-merge-closeout.md`, and `recovery.md`.
  This resolves the execution safety refusals; it grants no additional merge or deletion authority.
  Requirements and acceptance remain unchanged; no additional planning review or status change is authorized.

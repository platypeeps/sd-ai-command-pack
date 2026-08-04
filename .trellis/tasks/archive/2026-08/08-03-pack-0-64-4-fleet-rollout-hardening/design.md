# 0.64.4 fleet-rollout hardening — design

## 0. Ownership classification (decided during design; drives scope)

Not every finding is fixable in sd-ai-command-pack's shippable payload. Three
buckets, established by tracing install/source-of-truth:

- **PACK-shippable** — pack `scripts/*` that install to consumers (or gate their
  PRs). Fixable here, propagates on install.
- **FLEET-tooling** — pack `scripts/sd-ai-command-pack-fleet-*.py` + `docs/` used
  by the operator driving rollouts. In-repo, but operator-facing (not installed
  into consumer product paths). Fixable here.
- **TRELLIS-upstream** — `.trellis/scripts/{task.py,common/task_store.py,add_session.py}`
  are scaffolded by the external `trellis init` tool, **NOT** shipped by this
  pack's installer (confirmed: no `templates/.trellis`, install.py uses
  `trellis_init_platforms`; `task_store.py` exists only as this repo's local
  copy). We **cannot** ship these fixes to consumers from here.

| Finding | Primary site | Bucket |
|---|---|---|
| #1 require description (root) | `task_store.py:300-314` | TRELLIS-upstream |
| #1 checkout-validation guard | fleet SKILL / controller | FLEET-tooling |
| #5 seed rows (root) | `task_store.py:162-170,352-356` | TRELLIS-upstream |
| #5 tolerate seed (gate) | `review-preflight.mjs:810-839,3914-3916` | PACK-shippable |
| #3 finish-work in published head | new fleet publish helper | FLEET-tooling |
| #10 drift-safe repomix | same helper | FLEET-tooling |
| #4 real journal subject | reuse `record-session.py` wrapper (pack) + upstream note | PACK-shippable (wrapper) / TRELLIS-upstream (root) |
| #2 BLOCKED-but-mergeable | `pr-eligibility.py:817,1155` | PACK-shippable |
| #13 merge-queue surfacing | `fleet-controller.py:1076-1088` | FLEET-tooling |
| #12 relink-PR | descoped — see 2a | FOLLOW-UP (not this release) |
| #8 parked canary halt | `fleet-wave-plan.py`, `fleet-controller.py:1636` | FLEET-tooling |
| #9 peek/state-path/preflight/provenance | fleet-controller + docs | FLEET-tooling |
| #6 closed-PR body bleed | `review-scope.sh:184-240` (gh at 211) | PACK-shippable |
| #6 scope-colon template | already colon-correct (`pr-body-scope.py:73-75`) | verify-only |
| #7 KB read-only | `housekeeping.sh:270,302,1360-1362` | PACK-shippable |
| #11 unsafe-sibling diagnostics | `surface-check.py:306-321`, `status.py:894-905` | PACK-shippable |
| #11 recovery schema mismatch | `recovery-artifacts.py:456-457` | PACK-shippable |
| #9 timing cohort labels | `fleet-timing.py:597` | FLEET-tooling |
| Copilot-request recipe | `docs/FLEET_ROLLOUT.md:458-477` | FLEET-tooling (doc) |

**Decision (Open-Q1 = yes):** the TRELLIS-upstream roots (#1 require-desc, #5 seed,
#4 subject-root) are handled by (a) an in-pack compensating control where one
exists, and (b) a filed upstream note in `research/trellis-upstream-notes.md`. We do
NOT edit `.trellis/scripts/*` as a "pack fix" — that would only patch this repo, not
consumers, giving false confidence (the exact late-catch anti-pattern we're
removing). This repo is the pack SOURCE, not a fleet consumer (absent from
`consumers.json`); "passes on this repo" means source self-test + install-audit.

## 1. PACK-shippable changes

### 1a. review-preflight.mjs — tolerate lone `_example` seed (#5 compensating)
- Site: `validateBookkeepingTaskContexts()` (810-839), `findTrellisTaskContextIssues()`
  (3914-3916), reasonCode emit (836).
- Change: a manifest whose ONLY row is the scaffold `{"_example": …}` is classified
  `unfilled` (advisory/no-finding), not `seed` (blocking). A seed row MIXED with real
  rows stays a finding (that's genuine leftover scaffold). Net: fresh `--no-start`
  tasks pass completion validation without manual emptying, but real seed leakage is
  still caught.
- Contract: reasonCode surface unchanged for the mixed case; the lone-scaffold case
  drops from `findings[]` to an advisory note. bundleValid flips true for that case.

### 1b. review-scope.sh — ignore CLOSED same-branch PRs (#6)
- Site: `resolve_pr_body_scope_state()` (184-240); `gh pr view --json body,title,url`
  at 211.
- Change: request `state` too and skip a body whose `state != OPEN`; prefer
  `gh pr list --state open --head <branch> --json` to bind only an open PR. When no
  open PR exists, fall through to the env-provided intended body
  (`REVIEW_PREFLIGHT_PR_BODY`) — never a closed PR's body.
- SCOPE_BODY_PATTERN (170) unchanged (colon already required + template already
  colon-correct → #6 template half is verify-only).

### 1c. pr-eligibility.py — classify BLOCKED-but-mergeable (#2) — ADDITIVE-ONLY
- Sites: 817 + 1155, both `if pr["mergeStateStatus"] != "CLEAN": skip auto-merge`.
- **Hard invariant (C-7):** this change is PURELY additive to the emitted anomaly
  set. Every non-CLEAN classification STILL returns `status="blocked"` and the
  auto-merge path (`gh pr merge`) is never entered. No eligibility decision changes.
- **Data the evaluator must FETCH (Codex #2):** the current `gh pr view` does NOT
  request `mergeable`, `required_conversation_resolution`, or review-thread
  resolution, and `parse_checks()` knows only observed rollup states, not which
  contexts are *required*. So this change must extend the fetch:
  - add `mergeable`, `mergeStateStatus`, `reviewDecision` to the `gh pr view --json`
    field list (already partly present — audit and complete);
  - fetch unresolved review threads + `required_conversation_resolution` via a
    bounded GraphQL query (`repository.pullRequest.reviewThreads(first:100){isResolved}`
    + `branchProtectionRule.requiresConversationResolution`), first page only, with
    a graceful "unknown → no extra anomaly" on query failure.
- Change: when `mergeable == "MERGEABLE"` and rollup has 0 pending + 0 failing and
  `mss != CLEAN`, branch on the block reason from the fetched data:
  - unresolved review threads (+ `required_conversation_resolution`) → emit anomaly
    `merge_blocked_conversation` naming the N unresolved threads;
  - behind base (`BEHIND`) → `merge_blocked_out_of_date` "update branch";
  - required context match that needs data we cannot fetch → **out of scope**; emit
    the generic `merge_blocked_review` anomaly instead of naming the context.
- **Test (AC3.c, negative):** a fixture PR (BLOCKED+MERGEABLE+0/0) asserts the
  eligibility decision is byte-unchanged (`status="blocked"`), no `gh pr merge`
  invocation, AND the actionable anomaly is present. Plus the CLEAN path unchanged.
- Note: the operator settle-watch loop (scratch `smart-watch.sh`) stays operator-side
  (Open-Q2 = classification-only now); no shipped settle-watch this release.

### 1d. housekeeping.sh — KB refresh read-only tolerance (#7)
- Sites: `refresh_obsidian_kb()` (270), `kb_refresh_failed` (302), hard-block
  `return 1` (1360-1362).
- Change: KB refresh is advisory. On a write failure caused by a read-only target,
  emit a `kb_refresh_skipped` WARNING action and continue the merge instead of
  `kb_refresh_failed` + return 1. A refresh failure for any OTHER reason (missing
  tool, corrupt vault) still hard-blocks. Detect read-only via write-probe / EACCES,
  not by blanket-ignoring all failures.

### 1e. surface-check.py + status.py — unsafe-sibling diagnostics (#11) [child C7]
- Sites: `surface-check.py:_load_source_module()` 306-321 (msg 312), distinct
  branches O_NOFOLLOW-unavailable (249), symlink (254-255), non-regular (270-271);
  `status.py:collect_work_loop()` 894-905 (msg 905).
- Change: thread the specific `_UnsafeSiblingPath` reason through so the surfaced
  message reads "present but refused (<reason>)" vs "missing/not installed" ONLY when
  the path exists-but-refused. Reason enum: `no_o_nofollow`, `symlink`,
  `non_regular`, `unloadable`. **No control-flow change** to the refusal — the fail
  path still fails; text only.
- `recovery-artifacts.py:456-457` schema mismatch → include expected-vs-actual in the
  message.

### 1f. record-session.py — real journal subject (#4, reuse existing wrapper)
- The pack ALREADY ships `templates/scripts/sd-ai-command-pack-record-session.py`,
  which resolves real commit subjects (`git log -1 --format=%s`) and is already
  required by `sd-finish-work`. The C2 publish helper INVOKES this wrapper for
  `add_session`, so real subjects land at generation time. No new subject-repair
  behavior is invented; the root `add_session.py` `(see git log)` placeholder is a
  filed Trellis-upstream note only.

## 2. FLEET-tooling changes

### 2a. Redo-lane relink — DESCOPED (finding #12) [C-4]
- **NOT shipped in 0.64.4.** The proposed `resume --relink-pr` updates
  `lane["head"]/["prNumber"]` directly. That breaks the publication-epoch invariant:
  `validate_state()` requires `lane["head"]` to equal the latest successful
  publication receipt (fleet-controller.py:681/690), so a naked mutation fails
  validation; worse, the receipt guards (1182) compare new evidence against the
  MUTABLE lane values, so a naked relink could redefine the expected PR/head and let
  subsequent forged evidence pass. Integrity-sensitive.
- **Supported recovery for 0.64.4:** the proven fresh-campaign redo — attest
  checkout-validation..local-checks as `passed` (work already built + CI-green +
  receipt-valid), then record pr-publication with the existing head + new PR (a FIRST
  publication in the fresh ledger, no continuity constraint). Documented in
  `docs/FLEET_ROLLOUT.md` (AC4.c).
- **Follow-up filed** (`research/trellis-upstream-notes.md` → "controller follow-ups"):
  a typed recovery record carrying old→new PR+head, reason/provenance, no outstanding
  issued action, reset to `pr-publication`; the lane head changes ONLY when the new
  publication receipt establishes the new epoch; misuse + persisted-state tests.

### 2b. fleet-controller.py — merge-queue transparency (#13)
- Sites: `_eligible_lanes` 1076, merge-candidate select 1085-1088.
- Change: when a lane is at `merge/waiting` but is not the current `mergeCandidate`,
  populate `lane["blocker"]`/status text "merge held behind <mergeCandidate> (lower
  priority, not yet merged)". `status`/`next` JSON surfaces it. Display-only; queue
  order unchanged.

### 2c. fleet-controller.py — `--peek` / `--show-issued` + operator-decision provenance (#9)
- Sites: issuedAction store 1111-1114; resume/record parsers.
- Change: `status --show-issued` (or `next --peek`) returns each lane's
  `issuedAction.actionId` WITHOUT issuing a new action or requiring a state-file read.
  `record --result operator-decision --provenance <file>` accepts a first-class
  provenance path (currently hand-authored JSON). Both additive.

### 2d. fleet-wave-plan.py + controller — parked canary doesn't halt (#8)
- Sites: wave-plan pack-blocker `stop_starting=True` (167-176); controller status
  blocked-when-stopStarting (1636).
- Change: a canary lane terminal with `operator-decision` (recorded provenance) counts
  as canary-settled for wave progression under an explicit `--allow-parked-canary`
  opt-in (Open-Q3 = explicit flag, safer default) instead of setting `stop_starting`.
- **PREREQ (C-8):** confirm the EXACT current halt mechanism before editing. The
  investigator found only the pack-blocker path sets `stop_starting`; the
  parked-canary halt may be a distinct path. Phase-C spike gates this edit.

### 2e. fleet-timing.py — cohort labels (#9)
- Site: `parse_consumer` priority-int reject (597).
- Change: accept `canary|post-canary|final` and map to the existing int bands
  (10/50/90 or similar), OR the toolchain wrapper translates before calling. Keep int
  input working (back-compat).

### 2f. docs — Copilot recipe + ergonomics notes (#9, Copilot, #12 recovery)
- `docs/FLEET_ROLLOUT.md` (~458-477 review section): document the working
  `gh api …/requested_reviewers -f "reviewers[]=Copilot"` recipe + MCP/`--add-reviewer`
  failure modes; the campaign-state path `<state-home>/<repo-sha256>/<campaign>.json`;
  that `preflight` is a stage run via `fleet-preflight.py`, not a controller
  subcommand; and the **fresh-campaign redo recovery** (AC4.c).

### 2g. finish-work publish helper (#3 + #10) — the big one
- New: `scripts/sd-ai-command-pack-fleet-publish.py` (or `.sh`) codifying the proven
  scratch `publish-lane3` (a scratch artifact from the campaign, to be PORTED — it is
  not a file in this tree):
  1. detect repomix-indexed repo (tree has `scripts/update_repomix` +
     `docs/repomix-map.md`);
  2. if indexed, fs-move-simulate the archive, run `update_repomix`, move back →
     post-archive repomix folded into the WORK commit;
  3. WORK commit (pack + active task + repomix) = H1;
  4. real `task.py archive` (H2) + `add_session` via the record-session wrapper (H3);
  5. completion receipt base=H1 head=H3 → `.trellis`-only delta → valid;
  6. push; NO merge-stage head-advance.
- **Failure-safety (C-5) — REQUIRED, not optional:**
  - **Preconditions:** refuse to run on a dirty tree (`git status --porcelain`
    non-empty outside the task's own paths); assert the active task dir is owned by
    the current task and inside `.trellis/tasks/`.
  - **Transactional restore:** the fs-move-simulate (step 2) MUST run under a
    `trap …EXIT`/`finally` that restores the task dir to its original location on ANY
    error or interrupt, so a mid-run crash never strands the task in the archive
    location. (The scratch `publish-lane3.sh` lacked this — the port MUST add it.)
  - **Output allowlist:** update_repomix may write ONLY `docs/repomix-map.md`; assert
    the post-run diff touches no other path before committing.
  - **Delta assertion:** before push, assert the H1→H3 delta is `.trellis`-only
    (matches `bundle_scope` `.trellis`-only rule at review-preflight.mjs:1131).
- **Validation target (C-5, Codex #4):** this repo is NOT repomix-indexed (no
  `scripts/update_repomix`, no `docs/repomix-map.md`), so the Phase-B gate validates
  against an actual repomix-indexed consumer clone (consumers.json declares several,
  e.g. mezmo_benchmark). NOT against this repo.
- Integrates with the fleet SKILL as the prescribed pr-publication step.

## 3. Compatibility, rollout, rollback
- Version → 0.64.4; regenerate provenance/vouch (`.sd-ai-command-pack/provenance.json`)
  for every changed shipped script; install audit must pass on this repo (as SOURCE).
- All changes additive / message-only / new-flag — no removed flags, no schema
  version bumps to campaign state or receipts (existing ledgers load unchanged).
- Rollback = revert the release commit; consumers already on 0.64.3 are unaffected
  (0.64.4 is strictly additive hardening).
- Security: #11 and all loader-touching edits are text-only; the loader fail-safe
  test suite must pass BYTE-for-byte behavior (only assertion strings may change).

## 4. Testing strategy (maps to ACs)
- C1: review-preflight lone-seed now advisory (AC1.b); checkout-validation guard test
  (AC1.c). require-desc = upstream note (AC1.a, no pack test).
- C2: build a refresh via the new publish helper on a repomix consumer clone →
  receipt valid + drift test green + zero successor at merge (AC2.a/b); journal
  subjects real via record-session wrapper (AC2.c); helper failure-safety unit
  (dirty-tree refusal + trap-restore on injected error).
- C3: fixture PR JSON (BLOCKED+MERGEABLE+0/0) → classifier emits actionable anomaly
  (AC3.a) AND negative assertion eligibility byte-unchanged + no `gh pr merge`
  (AC3.c); status shows held-behind (AC3.b).
- C4: parked-canary wave test with `--allow-parked-canary` (AC4.a); `--show-issued`
  returns actionId (AC4.b); doc grep for fresh-campaign recovery (AC4.c).
- C5: closed-PR fixture → scope resolves from env body not closed PR (AC5.a); template
  renders colon (AC5.b, verify-only).
- C6: 0444 KB file → gate warns + continues; non-read-only failure still blocks (AC6.a).
- C7: refused-path fixtures (no O_NOFOLLOW / symlink) → "present but refused" msg
  (AC7.a); loader security tests unchanged (AC7.b).
- C8: timing init w/ cohort label ok + int still works (AC8.a); doc grep for recipe (AC8.b).
- Release: self-test + full suite (`make check`) + dry-run candidate-check on a
  repomix + a non-repomix consumer (AC-R1..R4).

## 5. Resolved review decisions
1. Open-Q1 — accept #1-require-desc / #5-seed-root / #4-subject-root as
   Trellis-upstream, ship only in-pack compensating controls: **YES**.
2. Open-Q2 — settle-watch: **classification-only now** (no shipped settle-watch.sh).
3. Open-Q3 — parked canary: **explicit `--allow-parked-canary`** (safer default).
4. C-4 — redo-lane relink **descoped** (unsafe as designed; fresh-campaign recovery
   retained; typed-recovery-record follow-up filed).

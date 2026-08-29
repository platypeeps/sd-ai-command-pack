# Design — simplify review and shipping composition

## Scope boundary

The composition half only. For the transitional **review** surfaces
(`sd-review-pr` and its family), removal scheduling and the transitional catalog
status belong to `07-28-retire-transitional-review-surfaces` and deletion
belongs to `07-24-remove-retired-review-surfaces`. `sd-watch-pr` sits in both
plans today: the sibling artifacts list it among their four scheduled surfaces,
while this task's own PRD R3 requires replacing it with an internal coordinator
and leaving **no public watch exposure** — a requirement deletion alone
satisfies. Phase B therefore executes the `sd-watch-pr` removal here, ahead of
the sibling schedule, and owns the 0.57.0 bump because the breaking change
ships here. The sibling line items become already-satisfied no-ops: at their
planning convergence, `07-28-retire-transitional-review-surfaces` and
`07-24-remove-retired-review-surfaces` drop `sd-watch-pr` from their surface
lists (four → three) — recorded here so the overlap is a sequencing decision,
not two owners deleting one surface. Housekeeping and the shared
exact-head eligibility evaluator stay untouched as the only merge mutation
owners.

## R7 is where the difficulty lives

`sd-ship` Stage 2 (`.agents/skills/sd-ship/SKILL.md:129-136`) currently gets
**three** things from `sd-review-pr`:

1. the bounded review loop (check, remote review, fixes, replies);
2. *"the one read-only, PR-scoped post-cycle review-learning pass; no other ship
   stage repeats it"*;
3. finish-work, conditionally — `until=review` invokes it **without**
   `defer-finish-work` so its Step 8 finishes the Trellis work; `until=merge`
   invokes it **with** `defer-finish-work` and defers to the Stage 4 handoff.

`sd-review` supplies only the first. `SKILL.md:73` states plainly:

> Do not merge, archive Trellis work, or run housekeeping from this skill.

and `grep -n "review-learning" .agents/skills/sd-review/SKILL.md` returns
**nothing** — the successor has no review-learning pass at all.

### The two `until=` values are not equally hard

- **`until=merge` is nearly mechanical.** Stage 4 already "runs finish-work"
  (`SKILL.md:145`) and reuses its schema-version-1 receipt bound to the exact
  final head. Deferral is already the behavior; the successor simply never had
  the thing being deferred.
- **`until=review` has no home for finish-work.** Its whole contract is *finish
  the Trellis work, then stop before merge*. Under the successor, no stage does
  that.

Options for `until=review`:

- **A — `sd-ship` runs finish-work itself as an explicit step after Stage 2.**
  Keeps the user-visible contract identical, puts the authority in the composer
  where R2 already says the lifecycle is explicit. Recommended.
- **B — `until=review` stops without finishing work.** Smallest diff, but changes
  observable behavior for every current caller and quietly moves work onto the
  operator.
- **C — give `sd-review` a finish-work mode.** Rejected: directly contradicts
  `SKILL.md:73` and re-creates the overlapping authority R6 exists to remove.

### The review-learning pass needs an owner, named explicitly

It is not optional plumbing — Stage 2 asserts it happens exactly once per cycle.
Either `sd-ship` invokes `sd-review-learnings` as its own step, or the pass is
dropped and that is written down as a decision. Silently losing a
once-per-cycle pass during a repoint is the failure mode to avoid.

## R3 and R4 land on Stage 3 together

Stage 3 (`SKILL.md:138-142`) invokes `sd-watch-pr` with `no-merge`, and the skill
says `no-merge` *"suppresses the standalone watch command's automatic
housekeeping handoff so Stage 4 owns that side effect exactly once."*

So:

- R3 (remove public `sd-watch-pr`) deletes the surface Stage 3 calls.
- R4 (no `no-merge` inversion; mutation must not be the default) deletes the
  mechanism Stage 3 relies on to stay safe.

Both are correct and they must land as one change: the internal read-only
coordinator replaces the surface **and** makes report-only the default, so the
suppression flag becomes unnecessary rather than merely removed. Doing R4 before
R3 would leave a public watch command whose default is now safe but whose callers
still pass a flag that no longer exists; doing R3 before R4 leaves the inversion
live in the internal coordinator.

## Contract shape

After this task the composition reads:

```
Stage 1  sd-create-pr        publish or reuse exactly one PR      (R1)
Stage 2  sd-review scope=pr  bounded review loop                  (R7)
Stage 2b sd-ship             finish-work / review-learning        (R7 gap)
Stage 3  internal coordinator  read-only bounded polling          (R3, R4)
Stage 4  sd-housekeeping     finish-work, receipt, merge, cleanup (unchanged)
```

**Stage 2b's owner is `sd-ship` — decided 2026-07-28, option A.** An earlier
draft left it `TBD`. Both halves land on the composer for the same reason: R2
makes the lifecycle explicit in `sd-ship`, and `sd-review/SKILL.md:73` forbids
finish-work inside the successor (option C), while option B silently drops work
onto the operator for every current `until=review` caller.

So Stage 2b is two explicit `sd-ship` steps, run once after Stage 2, with
different `until=` conditionality — the double-run hazard exists only for
finish-work, because Stage 4 already runs finish-work (`SKILL.md:145`) while no
other stage runs the learning pass:

1. `sd-review-learnings`, invoked by name in its documented completed-cycle
   form — `sd-ai-command-pack-review-learnings.py --github-pr <PR> --dry-run`
   (the skill's default scan analyzes the working-tree diff, which is the
   wrong scope post-merge-loop) — under both `until=review` and
   `until=merge`, because the predecessor's completed loop ran the pass
   regardless of `defer-finish-work` and Stage 4 has no learning step to
   collide with;
2. finish-work, bound to the same head Stage 2 reviewed — under `until=review`
   only; `until=merge` defers it to Stage 4.

Stage 2b does **not** collapse into Stage 2 (that is option C) and does not
collapse into Stage 4 (which `until=review` never reaches). Under `until=merge`
Stage 2b runs only its learning half — the finish-work skip is the double-run
guard, and both halves' per-`until=` counts are the thing to test.

*(Phase A shape, shipped in v0.56.8. Phase B's R2 decision below supersedes
the finish-work conditionality: Stage 2b runs finalization in both modes and
Stage 4 consumes the retained receipt — the double-run guard becomes receipt
reuse instead of a skip.)*

Because Stage 2b sits after Stage 2, `until=review`'s stop-point moves with
it: `SKILL.md:82` currently reads "stops after Stage 2's review loop
completes" and must be rewritten to stop after Stage 2b, or the new stage is
unreachable in exactly the mode that needs its finish-work half. The
user-visible promise — review completes, Trellis work finishes, no merge —
is unchanged; only the internal stage boundary shifts.

## Phase B decisions — recorded 2026-07-30, before code

Phase A shipped (PR #288, v0.56.8). The decisions below close the gates
`implement.md` steps 6–9 name. None of them touch `sd-housekeeping`, the
housekeeping script, or the shared eligibility evaluator — the scope boundary
holds, and Phase B needs **zero executable-script changes** for the
coordinator because the probe it needs already exists.

### Step 7's four coordinator decisions

1. **Where it lives:** `templates/.agents/skills/sd-ship/references/watch-coordinator.md`
   (installed at `.agents/skills/sd-ship/references/watch-coordinator.md`).
   A reference under the `sd-ship` skill root, following the existing
   `sd-help/references/` pattern. No command-source, no adapters, no catalog
   row, no help output — R3 removes a public surface and this adds none back.
   The new file **must be registered** in `SHARED_SKILL_REFERENCES`
   (`installer/registry.py:1480`) so `make generate` fans it out to `.agents`
   and every platform skill root; an unregistered template reference fails
   `surface-check` with `source.unregistered-template`. The registry edit is
   part of the same step-7 commit.
   Consumers: `sd-ship` Stage 3 and `sd-fleet-refresh`'s `merge-eligibility`
   stage (which today routes through `sd-watch-pr no-merge` at
   `sd-fleet-refresh/SKILL.md:181` and loses its dependency when R3 lands).
   `sd-review` is **not** a consumer: its remote-review materialization wait
   (`SD_AI_COMMAND_PACK_REVIEW_PR_REMOTE_SETTLE_POLLS`) is a different wait —
   reviewer activity, not PR settle — and its published contract stays
   untouched. PRD R3's "used by `sd-review`/`sd-ship`" names who may use it;
   the review loop has no need today.
2. **Bounded polling:** one probe per interval of 20 seconds, attempt ceiling
   `timeout-minutes × 3` (default budget 30 minutes → 90 attempts), matching
   the predecessor's cadence and default so `timeout-minutes=` forwarding
   keeps its meaning. Hitting the ceiling produces the distinct settle state
   `timed-out` in the coordinator's report — one of exactly four reportable
   outcomes (`settled-green`, `settled-blocked`, `timed-out`, `probe-failed`),
   never an exception, never a silent "not ready". `probe-failed` makes the
   classifier total: non-retryable `indeterminate` results (e.g.
   `pull_request_identity_mismatch`), `invalid_result`, and any unexpected
   probe exit (the CLI exits 2 for these) map to it, with the probe's own
   status/reason relayed as the diagnostic. Only `settled-green` advises
   proceeding; every other outcome stops the consumer's chain with the report.
3. **Complete thread pagination:** the probe is the **existing** read-only
   dependency-PR mode of `scripts/sd-ai-command-pack-pr-eligibility.py`,
   invoked in full as `--repo . --dependency-pr-number <N> --remote origin
   --default-branch <base> --github-repository <owner>/<repo>` through the
   toolchain wrapper — dependency mode requires the remote/default-branch
   arguments and returns `github_repository_unavailable` without the explicit
   repository identity. It already calls `collect_threads` — the bounded
   pager (`MAX_THREAD_PAGES = 100` at `:28`, overflow raising
   `EligibilityInputError`, surfaced as a retryable
   `review_threads_unavailable` result). No second pager, no new script, no
   evaluator change. Probe-result classification: `eligible` → settled-green;
   `blocked` with a still-pending check item in `checks.items` → keep
   waiting; `blocked` with no pending checks → settled-blocked;
   `indeterminate`+`retryable` → retry inside the budget; everything else →
   `probe-failed` (decision 2). "Pending" is type-specific, because
   `checks.items` has no common pending field: a `CheckRun` item is pending
   when `status != "COMPLETED"`, a `StatusContext` item when
   `state == "PENDING"`. The classification keys on **items, not reason
   codes**: the evaluator returns `merge_state_not_clean` before the check
   reason codes and before `collect_threads`, so reason codes alone cannot
   distinguish pending from failed and a merge-state-blocked report carries
   **no thread evidence** — `checks.items` (populated up front by `query_pr`)
   is the normative wait signal, and complete thread evidence is guaranteed
   only on `settled-green`, whose `eligible` status requires fully paginated,
   zero-unresolved threads. `settled-blocked` reports state which evidence
   the probe reached. The predecessor's
   reviewer grace period is deliberately dropped: both consumers run the
   coordinator only after a completed review loop has already heard the
   reviewer, so the coordinator watches checks, merge state, and threads.
4. **Reuse:** Stage 4 re-polls by construction, and that is not a TOCTOU
   window: the coordinator's output is sequencing advice (when to attempt
   the merge gate), never merge evidence. The authoritative read is the
   housekeeping eligibility evaluator's own recomputation, which runs
   atomically with the merge decision and independently re-validates the
   receipt, checks, threads, and exact head — the double-validation the
   evaluator already performs today. A stale coordinator snapshot can cost a
   wasted gate attempt, never a wrong merge.

### R2 — finalization and re-entry, both `until=` modes

PRD R2's order is explicit: publish/reuse → review → deterministically
selected finalization → re-enter check/review for any new exact head →
housekeeping merge. That order moves finalization **out of Stage 4's
interior and into Stage 2b for both modes**:

- Stage 2b runs the typed finish-work flow once after Stage 2's clean loop
  under `until=review` **and** `until=merge`. The completion-vs-planning
  selection is the deterministic contract published by
  `07-24-support-planning-only-pr-finalization`; `sd-ship` adds no task-state
  heuristics. Planning finalization preserves planned task state across the
  re-entry — the task stays open; only journal/bookkeeping commits appear.
- If finalization produced a new exact head, `sd-ship` re-enters Stage 2's
  check/review for that head, once. **Finalization** is expected to produce
  at most one new head — a second finalization head is a defect that stops
  the chain with a report (a resume re-enters at Stage 2), never a loop.
  The re-entered review loop pushing **fix commits** is not that defect: a
  review loop legitimately converges through fixes. Re-entry repeats
  **only** Stage 2's check/review: Stage 2b does not run again — its
  learning pass stays exactly-once per cycle and its finalization already
  produced the head under re-review. Under `until=review` the stop-point is
  after Stage 2b plus any re-entry completes.
- **Receipt currency.** The eligibility evaluator rejects a receipt whose
  head is not the current head, so the retained receipt is consumable only
  when re-entry pushed nothing. When the re-entered loop converges on a
  moved head, the receipt is recomputed at that head through the validator's
  own mode-specific re-validation entry — no second finalization, no new
  bookkeeping commits:
  - **Completion mode:** invoke the final-bundle validator with **base equal
    to the current head** — the documented re-validation entry
    (`sd-finish-work/SKILL.md:99-101`). The empty delta activates
    `validateCompletionSuccessorRecovery`
    (`review-preflight.mjs:1078-1084`), which recovers the adjacent
    bookkeeping tail and proves the re-entry fix commits as
    `post-archive-review-successor` — allowed to change code, tests, specs,
    and generated payloads, never task/workspace/finalization evidence. Do
    **not** reuse the original captured base: a moved head puts
    non-bookkeeping fix paths into that delta and fails
    `bundle_scope_invalid`.
  - **Planning mode:** re-run with the same captured base against the new
    head; the journal-only-recovery scope rules alone decide whether the
    enlarged delta (journal edits, maintenance fix commits) still validates.
  - Either way, an invalid recomputation stops the chain with the
    validator's report — fail closed, never a second finalization.
- Stage 4 stays the single merge owner and `sd-housekeeping` stays
  unchanged. Stage 4 runs **zero** finish-work flow invocations:
  housekeeping's run-finish-work-first step is already satisfied by Stage 2b
  in the same chain, and the finish-work wrapper's own rule — "do not rerun
  it for the same state" — forbids a second flow entry. Re-entering the flow
  is not merely redundant, it is unsafe: the delegated Trellis flow archives
  any active task and records a session, so under planning finalization it
  would archive the deliberately-open task. Instead `sd-ship`'s Stage 4
  documents the same retained-receipt handoff `sd-fleet-refresh`'s merge
  action already ships: unchanged head → pass the retained Stage 2b receipt
  through `--finish-work-receipt`; moved head (re-entry fixes) → recompute
  the receipt with a **direct validator invocation** per the mode-specific
  entries above — a read-only script call that runs no Trellis flow and
  mutates nothing. The double-run guard is the eligibility evaluator's
  independent recomputation of the receipt at merge time. Stage 2b owns
  finalization in both modes, and Stage 4 consumes rather than produces. The
  per-`until=` truth table in `implement.md` changes with it.

### R1 and R6 — one public behavior, no hidden second one

- R1: `sd-create-pr`'s verified Stage 1 orchestration mode (publish, report,
  never review) becomes the **only** behavior. Step 6's standalone handoff
  into `sd-review-pr` is removed; the final report names the next command
  (`sd-review scope=pr`, or `sd-ship` for the full chain) instead of running
  it. The skill description and catalog row change to publish-or-reuse-only
  wording.
- R6: with R1 in place the Stage 1 orchestration context (`caller:`,
  `stage:`, `return-after:`) gates nothing and is removed from both
  `sd-create-pr` and `sd-ship`; the composite invokes the public flow.
  Stage 3's `no-merge` dies with the public watch surface (R3+R4). The
  trusted `sd-work-backlog → sd-ship` context and `sd-fleet-refresh`'s
  contexts remain: they narrow report ownership inside an explicit parent
  workflow — the allowance R6 states — and are not composition modes that
  recreate the overlap.

### R5 sweep inventory

Repoint or remove, with `sd-watch-pr` gone and create/review orthogonal:
`sd-work-backlog/SKILL.md:237` (forbidden-separate-invocation list),
`sd-fix-ci/SKILL.md:39,44,117,141` (entry-point and next-step pointers),
`sd-fleet-refresh/SKILL.md:181` (merge-eligibility watches via the
coordinator reference), `sd-help/references/command-catalog.md` (drop the
watch row, reword the create row), `sd-help/references/examples.md:33`,
`templates/scripts/sd-ai-command-pack-status.py:1625,1746` (next-step
strings), `docs/SD_AI_COMMAND_PACK.md` guide text, `README.md`'s
`### sd-watch-pr` section, and the `sd-watch-pr` command-source plus the
template skill directory — deleting those two sources and running `make
generate`/`make sync` removes every generated adapter and manifest row
across all platform targets (claude, gemini, github prompts, cursor,
opencode, kiro, reasonix, trae, zcode). Also: the public command registry
row (`installer/registry.py:815-821` `CommandInfo("sd-watch-pr", ...)`),
the authored `sd-ship` adapter source
(`.github/command-sources/sd-ship.md:2,9,13` still names watch-pr),
`docs/FLEET_ROLLOUT.md:260-266` (fleet timing contract), and the active
spec `.trellis/spec/frontend/adapter-guidelines.md:1671-1680`, which still
requires `sd-watch-pr no-merge` and the Phase A finish-work ownership —
the spec updates in the same PR or it contradicts the shipped surface.
Test pins:
`tests/test_sdlc_commands.py:26,360,569,822`, the per-platform expected-file
lists in `tests/test_generated_parity.py` (~20 `watch-pr` rows), the command
list at `tests/test_script_lib.py:456`, and install fixtures.
`sd-fleet-refresh`'s `review` stage
keeps its `sd-review-pr` caller context: repointing the fleet review lane at
the successor needs a fleet-context design of its own — **parked, owner
named**: `07-24-remove-retired-review-surfaces` must add the fleet
review-stage repoint to its plan before it deletes `sd-review-pr` (its PRD
already requires every live caller on successor contracts; its current
implement.md never designs this repoint). Trigger: that task's planning
convergence. Recorded so the validation grep's remaining hit is a decision
with an owner, not an oversight.

### Version

Removing a public command is a breaking surface change for installed repos:
bump the pack to **0.57.0** (not a patch) in the same PR as the payload
changes, with CHANGELOG entries for the removal, the `until=merge`
finalization-owner shift, and the re-entry behavior.

## R8 — the guide

`docs/SD_AI_COMMAND_PACK.md:194` opens the "Recommended review loop", which then
interleaves successor and transitional steps (`:212`, `:230`, `:247`, `:256`)
across 18 steps with no decision point. Presenting the successor loop only is
simpler and is compatible with the predecessor still shipping — the transitional
commands remain callable, they just stop being recommended. Prefer that over
adding a branch the reader has to evaluate.

## Compatibility

`until=pr`, `until=review`, `until=merge` are the observable contract. Option A
preserves all three verbatim; option B changes `until=review`. Whichever is
chosen, the change is user-visible and belongs in the CHANGELOG.

## Rollout and rollback

R7 and R8 are the interim and can land before retirement. R1-R6 are the end
state. Each stage repoint is independently revertable while the predecessor still
ships — which is exactly the window this task should use, because after
`07-24-remove-retired-review-surfaces` lands there is no predecessor to revert
to.

## Risk

The failure mode is a repoint that looks complete because the review loop still
works, while finish-work and the review-learning pass have quietly gone missing —
both are post-loop side effects that no review-loop test would catch. Test for
their presence, not for the loop's success.

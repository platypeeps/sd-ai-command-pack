# Implementation — simplify review and shipping composition

## Prerequisites

`07-24-implement-read-only-sd-check`, `07-24-implement-unified-routed-sd-review`,
and `07-24-support-planning-only-pr-finalization` must have published stable
contracts. Verify the successor is actually self-contained before repointing at
it:

```bash
grep -n "self-contained" .agents/skills/sd-review/SKILL.md
```

## Order

### Phase A — the interim (R7, R8). Land first; it is what changes behavior today.

1. **Add Stage 2b to `sd-ship` — finish-work under `until=review` only.** Owner
   decided in planning (option A, `design.md`): the composer runs it as an
   explicit step after Stage 2, bound to the same head Stage 2 reviewed.
   `sd-review/SKILL.md:73` forbids it inside the successor and Stage 4 only
   covers `until=merge`, so no other placement is available. Because Stage 2b
   sits after Stage 2, also move `until=review`'s stop-point: `SKILL.md:82`
   ("stops after Stage 2's review loop completes") must become "stops after
   Stage 2b", or the new stage is unreachable in exactly the mode that needs
   its finish-work half.
   **Gate:** Stage 2b's finish-work half must not run under `until=merge` —
   Stage 4 already runs finish-work at `SKILL.md:145`, and an unconditional
   finish-work step runs it twice against two different heads. The learning
   half is exempt from this gate (step 2). Test both modes, not just the one
   being fixed.

2. **Add the review-learning invocation to the same stage.** `grep -n
   "review-learning" .agents/skills/sd-review/SKILL.md` returns nothing, so the
   successor has none and the pass has no owner today. `sd-ship` invokes
   `sd-review-learnings` by name in its documented completed-cycle form —
   `sd-ai-command-pack-review-learnings.py --github-pr <PR> --dry-run`, not the
   default working-tree scan — in **both** `until=review` and `until=merge`
   chains; only Stage 2b's finish-work half is `until=review`-conditional,
   because Stage 4 duplicates finish-work but has no learning step.
   **Gate:** exactly once per review cycle (`until=review` and `until=merge`;
   `until=pr` has no cycle — see Validation). Stage 2 asserts that, and a
   repoint is precisely when a once-per-cycle pass goes missing without anyone
   noticing.

3. **Repoint Stage 2** at `.agents/skills/sd-ship/SKILL.md:129` to
   `sd-review scope=pr`, and rewrite `:133-136` to express the decisions from
   steps 1 and 2 rather than the `defer-finish-work` branch, which has no
   successor equivalent.

4. **Rewrite the recommended review loop** (`docs/SD_AI_COMMAND_PACK.md:194`).
   Present the successor lifecycle only; the transitional steps at `:212`,
   `:230`, `:247`, `:256` come out. The predecessor stays callable — it just
   stops being recommended.

5. `make sync`. Verify no shipped skill or adapter routes the primary delivery
   path through `sd-review-pr`.

### Phase B — the end state (R1-R6)

Decisions for steps 6–9 are recorded in `design.md` § "Phase B decisions —
recorded 2026-07-30"; the steps below execute them.

6. **R1 — narrow `sd-create-pr`** to publish-or-reuse only: no AI review, remote
   routing, polling, finish-work, merge, or nested composition. Concretely:
   remove Step 6's standalone `sd-review-pr` handoff (the final report names
   `sd-review scope=pr` / `sd-ship` as the next command instead of running it),
   drop the review-loop halves of the description, safety rules, and final
   report, and update the command-source
   `.github/command-sources/sd-create-pr.md` so the adapters regenerate.

7. **R3 + R4 together — Stage 3.** Replace `sd-watch-pr` with the deterministic
   read-only internal coordinator **and** make report-only the default in the
   same change. The suppression flag becomes unnecessary: the coordinator never
   hands off to housekeeping, so there is nothing to suppress.
   **Gate:** these do not land separately. `design.md` records why either order
   leaves a broken intermediate state.

   The four AC4 decisions, recorded in `design.md` before this code:

   - **Where it lives:** `templates/.agents/skills/sd-ship/references/watch-coordinator.md`.
     Consumers: `sd-ship` Stage 3 and `sd-fleet-refresh` `merge-eligibility`.
     No command-source, adapter, catalog row, or help output. Register the
     reference in `SHARED_SKILL_REFERENCES` (`installer/registry.py:1480`) in
     the same commit — `make generate` fans it out to `.agents` and every
     platform skill root; unregistered, `surface-check` fails with
     `source.unregistered-template`.
   - **Bounded polling:** 20-second interval, ceiling `timeout-minutes × 3`
     attempts (default 30 minutes → 90). Four reportable outcomes, total:
     `settled-green`, `settled-blocked`, `timed-out`, `probe-failed`
     (non-retryable indeterminate / `invalid_result` / unexpected probe exit,
     diagnostic relayed) — never an exception or silent not-ready. Only
     `settled-green` advises proceeding.
   - **Complete thread pagination:** the probe is the existing read-only
     dependency-PR mode of `pr-eligibility.py`, invoked in full:
     `--repo . --dependency-pr-number <N> --remote origin --default-branch
     <base> --github-repository <owner>/<repo>` via the toolchain wrapper.
     It uses `collect_threads` — the bounded fail-closed pager
     (`MAX_THREAD_PAGES = 100`). No second pager, no evaluator change.
     Wait/settle classification keys on `checks.items`, not reason codes
     (pending: `CheckRun.status != "COMPLETED"`, `StatusContext.state ==
     "PENDING"`); merge-state-blocked reports carry no thread evidence, and
     complete thread evidence is guaranteed only on `settled-green` — the
     reference documents both limits per the design.
   - **Reuse:** Stage 4 re-polls by construction; no TOCTOU because the
     coordinator result is sequencing advice only — the merge decision's
     authoritative read is the housekeeping evaluator's own atomic
     recomputation, unchanged.

   Deletions in the same change: `.github/command-sources/sd-watch-pr.md`,
   `templates/.agents/skills/sd-watch-pr/`, and the generated adapters and
   manifest rows via `make generate`/`make sync`. Rewrite `sd-ship` Stage 3
   (`SKILL.md:150-155`) and the `no-merge` argument text (`:89-97`) to the
   coordinator reference.

7b. **R2 — the lifecycle `sd-ship` is now explicit about.** Execute the design's
   R2 section: Stage 2b runs the deterministically selected completion or
   planning finalization (the typed contract from
   `07-24-support-planning-only-pr-finalization` — no task-state heuristics in
   `sd-ship`) under **both** `until=review` and `until=merge`, retaining the
   exact-head finish-work receipt. If finalization produced a new exact head,
   re-enter Stage 2's check/review for that head **once**; a second
   *finalization* head is a defect that stops the chain with a report, not a
   retry. Fix commits pushed by the re-entered loop are legitimate — but they
   move the head, so the receipt is recomputed at the converged head per the
   design's receipt-currency rules: completion mode invokes the validator with
   **base equal to the current head** (activating the
   `post-archive-review-successor` recovery — never the original captured
   base, whose enlarged delta fails `bundle_scope_invalid`); planning mode
   re-runs the same captured base against the new head under the
   journal-only-recovery scope rules. Invalid recomputation → stop with
   the validator's report. Re-entry repeats only Stage 2, never
   Stage 2b — the learning pass and finalization stay exactly-once. Planned
   task state survives the re-entry, and `until=review` stops after Stage 2b
   plus any re-entry completes. Stage 4 runs **zero** finish-work flow
   invocations: housekeeping's run-finish-work-first step is satisfied by
   Stage 2b in the same chain (the wrapper's own "do not rerun it for the
   same state" rule — and a rerun under planning would archive the open
   task). Unchanged head → pass the retained receipt through the documented
   `--finish-work-receipt` path, the same retained-receipt handoff
   `sd-fleet-refresh`'s merge action documents; moved head → the direct
   read-only validator recomputation above, no Trellis flow.
   `sd-housekeeping` itself does not change.

   **Gate:** the AC names "completion/planning finalization, successor-head
   re-entry, preserved planned task state, and a single housekeeping merge
   owner" as one fixture. Re-entry that reruns Stage 4's merge is the failure to
   test for — the merge owner must still be exactly one.

8. **R5** — repoint everything at the orthogonal create/review/ship/housekeeping
   surface, per the design's sweep inventory: `sd-work-backlog/SKILL.md:237`,
   `sd-fix-ci` pointers, `sd-fleet-refresh:181` (coordinator reference),
   help catalog and examples, `status.py` next-step strings, guide docs,
   `README.md`'s watch section, the public registry row
   (`installer/registry.py:815-821`), the authored source
   `.github/command-sources/sd-ship.md:2,9,13`, `docs/FLEET_ROLLOUT.md:260-266`,
   the spec `.trellis/spec/frontend/adapter-guidelines.md:1671-1680`, and the
   test pins
   (`test_sdlc_commands.py:26,360,569,822`, generated-parity and install
   fixtures). `sd-fleet-refresh`'s `review` stage keeps `sd-review-pr` — parked
   with owner `07-24-remove-retired-review-surfaces`, whose planning must add
   the fleet review-stage repoint before deleting `sd-review-pr` (recorded in
   the design).

9. **R6** — remove the Stage 1 orchestration context from `sd-create-pr`
   (Invocation Modes section) and `sd-ship` (`:93-97`, `:124-127`, `:199-201`);
   `no-merge` is already gone with step 7. The `sd-work-backlog` and
   `sd-fleet-refresh` trusted contexts stay, per the design's R6 allowance.

10. `make sync`, manifest **0.57.0**, CHANGELOG entries (watch removal,
    `until=merge` finalization-owner shift, re-entry behavior).

## Validation

The two things a review-loop test will not catch — finish-work and the
review-learning pass — are the decisive cases:

```bash
python3 -m pytest tests/test_sdlc_commands.py -k "ship" -q
```

Assert the per-`until=` truth table. Phase A's table had `merge` finish-work
at Stage 4; R2 (step 7b) moves finalization to Stage 2b for both modes, with
Stage 4 consuming the retained receipt — update the pins with it:

| `until=` | finish-work | review-learning |
|----------|-------------|-----------------|
| `pr`     | 0 (stops after Stage 1) | 0 |
| `review` | 1 (Stage 2b)            | 1 (Stage 2b) |
| `merge`  | 1 (Stage 2b; Stage 4 runs zero finish-work invocations and consumes the retained or validator-recomputed receipt) | 1 (Stage 2b) |

Zero mutation from the internal coordinator:

```bash
python3 -m pytest tests/test_sdlc_commands.py -k "watch or coordinator" -q
```

No live route through the predecessor. References that are not routes stay
legal (the fleet review-lane carve-out, `sd-review`'s fallback prohibition,
`sd-finish-work`'s handoff-contract naming, the predecessor's own catalog
row, fleet docs, transitional-status wording) — the route check is scoped to
the delivery-path surfaces R5 sweeps:

```bash
grep -rn "sd-review-pr" .agents/skills/sd-ship/ .agents/skills/sd-create-pr/ .agents/skills/sd-work-backlog/ .agents/skills/sd-fix-ci/ scripts/sd-ai-command-pack-status.py
```

Expect empty: no next-step, handoff, or catalog delivery route names the
predecessor.

```bash
grep -c "sd-review-pr" .agents/skills/sd-fleet-refresh/SKILL.md
```

Expect nonzero: the fleet review-stage carve-out (parked, owner
`07-24-remove-retired-review-surfaces`) is still present, not silently
deleted.

```bash
make sync && make check
```

## Review gates

- Steps 1 and 2 answered before step 3. A repoint whose loop works while
  finish-work and review-learning silently vanish looks green.
- Phase A lands and ships before phase B starts — it is the interim the audit
  measures, and it is revertable only while the predecessor still exists.
- Step 7's two requirements land in one commit.
- Any change to `until=review`'s observable contract goes in the CHANGELOG.

## Rollback

Phase A: revert the Stage 2 repoint; the predecessor is still installed and
working, so rollback is real. Phase B: normal revert per requirement, but note
that after `07-24-remove-retired-review-surfaces` lands there is no predecessor
to fall back to — which is the argument for landing phase A well before it.

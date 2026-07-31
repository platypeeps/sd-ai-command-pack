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

6. **R1 — narrow `sd-create-pr`** to publish-or-reuse only: no AI review, remote
   routing, polling, finish-work, merge, or nested composition.

7. **R3 + R4 together — Stage 3.** Replace `sd-watch-pr` with the deterministic
   read-only internal coordinator **and** make report-only the default in the
   same change. `SKILL.md:138-142` shows Stage 3 passing `no-merge` to suppress
   the automatic housekeeping handoff; the replacement must make that suppression
   unnecessary rather than merely removing the flag.
   **Gate:** these do not land separately. `design.md` records why either order
   leaves a broken intermediate state.

   The coordinator's contract is four things AC4 names explicitly, and each one
   has to be a decision recorded in this step rather than an emergent property:

   - **Where it lives.** A reference under the `sd-ship` skill root, not a new
     installed command — R3 removes a public surface and must not add one back
     under a different name. State the path.
   - **Bounded polling.** An explicit attempt ceiling and interval, plus what it
     reports when the ceiling is hit. A timeout must be a distinguishable
     reported outcome, not an exception or a silent "not ready".
   - **Complete thread pagination.** Reuse `pr-eligibility.py`'s bounded pager
     rather than writing a second one: `MAX_THREAD_PAGES = 100` (`:28`), enforced
     at `:643`, overflow raising `EligibilityInputError`. Fail-closed on
     incomplete pagination is the existing contract; an unbounded or truncating
     pager silently reports "no unresolved threads" when there are more pages.
   - **Reuse.** Whether Stage 4 re-polls or consumes Stage 3's result. If it
     re-polls, say why the second read is not a TOCTOU window on the merge
     decision.

   **Gate:** all four written down before the code. AC4 is four assertions; a
   coordinator that polls correctly but reports a timeout as an error fails it
   just as surely as one that never terminates.

7b. **R2 — the lifecycle `sd-ship` is now explicit about.** Phase A added Stage
   2b; R2 additionally requires that `sd-ship` run the *deterministically
   selected* completion **or** planning finalization — the two are different
   depending on task state — and then **re-enter check/review for any new exact
   head** produced by that finalization.

   That re-entry is the part with no analogue in the current composition:
   finish-work can create a commit, and a review that ran against the pre-
   finalization head has not reviewed what will merge. Specify the loop bound
   (finalization is expected to produce at most one new head; a second one is a
   defect, not a retry) and preserve planned task state across the re-entry.

   **Gate:** the AC names "completion/planning finalization, successor-head
   re-entry, preserved planned task state, and a single housekeeping merge
   owner" as one fixture. Re-entry that reruns Stage 4's merge is the failure to
   test for — the merge owner must still be exactly one.

8. **R5** — repoint `sd-work-backlog`, help/catalog, examples, docs, adapters and
   tests at the orthogonal create/review/ship/housekeeping surface.

9. **R6** — remove hidden caller flags and private composition modes.

10. `make sync`.

## Validation

The two things a review-loop test will not catch — finish-work and the
review-learning pass — are the decisive cases:

```bash
python3 -m pytest tests/test_sdlc_commands.py -k "ship" -q
```

Assert the per-`until=` truth table, at the stages decided in steps 1-2:

| `until=` | finish-work | review-learning |
|----------|-------------|-----------------|
| `pr`     | 0 (stops after Stage 1) | 0 |
| `review` | 1 (Stage 2b)            | 1 (Stage 2b) |
| `merge`  | 1 (Stage 4)             | 1 (Stage 2b) |

Zero mutation from the internal coordinator:

```bash
python3 -m pytest tests/test_sdlc_commands.py -k "watch or coordinator" -q
```

No live route through the predecessor:

```bash
grep -rn "sd-review-pr" .agents/skills/ .claude/ docs/ | grep -v "sd-review-pr/"
```

Expect no delivery-path hit.

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

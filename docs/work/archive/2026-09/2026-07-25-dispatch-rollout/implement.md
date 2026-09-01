# Implementation — dispatch rollout to sd-test-gaps, sd-update-deps, sd-fleet-refresh

Three commits, in this order: **sd-update-deps → sd-fleet-refresh →
sd-test-gaps**. Not the PRD's title order. Cleanest first, riskiest last.

Blocked until `07-25-fix-ci-dispatch` is completed **and reviewed**. Inherit
from it: the section goes in `templates/.agents/skills/<name>/SKILL.md` (not the
16-line command source), trust is one carried-forward line and never a copied
classifier, and workers are read-only unless a divergence is recorded.

## Order

### Commit 1 — sd-update-deps

1. Add `## Dispatch protocol` to
   `templates/.agents/skills/sd-update-deps/SKILL.md`. Unit: one dependency PR
   through the 4-axis classification at `SKILL.md:60`.

2. **Dispatch step 2 only. Do not touch step 5.** `SKILL.md:78` is "Process the
   auto-merge class strictly sequentially, one PR at a time". R3 requires that
   rule restated *inside* the new dispatch section — it is the one acceptance
   criterion here that a grep can settle.

3. Workers do not merge and do not evaluate mergeability. `SKILL.md:89`
   delegates the mutation to the installed housekeeping owner via
   `gh pr merge --match-head-commit` and says "Do not reconstruct checks,
   thread, head, or mergeability logic in this skill."

4. Add one sentence on staleness. `SKILL.md:96` notes bots may rebase when the
   default branch moves, so eligibility can go stale between classification and
   merge. Parallel classification **narrows** that window. Without the
   sentence a reviewer will read it as a new risk.

5. `dry-run` (step 4) still stops after classification with no mutations.

### Commit 2 — sd-fleet-refresh

6. **Frame the unit as one controller-issued action, not one consumer repo.**
   Verified in `scripts/sd-ai-command-pack-fleet-controller.py`:

   ```
   :959  issue_next(state) -> list[dict]   # returns one action per eligible lane
   :940  _eligible_lanes(state, plan)      # where the policy lives
   ```

   `_eligible_lanes` gates `checkout-validation` on `lane["name"] in starts`
   (the wave/canary plan) and gates `merge` on
   `lane["name"] == merge_candidate` — **at most one merge lane is ever
   eligible**. The returned list already *is* the safe fan-out.

   **Gate:** a per-consumer framing licenses a worker to drive one consumer
   through several stages, which `SKILL.md:90` ("Drive work only from issued
   actions") forbids. Check the final prose for the word "repo" or "consumer"
   as the unit noun.

7. **Workers never call `next` or `record`.** Parent calls `next` once, fans
   out the returned actions, collects one result per worker, then calls
   `record` per result. Both commands take the campaign file lock
   (`:297 locked()`, lock path `:231`), so concurrent calls serialize — but a
   second `next` issues duplicate actions and `SKILL.md:118-120` rejects a
   conflicting receipt, duplicate action, or "invalid concurrent start", with
   manual state edits forbidden. Recovering from that is a manual
   reconciliation this task must not create.

8. State the two barriers so nobody adds a "worker may proceed" clause:
   `issue_next` returns nothing unless `preflight["status"] == "passed"`
   (`:967-969`), and any lane in `reconcile` sets the campaign `blocked` and
   returns nothing (`:971-973`).

9. Note the two task contexts. `checkout-validation` creates and activates a
   dedicated lightweight Trellis task **in the consumer checkout**
   (`SKILL.md:134`), while the inherited `Active task:` dispatch prefix names
   the **source** repo's task. They do not contend — different `.trellis` roots
   — but a prompt carrying both must say which is which.

10. R4's "controller contract unchanged (scripts untouched or additively
    extended)" is met by touching no script. The concurrency model being
    documented already exists in code.

### Commit 3 — sd-test-gaps

11. **Record the divergence before writing prose.** This is the only command in
    the program whose workers **write**. Every other worker is read-only —
    `07-25-fix-ci-dispatch` R2 and parent `07-25-agent-artifacts` R6. R1 of this
    PRD requires a recorded reason; the reason is that a read-only worker
    returning proposed test source makes the parent absorb every worker's full
    output (defeating the point) and cannot run the per-file implement/check
    loop the skill requires (`SKILL.md:75-76`) without files on disk.

    **Gate:** if this reason is not written into the pattern-conformance note
    (AC4), the divergence looks like an oversight to whoever reads it next —
    including `07-25-worker-agents`, which turns these protocols into named
    agent definitions with capability restrictions.

12. **Change `SKILL.md:71-72`.** It currently reads "for each of the top
    `max-gaps` files (default 3), **one file at a time**". The rollout
    parallelizes a step whose current text forbids it. That is a behavior
    change, not prose cleanup.

13. **Partition by target test module, not by product file.** `SKILL.md:80`
    tells workers to "extend the file's existing test module when one exists",
    so two gap files whose tests belong in the same module produce two workers
    editing one file. Parent groups colliding units and serializes each group.

    **Gate:** this is the failure this commit exists to avoid. Two workers
    writing one test module is a lost edit, and the re-measure step
    (`SKILL.md:81-84`) will show a targeted file that failed to improve without
    saying why.

14. Same for fixtures. `SKILL.md:78` — "Add fixtures only when the new tests
    need them." Two workers can add the same fixture name with different
    content. Parent owns fixture-name arbitration or workers namespace theirs.

15. Parent keeps, unchanged: baseline with abort-on-red (`SKILL.md:58`),
    ranking (`:66`), re-measure (`:81-84` — "no other file regressed" is a
    global property no single worker can assert), and the report table
    (`:116`).

16. `file=<path>` skips the ranking and yields exactly one unit. Confirm the
    dispatch text degenerates to today's flow in that case rather than
    dispatching a single worker for no reason.

17. `max-gaps` defaults to 3, so the realistic writing fan-out is 3. Say the
    bound out loud in the dispatch section — it is what makes the divergence
    tolerable.

### Every commit

18. Capability-first phrasing with the inline sequential fallback; `Active
    task:` prefix; one carried-forward `checkout-trust:` line, no copied
    classifier.

19. `make generate`, `make sync`, regenerate the catalog in
    `docs/SD_AI_COMMAND_PACK.md`.

20. Changelog + version bump.

21. AC4's pattern-conformance note is **three entries**, not one. Two
    conformances and one recorded divergence.

## Validation

AC1 — all three bodies carry the section and generation is byte-stable:

```bash
make generate && git diff --stat && make generate && git diff --exit-code
```

```bash
grep -c "Dispatch protocol" templates/.agents/skills/sd-test-gaps/SKILL.md templates/.agents/skills/sd-update-deps/SKILL.md templates/.agents/skills/sd-fleet-refresh/SKILL.md
```

Expect `1` for each.

AC2 — merge-serialization rule verifiably present in the new sd-update-deps
text. Confirm it is inside the dispatch section, not only at `:78`:

```bash
grep -n "strictly sequentially" templates/.agents/skills/sd-update-deps/SKILL.md
```

Expect at least two hits after the change; one of them inside the dispatch
section.

AC3 — fleet controller contract unchanged:

```bash
git diff --stat -- scripts/sd-ai-command-pack-fleet-controller.py
```

Expect empty.

No copied trust classifier anywhere (inherited gate):

```bash
grep -rn "trusted_local_branch\|untrusted_fork_pr\|indeterminate_" templates/.agents/skills/
```

Expect no hits.

```bash
make check
```

**Not verified by any of the above:** that three parallel sd-test-gaps workers
do not clobber each other's edits. No fixture exercises concurrent test
authoring, and `make check` runs the pack's own suite, not a dispatched
sd-test-gaps run. The partitioning rule in step 13 is a design constraint
enforced by review, not by a test. Say that plainly in the conformance note
rather than implying the risk was tested away.

## Review gates

- No commit lands before `07-25-fix-ci-dispatch` is reviewed. Copying an
  unreviewed pattern into three bodies is the whole ordering risk.
- Commit 2's diff touches no file under `scripts/`.
- Commit 2's unit noun is "issued action", not "consumer" or "repo" (step 6).
- Commit 2's prose never has a worker calling `next` or `record` (step 7).
- Commit 3 does not merge without the recorded divergence reason (step 11) and
  the module-partition rule (step 13).
- Commit 3 is the only diff in this task that changes an existing serialization
  sentence. If commit 1 or 2 also removes a "sequentially" or "one at a time",
  something is wrong.
- No dispatch section added to `sd-work-backlog` or `sd-housekeeping` (R5).

## Rollback

Each commit reverts independently; the sections are additive prose over paths
that still work sequentially, and R5-style inline fallback means every platform
keeps today's behavior.

Commit 3 is the asymmetric one: reverting restores "one file at a time", so an
in-flight parallel authoring run must finish or be discarded before the revert
— otherwise partially written test modules land against a body that says they
were written serially.

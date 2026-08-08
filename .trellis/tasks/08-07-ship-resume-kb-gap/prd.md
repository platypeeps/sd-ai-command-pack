# sd-ship resume enters at Stage 2, which cannot satisfy the KB check Stage 1 owns

## Goal

Make an `sd-ship` resume able to pass its own Stage 2 gate. Today a resume that
enters at Stage 2 is blocked by a deterministic check whose only remediation
belongs to Stage 1, which the resume contract skips by design.

The stage order is right and stays. What is wrong is that one stage owns a
precondition and a different stage enforces it, with no path between them.

## Problem

Three documented rules compose into a dead end. Each is correct alone.

**1. Stage 1 owns the KB refresh.** `sd-ship`'s Stage 1 runs `sd-create-pr`,
whose flow runs update-spec. `sd-update-spec` owns the Obsidian KB extension and
runs the refresh unconditionally from the repository root:

```bash
bash scripts/sd-ai-command-pack-toolchain.sh run-python -- \
  scripts/sd-ai-command-pack-update-spec-kb.py
```

No other `sd-ship` stage refreshes the KB. Stage 4's housekeeping owns "the one
post-finish Obsidian KB refresh", but that runs after the merge gate — far
downstream of the check that needs it.

**2. A resume with nothing to publish skips Stage 1.** From the `sd-ship`
preconditions: "with an open PR and nothing new to publish, start at Stage 2."
This is the documented and desirable behavior — re-running publish against an
already-published head would be a no-op at best.

**3. Stage 2 enforces the KB.** `sd-review scope=pr` gates on its typed
deterministic `sd-check`, whose `knowledge.obsidian-kb` row fails when any
copied file is out of date. The row's own remediation is to run the update-spec
KB helper — the Stage 1 step the resume skipped.

So: any resume whose branch already changed a file the KB copies enters at a
stage that requires a refresh only the skipped stage performs. The chain cannot
converge without an out-of-band manual command.

### Observed on PR #361 (`platypeeps/anomaly-metric-creator`, 2026-08-07)

The branch changed two files under `.trellis/spec/amc/backend/`, both of which
the KB copies. The PR was already open and pushed, so `sd-ship` correctly
resumed at Stage 2, and Stage 2 immediately blocked:

```text
status: blocked | phase: check | diagnostic: typed sd-check did not pass
-- knowledge.obsidian-kb failed | ... copies: 477 ... conflicts:
   - Other Documentation/documentation-review.md is not current
   - Other Documentation/testing-quality.md is not current
```

The finding was true — the KB really was two files behind. Running the helper by
hand reported `copies: 479`, `conflicts: none`, and the chain then proceeded to
a clean merge. Nothing in the resumed path would have run that command.

### Why this is not the receipt-pinning defect

`08-06-review-check-receipt-pinning` was hit on the *same* invocation and is
easy to conflate: after the manual repair, the coordinator replayed the stale
failure until a fresh `--attempt-id` was supplied. That defect is about a
*repaired* state not clearing. This one is about the state never being repaired
in the first place, because no stage in the resumed path owns the repair. Fixing
either leaves the other intact.

### Blast radius

- Every `sd-ship` resume — the documented recovery path after a stop-point, a
  blocked stage, or an interrupted session — in any consumer repository that has
  a `.obsidian-kb` and whose branch touched a copied file. Spec- and
  docs-heavy branches are the likeliest to qualify.
- The failure is silent until Stage 2 runs, and it presents as a review blocker
  rather than a missing setup step, so the operator's natural next move is to
  re-run review rather than to refresh the KB.

## Requirements

### Functional

- R1: an `sd-ship` resume that enters at Stage 2 must be able to reach a passing
  `knowledge.obsidian-kb` check without an out-of-band manual command.
- R2: the fix must not make Stage 2 a second KB owner in the sense of
  duplicating update-spec's logic. `sd-update-spec` remains the owner of what a
  refresh *is*; whatever runs it on the resume path invokes that owner.
- R3: a resume must not silently acquire the rest of Stage 1. Publishing,
  committing, and PR creation stay skipped; only the precondition the resumed
  path depends on is satisfied.
- R4: the KB refresh must stay idempotent and must remain a visible no-op when
  no `.obsidian-kb` exists — the `--if-present` contract `sd-work-backlog`
  already relies on.

### Non-functional

- R5: no additional refresh on the non-resume path. A full chain already
  refreshes in Stage 1; the fix must not make it run twice per ship.

## Constraints

- Do not weaken `sd-check`. The `knowledge.obsidian-kb` row is a true finding
  and must keep blocking a genuinely stale KB.
- Do not relocate KB ownership into `sd-review`. Stage 2 is review-only by
  contract, and the skill explicitly forbids lifecycle side effects there.
- Housekeeping's post-finish refresh stays exactly one refresh with one owner;
  this must not become a second call inside Stage 4.
- An `environment_blocked` `kb-target` result must keep its existing bounded
  recovery and must not be widened by whatever new call site is added.

## Open questions (resolve in design)

- Which stage should own the resume-path refresh? Candidates: a resume-entry
  step in `sd-ship` itself before Stage 2; a narrow publish-skipping mode of
  `sd-create-pr` that runs update-spec and returns; or a precondition on Stage 2
  that invokes the KB helper through its owner. The second re-opens the
  "no composite-only delegation context" rule that `sd-ship` states twice, so it
  needs an explicit decision rather than an implicit one.
- Should the refresh be unconditional on resume, or conditional on the check
  having failed? Unconditional is simpler and idempotent; conditional avoids
  work but needs the check to run first, which is the thing being unblocked.
- Do any other `sd-check` rows read state that only a skipped Stage 1 produces?
  `pack.review-scope` reads the PR body, which Stage 1 also writes — a resume
  reusing an existing PR inherits whatever body is there. This may be the same
  gap with a second face; confirm before scoping the fix to the KB alone.

## Acceptance Criteria

- [ ] A resume fixture — open PR, clean tree, branch changing one KB-copied
      file, KB deliberately stale — reaches a passing `knowledge.obsidian-kb`
      check with no manual command between chain entry and Stage 2.
- [ ] That same fixture performs no publish, no commit, and no PR mutation,
      asserted rather than observed.
- [ ] A full (non-resume) chain refreshes the KB exactly once, asserted by
      counting helper invocations across the run.
- [ ] A repository with no `.obsidian-kb` resumes with the refresh reported as a
      visible no-op and no directory created.
- [ ] `.agents/skills/sd-ship/SKILL.md` states which stage owns the resume-path
      refresh, and the Stage 1 skip reason in its stage table names what the
      resume still runs.

## Notes

- Source: shipping `08-07-capture-ship-review-learnings` on PR #361 in
  `platypeeps/anomaly-metric-creator`, 2026-08-07. The chain merged cleanly, but
  only after a manual `update-spec-kb.py` run that no stage in the resumed path
  would have performed.
- Distinct from `08-06-review-check-receipt-pinning` and
  `08-07-review-check-stale-cache`, both of which concern a *repaired* check not
  clearing. Both defects fired on this one invocation, in sequence, which is why
  the distinction is worth stating explicitly.
- Complex enough to need `design.md` and `implement.md` before `task.py start`:
  the ownership question in the first open question is a real design choice, and
  R2 and R3 constrain it from opposite directions.

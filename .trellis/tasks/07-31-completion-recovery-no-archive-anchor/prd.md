# Fix completion-mode recovery for partial multi-lane tasks with no archive anchor

## Goal

`sd-housekeeping`'s standard PR-merge path cannot auto-merge a PR for a
legitimately multi-lane Trellis task that ships one lane and stays
`in_progress` (other lanes still open), because **no supported `final-bundle`
mode can produce a valid finish-work receipt for that branch shape** — even
with a perfectly correct, explicitly-captured `--base`. Give this shape a
real, safe validation path, without weakening any safety property the
07-29/07-30 task family established.

## Background: how the validator actually works today

`scripts/sd-ai-command-pack-review-preflight.mjs`'s `final-bundle` command
validates a `--base`..`--head` bookkeeping delta in one of two modes.
`final-bundle` cannot be given a `--task-dir` hint — "final-bundle derives
task directories from the committed delta" is an explicit, enforced
CLI-contract line (`:530-532`); every mode must derive scope from git content
alone.

- **`--mode completion`**, normal path (`validateCompletionBundle`, `:1489`):
  requires the delta to contain at least one active→archived `task.json`
  move. **No alternative shape is accepted** — zero mappings is
  `completion_archive_move_missing`, unconditionally. If `--base == --head`
  (no delta), falls back to `validateCompletionSuccessorRecovery` (the
  `post-archive-review-successor` auto-recovery subtype, `:1154-1258`).
- **`--mode planning`**, normal path (`validatePlanningBundle`, `:1583`):
  requires the delta to touch at least one active task directory, **and
  unconditionally enforces `current.status !== 'planning' ||
  current.completedAt !== null || current.branch !== null` →
  `planning_lifecycle_mutation`** (`:1621` — message literally: "planning
  task must keep status planning"). This check is not skippable: the cited
  "active task" category inside `journal-only-recovery` (`:1846`) also
  resolves through this same function
  (`validatePlanningBundle(taskRelatedEntries, ..., {lifecycleOnly: true})`
  per the 07-29 design's Change B), so it applies to the recovered/cited path
  too. **Planning mode is scoped to pre-`task.py start` (Phase 1,
  status=`planning`) tasks only** — it has nothing to do with in-progress
  execution work.

**Consequence, confirmed by direct code reading, not inference:** an
`in_progress`/`review` task's own bookkeeping touch (a `prd.md` checkbox, an
`implement.md` note) has **no valid path through either mode today, under any
`--base`.** Completion mode demands an archive; planning mode demands
status=`planning`. This is the actual root gap — more fundamental than "the
auto-recovery search is unscoped," which was the original report's framing.

### `post-archive-review-successor`'s search mechanism (existing, unchanged by this task except where noted)

`validateCompletionSuccessorRecovery` (`:1154-1258`) walks first-parent
history back from `--head` for the **nearest** commit pair anywhere in
history shaped like "adjacent journal commit + adjacent archive-move commit"
(`isAdjacentJournalCommit` / `isAdjacentArchiveCommit`, `:1260-1292`) — **for
any task, not the one this session is finishing.** Once found, it evaluates
the successor range from that anchor to `--head`
(`evaluateCompletionSuccessorRange`, `:1319-1420`): every commit must have
exactly one parent (else `completion_successor_history_non_linear`), and no
`.trellis/tasks|workspace|.runtime` path may appear in that range (else
`completion_successor_scope_invalid`), bounded by
`MAX_BOOKKEEPING_SUCCESSOR_COMMITS = 50` /
`MAX_BOOKKEEPING_ANCHOR_SEARCH_COMMITS = 100` /
`MAX_BOOKKEEPING_CHANGED_PATHS = 500`. **If that evaluation fails, the
function returns immediately — it does not search for a different anchor.**
Because some archive+journal pair almost always exists within 100 first-parent
commits of any head in an active repo, and that pair is very likely to belong
to an unrelated, already-merged task, the search reliably latches onto a
wrong anchor and fails on the long, contaminated range back to head —
producing noisy, misleading reason codes from unrelated PR history instead of
a direct "no archive exists for the active task" diagnostic.

Per `.agents/skills/sd-finish-work/SKILL.md` Step 7, this subtype is
documented for one scenario: "a base equal to the current head may
automatically recover **one bounded adjacent archive/journal tail** and prove
every later first-parent commit as a `post-archive-review-successor`" — an
archive completion already happened somewhere, and everything since is clean
review-remediation. Step 4 frames its precondition as "no active task exists
because the branch already contains a canonical archive/journal completion."
That precondition is false by construction for an intentionally-partial
multi-lane task: there is an active task, and it was never archived.

### Empirical case study: PR #292 (`fix/measure-unmeasured-runtime-surface`)

Git-verified commit sequence (oldest first), merged to `main` via `518a74b6`:

1. `82cc6a03` — feat: measure `.github/scripts` Python under coverage (lane 1
   work; non-`.trellis` paths)
2. `0c73cb0f` — chore(task): record lane 1 baseline for
   `07-28-measure-unmeasured-runtime-surface` — touches the **active**
   (`in_progress`) task's `prd.md`; not an archive move
3. `1592aab5` — chore: record journal (new session, `.trellis/workspace/`)
4. `f8c7b409`, `62eb33db` — empty CI-retrigger commits
5. `f2931047` — **merge commit**: `main` merged into the feature branch
   mid-flight
6. `4c35bd41` — in-place edit of the *already-recorded* journal-6.md session
   (Copilot flagged an internal inconsistency), touching only
   `.trellis/workspace/sdelmas/{index.md,journal-6.md}`

This one branch demonstrates two independent, already-tracked-elsewhere gaps
compounding with the gap this task owns:

- `4c35bd41` is root-cause-3's exact shape from
  `.trellis/tasks/07-30-recover-bookkeeping-repair-sessions` (T-35): editing
  an existing journal session (not adding a new one) makes
  `validateBookkeepingJournalBundle`'s content-diff check (`:1756-1766`)
  treat it as a "new completed session" needing full citation validation
  again, and if that session's recorded commit list cites a
  `.trellis/workspace/**`-touching commit, planning mode's
  `journal-only-recovery` rejects it. **T-35's scope, not this task's.**
- The mid-flight `f2931047` merge independently breaks both a direct
  base..head tree diff (sweeps in unrelated `main` changes →
  `bundle_scope_invalid`) and any first-parent linear walk
  (`completion_successor_history_non_linear`). "Cited commits stay published,
  linear, bounded ancestors" is an intentional, load-bearing safety property
  from the 07-29/07-30 family, not a gap. **A branch that merges `main` into
  itself mid-flight instead of rebasing will still fail after this task's
  fix** — that is expected, not a regression to chase.
- Reproduction against this branch's head used `--base == --head` under both
  modes (three independent invocations), each failing for its own
  above-documented reason — confirmed 2026-07-31.

**Consequence for this task's acceptance criteria:** PR #292's actual
historical branch will **not** become valid after this fix (merge commit +
T-35 gap both remain). Acceptance criteria target a clean synthetic fixture
reproducing the general structural shape (one task, one lane, no merges, no
journal self-edits), not a literal replay of that branch.

## Confirmed facts

- Constants: `MAX_BOOKKEEPING_FINDINGS = 100`,
  `MAX_BOOKKEEPING_CHANGED_PATHS = 500`,
  `MAX_BOOKKEEPING_SUCCESSOR_COMMITS = 50`,
  `MAX_BOOKKEEPING_ANCHOR_SEARCH_COMMITS = 100`.
- Task statuses (`.trellis/scripts/task.py:331`): `planning`, `in_progress`,
  `review`, `completed`. Archived tasks physically move under
  `.trellis/tasks/archive/YYYY-MM/`.
- `sd-ai-command-pack-pr-eligibility.py`'s `validate_finish_work_receipt`
  (`:219-296`) type-checks `evidence.completionSubtype` /
  `evidence.planningSubtype` as free-form strings with **no whitelist**
  (`require_string(..., limit=100)`, no enum) — confirmed by direct reading.
  A new subtype value needs **no eligibility code change**, matching the
  07-29 precedent for `journal-only-recovery`. The `mode` field itself
  (`completion`/`planning`) **is** a closed enum there — a new third
  `--mode` value would require an eligibility code change; a new subtype
  string does not.
- `sd-ai-command-pack-pr-eligibility.py`'s `finishWorkRequired` is
  `not dependency_mode` (~`:1343`) — the standard branch-merge path
  unconditionally requires a valid receipt; no bypass exists for "task
  legitimately still open." PR #292 had to be merged manually via
  `gh pr merge`, bypassing the automated gate, because no valid receipt was
  obtainable through either mode.
- No existing helper enumerates *all* active task directories and their
  statuses; `locateTrellisTaskRecord(name)` (`:2873`) locates one *named*
  task (active or archived), it does not scan for "whichever task is
  active." A new small helper is needed (same primitives already imported:
  `readdirSync`, `loadTrellisTaskMetadataFile`).
- The 07-29 design
  (`.trellis/tasks/archive/2026-07/07-29-scope-final-bundle-validator-to-delta/design.md`)
  is the load-bearing prior art: delta-scoped findings (blocking vs.
  `advisories`), the widened `journal-only-recovery` commit-scope partition
  (archive / active-task / malformed-task-namespace / workspace / repo), and
  the safety properties this task must not weaken (bounded range, no merge
  commits admitted into a validated range, no unaudited workspace admission,
  archived history stays immutable).
- T-35 (`07-30-recover-bookkeeping-repair-sessions`) is still in planning
  (PRD only) and owns the workspace-repair-commit-citation gap. This task
  must not duplicate that design.

## Decisions on record

1. **Deliver a real new recovery capability**, not just a diagnostic/routing
   fix — the diagnostics-only alternative would leave `sd-housekeeping`
   permanently unable to auto-merge this shape, which is this PRD's actual
   goal.
2. **Single bounded segment only** (precise meaning fixed during review — see
   Notes; the original wording here was ambiguous and got misread as "at most
   one touch total" during the adversarial review pass). It means: one
   discovery pass, one search for the range's starting point, one range
   validated as a unit — never a second, independent search for an older
   starting point if this one's checks fail. It does **not** mean the range
   may contain at most one touch to the active task's own directory: the
   search deliberately finds the *oldest* qualifying touch within the bound,
   so the one range can legitimately contain more than one (that is exactly
   PR #292's shape — a touch+journal pair, then a later journal correction).
   The bound is the same commit-count/path-count caps already governing the
   range, not a separate "how many touches" counter. What stays rejected is
   bookkeeping history *older than the bound* — that fails closed with a
   clear diagnostic rather than triggering a second, deeper search; a task
   with history older than the search window is a bookkeeping-hygiene signal
   (receipts should be consumed close to when produced), not something this
   validator papers over.
3. **Widen `validateCompletionBundle`'s normal path** (root-cause fix) rather
   than building an isolated recovery-only leaf validator or introducing a
   third `--mode` value. A second valid bundle shape — "in_progress/review
   task's own-directory touch + journal, status/completedAt/branch unchanged,
   no archive" — becomes reachable both directly (a caller with a correct
   `--base` can validate it with no recovery hatch) and via the new recovery
   subtype (which proves the same invariant across one bounded range, sharing
   one identity-check definition instead of duplicating validation logic
   across two paths).
4. **No status/branch transition tolerance for this shape** (added during
   planning-adversarial review — see Notes). Status and branch must be
   byte-identical between base and head; unlike the archive-move shape, there
   is no "newly recorded branch" exception and no `in_progress ↔ review`
   transition allowance. `review` status describes a task whose entire scope
   is done and awaiting archive-review, which is incoherent for a task that
   by definition still has open lanes — there is no motivating scenario for
   this shape to need a transition, so the design stays at the narrower,
   safer invariant rather than speculatively supporting one.

## Requirements

- **R1 — widen the normal completion-bundle shape.** `validateCompletionBundle`
  accepts a second valid shape alongside the existing archive-move shape:
  exactly one active (non-archived) task directory touched; that task's
  `status` is `in_progress` or `review` and **unchanged** between `--base`
  and `--head`; `completedAt` stays `null`; `branch` stays unchanged; no
  task-artifact deletions/renames. The existing unconditional journal-session
  requirement (`validateBookkeepingJournalBundle`) still applies. The
  existing archive-move shape and its reason codes are unchanged.
- **R2 — new recovery subtype** (proposed name `active-task-review-successor`,
  open to bikeshedding at implementation time) for the `--base == --head`
  fallback, attempted when the existing archive-anchor search does not
  produce a valid result. Unlike the archive case, this does **not** prove an
  isolated anchor commit and then separately tolerate a successor range — see
  Notes for why that structure doesn't transfer to a directory whose content
  is expected to change again. Instead, it validates one bounded range as a
  unit:
  - Discover "the active task" purely from `.trellis/tasks/**` content at
    `--head` (excluding `archive/`): exactly one non-archived task with
    status `in_progress` or `review` → that is the active task. Zero matches,
    multiple matches, or *any* candidate task record that fails to load
    (unreadable/malformed) → fail closed immediately with a dedicated reason
    code; no history walk is attempted.
  - Search first-parent history from `--head`, bounded by the existing
    search caps, for the **oldest** commit within the bound that touches the
    active task's own directory — not the nearest one; the range below must
    cover every touch to this task inside the search window for a
    multi-touch fixture (AC3) to be provable at all. That commit's parent
    becomes the range's starting point.
  - Validate the whole range (starting point → `--head`) as a unit: linear
    and bounded (existing caps, unchanged mechanism), a **per-commit** scope
    check (not a net diff — a forbidden mutation that a later commit reverts
    must still be caught) restricting every commit's changed paths to
    ordinary non-bookkeeping content, the active task's own directory, or
    journal/index files, a net-effect identity check (R1's invariant, reads
    the range's start via git and `--head` live) and a journal-presence check
    (the existing, unmodified journal validator, run once across the whole
    range).
  - Single bounded segment (Decision 2): one search, one range, validated
    once — never a second, independent search for an older starting point if
    this range's checks fail.
- **R3 — ordering.** The existing archive-anchor search
  (`post-archive-review-successor`) runs first, unchanged. The new subtype
  (R2) is attempted only as a fallback when that search does not produce a
  valid result. No change to behavior when a task actually gets archived.
- **R4 — no eligibility code change.** Confirmed unnecessary (see Confirmed
  facts); the new subtype string flows through the existing free-form check.
- **R5 — operator documentation.** Update
  `.agents/skills/sd-finish-work/SKILL.md` (+ template mirror) Step 7's
  completion-mode paragraph to document the new subtype and its
  preconditions, mirroring how the 07-29 task documented
  `post-archive-review-successor` and `journal-only-recovery`.
- **R6 — preserve safety properties.** No relaxation of: bounded ranges, no
  merge commits admitted into any validated range, archived history stays
  immutable, no unaudited `.trellis/workspace/**` admission beyond what R2's
  own-task-journal citation explicitly validates.

## Out of scope

- T-35's workspace-repair-commit-citation gap (citing a
  `.trellis/workspace/**`-touching commit from `journal-only-recovery`).
- Relaxing the no-merge-commits / linearity safety property.
- Multi-segment replay (Decision 2) — recovering more than one prior
  unconsumed bookkeeping segment for the active task.
- A new third `--mode` value.
- Making PR #292's actual historical branch validate as-is (merge commit +
  T-35 gap both remain out of this task's reach; see Empirical case study).
- Any `sd-ai-command-pack-pr-eligibility.py` code change (R4).

## Acceptance criteria

- [x] **AC1 (R1, direct path).** Synthetic fixture: one task, status
      `in_progress`, one lane shipped (non-`.trellis` work commit), one
      task-directory bookkeeping touch (e.g. a `prd.md` checkbox) + journal
      session, no merge commits, no journal self-edits. Validates via
      `--mode completion --base <work-commit> --head <head>` directly, with
      `evidence.completionSubtype` absent/null (proves the direct,
      non-recovery path now accepts this shape).
- [x] **AC2 (R2, recovery path).** The same fixture, called with
      `--base == --head`, validates via the new recovery subtype, reporting
      `evidence.completionSubtype: "active-task-review-successor"` (or
      whatever name is finalized) with the range's starting point resolving
      to the commit before the `prd.md` touch.
- [x] **AC3 (R2, one range covers more than one touch).** Fixture with a
      second legitimate touch to the same active task after the first (two
      sessions, two `prd.md` ticks + two journal entries, still `in_progress`,
      no merges) validates via the recovery subtype; the range's starting
      point resolves to before the *older* of the two touches (the search
      finds the oldest qualifying touch within the bound, not the nearest),
      and both journal sessions are confirmed present.
- [x] **AC4 (R6, safety preserved).** Fixtures where the range is
      contaminated by a touch to a different task, a touch to the archive, a
      merge commit, or (added during review) a forbidden-path mutation that a
      later commit in the same range reverts, each still block with a
      specific, non-noisy reason code — the last case specifically proves the
      scope check is per-commit, not a net diff that a revert could evade.
- [x] **AC5 (R2, ambiguous active task).** Fixtures with zero, with multiple,
      and (added during review) with one valid `in_progress` task plus one
      sibling task directory whose `task.json` is corrupt/unparseable, each
      fail closed immediately with the dedicated "ambiguous active task"
      reason code — no history walk in any case.
- [x] **AC6 (R2, no anchor).** Fixture with no commit touching the active
      task's own directory within the bounded search window fails closed
      with a direct "no anchor found for the active task" diagnostic, not the
      old noisy non-linear/oversized codes from unrelated history.
- [x] **AC7 (regression).** All existing `tests/test_bookkeeping_validator.py`
      cases pinning archive-successor and `journal-only-recovery` behavior
      stay green.
- [x] **AC8 (R4 regression).** `tests/test_pr_eligibility.py` stays green with
      no code change to `sd-ai-command-pack-pr-eligibility.py`.
- [x] **AC9 (R5).** SKILL.md + template mirror updated; `make sync` /
      mirror-parity check stays green.
- [x] **AC10 (Decision 4, added during review).** A fixture where the
      in-place shape's base/head records differ in `status`
      (`in_progress`→`review`) or newly record `branch` blocks with
      `completion_source_lifecycle_invalid` / `completion_task_identity_changed`
      — proving no transition tolerance exists for this shape, unlike the
      archive-move shape.
- [x] **AC11 (R2, added during round-2 review — the most serious finding of
      that round).** A fixture where the task is created (`task.py create`,
      status `planning`) and started (`task.py start`, → `in_progress`)
      *inside* the bounded search window, followed by the normal
      touch+journal pair, still recovers via the new subtype — the search
      must resolve its starting point to after `task.py start`, never to the
      creation or start commit itself. This is the ordinary shape for any
      task young enough that its whole lifecycle fits in the search window,
      not an edge case; a naive "oldest commit touching the task directory"
      search would fail it, since `task.py create`/`start` also touch the
      task's own directory but their own preceding state can never satisfy
      this shape's `in_progress`/`review` precondition.

## Notes

- Complex task: `design.md` + `implement.md` required before `task.py start`
  (confirmed by user at task creation).
- Exact new reason-code names and the final subtype-name choice are
  implementation detail, finalized in `design.md`.
- **Planning-adversarial review.** This PRD and `design.md` went through the
  mandatory host + Codex review at
  `.claude/sd-ai-command-pack/planning-adversarial-review.md` before
  implementation approval. The first design draft had seven confirmed
  blocking defects — most fundamentally, an anchor-proving mechanism modeled
  too literally on the archive case's isolated-commit proof, which relies on
  archived content never changing again; that assumption doesn't hold for an
  active task's own directory, which this task explicitly allows to be
  touched again. `design.md`'s Change B section documents the corrected
  mechanism (one unified range, not an isolated anchor plus a tolerant
  successor) and maps every review finding to its fix. Decisions 2 and 4
  above, and R2's wording, were tightened directly as a result.

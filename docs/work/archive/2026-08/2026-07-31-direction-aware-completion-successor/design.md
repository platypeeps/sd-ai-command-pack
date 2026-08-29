# Design — direction-aware completion-successor validation

## Rebased onto origin/main (post-#302) — authoritative structure

This plan was first written against the pre-#302 base. The branch has since been
fast-forwarded onto `origin/main`, which merged PR #302
(`07-31-completion-recovery-no-archive-anchor`). That PR **rewrote the same
subsystem** (+610/−45 in `review-preflight.mjs`). The direction-blind bug this task
targets is **still present** on the new base (verified: `isAdjacentArchiveCommit` is
byte-identical), and the PR #301 shape still yields an opaque
`completion_successor_scope_invalid` (verified by reproduction). The design below
holds; only the surrounding structure and line anchors moved. New anchors are
authoritative over any older `:NNNN` cited later in this file:

- `validateCompletionSuccessorRecovery` (`:1684`) is now a **thin dispatcher**:
  1. `attemptArchiveAnchorRecovery(headOid)` (`:1205`) — the original archive/journal
     tail search; it **contains the old recovery loop** and is where C1/C2/C4/C6 land.
  2. `attemptActiveTaskAnchorRecovery(headOid)` (`:1600`) — new in #302; recovers
     open multi-lane tasks that have no archive anchor.
  3. Dispatcher decision (`:1705`): commits `archiveResult.findings` when
     `archiveResult.shapedTailCount > 0 || status === 'indeterminate'`, else
     `activeTaskResult.findings`.
- `isAdjacentArchiveCommit` `:1769`; `evaluateCompletionSuccessorRange` `:1832`
  (unchanged logic; C2b adds `entries` to its return at the final `return`);
  `bookkeepingChangedEntries` `:1949`; new helpers `archiveTaskName` `:1730`,
  `archiveMoveSet` `:1744`, `completionAnchorRevertedNames` `:1781`. Regex consts
  `ARCHIVE_TASK_JSON`/`ACTIVE_TASK_JSON` live at top-of-file (`:52`) — **not** beside
  the helpers — because the CLI dispatch runs at `:462`, before the helper region;
  module-level `const` beside the helpers would be a temporal-dead-zone crash at that
  dispatch (observed and fixed).
- **The successor block** (`attemptArchiveAnchorRecovery:1260`,
  `if (successor.status !== 'valid')`) is the C4/C6 site: prepend
  `completion_successor_anchor_reverted` (`:1266`) before the existing
  `successor.findings` loop (`:1272`), then the existing
  `return { status: 'invalid', shapedTailCount, findings, evidence: {} }`. My finding
  rides in `archiveResult.findings`; for the PR #301 shape `shapedTailCount > 0`, so
  the dispatcher commits it — verified end-to-end:
  `['completion_successor_anchor_reverted', 'completion_successor_scope_invalid']`.

**Behavior change the rebase introduces (documented, intended):** a *pure* un-archive
(archive→active with no real archive tail) was `anchor_invalid` on the buggy base
(the blind predicate accepted it). With C1 it is no longer a shaped archive tail, so
recovery falls through to the active-task path and reports
`completion_successor_active_task_anchor_missing`. This supersedes the old
`anchor_missing` expectation; T3 asserts the new code. It is a strictly better
diagnosis and does not weaken any guard.

**Out of scope (pre-existing #302 debt):** #302 added
`completion_successor_active_task_anchor_missing` and
`completion_successor_active_task_ambiguous` but did **not** add matrix rows for them
in `quality-guidelines.md`. This task's spec amendment adds only its own
`completion_successor_anchor_reverted` row; the matrix↔code review gate is therefore
scoped to *this task's* code, and the #302 matrix gap is flagged as follow-up, not
absorbed here.

## Verified current behavior

`validateBookkeepingFinalBundle` (`scripts/sd-ai-command-pack-review-preflight.mjs:1041`)
enters successor recovery only when the requested `base..head` delta is empty:

```js
if (options.mode === 'completion' && entries.length === 0
    && runtime.allowCompletionSuccessor !== false) {
  validateCompletionSuccessorRecovery(evidence, headOid, add);
  return;
}
```

`bookkeepingChangedEntries` (:1435) runs `git diff --raw -z --find-renames base head --`
with **no pathspec**, so `entries.length === 0` means base and head have identical
*trees* — not that they are the same commit. No OID-equality check exists at the
trigger (:1042-1046, :1078-1084). Recovery then walks first-parent history
newest-first, testing each `[journalCommit, archiveCommit, base]` triple for shape.

This two-endpoint (not per-commit-union) diff shape recurs at :1375 and is load
bearing for the decisions below.

Entry shape is settled by the parser at :1456-1470:

| status | `oldPath` | `path` |
| --- | --- | --- |
| `R…` / `C…` | rename source | rename destination |
| `A` `M` `D` `U` `T` | `''` | the single path |

Note `D` puts the deleted path in `path`, not `oldPath`.

## Defects

### D1 — `isAdjacentArchiveCommit` is direction-blind (:1279)

It flattens `oldPath` and `path` into one bag and never reads `entry.status`:

```js
const paths = entries.flatMap((entry) => [entry.oldPath, entry.path].filter(Boolean));
const activeTaskNames = new Set(/* …/tasks/<name>/task.json from paths */);
return paths.some((path) => /* …/tasks/archive/<ym>/<name>/task.json */ && activeTaskNames.has(name));
```

A rename active→archive and a rename archive→active produce the *same* two paths,
so both satisfy the predicate. A pure un-archive is accepted as an archive commit.
This is the exact bug `b3d0cb25` fixed on the Python side by requiring change type
`A`/`M` under `archive/`.

### D2 — WITHDRAWN: "one bad candidate aborts the scan" is not a defect

Originally this design proposed replacing the `return` at :1209 with `continue` so a
later valid anchor stays reachable. Adversarial review rejected that, and the
rejection holds on inspection. Recorded here rather than deleted, because the
reasoning constrains what C1 and C3 are allowed to do.

**Why it is unsafe.** Two independent fail-open paths:

1. `evaluateCompletionSuccessorRange` returns `indeterminate` — not just `invalid` —
   when git cannot inspect the range (:1333), a commit subject (:1366), or the
   changed paths (:1383). `status !== 'valid'` covers both. Scanning past an
   `indeterminate` converts an inspection failure into a pass. Today's `return`
   fails closed; `continue` would not.
2. Successor scope comes from a single two-endpoint diff (:1375). For an *older*
   anchor, a bookkeeping mutation and its later reversal cancel inside that one
   diff, so the path never appears. Continuing past a nearer scope-invalid
   candidate would let precisely the post-finalization mutation the guard exists to
   catch reach an eligible verdict — contradicting `prd.md` Non-Goals and the
   normative "reject every change" contract at
   `.trellis/spec/backend/quality-guidelines.md:1214-1218`.

**Why it is also unnecessary.** PR #301's nearer candidate was only shaped because
`isAdjacentArchiveCommit` accepted an un-archive (D1). Once C1 makes the predicate
direction-aware, that triple fails the shape test and the *existing* `continue` at
:1201 walks past it to the real archive tail. The motivating scenario is fully
closed by C1. `continue`-on-failure would buy nothing and cost both regressions
above.

**Decision:** the `return` at :1209 stays. Non-`valid` successor status remains
terminal, for `invalid` and `indeterminate` alike.

### D3 — a reverted anchor reports as a scope violation (:1395)

`evaluateCompletionSuccessorRange` flags any successor path under `.trellis/tasks/`,
`.trellis/workspace/`, `.trellis/.runtime/`, or `.sd-ai-command-pack/finish-work` as
`completion_successor_scope_invalid`. When the successor commit is a revert that
restores the anchored task, the operator gets a path-level scope error with no
indication that the finalization itself was undone or that the receipt is stale.

## Decisions

**Keep the scope guard.** D3 is a diagnosability fix, not a permissiveness fix. A
branch whose finalization was reverted still fails; it just fails legibly, with a
named recovery action. PR #301 under this design would still not merge via the gate
— it would say *why* and *what to do*.

**Detect the revert in the recovery loop, not in the scope loop.**
`evaluateCompletionSuccessorRange` stays a pure scope predicate with no knowledge of
which task the anchor archived. The recovery loop already holds `archiveEntries` and
can derive the archived task names, so the revert check belongs there.

**It runs after the scope evaluation and adds to it — it never replaces or skips
it.** An earlier revision had the revert check run first and `continue` past the
candidate. That would have suppressed genuinely independent violations: a successor
that both un-archives the anchored task *and* writes `.trellis/.runtime/` would have
reported only the revert, while `prd.md` requires runtime writes to keep reporting
`completion_successor_scope_invalid`. The revert code explains *why the anchor is
void*; it does not absolve anything else in the same range.

**Where the stale receipt is really detected.** The `prd.md` open question resolves
to: fix the validator. Receipt generation cannot know about commits that land after
it. The validator sees the final head and is the only component positioned to notice
that the attested finalization no longer holds — so it must be the one to say so.
Whether finish-work should additionally refuse to reuse a receipt across a revert is
a separate, narrower question and is not taken up here.

## Changes

### C1 — direction-aware archive predicate (D1, R1)

Replace the flattened-bag check with a move assertion. The task must both land in
`archive/` and vacate its active location in the same commit:

- `archivedNames` — names whose `.trellis/tasks/archive/<ym>/<name>/task.json`
  appears as the **destination** of a non-`D` entry (`entry.path`).
- `vacatedNames` — names whose `.trellis/tasks/<name>/task.json` appears as a
  rename **source** (`entry.oldPath` of an `R…` entry) or as the path of a `D`
  entry. `bookkeepingChangedEntries` runs `git diff --raw --find-renames` with
  **no** `--find-copies` (:16), so git never emits a `C…` status here; the parser
  handles `C…` (:1456) only defensively, and it is an unreachable state on this
  path. Were a copy ever produced, its source would not vacate (the original
  stays), so the rename-only rule is also correct in principle.
- qualify only when the two sets intersect. This intersection — names that both
  landed in `archive/` and left their active location — is the commit's true
  archive move-set. C3 reuses exactly this set (not the raw archive destinations)
  so an unrelated archive copy in the same commit cannot be mistaken for the
  anchored task.

The existing "every path under `.trellis/tasks/`" guard is retained.

Observed shape, not assumed — both directions measured directly:

```
c74a79eb (archive)     R100 ×5 artifacts,  R093 task.json  f4bf5bfa → 461ded35
c59db841 (un-archive)  R100 ×5 artifacts,  R093 task.json  461ded35 → f4bf5bfa
```

The archive changes `task.json` (`status` → `completed`, `completedAt` → a date)
yet `--find-renames` still reports `R093`, not delete+add. So the rename branch is
the path that actually executes; `D`-entry handling is retained as defensive
coverage for a below-threshold similarity, not because it is the shape git
currently produces.

Extract the name-matching regexes into shared helpers so C3 reuses them rather than
restating them.

### C2 — WITHDRAWN (see D2)

No change to the control flow at :1205. Both `invalid` and `indeterminate` stay
terminal. This is now a deliberate no-op step, kept numbered so C3/C4 references and
the `implement.md` ordering stay stable.

The surrounding scan already has the right shape: unshaped candidates `continue`
(:1201), and the nearest shaped candidate is authoritative — matching
`.trellis/spec/backend/quality-guidelines.md:1238` ("shaped *nearest* candidate")
and the exact-array assertion at `tests/test_bookkeeping_validator.py:1086`.

### C3 — anchor-revert detection (D3, R3/R4)

New `completion_successor_anchor_reverted`, emitted as a *classification* of a
candidate that has already failed — never as a reason to skip one.

Test each name in the anchor's **archive move-set** — the C1 `archivedNames ∩
vacatedNames` intersection, not the raw archive destinations — for a genuine
un-archive in the successor range. **Both directional halves are required for the
same name:**

- the archived `.trellis/tasks/archive/<ym>/<name>/task.json` **leaves** (rename
  source of an `R…` entry, or the path of a `D` entry; a `C…` copy source cannot
  occur here — no `--find-copies` — and would not count anyway), **and**
- the active `.trellis/tasks/<name>/task.json` **arrives** (non-`D` destination).

An `and`, not an `or`. Either half alone is a different event and must not borrow
the stale-receipt diagnosis: deleting an archived task without restoring it is
cleanup, and adding an active copy while the archive remains (an `A` add on the
active side, the archive path untouched) is a duplicate. Both still fail the scope
guard — under their own code.

**One authoritative diff read.** C3 must **not** issue its own
`bookkeepingChangedEntries` call. `evaluateCompletionSuccessorRange` already reads
and parses this exact range at :1375; extend its return to expose those `entries`,
and have C3 consume `successor.entries`. A second read would create an independent
failure mode: if the evaluator's read succeeded (producing `invalid` findings) but
C3's second read then failed, returning on that failure would suppress the very
scope findings the additive contract requires. With a single read there is no such
window — and because C3 runs only when `status === 'invalid'` (C4), a `null` read
never reaches it: the evaluator already turns a failed read into `indeterminate`
(:1383), which the unchanged terminal `return` at :1209 emits as
`completion_successor_history_unavailable`.

Message names the anchor, the task, and the action:

> the completion anchor at `<oid>` archives `<name>`, but a later commit restores it
> to `.trellis/tasks/<name>`; the finish-work receipt no longer describes this head —
> re-run finish-work to regenerate it

### C4 — reporting, additive not exclusive

The candidate's successor findings are emitted exactly as they are today (the
`return` at :1209 is unchanged). C3 **prepends** `completion_successor_anchor_reverted`
when its two-halves test fires, so the operator reads the actionable cause first and
the full failure set after it:

```
completion_successor_anchor_reverted     ← C3, first: names the cause and the fix
completion_successor_scope_invalid …     ← every path finding, unchanged
```

Ordering is presentational only. No finding is downgraded or replaced. The only loss
is the pre-existing `MAX_BOOKKEEPING_FINDINGS` (100) cap: `add` silently drops
anything past the 100th finding (:551 outer, :1322 evaluator). That cap counts **all**
finding types cumulatively — config findings on the outer collector, and
history/non-linear/oversized/scope findings inside the evaluator (:1336, :1388, plus
the scope loop) — so once the total reaches 100, prepending one more truncates the
current last finding regardless of how many are scope paths. This is not new loss:
the same cap already governed output before this change, and the prepend only changes
*which* finding is the one past the boundary. Because it is unchanged pre-existing
bounded-output behavior, not a behavior this task introduces, it needs no new R5 test.
A reverted anchor that also writes `.trellis/.runtime/` reports both codes, satisfying
`prd.md` AC3 and AC5 simultaneously rather than trading one against the other.

`indeterminate` dispositions are never reordered or suppressed — an inspection
failure is not a diagnosis, and C3 must not dress one up as a revert.

## Spec amendment (normative)

`.trellis/spec/backend/quality-guidelines.md:1233-1250` is a normative
"Validation & Error Matrix", not descriptive prose. One row is added:

- `completion_successor_anchor_reverted` — the successor range un-archives the exact
  task the candidate anchor archived, so the finish-work receipt no longer describes
  this head.

`:1246` ("protected bookkeeping/runtime path -> `completion_successor_scope_invalid`")
is **not** narrowed. Withdrawing C2 and making C4 additive means the un-archive still
produces its scope findings; the new code accompanies them. The matrix row for
`:1246` therefore stands as written, and no existing row becomes unreachable.

`:1235` ("no candidate inside the complete bounded history") is likewise untouched:
C2's withdrawal leaves the meaning of "candidate" exactly as the matrix already
defines it.

Constants cited by the matrix were checked and are unchanged: 100-commit anchor
window, 50 successor commits, 500 changed paths
(`scripts/…-review-preflight.mjs:27-35`).

The spec edit is a required deliverable of this task, not follow-up cleanup: leaving
it stale would make the shipped validator contradict its own normative contract.

## Compatibility

Existing tests must not move:

- `:1136` runtime-evidence and `:1162` mutate-archived-bookkeeping are not
  un-archives, so C3's two-halves test does not fire and their findings are emitted
  by the unchanged `return` at :1209 — still exactly
  `completion_successor_scope_invalid`.
- `:1086` invalid-nearest-anchor has a valid successor range, so it reaches the
  anchor check unchanged and still returns exactly
  `["completion_successor_anchor_invalid"]`.
- `:1221` canonical-anchor-required has no shaped tail at all and still returns
  exactly `["completion_successor_anchor_missing"]`.

## Mirror constraint

`templates/scripts/sd-ai-command-pack-review-preflight.mjs` is a byte-identical twin
of `scripts/…` (Makefile:52; verified with `diff -q` — identical at branch point).
Every edit lands in both. `scripts/sd-ai-command-pack-surface-check.py:648` emits
`mirror.stale` and the "Release payload gate" CI job (`.github/workflows/tests.yml:491`)
enforces it. `make lint` runs `node --check` against both copies.

## Rollback

Self-contained within one function group in one file plus its mirror. Revert the
commit; no state, schema, or receipt format changes, and no existing reason code is
removed or repurposed.

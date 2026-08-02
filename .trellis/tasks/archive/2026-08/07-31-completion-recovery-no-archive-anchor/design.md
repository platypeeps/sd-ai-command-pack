# Design: a real completion-bundle shape for legitimately-open tasks

Line references are to the current tree (commit `518a74b6`); function identity
matches `prd.md`'s Background section.

**Revision note:** this is the second draft. The first draft went through a
host + Codex adversarial review (contract:
`.claude/sd-ai-command-pack/planning-adversarial-review.md`) that found ten
confirmed blocking defects (across both lanes, deduplicated), several of them
fundamental (a shared-helper extraction that would have broken every
archive-move fixture; an anchor mechanism that could never actually recover
the case it exists for; a historical-proof step that silently read live
worktree state instead of the historical ref for content that isn't
immutable the way archived content is). Change B below is a materially
different, simpler mechanism than the first draft's — see "What changed and
why" at the end of the Change B section for the specific defects each part
fixes. A planned round-2 dual-lane re-review (fresh Codex + fresh host
sub-agent) was interrupted mid-run; before retrying, direct self-verification
against the actual code found and fixed two smaller defects the rewrite
itself introduced (C-8, C-9 in the table below). A retried, Codex-only round
2 (read-only, against the artifacts including the C-8/C-9 fixes) then found
five further blocking defects — most seriously, that the "oldest touch"
search would usually select `task.py create` or `task.py start` itself,
which structurally cannot satisfy this shape's own preconditions, meaning the
mechanism would have failed on the single most common real case. All five are
fixed below (see the "What changed and why" table's round-2 Codex rows),
verified directly against the code, still without a second independent
reviewer confirming these specific fixes — that is an open item for whoever
reviews this package next, not a claim of final convergence.

## Shape of the change

Three coordinated changes to `scripts/sd-ai-command-pack-review-preflight.mjs`
(+ template mirror), one commit:

- **A. Widen `validateCompletionBundle`'s normal path** with a second valid
  bundle shape: an `in_progress`/`review` task's own-directory touch, status
  and branch **unchanged** (no transition tolerance — see Decision 4), no
  archive. Root-cause fix — a caller with a correct `--base` can now validate
  this directly.
- **B. New recovery subtype**, `active-task-review-successor`, for the
  `--base == --head` fallback when the existing archive-anchor search does
  not produce a valid result. Finds the single active task's own bounded
  bookkeeping range and validates it as one unit — not by proving an isolated
  "anchor commit" the way the archive case does (that mechanism does not
  transfer to a directory whose content is expected to change again).
- **C. Operator documentation.** `sd-finish-work/SKILL.md` Step 7 documents
  the new subtype and its preconditions.

No new `--mode` value, no schema version bump, no
`sd-ai-command-pack-pr-eligibility.py` code change (Decision 3 / R4 — subtype
strings are free-form there, confirmed by direct reading).

## Decision 4 (new, from review remediation): no status/branch transition tolerance

The first draft let Change A's in-place shape tolerate an `in_progress ↔
review` transition and a newly-recorded `branch`, mirroring the archive-move
shape's tolerances. Review caught that this directly contradicted `prd.md`
R1's own wording ("status ... unchanged", "branch stays unchanged") — a
cross-artifact inconsistency, not a considered design choice. Re-examined:
`review` status describes a task whose *entire* scope is done and awaiting
archive-review, which is incoherent for a task that by definition still has
open lanes; there is no motivating scenario for this shape to need a
transition. Resolved by tightening the design to the PRD's original, narrower
wording rather than loosening the PRD: **status and branch must be
byte-identical between base and head for this shape.** This also simplifies
the shared identity helper (below) to a straight equality check instead of
independent set-membership checks per side.

## Change A — widen `validateCompletionBundle` (`:1489-1576`)

### Current shape (unchanged)

`uniqueMappings` detects active→archived `task.json` moves. When
`uniqueMappings.length > 0`, each mapping is validated: the archived directory
gets the full `validateBookkeepingTaskDirectory` sweep, the source status
must be `in_progress`/`review`, and `source`/`archived` records must be
field-identical except `status`, `completedAt`, and a newly-recorded `branch`
(the `stripLifecycle` + `branchNewlyRecorded` + `stableJson` block,
`:1550-1574`). **This block is entirely unchanged by this task** — see the
shared-helper note below for why it stays a distinct call, not a shared
unconditional check.

### New shape: in-place active-task touch

When `uniqueMappings.length === 0`, instead of failing immediately, check
whether `taskEntries` resolves to **exactly one** active (non-`archive/`)
task directory with no partial/malformed archive-looking paths mixed in:

```
if (uniqueMappings.length === 0) {
  const inPlace = detectInPlaceTaskTouch(taskEntries, add);
  if (inPlace) {
    validateInPlaceTaskTouch(inPlace.taskDir, baseOid, add, options);
    return;
  }
  add('completion_archive_move_missing', '', 'completion bundle must move an active task into an archive month, or touch exactly one active task directory in place');
  return;
}
```

`detectInPlaceTaskTouch`: collects the set of active task directories touched
by `taskEntries` (same `/^\.trellis\/tasks\/\d{2}-\d{2}-[^/]+\//` extraction
`validatePlanningBundle` already uses at `:1591`). Any `archive/`-prefixed
path here means a malformed/partial archive attempt — do not fall through to
the in-place shape; let the existing `completion_archive_move_missing`
message cover it. Exactly one non-archive directory, zero archive-prefixed
paths → proceed. Zero or more than one → falls through to the existing
failure.

`validateInPlaceTaskTouch(taskDir, baseOid, add, options, evidence)`:

1. `current = validateBookkeepingTaskDirectory(taskDir, {add, archived: false, addAdvisory: options.addAdvisory ?? null, deltaPaths: options.deltaPaths ?? null})`.
2. `source = loadBookkeepingJsonAtRef(baseOid, `${taskDir}/task.json`, add)`.
3. Deletion/rename guard: any `taskEntries` path under `taskDir` with status `D`/`R` → `completion_task_scope_invalid` (reusing the existing code).
4. `validateTaskLifecycleIdentity(source, current, `${taskDir}/task.json`, `${taskDir}/task.json`, add, IN_PLACE_IDENTITY_OPTIONS)` — see shared helper below.
5. `evidence.taskDirectories = [taskDir]` — **fixes a round-2 non-blocking finding**: the first draft never assigned this, so a valid in-place result would have reported an empty `taskDirectories` array despite deriving exactly one. Mirrors the archive-move path's own `evidence.taskDirectories = uniqueMappings.map(...)` assignment (`:1525`); `validateCompletionBundle` needs `evidence` threaded into `validateInPlaceTaskTouch` as a parameter to make this assignment.

### Shared helper: `validateTaskLifecycleIdentity` (**revised — was blocking defect C-1**)

The first draft proposed one unconditional check function whose
`current.status` / `current.completedAt` rules were written for the in-place
shape's invariants and applied unmodified to the archive-move caller too.
Since `task.py archive` unconditionally sets `status: 'completed'` and a
non-empty `completedAt` on every archived record
(`.trellis/scripts/common/task_store.py:481-482`, independently required by
`review-preflight.mjs:747` — `archived && record.status !== 'completed'` is
itself a blocking finding), that draft's checks would have fired on every
legitimate archive move. Fixed by parameterizing the expected transition
instead of hardcoding one:

```
function validateTaskLifecycleIdentity(source, current, sourcePath, currentPath, add, options) {
  const {
    sourceStatuses,             // required both callers, e.g. ['in_progress', 'review']
    checkCurrentStatus = false, // archive-move: false, in-place: true — see note below
    currentStatuses,            // used only if checkCurrentStatus
    requireStatusEqual = false, // Decision 4: true for in-place, false for archive-move
    checkSourceCompletedAtNull = false, // in-place: true; archive-move: false (source is pre-archive, same as today)
    checkCompletedAt = false,   // archive-move: false, in-place: true — see note below
    currentCompletedAtRule,     // used only if checkCompletedAt: 'null' | 'non-empty'
    tolerateBranchNewlyRecorded = false, // true for archive-move only (existing behavior)
    sourceCode = 'completion_source_lifecycle_invalid',
    identityCode = 'completion_task_identity_changed',
  } = options;
  if (!source || !current) return;
  if (!sourceStatuses.includes(source.status)) {
    add(sourceCode, sourcePath, `source status must be one of: ${sourceStatuses.join(', ')}`);
  }
  if (checkSourceCompletedAtNull && source.completedAt !== null) {
    add(sourceCode, sourcePath, 'source completedAt must be null for this bundle shape');
  }
  if (checkCurrentStatus && !currentStatuses.includes(current.status)) {
    add(sourceCode, currentPath, `status must be one of: ${currentStatuses.join(', ')}`);
  }
  if (requireStatusEqual && source.status !== current.status) {
    add(sourceCode, currentPath, 'status must stay unchanged for this bundle shape');
  }
  if (checkCompletedAt) {
    const completedAtOk = currentCompletedAtRule === 'null'
      ? current.completedAt === null
      : typeof current.completedAt === 'string' && current.completedAt.trim().length > 0;
    if (!completedAtOk) {
      add(identityCode, currentPath, `completedAt must be ${currentCompletedAtRule === 'null' ? 'null' : 'a non-empty timestamp'} for this bundle shape`);
    }
  }
  const stripLifecycle = (record) => { const c = {...record}; delete c.status; delete c.completedAt; return c; };
  const sourceRecord = stripLifecycle(source);
  const currentRecord = stripLifecycle(current);
  const branchNewlyRecorded = tolerateBranchNewlyRecorded
    && sourceRecord.branch === null
    && typeof currentRecord.branch === 'string'
    && currentRecord.branch.trim().length > 0;
  if (branchNewlyRecorded) { delete sourceRecord.branch; delete currentRecord.branch; }
  if (stableJson(sourceRecord) !== stableJson(currentRecord)) {
    add(identityCode, currentPath, 'fields other than status, completedAt, and (where tolerated) a newly recorded branch changed');
  }
}

const ARCHIVE_MOVE_IDENTITY_OPTIONS = {
  sourceStatuses: ['in_progress', 'review'],
  checkCurrentStatus: false,        // see note — already enforced by validateBookkeepingTaskDirectory
  checkSourceCompletedAtNull: false, // matches today: source-side completedAt was never checked here either
  checkCompletedAt: false,          // see note
  tolerateBranchNewlyRecorded: true,
  sourceCode: 'completion_source_lifecycle_invalid',
  identityCode: 'completion_archive_identity_changed',
};
// Call site: validateTaskLifecycleIdentity(source, archived, `${mapping.sourceDir}/task.json`, `${mapping.archiveDir}/task.json`, add, ARCHIVE_MOVE_IDENTITY_OPTIONS)
// — sourcePath and currentPath are genuinely different paths here, matching :1547 (source-status finding
// reported at the active path) and :1573 (identity finding reported at the archive path) exactly.

const IN_PLACE_IDENTITY_OPTIONS = {
  sourceStatuses: ['in_progress', 'review'],
  checkCurrentStatus: true,
  currentStatuses: ['in_progress', 'review'],
  requireStatusEqual: true,          // Decision 4
  checkSourceCompletedAtNull: true,  // fixes a round-2 finding — see note
  checkCompletedAt: true,
  currentCompletedAtRule: 'null',
  tolerateBranchNewlyRecorded: false, // Decision 4
  sourceCode: 'completion_source_lifecycle_invalid',
  identityCode: 'completion_task_identity_changed',
};
// Call site: validateTaskLifecycleIdentity(source, current, `${taskDir}/task.json`, `${taskDir}/task.json`, add, IN_PLACE_IDENTITY_OPTIONS)
// — sourcePath === currentPath here (same file, same path, two different refs), unlike the archive-move caller.
```

**Fixes a round-2 finding: the signature now takes `sourcePath`/`currentPath`
separately**, not one shared `path`. The original archive-move code reports
the source-status finding at the *active* task's path (`:1547`,
`${mapping.sourceDir}/task.json`) but the identity-changed finding at the
*archived* path (`:1573`, `${mapping.archiveDir}/task.json`) — a single
shared parameter cannot reproduce that split. For the in-place caller both
paths are the same string (the file never moves), so this only matters for
the archive-move caller, but the function has to support both callers
correctly.

**Fixes a second round-2 finding: `checkSourceCompletedAtNull`.** The
previous draft checked `current.completedAt === null` but never checked
`source.completedAt`, then stripped `completedAt` from both records before
the field-identity diff — so a source record with a stray non-null
`completedAt` (nothing currently validates a historical ref's record shape
the way `validateBookkeepingTaskDirectory` validates live content) that got
"corrected" to `null` by head would silently pass. For the in-place shape,
Decision 4's "byte-identical, no repair tolerance" stance applies here too:
`source.completedAt` must already be `null`, not just `current.completedAt`.

**Note on `checkCurrentStatus`/`checkCompletedAt` (found during round-2
self-verification, after the round-1 fix above but before implementation —
no code was written yet, so this is a design correction, not a regression):**
for the archive-move caller, `current` is the archived record, and both
`current.status === 'completed'` and `current.completedAt` non-empty are
**already independently enforced** before this helper ever runs —
`validateBookkeepingTaskDirectory(mapping.archiveDir, {archived: true, ...})`
itself raises `task_lifecycle_incomplete` when `record.status !== 'completed'`
(`:747`), and `validateTrellisBookkeepingMetadata` raises
`task_metadata_invalid` when a `completed` record's `completedAt` is
empty or the record isn't under `archive/` (`:2649-2656`). A first cut of
this parameterization (checking `current.status`/`current.completedAt`
unconditionally, just with different expected values per caller) would have
made the archive-move caller ALSO emit `completion_source_lifecycle_invalid`
for a malformed archived record — a code the original, unrefactored logic at
`:1547-1574` never emits, since it only checks `source.status` and the
field-identity diff. That extra code wouldn't cause a false failure (a
correctly-archived record still passes trivially), but it would change the
exact reason-code set on any existing fixture that pins a malformed-archive
case, breaking the "byte-identical" claim step 1's gate depends on.
`checkCurrentStatus`/`checkCompletedAt` are `false` for
`ARCHIVE_MOVE_IDENTITY_OPTIONS` specifically so the archive-move caller
reproduces `:1547-1574` exactly (source-status check + field-identity diff,
nothing else); they're `true` for `IN_PLACE_IDENTITY_OPTIONS` because there
*is* no other check anywhere in the file that a non-archived task's own
status is specifically `in_progress`/`review` (as opposed to `planning`) —
the closest existing check, `ACTIVE_TRELLIS_TASK_STATUSES` (`:50`, includes
`planning`), only enforces "`completedAt` is null while status is any active
one," not which active status.

The archive-move path is refactored to call this with `ARCHIVE_MOVE_IDENTITY_OPTIONS`
— **behavior-preserving**, verified by AC7 (the option values reproduce
exactly what `:1547-1574` already checks today, with no added reason codes).
The in-place shape calls it with `IN_PLACE_IDENTITY_OPTIONS`.

### New/changed reason codes (Change A)

| Code | Site | Meaning |
|------|------|---------|
| `completion_archive_move_missing` | existing, message text only | Neither an archive move nor a coherent single-task in-place touch was found. |
| `completion_task_scope_invalid` | existing, reused | A task-entry path falls outside the one detected active task directory, or is a delete/rename. |
| `completion_source_lifecycle_invalid` | existing, reused | Status invariant violated for whichever shape applies (see options tables above). |
| `completion_task_identity_changed` | **new** | Fields other than status/completedAt changed on the in-place shape (no branch exception — Decision 4). |

## Change B — new recovery subtype (**mechanism replaced — was blocking defects C-2, C-3, C-4, C-6, C-7**)

### Why the first draft's mechanism doesn't work

The archive case's anchor mechanism (`validateCompletionSuccessorRecovery`,
unchanged, `:1154-1258`) proves an isolated two-commit window
(`baseOid`..`bookkeepingHeadOid`) is a *complete, self-contained* finalization
bundle, then separately proves nothing bookkeeping-shaped happens between
that window and head. This works because **the successor range's existing
scope rule already forbids any further `.trellis/tasks|workspace` change**,
which means by the time the isolated window is re-validated, its content is
guaranteed identical to head's live content — so `validateBookkeepingTaskDirectory`
and the journal loaders reading the *live* filesystem
(`review-preflight.mjs:691`, `:2954`, `:1740` — all live `readdirSync`/`lstatSync`
reads, not git-at-ref) coincidentally produce the historically-correct
answer.

This task's whole premise is that the active task's own directory **may be
touched again** inside the successor range (that's the PR #292 shape: a
task-touch + journal pair, then later a separate journal correction). Once
that's allowed, the "isolated window equals live content" equivalence breaks:
proving an early window in isolation via the same live-reading functions
would silently substitute *later* content for the window's own state,
producing false results in either direction. Trying to preserve a two-commit
adjacency shape (task-touch commit immediately followed by its journal
commit, mirroring `isAdjacentJournalCommit`/`isAdjacentArchiveCommit`) doesn't
fix this and adds a second problem: PR #292's own commits show the task-touch
(`0c73cb0f`) and its journal (`1592aab5`) as two *separate* commits, and
`git rev-list --first-parent --reverse` order means "nearest matching pair to
head" is not the same thing as "the pair AC3's two-touch fixture expects as
the anchor" — the first draft's pseudocode picked the wrong one.

### The fix: validate one unified range, not an isolated anchor plus a separately-tolerant successor

Drop the "prove an isolated anchor, then separately evaluate a successor
range" structure entirely. Find one bounded range,
`historicalBase..headOid`, and validate it as a single unit using genuinely
sound reads at both ends: `historicalBase` via git (a real historical ref —
every read on that side goes through `loadBookkeepingJsonAtRef`/
`bookkeepingChangedEntries`, which already read git objects, not the
filesystem), and `headOid` via the live, currently-checked-out worktree
(genuinely current — this function is only reachable from the top-level,
non-historical call, which has already asserted `HEAD` matches `headOid`).
No intermediate point is ever treated as "historical" while actually being
read live.

`attemptActiveTaskAnchorRecovery(headOid)`:

1. **Discover the active task** — `discoverActiveTrellisTaskDirectory()`:
   `readdirSync('.trellis/tasks', {withFileTypes:true})`, excluding
   `archive`, for each `\d{2}-\d{2}-[^/]+` directory load `task.json` via
   `loadTrellisTaskMetadataFile`. **Any candidate that fails to load
   (`unreadable`/`unsafe`/`oversized` per `:2954`) counts as ambiguity** —
   fixes C-7: a malformed sibling record must not be silently treated as
   "not a candidate," since that could hide a genuine second `in_progress`
   task. Keep candidates whose record loads and has `status` in
   `{in_progress, review}`. Exactly one → proceed. Zero, more than one, or
   any load failure → `{status: 'invalid', findings: [{reasonCode:
   'completion_successor_active_task_ambiguous', ...}]}`.
2. **Find `historicalBase`** (**materially revised — was round-2 blocking
   finding #1, the most serious of that round**). A task's own directory is
   also touched by `task.py create` (writes `status: 'planning'`,
   `.trellis/scripts/common/task_store.py:310-315`) and `task.py start`
   (flips `planning → in_progress`, `.trellis/scripts/task.py:111-131`) —
   both are ordinary commits that touch `${taskDir}/task.json` and are
   therefore indistinguishable from an in-place bookkeeping touch by a plain
   path-prefix test alone. The previous version of this step took the
   *oldest* path-touching commit unconditionally, which — for any task
   created and started within the search window, i.e. the ordinary case for
   a small or new task — would very likely select the creation or start
   commit as the range's starting point. Its own parent state is either
   nonexistent (before creation) or `status: 'planning'` (before start),
   neither of which satisfies `IN_PLACE_IDENTITY_OPTIONS`'s
   `sourceStatuses: ['in_progress', 'review']`, so the whole recovery would
   fail on the single most common real-world shape.

   Fixed by requiring the candidate's *parent* state to already be a
   qualifying task, not just requiring the candidate to touch the directory:
   reuse the bounded `commits` array the outer
   `validateCompletionSuccessorRecovery` already fetched (`git rev-list
   --first-parent --max-count=<bound+1> headOid`, unchanged; `commits.length`
   is at most `bound + 1`). Walk indices `i` from `commits.length - 2` down
   to `0` (never past `commits.length - 2` — `commits[commits.length]` is out
   of bounds, and there is no commit further back within the fetched window
   to serve as a parent). For each `i` where
   `bookkeepingChangedEntries(commits[i+1], commits[i])` touches
   `${taskDir}/`: probe `loadBookkeepingJsonAtRef(commits[i+1], `${taskDir}/task.json`,
   () => {})` (a no-op `add` — this is a shape probe, not a validation step;
   the same silent-probe pattern the archive case already uses for
   `isAdjacentJournalCommit`/`isAdjacentArchiveCommit`, `:1180`, `:1190`). If
   the probed record loads and its `status` is in `{in_progress, review}`,
   this candidate **qualifies**: `historicalBase = commits[i+1]`. Take the
   **first (i.e., oldest) qualifying candidate found in this descending
   walk** — a touch whose own parent isn't yet a qualifying task (creation,
   start, or a touch whose parent record fails to load) is skipped, and the
   walk continues toward more recent commits. This correctly lands on
   whatever commit comes right after `task.py start` (or after an even
   earlier qualifying touch, if one exists within the window) as the range's
   starting point, and still finds the true oldest of multiple later touches
   for a PR #292-shaped fixture (AC3), since the search only skips
   candidates that fail to qualify, not candidates in general.

   Bound handling: if `commits.length > MAX_BOOKKEEPING_ANCHOR_SEARCH_COMMITS`
   (the fetch hit its count cap) **and** the oldest qualifying candidate is
   at the very edge (`i = commits.length - 2`), report
   `completion_successor_history_oversized` instead of treating that edge
   match as confidently resolved — the window cannot distinguish "this is
   really where the task's bookkeeping starts" from "the task's history
   continues past what was fetched." No qualifying candidate found at all
   within the bound (including the case where every touch's parent is
   `planning` or missing, all the way to the edge) →
   `completion_successor_active_task_anchor_missing`.

   The full lifecycle/identity rigor (`completedAt`, branch, field identity —
   step 5 below) is deliberately **not** part of this qualification probe;
   the probe's only job is picking a well-defined starting point. Step 5
   re-reads `historicalBase`'s record authoritatively (with real `add`
   reporting) and is where an actual defect at the starting point surfaces as
   a finding — implementations may reuse the probed record directly for step
   5's `source` value rather than reading it twice, as a performance detail,
   not a correctness requirement.

   Per Decision 2 (single bounded segment): once `historicalBase` is chosen
   this way, the design commits to it. If step 5, 6, or 7 below fails for any
   reason, the result is invalid — there is no second attempt against a
   different or newer candidate.
3. **Bound and linearity** — `range = git rev-list --first-parent --reverse historicalBase..headOid`
   (same call shape `evaluateCompletionSuccessorRange` already uses,
   `:1325`), bounded by `MAX_BOOKKEEPING_SUCCESSOR_COMMITS`. For every commit
   in `range`, `git rev-list --parents -n1 <oid>` must show exactly one
   parent → else `completion_successor_history_non_linear`. Because this
   walks *every* commit between `historicalBase` and `headOid` — including
   whichever commit is the "oldest task touch" found in step 2 — a merge
   commit anywhere in that span is caught here automatically; there is no
   separate "is the anchor itself a merge" case to special-case (fixes C-6).
4. **Scope check — two orthogonal properties, not one** (**revised — was
   round-2 blocking finding #5**: the previous draft specified per-commit
   inspection without saying how the existing 500-path cap applies to it,
   leaving it ambiguous between "500 per commit" — which could admit far more
   than 500 total changed paths across a range — and "500 net unique" —
   which is what the existing archive-successor mechanism does today
   (`bookkeepingChangedEntries(anchorOid, headOid)` deduplicated into a
   `Set`, `:1375-1394`)). Both checks below run; neither replaces the other:
   - **Aggregate path count (reuses the existing pattern exactly):**
     `bookkeepingChangedEntries(historicalBase, headOid, add)` once, dedup
     into a `Set` across old/new paths exactly as `:1385-1387` already does,
     and apply the existing `MAX_BOOKKEEPING_CHANGED_PATHS` cap to that set's
     size → `completion_successor_scope_oversized` if exceeded. This is a
     property of the *whole range* and is unaffected by per-commit
     structure.
   - **Per-commit category check (new, for the mutate-then-revert case):**
     for each commit in `range`, `bookkeepingChangedEntries(parent, commit)`;
     every changed path in *that commit's own diff* must be one of: under
     `${taskDir}/`; under `.trellis/workspace/` matching `journal-\d+\.md` or
     `index.md` (the same path shape `isAdjacentJournalCommit` uses,
     `:1269`); or, failing both of those, **not** under `.trellis/tasks/`,
     `.trellis/workspace/`, `.trellis/.runtime/`, or
     `.sd-ai-command-pack/finish-work` (ordinary code — reusing exactly the
     forbidden-prefix list `evaluateCompletionSuccessorRange` already checks,
     `:1838`, not a fresh "not under `.trellis/`" rule that would need its own
     carve-out for the non-`.trellis` `.sd-ai-command-pack/finish-work`
     prefix). Anything matching one of those four forbidden prefixes without
     also matching the first two allowed categories →
     `completion_successor_scope_invalid`. This check
     inspects *every* path in *every* commit — a single commit touching both
     an allowed and a forbidden path still flags the forbidden one; doing
     this per commit rather than as one net diff means a forbidden mutation
     later reverted by another commit in the same range is still caught,
     since the net diff would show no change at that path at all.
5. **Lifecycle/identity net effect** — `validateTaskLifecycleIdentity(loadBookkeepingJsonAtRef(historicalBase, `${taskDir}/task.json`, add), <live task.json for taskDir>, ..., IN_PLACE_IDENTITY_OPTIONS)`.
   Sound: `historicalBase` side is a genuine git-at-ref read; the "live" side
   is genuinely current head, not a stand-in for some earlier point.
6. **Journal presence** — `validateBookkeepingJournalBundle(bookkeepingChangedEntries(historicalBase, headOid, add), historicalBase, headOid, add)`,
   the existing, **unmodified** function, called once across the whole range.
   Sound for the same reason as step 5: both endpoints are what they claim to
   be. This one call naturally covers both a single touch+journal pair (AC2)
   and multiple touches with multiple journal entries across the range
   (AC3) — `validateBookkeepingJournalBundle` already returns *every* newly
   completed session it finds relative to its `baseOid` argument, and every
   session found this way has already had its own commit-scope validated in
   step 4.
7. **Full content sweep, once, live** — `validateBookkeepingTaskDirectory(taskDir, {archived: false, addAdvisory: options.addAdvisory ?? null, deltaPaths: null})` at the live/current state. This is the same per-file check (whitespace, PRD non-empty, topology, etc.) Change A's direct path already runs; it runs here exactly once, against genuinely current content, not once per historical checkpoint.

If all of the above pass: `evidence.completionSubtype = 'active-task-review-successor'`,
`evidence.taskDirectories = [taskDir]`, `evidence.completionAnchor = {source: 'active-task-range', taskDir, historicalBase, headOid}`.

### Control flow (**revised a third time — see "Round 3" note below**)

```
function validateCompletionSuccessorRecovery(evidence, headOid, add) {
  const archiveResult = attemptArchiveAnchorRecovery(headOid);       // existing logic, local findings (mechanical extraction, no behavior change) — now also returns shapedTailCount
  if (archiveResult.status === 'valid') {
    commitArchiveAnchorEvidence(evidence, archiveResult);            // exactly today's evidence assignment
    return;
  }
  const activeTaskResult = attemptActiveTaskAnchorRecovery(headOid); // new, see above
  if (activeTaskResult.status === 'valid') {
    commitActiveTaskAnchorEvidence(evidence, activeTaskResult);
    return;
  }
  // Both failed. Prefer the archive search's OWN diagnosis when it found a
  // real shaped archive/journal tail that failed downstream (a specific,
  // actionable reason already exists there — see Round 3 note). Only defer
  // to the active-task diagnosis when the archive search found no shaped
  // tail at all anywhere in the bounded history.
  const findingsToCommit = (archiveResult.shapedTailCount > 0 || archiveResult.status === 'indeterminate')
    ? archiveResult.findings
    : activeTaskResult.findings;
  for (const f of findingsToCommit) add(f.reasonCode, f.path, f.message, f.disposition);
}
```

**Round 3 note (found empirically during implementation, not by either
review round):** the previous version of this control flow always preferred
`activeTaskResult`'s findings on double failure ("there is never a reason to
prefer `archiveResult`'s findings instead"). That reasoning was wrong.
`attemptArchiveAnchorRecovery`'s existing, unmodified body
(`:1214-1269` in the current tree) tracks `shapedTailCount` — how many
archive+journal-shaped tails it found anywhere in bounded history — and every
one of its *existing* test fixtures archives the one task under test, so at
head there are **zero** active task directories in every such fixture.
`attemptActiveTaskAnchorRecovery`'s discovery step correctly classifies zero
active tasks as `completion_successor_active_task_ambiguous` — but
unconditionally preferring that finding meant every existing archive-failure
fixture's specific, correct diagnosis (`completion_successor_history_non_linear`,
`_scope_invalid`, `_history_oversized`, `_anchor_invalid`, etc.) got silently
replaced by a generic, actively misleading "ambiguous active task" message,
even though the archive search had found a real shaped tail and diagnosed a
real, specific problem with it. This was caught by running the existing
`tests/test_bookkeeping_validator.py` completion-successor suite against a
literal implementation of the previous control-flow text (9 of 11 existing
tests failed) — a check neither review round performed, since both were
read-only/text-based per this document's earlier revision notes.

`shapedTailCount > 0` is *most* of the right discriminator, but not quite
all of it: implementing exactly that (verified empirically — the full
`completion_successor_*` suite run against a literal implementation) found
one further gap, caught by two existing tests injecting a raw Git failure.
The search loop's two `bookkeepingChangedEntries(...) === null` checks
(`:1220-1239` in the current tree) fire *before* the shape check that would
increment `shapedTailCount`, adding a `completion_successor_history_unavailable`
finding with disposition `'indeterminate'` and returning immediately — so
`shapedTailCount` stays `0` even though the real problem is "Git itself
failed mid-search," not "no shaped tail exists." That is a materially
different, more urgent situation than the genuine "found nothing" case, and
should not be replaced by an active-task diagnostic either. Fixed by also
checking `archiveResult.status === 'indeterminate'` — mirroring the
three-way `valid`/`invalid`/`indeterminate` status convention
`evaluateCompletionSuccessorRange` (`:1418`) already uses elsewhere in this
same file, where `indeterminate` specifically means "a finding exists but
its disposition doesn't definitively invalidate the result," distinct from a
hard `invalid`.

The final, verified condition —
`archiveResult.shapedTailCount > 0 || archiveResult.status === 'indeterminate'`
— defers to the active-task diagnosis in exactly one case: `shapedTailCount`
is `0` **and** the archive search's status is a definitive `invalid` (no
Git errors, genuinely no shaped tail found anywhere in bounded history:
`completion_successor_history_oversized` or `completion_successor_anchor_missing`).
That is precisely AC5/AC6's genuinely-unarchived case. One existing test,
`test_completion_successor_requires_a_canonical_anchor` (a one-commit repo
with no task and no archive ever created), pinned the *old*
`completion_successor_anchor_missing` behavior for exactly this case — its
assertion should be updated to expect `completion_successor_active_task_ambiguous`
as an intentional improvement (a more precise diagnostic for a repo with no
task at all), not chased as a regression. Archive-anchor search still runs
first and is tried exactly as today — zero behavior change when a task
actually gets archived (AC7, now the actually-verified claim, backed by the
full existing suite passing, not just the stated intent); the new subtype is
attempted only as a fallback (R3).

### Non-goal, restated precisely (Decision 2 / addresses C-5's PRD-wording sibling, Codex #8)

"Single bounded segment" means: **one discovery pass, one `historicalBase`
search, one range validated as a unit** — never a second, independent search
for an older anchor if this one's checks fail. It does **not** mean "at most
one touch to the active task's own directory is tolerated" — step 2
deliberately finds the *oldest* qualifying touch within the bound precisely
so the one range can contain more than one. The bound on how much this can
recover is the same `MAX_BOOKKEEPING_SUCCESSOR_COMMITS` /
`MAX_BOOKKEEPING_CHANGED_PATHS` caps already governing the range, not a
separate "how many touches" counter — identical in kind to how the archive
case has always been bounded by commit/path count rather than by "how many
semantic events." A task with bookkeeping history older than the bound simply
isn't reachable by this search (`completion_successor_active_task_anchor_missing`
or the oversized codes), the same way an ancient archive is unreachable to
the existing mechanism today.

### What changed and why (map from review findings to fixes)

| Finding | Fix |
|---|---|
| Host BLOCKING #1 / Codex #1 (C-1): shared helper breaks archive-move | Parameterized `validateTaskLifecycleIdentity`; archive-move keeps its own option set, unchanged behavior. |
| Codex #2: PRD/design contradiction on status/branch transitions | Decision 4 — tightened design to PRD's original "unchanged" wording; removed the transition tolerance. |
| Codex #3 (C-3): historical proof silently read live state | Removed the isolated-anchor-proof step entirely; every read is now either genuinely at `historicalBase` (git) or genuinely at live `headOid`. |
| Host BLOCKING #2 / Codex #4 (C-2): anchor proof needs a journal that's in a separate commit; nearest ≠ oldest | Single unified range from the *oldest* qualifying touch, journal checked once across the whole range via the existing function — no isolated single-commit proof, no adjacency requirement. |
| Codex #5: unreachable ambiguity diagnostic | Removed the `attempted` conditional; active-task findings are always preferred on failure. |
| Codex #6 (C-6): anchor-is-a-merge-commit | Subsumed by the per-commit linearity walk over the whole range (step 3), which checks every commit including whichever one is "oldest touching." |
| Codex #7 (C-4): net-diff scope check misses mutate-then-revert | Scope check is per-commit (step 4), not a `historicalBase`..`headOid` tree diff. |
| Codex #8 (C-5 sibling): "single bounded segment" ambiguous in prose | Restated precisely above; PRD Decision 2 rewritten to match. |
| Codex #9: no linearity guarantee for the anchor itself / direct path | Direct path (Change A) has never had a linearity requirement, consistent with every other direct-mode path (`validatePlanningBundle`, the existing archive-move direct path) — none of them walk commit-by-commit, all of them accept whatever `--base` the caller supplies. Not a new gap. The anchor-is-a-merge half of this concern is fixed as above (C-6). |
| Codex #10 (C-7): unreadable candidate during discovery | Any load failure counts as ambiguity (step 1). |
| Host non-blocking: untracked files invisible to the dirty-worktree guard | Accepted as a pre-existing characteristic of the outer dirty check (`:1055-1064`, tracked-paths only); discovery inherits it. Out of scope to change the dirty-worktree guard itself here. |
| Self-found before round-2 review (C-8): naive parameterization would add a reason code the archive-move path never emits today | `checkCurrentStatus`/`checkCompletedAt` made conditionally-skippable per caller; archive-move caller skips both (already independently enforced by `validateBookkeepingTaskDirectory`'s `task_lifecycle_incomplete` and `validateTrellisBookkeepingMetadata`'s `task_metadata_invalid`), reproducing `:1547-1574` exactly. |
| Self-found before round-2 review (C-9): oldest-touch search could index `commits[commits.length]`, out of bounds, at the search-window edge | Search walk explicitly bounded to `i <= commits.length - 2`. Superseded/absorbed by round-2 finding #1's fix below (the oversized-at-the-edge logic now applies to the *qualifying*-candidate walk, not the naive one). |
| Round-2 Codex finding #1 (most serious): "oldest touch" usually selects `task.py create`/`task.py start` itself, whose parent state can't satisfy `sourceStatuses` | Search now requires the candidate's *parent* record to already have status in `{in_progress, review}` (a no-op-`add` probe read, mirroring `isAdjacentJournalCommit`'s shape-probe style) before accepting it; creation/start commits are skipped, not treated as usable starting points. |
| Round-2 Codex finding #2: shared helper had one `path` param but the archive-move caller needs two different paths (source-status finding at the active path, identity finding at the archive path) | Signature changed to `(source, current, sourcePath, currentPath, add, options)`; archive-move call site passes the two real, different paths; in-place call site passes the same path twice (same file, same path, two refs). |
| Round-2 Codex finding #3: helper never checked `source.completedAt`, only `current.completedAt`, before stripping the field for the identity diff | Added `checkSourceCompletedAtNull` (true for in-place, matching Decision 4's byte-identical stance; false for archive-move, matching today's code, which never checked the source side either). |
| Round-2 Codex finding #4: oversized-boundary check didn't account for the qualification requirement (finding #1's fix) | Reapplied the same edge-of-window logic to the *qualifying* candidate, not the raw oldest touch — see step 2's "Bound handling" paragraph. |
| Round-2 Codex finding #5: per-commit scope check left the existing 500-path cap's application ambiguous | Split into two explicit, orthogonal checks: an aggregate net-unique-path count (reuses the existing pattern exactly) and a per-commit category check (the new mutate-then-revert protection) — neither substitutes for the other. |
| Round-2 non-blocking: `validateInPlaceTaskTouch` never set `evidence.taskDirectories` | Added as the final step of that function, mirroring the archive-move path's own assignment. |
| Round-2 non-blocking: `implement.md` allowed renaming reason codes "without a design revisit," contradicting `prd.md`'s "finalized in design.md" | `implement.md`'s reviewer-checklist wording tightened to require any renamed code to be reflected back into `design.md` in the same change, not silently drift. |
| Round 3, first pass (found empirically during implementation, by actually running the existing test suite — not by either review round): unconditionally preferring `activeTaskResult`'s findings on double failure silently replaced every existing archive-failure fixture's specific, correct reason code with a generic `completion_successor_active_task_ambiguous`, since every such fixture archives its task and therefore has zero active tasks at head | Findings choice conditioned on `archiveResult.shapedTailCount > 0` — fixed 8 of 9 initially-failing fixtures. |
| Round 3, second pass (found empirically implementing the first pass's fix — 2 of 11 fixtures still failed): `shapedTailCount` stays `0` when Git itself fails mid-search (two early-loop error returns, before the shape check that would increment it), which is a materially different, more urgent situation than "genuinely found nothing," and got wrongly routed to the active-task diagnosis too | Condition extended to `shapedTailCount > 0 \|\| status === 'indeterminate'`, reusing the three-way status convention `evaluateCompletionSuccessorRange` already establishes elsewhere in the file. The one remaining fixture (`test_completion_successor_requires_a_canonical_anchor`) pins genuinely-superseded behavior and needs its assertion updated, not the design changed further. |

### New/changed reason codes (Change B)

| Code | Meaning |
|------|---------|
| `completion_successor_active_task_ambiguous` | **New.** Zero, more than one, or any unreadable/malformed `in_progress`/`review` task candidate at head; the new subtype cannot attempt a search. |
| `completion_successor_active_task_anchor_missing` | **New.** Exactly one active task identified, but no commit touching its directory exists within the bounded search window. |
| `completion_successor_history_non_linear` / `_history_oversized` / `_scope_invalid` / `_scope_oversized` | Existing, reused by the per-commit range walk. |
| `completion_source_lifecycle_invalid` / `completion_task_identity_changed` | Reused from Change A (step 5 calls the same helper with the same options). |
| `evidence.completionSubtype = 'active-task-review-successor'` | **New** subtype value, sibling to `'post-archive-review-successor'`. Not load-bearing outside this repo (eligibility does not whitelist subtype strings). |

## Change C — operator documentation

`.agents/skills/sd-finish-work/SKILL.md` (+ template mirror), Step 7's
completion-mode paragraph gains a second paragraph describing
`active-task-review-successor`: when it applies (exactly one `in_progress`/
`review` task, no archive this session), what it proves (the active task's
own bookkeeping since the oldest reachable prior touch, plus everything else
in that range, forms one valid, scope-bounded unit), and its limits (one
bounded range; a merge commit anywhere in it, or bookkeeping history older
than the search bound, still fails and is not a bug). Cross-reference: this
is a sibling to `journal-only-recovery`'s existing documented recovery route,
not a replacement for it — a task still in the `planning` phase (pre-`task.py
start`) continues to use `--mode planning`.

## Consumer matrix

| Surface | Change |
|---------|--------|
| `templates/scripts/sd-ai-command-pack-review-preflight.mjs` + root mirror | Changes A and B |
| `templates/.agents/skills/sd-finish-work/SKILL.md` + root mirror | Change C |
| `scripts/sd-ai-command-pack-pr-eligibility.py` | No change (confirmed: `evidence.completionSubtype` is a free-form string, `require_string(..., limit=100)`, no enum — `pr-eligibility.py:~250-260`) |
| `.github/workflows/tests.yml`, `.github/scripts/bookkeeping_ci_scope.py` | None |
| `scripts/sd-ai-command-pack-housekeeping.sh` | None |
| `pre-archive` lane, `task.py` wrappers | None (`final-bundle` still derives task directories from the delta only; no new CLI flag) |

## Test plan (maps to `prd.md` acceptance criteria)

In `tests/test_bookkeeping_validator.py` unless noted. All fixtures are
synthetic (PR #292's actual branch will not validate after this fix, because
of its unrelated merge commit and the separately-tracked T-35 gap — see
prd.md's Empirical case study).

1. **In-place touch validates directly (AC1).** Task status `in_progress`,
   one non-`.trellis` work commit, one `prd.md` checkbox commit + journal
   session, linear, no merges. `--mode completion --base <work-commit> --head <head>`
   → `status: valid`, `reasonCodes: ["completion_bundle_valid"]`,
   `evidence.completionSubtype` absent/null.
2. **Same fixture recovers (AC2).** `--base == --head` → `status: valid`,
   `evidence.completionSubtype: "active-task-review-successor"`,
   `historicalBase` resolves to the commit before the `prd.md` touch.
3. **Two touches inside one range (AC3, corrected).** Fixture: touch1 +
   journal1, then (after some ordinary commits) touch2 + journal2, all still
   `in_progress`, still linear. Recovery succeeds; `historicalBase` resolves
   to before touch1 (the *oldest qualifying* touch, per step 2 — touch1's own
   parent state must already be a valid `in_progress`/`review` record) — not
   touch2 — and `validateBookkeepingJournalBundle` reports both sessions.
3b. **Task created and started inside the search window (AC11, the most
   serious round-2 finding).** Fixture: `task.py create` (status
   `planning`) then `task.py start` (→ `in_progress`) then the normal
   touch+journal pair, all within the bounded window. Recovery must still
   succeed, with `historicalBase` resolving to the commit right after
   `task.py start` (or later) — never to the creation or start commit
   itself. Without step 2's qualification probe, this is exactly the fixture
   that would fail: it is the *ordinary* shape for any task young enough that
   its whole lifecycle fits in the search window, not an edge case.
4. **Change A rejects a status/branch transition (Decision 4, new).**
   Fixture where the in-place shape's `--base`/`--head` records differ in
   `status` (`in_progress`→`review`) or newly record `branch` → blocks with
   `completion_source_lifecycle_invalid` / `completion_task_identity_changed`,
   proving Decision 4 is enforced, not just documented.
5. **Safety preserved (AC4).** Fixtures, each still blocking: (a) range
   touches a second, unrelated active task directory →
   `completion_successor_scope_invalid`; (b) range touches
   `.trellis/tasks/archive/**` → same code; (c) a merge commit inside the
   range → `completion_successor_history_non_linear`; (d) **new** — a commit
   mutates a forbidden path (e.g. another task's `task.json`) and a later
   commit in the same range reverts it → still blocks with
   `completion_successor_scope_invalid` (proves the per-commit scope check,
   not a net diff).
6. **Ambiguous active task (AC5).** Fixtures with zero, with two
   `in_progress` tasks, and **new** — with one valid `in_progress` task plus
   one sibling task directory whose `task.json` is corrupt/unparseable — all
   three fail immediately with `completion_successor_active_task_ambiguous`.
7. **No anchor (AC6).** Fixture with exactly one active task but no history
   touching its directory within the bound →
   `completion_successor_active_task_anchor_missing`, not the old
   `completion_successor_history_oversized`/`_non_linear` noise.
8. **Archive-move regression (AC7).** Existing archive-move fixtures
   (identity check, source-lifecycle check, `pre-archive`/`post-archive`
   paths) stay green unmodified — proves `ARCHIVE_MOVE_IDENTITY_OPTIONS`
   reproduces `:1547-1574`'s exact behavior.
9. **`journal-only-recovery` and archive-successor regression (AC7).**
   Existing planning-recovery and archive-anchor fixtures stay green
   unmodified — this task does not touch either function.
10. **Eligibility regression (AC8).** `tests/test_pr_eligibility.py`: a
    receipt with `evidence.completionSubtype: "active-task-review-successor"`
    passes `validate_finish_work_receipt` with no code change, proving R4.
11. **Mirror parity (AC9).** `make sync` then `git diff --exit-code` on both
    template/root pairs — already enforced by `make check`.

## Risks

- **In-place shape becomes an archive bypass.** Mitigated by
  `validateTaskLifecycleIdentity`'s field-identity check plus Decision 4's
  strict equality requirement — a bundle cannot change status, branch, or any
  other field. Reaching `completed` still requires an actual directory move.
- **Range becomes unaudited admission.** Mitigated by the per-commit scope
  check (step 4) rather than a net diff, and by requiring every allowed
  workspace path to be a `journal-N.md`/`index.md` file re-validated through
  the existing, unmodified journal-bundle content audit (step 6).
- **Anchor search regresses the archive case.** Mitigated by trying the
  existing archive-anchor search first, unchanged, and only falling back on
  failure (R3) — AC7 pins zero behavior change when an archive exists.
- **Historical-read unsoundness reintroduced by a future edit.** The design
  now depends on a specific invariant: every read against `historicalBase` or
  earlier must go through a ref-aware helper (`loadBookkeepingJsonAtRef`,
  `bookkeepingChangedEntries`), and every read treated as "live" must
  actually be live head, never an intermediate historical point passed to a
  filesystem-reading function like `validateBookkeepingTaskDirectory`. This
  is why step 7 runs that function exactly once, at true head, and nowhere
  else in Change B.

## Rollback

Single revert of the one commit restores today's validator and docs.
Receipts are ephemeral (deleted after housekeeping consumes them, per
SKILL.md Step 7), so no stored artifact depends on the new bundle shape or
subtype surviving a rollback.

# Design: scope the finalization bundle validator to the change delta

Line references are to the current tree (commit `126f437e`); the PRD cites an
older revision and some of its line numbers have drifted. Function identity is
unchanged.

## Shape of the change

Three coordinated changes, one commit:

- **A. Delta-scoped per-file findings with an advisory channel.** Per-file
  content-quality findings in files the bundle did not change move from
  `findings` (blocking) to a new top-level `advisories` array (reported,
  non-blocking).
- **B. Widened `journal-only-recovery` cited-commit scope — repo paths only.**
  The recovery subtype keeps its journal-plus-index bundle shape but stops
  requiring every cited work commit to be a task-only planning edit: ordinary
  repo paths become citable. This is the repo-maintenance route.
  `.trellis/workspace/**` cited commits stay rejected — root cause 3
  (journal-repair and dirty-parent lifecycle-repair sessions) is descoped to
  the follow-up task `07-30-recover-bookkeeping-repair-sessions` per the PRD's
  scope decision.
- **C. Operator documentation.** `sd-finish-work/SKILL.md` documents the base
  semantics (`--base` = last work commit, not the merge-base with the default
  branch), the maintenance-branch flow, and the advisory channel.

No new `--mode` value. No schema version bump. `sd-ai-command-pack-pr-eligibility.py`
needs no code change (argued below, and proven by an end-to-end test).

## Reason-code classification

Every code emitted by the `validateBookkeepingTaskDirectory` family
(`scripts/sd-ai-command-pack-review-preflight.mjs:644-818`), grouped per the
PRD's taxonomy. "Delta-scoped" means: blocking when the finding's `path` is in
the base..head delta, advisory otherwise.

### Group 1 — per-file, delta-scoped

| Code | Site | File it names |
|------|------|---------------|
| `task_artifact_invalid` | `:680` | `task.json` |
| `task_prd_invalid` | `:683` | `prd.md` |
| `task_json_invalid` | `:691` | `task.json` |
| `task_metadata_invalid` | `:695` | `task.json` |
| `task_lifecycle_incomplete` | `:704` | `task.json` (archived dir) |
| `task_prd_empty` | `:708` | `prd.md` |
| `task_context_invalid` | `:734` | `implement.jsonl` / `check.jsonl` |
| `task_context_seed` / `task_context_malformed` / `task_context_reference` | `:745` | `implement.jsonl` / `check.jsonl` |
| `bookkeeping_whitespace_invalid` | `:810-818` when called from this family | the scanned file |

Notes:

- `task_lifecycle_incomplete` is absent from the PRD's list but is per-file and
  belongs here. In practice an archive move always places `task.json` in the
  delta, so it remains blocking on every real completion bundle.
- When `task.json` is unreadable or unparseable (`task_artifact_invalid`,
  `task_json_invalid`) the function still returns `null`, so downstream
  lifecycle checks that need the record are skipped — exactly the current
  behavior for a failed load. Delta-scoping changes only whether the load
  failure blocks, not what runs after it. The planning-mode baseline check
  (`validatePlanningBundle` reading `task.json` at the base ref) is
  independent of the head worktree file and still runs.
- Whitespace findings from `validateBookkeepingJournalBundle` (journal and
  index files) are unaffected: those files are in the delta by definition of
  that validator's scope.
- `validateBookkeepingDiffWhitespace` (`:1052`) is already diff-scoped and is
  untouched.
- **Scope boundary:** delta-scoping applies to the emission sites *inside* the
  `validateBookkeepingTaskDirectory` family only. Some of the same reason codes
  are also emitted elsewhere — `loadRecoveredPlanningTaskRecord` (`:1632`,
  `:1641`) and the at-ref loaders used by the planning baseline and recovery
  lanes (`planning_recovery_commit_*` variants). Those sites keep raw `add`:
  their anchors are by construction part of the validated change (a bundle
  entry or a cited commit's path), so "untouched file" cannot arise there.

### Group 2 — directory-level, unchanged (always blocking)

`task_layout_invalid`, `task_path_outside_repository`
(`:649-662`), `task_directory_unreadable` (`:667`), `task_directory_unsafe`
(`:671`). Raised before any file is read, with an early `return`; there is no
file to test against the delta. Unchanged.

### Group 3 — completion-ready only, unchanged

`task_lifecycle_not_completion_ready` (`:698`), `task_branch_invalid` (`:701`),
and the `validateBookkeepingAcceptanceReadiness` findings (`:712`). All are
gated on `completionReady`, which only the `pre-archive` command sets
(`:566-570`). They never fire in `final-bundle` at all, in either mode.
Unchanged.

### Group 4 — relationship (topology), governed by the anchor file

`validateBookkeepingTopology` (`:751-808`) emits `task_topology_unverifiable`,
`task_topology_missing`, `task_topology_ambiguous`,
`task_topology_not_reciprocal`, `task_topology_base_invalid`,
`task_topology_prd_missing_child`.

**Rule: the end being validated governs.** A topology finding raised while
validating directory X blocks when X's own `task.json` (or `prd.md` for
`task_topology_prd_missing_child`) is in the delta, and is advisory otherwise.
This is symmetric without special cases: if the bundle changes task B and
breaks reciprocity with untouched neighbor A, the validation of B's directory
raises the finding — B's anchor is in the delta, blocking. Validation of A's
directory (if A is dragged in at all) — advisory. The end that changed is the
end that gates.

**Routing must key on the anchor, not the finding's reported `path`.** Two
`task_topology_unverifiable` sites report the *linked neighbor's* path
(`:770`, `:776` — unreadable/invalid linked `task.json`), so path-based
routing would demote a changed task's broken link to advisory whenever the
neighbor is untouched. Topology emission sites therefore pass an explicit
anchor (the validated directory's own file) to the routing wrapper; the
finding's reported `path` stays what it is today.

### Outside the family, unchanged

Bundle-level codes keep their current blocking behavior:
`bundle_scope_invalid` (`:1040` — the PRD explicitly keeps it blocking),
`bundle_head_not_checked_out`, `bundle_worktree_dirty`,
`bundle_unsupported_file_mode`, the `journal_*` family, the `completion_*`
family, and the `planning_*` family except where change B narrows the recovery
commit-scope rule.

## Change A — mechanism

### Result document

`runBookkeepingValidator` (`:536`) gains a top-level `advisories: []` sibling
of `findings`. Entry shape `{reasonCode, path, message}` — no `disposition`
(advisories are definitionally non-blocking). Deterministic ordering (emission
order, same as `findings`); same path/message truncation as `add` (`:549-554`,
300/500 chars).

**Cap: a separate `MAX_BOOKKEEPING_ADVISORIES = 25`, not the findings cap of
100.** The reason is a hard consumer limit: eligibility refuses any receipt
file over `MAX_INPUT_BYTES = 64 KiB` before parsing
(`sd-ai-command-pack-pr-eligibility.py:27`, `:305`), and receipts are
pretty-printed (`:430`). A worst-case advisory entry is ~0.9 KB pretty-printed
(300-char path + 500-char message + code + indentation), so 100 entries alone
could contribute ~90 KB and push a *valid* receipt past the limit — recreating
the exact "valid result, unobtainable receipt" failure this task exists to
fix. 25 entries bound the **advisory contribution** at ~23 KB. That is a bound
on what this change adds, not a whole-document guarantee: `changedPaths` may
already carry up to 500 entries of 300 chars (`:28`, `:1019-1021`), which can
exceed 64 KiB on its own today, advisories or not — a pre-existing bound gap
this task neither introduces nor fixes. The boundary regression test pins the
realistic worst case this change creates (advisory-saturated receipt over a
normal-sized bundle stays consumable). The cap drops deterministically
(emission order), so revalidation reproduces the same truncated list.

**Truncation is visible, not silent.** The PRD's signal-preservation
requirement (`prd.md:188-194`) forbids silently dropping untouched-file
findings, and a bare cap would silently drop advisory 26+. When any entry is
dropped over the cap, the validator records the count as
`evidence.advisoriesDropped` (additive evidence key, schema-1-safe for the
same reasons as `advisories` itself, reproduced deterministically on
revalidation so the `:412` equality holds), and `printBookkeepingResult`
prints it alongside the advisory count. The individual dropped entries are
gone, but the drop is reported.

**Schema-1-additive, not a version bump.** `BOOKKEEPING_SCHEMA_VERSION` stays
1. Verified consumer tolerance:

- `sd-ai-command-pack-pr-eligibility.py:219-302` validates named keys and never
  rejects unknown keys; `:250` (`findings == []`), `:246`
  (`reasonCodes == [f"{mode}_bundle_valid"]`), and `:224` (schema 1) all hold
  for a valid receipt with advisories. The exact-equality recomputation check
  (`:412`, `dict(observed) != dict(receipt)`) holds because the recomputing
  validator is the same build and reproduces the same advisories
  deterministically.
- The CI bookkeeping fast lane (`.github/workflows/tests.yml:236-244`) asserts
  a jq subset (`schemaVersion`, `status`, `mode`, `headOid`, `reasonCodes`) and
  ignores unknown keys.
- `sd-ai-command-pack-housekeeping.sh:1297-1319` validates only file shape.

Cross-version receipt reuse (new-validator receipt judged by an old
eligibility, or vice versa) would fail the `:412` equality — that is already
true today for any validator change and is out of contract: receipts are
ephemeral, produced and consumed at the same head by scripts shipped in the
same commit.

### Routing

`validateBookkeepingTaskDirectory` and its two per-file callees
(`validateBookkeepingTaskContexts`, `validateBookkeepingTopology`,
plus `validateBookkeepingTextWhitespace` at its family call sites) receive a
routing sink instead of raw `add`. Concretely: `options.deltaPaths` —
`Set<string> | null`.

- `deltaPaths === null` → legacy behavior, everything blocking. The
  `pre-archive` command passes null: it is an operator gate that validates a
  directory about to be archived, where whole-directory strictness is the
  point.
- `deltaPaths` set → a small wrapper `addScoped(reasonCode, path, message,
  anchorPath = path)` used **only at group 1 and group 4 emission sites**
  routes to `add(...)` when `deltaPaths.has(anchorPath)` and to the advisory
  sink otherwise. Group 1 sites use the default (`anchorPath === path`);
  topology sites pass the validated directory's own file as `anchorPath`
  because two of their emission sites report the neighbor's path (§Group 4).
  Group 2 sites keep calling `add` directly (group 3 sites are unreachable in
  `final-bundle`).

Callers:

- `validatePlanningBundle` (`:1529`, called at `:1060` and per-commit at
  `:1921`) passes the bundle's changed-path set. The per-commit
  (`lifecycleOnly`) path already bypasses `validateBookkeepingTaskDirectory`,
  so this affects only the head-directory validation at `:1559`.
- `validateCompletionBundle` (`:1437`, archive-directory validation at
  `:1485`) passes the set too. An archive move puts every file of the moved
  directory in the delta, so behavior is unchanged in practice; passing it
  keeps the rule uniform rather than special-casing completion.
- `pre-archive` (`:566`) passes null.

`printBookkeepingResult` (`:629`) prints `ADVISORY <code> <path>: <message>`
lines after the PASS/FAIL block and includes the advisory count — plus the
`advisoriesDropped` count when present — in the summary line, so the human
lane sees the debt signal the receipt carries.

## Change B — mechanism

`validateJournalOnlyPlanningRecovery` (`:1787`) currently enforces, per cited
commit: no D/R/C entries (`:1890-1898`), every path inside an active task
directory (`:1900-1908`), a regular blob at head of each path (`:1910-1916`),
then per-commit planning-lifecycle validation (`:1920-1929`). This rejects
maintenance sessions (cited commits touch `scripts/`, `templates/`, docs,
tests — PR #274/#284), which this change admits. It also rejects
journal-repair and dirty-parent lifecycle-repair sessions (root cause 3,
session 251) — those stay rejected here and belong to the follow-up task
`07-30-recover-bookkeeping-repair-sessions`.

New per-cited-commit rule — partition each commit's changed paths:

| Category | Paths | Rule |
|----------|-------|------|
| Archive | `.trellis/tasks/archive/**` | Blocking `planning_recovery_commit_scope_invalid` — archived history stays immutable. |
| Active task | `.trellis/tasks/<dd-dd-name>/**` | Exactly today's rules: no D/R/C, regular blob at the commit, per-commit planning-lifecycle validation via `validatePlanningBundle(..., {lifecycleOnly: true})`. **Pass only the task-path entries into that per-commit call** — feeding it repo-path entries would raise `planning_task_layout_invalid` (`:1539`) and undo the widening. |
| Malformed task namespace | any other `.trellis/tasks/**` | Blocking `planning_recovery_commit_scope_invalid`. The reserved namespace must not fall through to the repo category: today `.trellis/tasks/not-a-task/file` is rejected by the task-directory regex, and the partition preserves that. |
| Workspace | `.trellis/workspace/**` | Blocking `planning_recovery_commit_scope_invalid` — unchanged from today. Admitting workspace paths without a per-commit content audit is unsound (an initial PR push is classified full CI, not `bookkeeping`, so cited workspace mutations can reach a merge with no increment validation anywhere); the audit design is the follow-up task's core problem. |
| Repo | everything else | Allowed, including deletes and renames — ordinary repo work. No per-path validation. |

This partition is the **exact allowlist the PRD requires** (`prd.md:195-197`):
it is total — every path a cited commit can touch falls in exactly one
category — and the finalization range itself must still carry the
journal-plus-index pair (the bundle-scope rule below is unchanged, so
`journal_session_missing` still fires on a range without it).

Why admitting repo paths without per-path validation is sound: the
finalization bundle this route can merge is still the journal-plus-index pair
and nothing else, so recovery never *carries* repo content — it only records
that published commits exist. Cited commits must be ancestors of the receipt
base and reachable from head (`:1771-1783`, `:1844`); ancestors of a pushed,
reviewed, CI-green PR head are ordinary code commits inside the PR's review
scope, and re-reviewing code content is not this validator's mandate — its
mandate is the bookkeeping surfaces under `.trellis/`, which the other four
partition rows keep guarding. What the route does **not** prove is citation
*completeness* — a session may cite fewer commits than the branch carries.
That is not new: today's task-only recovery cannot prove completeness either,
and the journal is a record, not the merge gate.

The D/R/C rejection (`:1890-1898`) therefore narrows from all entries to
task-path entries (workspace and malformed-task entries are rejected outright;
repo entries are free).

`planning_recovery_task_change_missing` has three emission sites: no completed
session (`:1799`), commit list over the bound (`:1825`), and empty
`recoveredTaskDirs` at the end (`:1934`). The first two stay as they are — a
sessionless or unbounded recovery still proves nothing. Only the final site is
reformulated: fire when the cited commits collectively change **zero paths in
an allowed category** (active-task or repo) — a session that provably did
nothing. A maintenance session with repo-path commits and an empty
`evidence.taskDirectories` is valid.

Unchanged and load-bearing (the non-bypass argument):

- The finalization bundle itself is still journal-plus-index only
  (`planning_recovery_bundle_scope_invalid`, `:1804-1815`), so this route can
  never carry code into a merge — it only records.
- The session must be newly completed with real content
  (`journal_content_missing`, `:1753-1766`), cite ≥1 commit, and every cited
  commit must resolve, be reachable from head (`:1771-1783`), be an ancestor of
  the captured base (`:1844`), be linear (`:1866-1873`), and the commit count
  stays bounded (`:1817`).
- `mode` stays `planning`; `evidence.planningSubtype` stays
  `'journal-only-recovery'` (the bundle shape it names is unchanged). No new
  evidence fields. Eligibility (`:259-279`) type-checks the subtype string
  without a name whitelist, so nothing there moves.
- The CI fast lane classifier (`.github/scripts/bookkeeping_ci_scope.py:238`)
  already routes journal-only push increments to `planning`; the widened
  commit scope is what lets a maintenance increment pass there
  (journal-repair increments stay blocked — descoped to the follow-up task).
  Classifier and workflow are unchanged.

## Change C — operator documentation

`templates/.agents/skills/sd-finish-work/SKILL.md` (and mirror), in the receipt
step around `:150`:

- `--base` is the last work commit — the parent of the first finalization
  (archive/journal) commit — not the merge-base with the default branch. On a
  branch whose only commits are bookkeeping the two coincide. (PR #286 evidence:
  base=origin/main returned `bundle_scope_invalid` for every work path; base=
  last work commit validated.)
- Maintenance-branch flow: work commits carry the repo changes; finalization
  records a journal session citing them; the receipt is
  `--mode planning` over the journal-plus-index delta.
- **Rewrite, not just extend, the recovery paragraph around `:157`**: it
  currently states the helper proves "task-only work commits" and "verifies
  task-only scope" — false after change B. The passage must describe the
  widened cited-commit scope (active-task and ordinary repo paths; archive,
  malformed task-namespace, and `.trellis/workspace/**` paths still
  forbidden).
- A valid receipt may carry non-empty `advisories`; they are informational and
  do not block eligibility. Fixing the debt they name belongs to a follow-up
  session, not the current finalization.

The mode list at `:150` (`--mode <completion|planning>`) and the schema-1
requirements at `:88`/`:155` are unchanged.

## Consumer matrix

| Surface | Change |
|---------|--------|
| `templates/scripts/sd-ai-command-pack-review-preflight.mjs` + root mirror | Changes A and B |
| `templates/.agents/skills/sd-finish-work/SKILL.md` + root mirror | Change C |
| `scripts/sd-ai-command-pack-pr-eligibility.py` | No code change; end-to-end regression test added |
| `.github/workflows/tests.yml`, `.github/scripts/bookkeeping_ci_scope.py` | None |
| `scripts/sd-ai-command-pack-housekeeping.sh` | None |
| `pre-archive` lane, `task.py` wrappers | None (`deltaPaths: null`) |

## Test plan (maps to PRD acceptance criteria)

In `tests/test_bookkeeping_validator.py` unless noted. Tests 1, 2, 4, 5, and
10 assert the *new* behavior and must fail against the current validator
(asserted during implementation by running them before the fix). Tests 3, 6,
7, and 8 are preservation regressions — they pin behavior the current
validator already has and are expected green both before and after the
change.

1. **Clean-sibling bundle validates.** Fixture task directory with a stale
   `_example` scaffold row in `check.jsonl` and an empty `task.json`
   description; bundle delta touches only `prd.md`. Assert `status: valid`,
   `reasonCodes: ["planning_bundle_valid"]`, and both defects present in
   `advisories` (`task_context_seed`, `task_metadata_invalid`). **Companion
   test in `tests/test_pr_eligibility.py` consumes this receipt** — the one
   with non-empty `advisories` — and asserts `validate_finish_work_receipt`
   accepts it. This, not the maintenance receipt, is the AC 4 end-to-end
   proof: the recovery route never runs the whole-directory scan, so a
   maintenance receipt's `advisories` is empty by construction. (AC 1, AC 4.)
2. **Every group-1 producer delta-scopes.** Same shape asserting one advisory
   code from each producer: `task_prd_empty` (directory whose `prd.md` is
   empty but untouched — delta touches `check.jsonl`),
   `task_context_malformed`, and `bookkeeping_whitespace_invalid` from an
   untouched file. (AC 2.)
3. **Delta-contained defect still blocks.** Same fixtures with the defective
   file in the delta → `status: invalid` with the blocking code. (AC 3.)
4. **Topology anchor rule.** Three cases: (a) delta touches the task's
   `task.json`, which carries a non-reciprocal parent link → blocking;
   (b) delta touches only a sibling file (`prd.md`) of the same directory,
   anchor `task.json` untouched → the same finding routes to `advisories`;
   (c) delta touches the task's `task.json`, which links to an untouched
   neighbor whose `task.json` is unparseable → `task_topology_unverifiable`
   **blocks** even though the finding reports the neighbor's path (`:770`) —
   this pins the anchor-keyed routing. (A directory absent from the delta is
   not validated at all — no finding either way.)
5. **Maintenance receipt end to end.** Fixture branch: work commit touching
   `scripts/tool.sh` (including a delete/rename to cover repo-path D/R),
   journal session citing it, finalization delta = journal+index. Assert
   `status: valid`, `planning_bundle_valid`, subtype `journal-only-recovery`,
   `advisories: []`. Companion test in `tests/test_pr_eligibility.py`: this
   receipt passes `validate_finish_work_receipt` (the advisories-bearing
   eligibility case lives in test 1). (AC 5, AC 6.)
6. **Workspace cited commit still blocks.** Cited commit touching
   `.trellis/workspace/` → `status: invalid` with
   `planning_recovery_commit_scope_invalid`. Pins the descope boundary
   (root cause 3 stays rejected until
   `07-30-recover-bookkeeping-repair-sessions` lands); green before and after
   this change.
7. **Recovery still blocks what it must.** Cited commit mutating
   `.trellis/tasks/archive/**` → invalid; cited commit deleting a task
   artifact → invalid; cited commit with an invalid planning lifecycle →
   invalid (existing tests `:1745`, `:1865` extended or paralleled). New
   negative for the partition boundary: cited commit touching a **malformed
   task-namespace path** (`.trellis/tasks/not-a-task/file`) → invalid — the
   reserved namespace must not fall through to the repo category.
8. **`bundle_scope_invalid` regression.** Finalization delta containing
   `.trellis/audit/ledger.md` → invalid. (AC 7.)
9. **PR #273 replay** (AC 8) is a manual implementation-time verification, not
   a CI test: it needs this repository's real history. Run the fixed validator
   from the working tree against a temporary worktree checked out at
   `7fde6218` via `--repo` (`:512` — the worktree keeps the head-checkout
   guard satisfied while the validator build stays fixed). Expected: the 25
   whole-directory findings drop to `advisories`; `findings` retains the 2
   `bundle_scope_invalid` and the `journal_session_missing` family;
   `status: invalid`. Output recorded in the session journal.

10. **Advisory-cap receipt stays consumable.** Fixture bundle engineered to
    produce more than `MAX_BOOKKEEPING_ADVISORIES` advisory-eligible defects
    with long paths/messages. Assert the emitted `advisories` length is
    exactly 25, `evidence.advisoriesDropped` equals the engineered overflow
    count (truncation reported, not silent), the serialized pretty-printed
    receipt is under 64 KiB, and eligibility's `load_request` accepts the
    file.

Mirror parity (AC 9): `make sync` then `git diff --exit-code` on both pairs —
already enforced by `make check`.

## Risks

- **A blocking code silently demoted.** Routing is opt-in per emission site;
  groups 2-4 sites keep raw `add` (group 4 through the anchor rule). Test 3
  asserts the blocking path per producer.
- **Recovery widening becomes a bypass.** The bundle stays journal-only; cited
  commits stay published, linear, bounded ancestors; workspace and malformed
  task-namespace paths stay rejected. Tests 6 and 7 pin the blocked shapes.
- **Eligibility drift.** No eligibility code change; test 5's companion proves
  acceptance, and the `:412` equality check keeps receipt and recomputation
  locked.

## Rollback

Single revert of the one commit restores the previous validator and docs;
receipts are ephemeral so no stored artifact depends on the new shape.

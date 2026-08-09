# Bookkeeping Validator Notes

> Non-obvious gotchas and conventions specific to
> `scripts/sd-ai-command-pack-review-preflight.mjs`, learned from
> `.trellis/tasks/archive/2026-08/07-31-completion-recovery-no-archive-anchor`.

---

## Gotcha: top-level `const` placement is not cosmetic

Adopted 2026-08-01. This file's CLI dispatch (`if (isMainModule()) { ... }`)
runs as literal top-level module code — it executes synchronously during
import, interleaved with every other top-level statement in file order, not
inside a function called later. A `const` declared *after* that dispatch
block is in its temporal dead zone at the exact moment the dispatch chain
calls into a function that references it, throwing
`ReferenceError: Cannot access '<name>' before initialization` on every real
invocation. `node --check` does not catch this — it only parses, it does not
execute, so a broken file can look clean right up until someone runs it.

This is why every top-level constant this file needs at dispatch time
already lives in one block near the top (`MAX_BOOKKEEPING_*`,
`ACTIVE_TRELLIS_TASK_STATUSES`, etc.). Any new top-level `const`/config
object — including one a design doc's illustrative pseudocode shows "near
its callers" for readability — must go in that existing top block instead.
Verify by actually running the code path (a targeted test, not just
`node --check`) before considering the change done.

- Bad: adding `const ARCHIVE_MOVE_IDENTITY_OPTIONS = {...}` physically next
  to the function that uses it, if that function is reachable from the
  top-level dispatch block above the declaration.
- Good: adding it to the existing top-of-file constants block, then
  confirming with a real test run (not just `node --check`) that it resolves.

Re-confirmed 2026-08-09 (task `08-08-shell-coverage-kcov-flake`): the same
TDZ applies to module-level `let` slots, not just `const`. A
`let lastBookkeepingGitFailure = null;` placed near its readers (after the
dispatch block) threw the identical `ReferenceError` on every CLI run while
`node --check` stayed green; the fix was moving the slot (and the constants
it feeds) above `if (isMainModule())`.

## Design principle: a "historical proof" via a live-reading function is only sound for immutable content

Adopted 2026-08-01. The completion-mode auto-recovery mechanisms
(`post-archive-review-successor`, `active-task-review-successor`) need to
prove things about a historical point in git history. Several core
functions this file already has — `validateBookkeepingTaskDirectory`,
`loadTrellisTaskMetadataFile`, `safeJournalFiles`,
`loadBoundedTrellisTaskArtifact` — read the **live, currently-checked-out
worktree** via `readdirSync`/`lstatSync`, not git objects at a ref. Two
different helpers exist for genuinely historical reads:
`loadBookkeepingJsonAtRef` and `bookkeepingChangedEntries` (both backed by
`git cat-file`/`git diff`, not the filesystem).

The archive-successor mechanism gets away with calling the live-reading
functions inside what's conceptually a "historical" proof only because the
content in question — an already-archived task directory — is provably
immutable from that point forward (nothing can legally mutate
`.trellis/tasks/archive/**` again; other checks in this same family enforce
that). Live and historical reads coincide *because nothing changed in
between*, not because the mechanism is generically safe to reuse.

**Before reusing this pattern for any new recovery mechanism, ask: is the
content I'm "historically" proving guaranteed static from that point to
true head?** If the answer is no — as it is for an *active* task directory
that a design deliberately allows to be touched again later — do not call a
live-reading function against anything but genuinely-live true head. Prove
the historical side entirely through `loadBookkeepingJsonAtRef` /
`bookkeepingChangedEntries`, and run whatever full-content sweep is needed
exactly once, at live head, not once per historical checkpoint. This was
caught by adversarial review before any code was written for
`active-task-review-successor` (see that task's `design.md`, Change B, "Why
the first draft's mechanism doesn't work") — it is easy to reach for the
existing pattern by analogy and miss that its safety depends on a property
the new case doesn't have.

## Contract: root-task base_branch rule and its default-branch resolver

Added 2026-08-08 (task 08-06-task-create-base-branch-seed, v0.64.30).

`validateTrellisRootTaskBaseBranch(record, defaultBranchName)` — exported,
pure. Population: changed active task records (the same delta-scoped
`changedTaskFiles` walk as the other task-metadata rules — at-rest records
are never inspected) whose `parent` is null OR absent (the structural
validator permits an undefined `parent`, so a literal-null check would leak
roots) and whose `base_branch` has a non-empty trim. Passes when
`base_branch.trim()` equals the default branch name, or when
`meta.base_branch_exemption` is a string with non-empty trim (written via
`task.py set-meta <dir> base_branch_exemption "<reason>"`; whitespace-only
and non-string values do not exempt). Trim tolerance on `base_branch` is
deliberate: `set-base-branch` persists its argument raw.

Default-branch resolution (`trellisRootDefaultBranchName()`):

1. `SD_AI_COMMAND_PACK_DEFAULT_BRANCH` env, trimmed non-empty — a statement
   of the default branch NAME, not a diff base. Do NOT feed the rule from
   `defaultReviewBaseRef()` or the `..._BASE_REF` variables: those answer
   "what do I diff against" and may legitimately be a stacked-PR feature
   base, the current branch's upstream, an alphabetically-first remote ref,
   or (in CI) an exact SHA.
2. `origin/HEAD` symbolic ref, `origin/` stripped.
3. Neither → the rule SKIPS for the run (unverifiable is not failable;
   remoteless local checkouts are supported).

The CI `Validate event head` step exports
`SD_AI_COMMAND_PACK_DEFAULT_BRANCH` from
`github.event.repository.default_branch` because the pinned-SHA checkout
never establishes `origin/HEAD` (the bookkeeping final-bundle step exports
it too, same rationale). The event-head step runs the preflight on every
head in every mode, against the pull request's own base on `pull_request`
events and `github.event.before` on `push` events, with a fail-closed
guard on an unverifiable base — closing the former full-mode preflight
gap (task `08-07-ci-preflight-full-mode-gap`). The local pre-publication
gate in `sd-create-pr` remains the first enforcement point; CI is now the
backstop in both modes.

The emptiness predicate divergence pinned alongside this rule: JS
`String.trim()` strips U+FEFF and keeps U+0085; Python `str.strip()` does
the opposite. Tests in `tests/test_review_preflight.py` pin both halves; if
either runtime changes, the pins disagree visibly. An upstream create-time
refusal (Trellis fork task `08-08-create-empty-metadata-rejection`) is
expected to flip these pins into an equality assertion at uptake.

## Contract: git-failure diagnostics enrichment (`lastBookkeepingGitFailure`)

Adopted 2026-08-09 (task `08-08-shell-coverage-kcov-flake`, the kcov-lane
flake). Every git-caused `*_unavailable` finding must name the failed git
command, its exit status, and bounded stderr — a bare "Git could not
inspect" receipt is undiagnosable when the failure only reproduces on a CI
runner.

### Signatures

- `let lastBookkeepingGitFailure: {commandArgs, status, stderr} | null` —
  module slot, declared in the top-of-file block (see TDZ gotcha above).
- `boundedGitFailureStderr(stderr) -> string` — first stderr line, capped
  at `GIT_FAILURE_STDERR_LIMIT` (200) chars with `...`, or
  `'no stderr output'`.
- `gitFailureSuffix(commandArgs, status, stderr) -> string` — appended to
  direct-status failure sites: `` ` (git <args> exited <status>: <stderr>)` ``.
- `describeGitFailure(prefix) -> string` — for slot-readers: returns
  `prefix` unchanged when the slot is null, else prefix + suffix.

### Slot lifecycle (stale-safety, non-negotiable)

- Cleared at `bookkeepingChangedEntries` **entry**: a status-0
  malformed-output null return must not inherit an older invocation's
  failure text.
- Reset in `runBookkeepingValidator`'s module-state block: two validator
  runs in one process must not leak failure detail across receipts.
- Set only on nonzero `git diff --raw` status, immediately before the
  `bundle_diff_unavailable` finding.

### Contract invariants

- Receipt schema unchanged: same 9 keys (`schemaVersion` 1), same reason
  codes, same dispositions. Enrichment is append-only text inside existing
  `findings[].message` strings.
- No retries, no semantic change: a git failure still yields the same
  reason code and `indeterminate`/`invalid` status it did before.
- Site taxonomy: slot-readers (silent-probe `bookkeepingChangedEntries`
  callers) use `describeGitFailure`; direct-status sites (`rev-list`,
  subject probe, whitespace, parents probe) use `gitFailureSuffix`; the
  real-`add` diff callers are covered by the enriched
  `bundle_diff_unavailable` itself.

### Tests (assertion points)

`tests/test_bookkeeping_validator.py`: PATH-prefix git stubs inject
failures per-site (pair-selective on oids to hit the archive-delta site,
not the journal-delta site that diffs first); assertions cover message
content ("exited N" + injected stderr), stderr bounding (200-char cap,
first line only), stale-slot regression across two in-process runs (with
a positive control on the first receipt), and failure-receipt shape
(`assert_failure_receipt_shape`). Fixture-side: `run_git`/`git_output`
failures append a repo-state context block (HEAD bytes, loose/packed ref
state, lock files) — capture lives in the assertion wrappers only, never
`_run_git_process`, whose direct callers expect nonzero exits.

## Related

- [Code Reuse Thinking Guide](../guides/code-reuse-thinking-guide.md) — this
  file's primitives (`bookkeepingChangedEntries`, `loadBookkeepingJsonAtRef`,
  the `validateTaskLifecycleIdentity` shared helper) are reused across many
  call sites; search before adding a new one.
- [guides/index.md](../guides/index.md), "When Verifying AI Cross-Review
  Results" — the review-methodology lesson from the same task (static
  review vs. running the real test suite) lives there, since it applies
  beyond this one file.

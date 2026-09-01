# Design — reduce review tooling process spawns

## Scope boundary

Four independent optimizations in three files. No behavior change anywhere:
every requirement is "same answer, fewer processes". Nothing here is coupled —
R1, R2, R3, and R4 can land in any order or separately.

## Confirmed measurements

### 1. R1's line numbers do not match either function

Measured against `scripts/sd-ai-command-pack-review-preflight.mjs` (4,547 lines):

| symbol | PRD says | actually |
|---|---|---|
| `defaultReviewBaseRef()` definition | `~:2040` | **`:3816`** |
| `defaultReviewBaseRef()` call sites | `~:485/:598/:935/:1281` | **`:3843`, `:3851`, `:3865`** (three) |
| `currentChangedPaths()` definition | — | **`:4053`** |
| `currentChangedPaths()` call sites | — | **`:2094`, `:2207`, `:2279`, `:2877`, `:3277`** (five) |

None of the four PRD call-site numbers lands on either function. The counts are
also different from what "memoize two functions" implies: eight call sites, not
four.

### 2. A-024 is already fixed, and it is the pattern R1 should copy

`.trellis/audit/ledger.md:432` — `status: fixed`, "fixed in 0.13.1 via
`.trellis/tasks/07-15-p3-polish-batch` — preflight guard-file list + readText
memoized". On disk:

```
review-preflight.mjs:16     let documentationGuardFilesCache;
review-preflight.mjs:180    documentationGuardFilesCache = undefined;   (in runReviewPreflight)
review-preflight.mjs:3715   if (documentationGuardFilesCache !== undefined) return ...
```

So R1's "fold in the A-024 documentation-list recomputation while there" is
already done. The requirement survives as a **template**, not as work: the two
new caches should look exactly like this one. (A-024's own evidence lines —
`:759-777`, `:327`, `:352`, `:1200` — no longer resolve; the file has roughly
sextupled since that row was written.)

### 3. There are two entry points, and only one clears the caches

```
review-preflight.mjs:174   export function runReviewPreflight(options = {})
review-preflight.mjs:180     documentationGuardFilesCache = undefined;
review-preflight.mjs:181     readTextCache.clear();

review-preflight.mjs:536   export function runBookkeepingValidator(options = {})
review-preflight.mjs:539     readTextCache.clear();
```

`readTextCache` is reset in both. `documentationGuardFilesCache` is reset only
in the first — harmless, because the bookkeeping validator never reads docs.

**That exemption does not extend to the R1 caches.** `runBookkeepingValidator`
operates on explicit base/head oids and can run in the same process as a
preflight, so a base ref or changed-path list memoized during
`runReviewPreflight` would leak into it. R1 says "reset in
`runReviewPreflight()`" — that is half the reset the caches need.

### 4. R2's ~1500 forks are command substitutions, not greps

`scripts/sd-ai-command-pack-review-scope.sh` (303 lines). `normalize_repo_path`
(`:66-69`) is pure shell — `${1#./}` and `${path//\\//}`, no external command —
but every caller invokes it through `$( )`, which forks a subshell:

```
:88   is_trellis_runtime_path
:118  is_pack_target_path
:132  is_copied_review_scope_path
:143  is_repository_map_scope_path
:156  is_trellis_journal_scope_path
```

The classification loop (`:259-275`) calls up to four of these per changed file.
378 files × ~4 = **~1512 forks** — which is where the Goal's "~1500" comes from.

The actual membership test, `grep -Fxq -- "$path" "$TARGETS_FILE"` (`:127`),
fires **at most once per file**, and less than that because the `case` at
`:121-124` short-circuits three paths before reaching it. So it is ≤378
processes, not ~1500.

**Consequence:** R2's first clause (one associative array or one `grep -Fxf`
pass) removes ≤378 processes. R2's second clause (drop the per-file command
substitutions) removes ~1500. The Goal's sentence — "answers 378 membership
tests with one process instead of ~1500 forks" — merges two different counts,
and the smaller one is the one it names.

### 5. "full-check pays review-scope twice" is true — but not as two full-check stages

```
full-check.sh:1034   run_sd_ai_command_pack_scope_check   -> :457-465, runs the script
full-check.sh:977    runs review-preflight.mjs
review-preflight.mjs:3396   spawnSync('bash', [script])    with SD_AI_COMMAND_PACK_SCOPE_CHECK='advisory'
```

`full-check.sh:1035` is `run_sd_ai_command_pack_pr_body_scope_check` (`:874`) —
a **different** script (`pr-body-scope.py`), not a second review-scope pass.

The second payment is nested inside preflight, in advisory mode. It is the same
script, so one fix covers both, but AC2's "in both full-check passes" should
read "both invocations" — and the nested one is skipped entirely when
`SD_AI_COMMAND_PACK_SCOPE_CHECK` is falsey (`:3388-3390`), which any measurement
harness must control for.

### 6. R3 is correctly derived, and it already corrects the ledger

Loop A — `:1283`, bounded by `MAX_BOOKKEEPING_SUCCESSOR_COMMITS = 50` (`:33`):
two spawns per commit, `rev-list --parents -n 1` then `log -1 --format=%s`.
Contiguous range. One `rev-list --format` replaces it, exactly as the PRD says.

Loop B — `:1819` over `uniqueCommits`, bounded by
`MAX_BOOKKEEPING_RECOVERY_COMMITS = 100` (`:29`, enforced at `:1793`): four
spawn classes per commit —

```
merge-base --is-ancestor            ancestry
rev-list --parents -n 1             parents
bookkeepingChangedEntries(...)      changed entries
bookkeepingRegularPathsAtCommit()   ls-tree, already chunked at :1914-1918
```

The ledger's own `fix:` field (`ledger.md:1873`) says "Replace the loops with a
single `git rev-list --format='%H %P %s'`". **That is wrong for loop B** —
`rev-list --format` supplies neither ancestry nor changed entries, and the
commits are not necessarily one contiguous range. The PRD already caught this
and split R3 into two shapes. Keep that split.

`bookkeepingRegularPathsAtCommit` (`:1914-1918`) is the in-file batched idiom to
imitate, including its `chunkBookkeepingGitPathspecs` bound
(`MAX_BOOKKEEPING_GIT_PATHSPEC_BYTES = 8 * 1024`, `:32`).

### 7. R4 names one call site that does not exist, and misses that there are two base refs

```
full-check.sh:192   full_check_base_ref()        -> configured_review_base_ref(SD_..._BASE_REF) || default_review_base_ref
full-check.sh:199   full_check_gito_base_ref()   -> configured_review_base_ref(SD_..._GITO_BASE_REF) || full_check_base_ref  (:203)
```

Call sites of `full_check_base_ref`: **`:203`, `:208`, `:410`, `:609`, `:909`**.
`:408` — cited by both the PRD and `ledger.md:1919` — contains no base-ref call;
the hit is `:410`. `:439` calls `full_check_gito_base_ref`, the *other*
function.

Two consequences the requirement does not carry:

- **"Export it readonly" is singular; the script has two refs.** The gito ref
  is separately configurable and falls back to the plain one. One cached value
  silently collapses that distinction and changes what `gito review --vs` is
  given.
- **`configured_review_base_ref` runs first.** Caching must sit *below* the env
  check or above it consistently, and the cache variable must not be named like
  the input env vars — `:609` already does
  `SD_AI_COMMAND_PACK_FULL_CHECK_RELEASE_BASE_REF="${SD_...:-$release_base_ref}"`,
  so that namespace is live.

Cost per uncached resolution, `shell-lib.sh:253` `default_review_base_ref`:
`symbolic-ref`, then `rev-parse --abbrev-ref @{upstream}`, then
`for-each-ref | grep`, with a `has_ref` (`rev-parse --verify`) after each
candidate — three to six processes per hop.

## The central tension

Every one of these is a pure-performance change with no observable output
delta, which means **the only thing that can go wrong is a correctness
regression introduced by the cache itself**. The two live traps are both about
cache lifetime, not cache logic:

- an R1 memo that survives into `runBookkeepingValidator` (measurement 3), and
- an R4 cache that collapses two distinct base refs into one (measurement 7).

Neither is caught by "identical classification output on a fixture diff" (AC1)
unless the fixture exercises both entry points and both refs.

## Contract

**R1.** Two module-scoped caches beside `documentationGuardFilesCache`,
following its exact shape — `undefined` means unset, so a legitimately empty
result still caches. Reset in **both** `runReviewPreflight` (`:174`) and
`runBookkeepingValidator` (`:536`), next to the existing `readTextCache.clear()`
calls.

**R2.** `normalize_repo_path` writes to a caller-visible variable instead of
stdout, so the five call sites stop using `$( )`. Installed targets load once
into an associative array at first use. Predicates keep their exact names,
argument order, and return codes — `tests/test_review_scope.py` drives the
script end-to-end from nine call sites and is the contract.

**R3.** Loop A: one `git rev-list --format='%H %P %s'` over the range, parsed
once. Loop B: one batch per evidence class over the explicit commit list —
ancestry, metadata, diff/tree — never a single `rev-list`. Every existing
finding code, its `invalid` vs `indeterminate` status, and the per-commit
`continue` short-circuit order must be preserved; batching turns sequential
early-exits into set operations, and a commit that used to `continue` before
reaching the diff must still produce exactly one finding.

**The ancestry batch is `rev-list`, not `merge-base`.** Decided in planning
(2026-07-28); an earlier draft left "`merge-base --is-ancestor` batched, or a
single `rev-list --ancestry-path`" open, and the first of those is not a real
option — `merge-base --is-ancestor` communicates its answer through the process
exit code, so it is one process per pair by construction and cannot be batched at
all. That is exactly the per-commit spawn at `review-preflight.mjs:1819` this
requirement exists to remove.

The commits under test are an arbitrary set, not a contiguous range, so the
batch is a **membership test against one materialized set**:

```
git rev-list <base>..<head>          # one spawn, full hash list
```

Load the output into a `Set`; a commit is in-range exactly when it is a member.
That maps back to per-commit findings directly — the set is keyed by the same
full hashes the loop already holds — and it needs no `--ancestry-path`, whose
first-parent semantics differ from `--is-ancestor` and would change verdicts on
merge commits. If `base` and `head` are not both resolvable the batch cannot run
and every commit is `indeterminate`, which is the existing behavior for an
unresolvable ref and must not silently become `invalid`.

**R4.** Memoize on first call inside `full_check_base_ref` and
`full_check_gito_base_ref` **separately**, below the `configured_review_base_ref`
check. Not `readonly` in `main`: the helpers are callable before `main`'s
assignment and the test suite sources the script more than once, so a
first-call memo is the safe shape and `readonly` is a re-assignment error
waiting to happen.

## Compatibility

No output, exit code, finding code, or JSON field changes in any of the four.
Consumers see identical results; only wall time and process count move.

Both `review-scope.sh` and `full-check.sh` are shipped payload with
`templates/` originals and root mirrors, so R2 and R4 need `make sync` and the
usual version bump, changelog, and candidate restamp. `review-preflight.mjs` is
too (`templates/scripts/sd-ai-command-pack-review-preflight.mjs`).

Independent of `07-28-reduce-review-hashing-and-classifier-cost` (A-101, A-105)
— that task owns hashing and glob-matching cost in different files, shares no
code, and can land in either order. The PRD already records this.

## Rollout and rollback

Four commits, one per requirement, in cheapest-verification order:

1. **R4** — smallest diff, single file, most obvious win.
2. **R1** — two caches copied from an existing in-file pattern.
3. **R2** — one file, but ten end-to-end tests to keep green.
4. **R3** — the only one that restructures control flow; do it last and alone.

Each reverts independently. R3 is the only revert that matters, because it is
the only one where a mistake produces *wrong findings* rather than *slow correct
findings*.

## Risk

1. **R3 loop B collapsed into one `rev-list`.** The ledger's own suggested fix
   says to do this. It cannot work: ancestry and changed entries are not in
   `rev-list --format` output, and the commits are not necessarily contiguous.
   This is the single highest-consequence error available in this task.
2. **R3 reordering finding emission.** The loops `continue` on the first
   failure per commit. Batched, every class is computed for every commit, so a
   commit that previously emitted one finding can emit several unless the
   short-circuit is reconstructed explicitly.
3. **R1 memo leaking into `runBookkeepingValidator`** (measurement 3). Produces
   a wrong base ref in the second entry point, in-process only — invisible to
   any test that runs one entry point per process.
4. **R4 collapsing the two base refs** (measurement 7). Changes what
   `gito review --vs` compares against, silently.
5. **R2 fixing only the grep.** Removes ≤378 processes and leaves ~1500
   subshells, then reports the AC as met (measurement 4).
6. **Measuring R2 without pinning `SD_AI_COMMAND_PACK_SCOPE_CHECK`.** The
   nested preflight invocation returns early when it is falsey
   (`review-preflight.mjs:3388-3390`), so the "twice" in AC2 quietly becomes
   once and the improvement looks half as large.
7. **Chasing A-024.** It is fixed (measurement 2); its evidence lines no longer
   resolve. Time spent re-fixing it is time not spent on R3.

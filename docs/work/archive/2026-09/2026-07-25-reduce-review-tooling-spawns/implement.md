# Implementation — reduce review tooling process spawns

**Four commits, one per requirement, in this order: R4 → R1 → R2 → R3.** Not
the PRD's listing order. R4 is the smallest single-file diff, R1 copies an
existing in-file pattern, R2 has nine end-to-end tests to keep green, and R3 is
the only one that restructures control flow — it goes last and alone.

Nothing here is coupled. Any commit can be dropped without affecting the others.

## Order

### Before anything — establish the baseline

1. **Record a spawn count and a wall time before touching code.** Every
   acceptance criterion here is comparative; without a baseline there is nothing
   to compare to and "measurable spawn reduction" (AC2) cannot be reported
   honestly.

   Pin `SD_AI_COMMAND_PACK_SCOPE_CHECK` to a truthy value while measuring.

   **Gate:** `review-preflight.mjs:3388-3390` returns early when that variable
   is falsey, which silently removes the nested `review-scope.sh` invocation —
   half of AC2's "both passes". A baseline taken with it unset understates the
   before-number and overstates the improvement.

2. **Do not implement A-024. It is fixed.** `.trellis/audit/ledger.md:432` reads
   `status: fixed`, "fixed in 0.13.1 via `.trellis/tasks/07-15-p3-polish-batch`".
   On disk:

   ```
   review-preflight.mjs:16     let documentationGuardFilesCache;
   review-preflight.mjs:180    documentationGuardFilesCache = undefined;
   review-preflight.mjs:3715   if (documentationGuardFilesCache !== undefined) return ...
   ```

   **Gate:** R1's "fold in the A-024 documentation-list recomputation while
   there" is dead work. Read `documentationGuardFiles()` as the **template** for
   step 5 and write no new doc-list code. A-024's cited lines (`:759-777`,
   `:327`, `:352`, `:1200`) no longer resolve — the file is six times longer
   than when that row was written.

### Commit 1 — R4, base-ref discovery in full-check.sh

3. **Ignore the cited call sites; `:408` has none.** Measured:

   ```
   full-check.sh:192   full_check_base_ref()
   full-check.sh:199   full_check_gito_base_ref()      -> falls back at :203
   call sites of full_check_base_ref:   :203  :208  :410  :609  :909
   :439 calls full_check_gito_base_ref, a different function
   ```

   Both the PRD and `ledger.md:1919` name `:408`. The hit is `:410`.

4. **Memoize the two functions separately.** They are not one ref:
   `full_check_base_ref` reads `SD_AI_COMMAND_PACK_FULL_CHECK_BASE_REF`,
   `full_check_gito_base_ref` reads
   `SD_AI_COMMAND_PACK_FULL_CHECK_GITO_BASE_REF` and only then falls back.

   **Gate:** R4 says "resolve it once in `main` and export it readonly",
   singular. One cached value collapses the gito distinction and changes what
   `gito review --vs "$base_ref"` (`:454`) compares against. Two caches, or none.

5. **Memoize on first call inside each function — not `readonly` in `main`.**
   The helpers are reachable before `main` runs its assignment, and the test
   suite sources the script more than once per process; `readonly` re-assignment
   is a hard error. Keep the memo *below* the `configured_review_base_ref`
   check so env precedence is unchanged.

   **Gate:** do not name the cache variable in the
   `SD_AI_COMMAND_PACK_FULL_CHECK_*_BASE_REF` namespace — those are inputs, and
   `:609` already writes `SD_AI_COMMAND_PACK_FULL_CHECK_RELEASE_BASE_REF` from
   one.

   Cost being removed, per resolution
   (`shell-lib.sh:253` `default_review_base_ref`): `symbolic-ref`, then
   `rev-parse --abbrev-ref @{upstream}`, then `for-each-ref | grep`, with a
   `has_ref` `rev-parse --verify` after each candidate.

### Commit 2 — R1, preflight memoization

6. **Use the measured symbols, not the PRD's.**

   ```
   defaultReviewBaseRef()   defined :3816   called :3843 :3851 :3865
   currentChangedPaths()    defined :4053   called :2094 :2207 :2279 :2877 :3277
   ```

   The PRD's `~:2040` and `~:485/:598/:935/:1281` match neither function. Eight
   call sites, not four.

7. Add two module-scoped caches beside `documentationGuardFilesCache` (`:16`),
   using the same `undefined`-means-unset convention so a legitimately empty
   changed-path list still caches.

8. **Reset both caches in *both* entry points.**

   ```
   review-preflight.mjs:174   runReviewPreflight        -> resets at :180-181
   review-preflight.mjs:536   runBookkeepingValidator   -> resets at :539
   ```

   **Gate:** R1 says "reset in `runReviewPreflight()`", which is half the reset
   these caches need. `runBookkeepingValidator` works from explicit base/head
   oids and can run in the same process as a preflight, so a memoized base ref
   or changed-path list leaks straight into it. `documentationGuardFilesCache`
   gets away with a single reset only because the bookkeeping validator never
   reads docs — that exemption does not transfer.

### Commit 3 — R2, review-scope.sh

9. **Fix the command substitutions first; they are the ~1500.**
   `normalize_repo_path` (`:66-69`) is pure shell — `${1#./}` and
   `${path//\\//}`, no external command — but every caller wraps it in `$( )`,
   which forks:

   ```
   :88   is_trellis_runtime_path
   :118  is_pack_target_path
   :132  is_copied_review_scope_path
   :143  is_repository_map_scope_path
   :156  is_trellis_journal_scope_path
   ```

   The loop at `:259-275` reaches up to four per changed file: 378 × 4 ≈ 1512.

   Convert `normalize_repo_path` to assign into a caller-named variable and drop
   the five `$( )` wrappers.

10. Then load `installed-targets.txt` once into an associative array, replacing
    `grep -Fxq -- "$path" "$TARGETS_FILE"` (`:127`).

    **Gate:** this step is the *smaller* win. The grep fires at most once per
    file — ≤378 processes, fewer because the `case` at `:121-124` short-circuits
    three paths before reaching it. Doing only this step removes ≤378 processes
    and leaves ~1500 subshells standing, while the AC text ("one process instead
    of ~1500 forks") reads as satisfied. Step 9 is not optional.

11. Keep every predicate's name, argument order, and return code.
    `tests/test_review_scope.py` invokes the script end-to-end from nine call
    sites (`:199`, `:224`, `:774`, `:835`, `:896`, `:953`, `:1007`, `:1045`,
    `:1086`) — that suite is the contract, not the internals.

### Commit 4 — R3, bookkeeping loop batching

12. **Loop A (`:1283`) takes the simple fix.** Bounded by
    `MAX_BOOKKEEPING_SUCCESSOR_COMMITS = 50` (`:33`), two spawns per commit
    (`rev-list --parents -n 1`, then `log -1 --format=%s`), contiguous range.
    One `git rev-list --format='%H %P %s'` over the range, parsed once.

13. **Loop B (`:1819`) does NOT.** Bounded by
    `MAX_BOOKKEEPING_RECOVERY_COMMITS = 100` (`:29`, enforced at `:1793`), over
    `uniqueCommits` — four spawn classes per commit:

    ```
    merge-base --is-ancestor              ancestry
    rev-list --parents -n 1               parents
    bookkeepingChangedEntries(...)        changed entries
    bookkeepingRegularPathsAtCommit(...)  ls-tree (already chunked, :1914-1918)
    ```

    **Gate:** `ledger.md:1873`'s own `fix:` field says "Replace the loops with a
    single `git rev-list --format='%H %P %s'`". That is wrong here —
    `rev-list --format` supplies neither ancestry nor changed entries, and these
    commits are not necessarily one contiguous range. Batch per evidence class:
    one ancestry sweep, one metadata batch over the explicit commit list, one
    diff/tree batch. The PRD already caught this; do not regress to the ledger's
    version.

    The ancestry sweep is settled in `design.md` — one `git rev-list <base>..<head>`
    materialized into a `Set`, membership-tested per commit. Do **not** try to
    batch `merge-base --is-ancestor`: it answers through the process exit code,
    so it is one spawn per pair and is the very call at
    `review-preflight.mjs:1819` being removed.

14. **Preserve the short-circuit order.** Both loops `continue` on the first
    failure per commit, so today a bad commit yields exactly one finding.
    Batched, every class is computed for every commit — reconstruct the
    precedence explicitly.

    **Gate:** a commit that previously emitted
    `planning_recovery_commit_not_published` and stopped must not now also emit
    `planning_recovery_commit_non_linear` and
    `planning_recovery_commit_scope_invalid`. Finding codes, their
    `invalid`/`indeterminate` status argument, and their count per commit are
    all part of the output contract.

15. Copy the in-file batching idiom rather than inventing one:
    `bookkeepingRegularPathsAtCommit` (`:1914-1918`) with
    `chunkBookkeepingGitPathspecs` and
    `MAX_BOOKKEEPING_GIT_PATHSPEC_BYTES = 8 * 1024` (`:32`).

16. Fixtures must include **noncontiguous** commits for loop B, and a
    100-commit and 50-commit range for the bounds (AC3).

17. `make sync`, changelog, version bump, candidate restamp — all three scripts
    are shipped payload with `templates/` originals and root mirrors.

## Validation

Classification output is byte-identical on a fixture diff (AC1) — the decisive
check, since every commit here is supposed to be output-neutral:

```bash
python3 -m pytest tests/test_review_scope.py tests/test_review_preflight.py tests/test_full_check.py -q
```

Spawn reduction, both invocations (AC2). **Count processes, not time or memory** —
an earlier draft used `/usr/bin/time -l`, which reports rusage and says nothing
about how many children were forked. Interpose a counting shim ahead of the real
`git` on `PATH`, run the baseline, then run the same thing after the change:

```bash
mkdir -p /tmp/sdshim && printf '#!/bin/sh\necho "$@" >> /tmp/sdshim/git.log\nexec /usr/bin/git "$@"\n' > /tmp/sdshim/git && chmod +x /tmp/sdshim/git
```

```bash
rm -f /tmp/sdshim/git.log && PATH=/tmp/sdshim:$PATH SD_AI_COMMAND_PACK_SCOPE_CHECK=1 bash scripts/sd-ai-command-pack-full-check.sh >/dev/null 2>&1; wc -l < /tmp/sdshim/git.log
```

**Gate:** record the baseline count before the change and the count after, and
put both numbers in the PR body. AC2 and AC3 are stated as bounded spawn budgets;
a wall-clock improvement is not evidence for them, and a shim that reports zero
means the script invoked git by absolute path and the measurement missed
everything — check `git.log` is non-empty before trusting any delta.

R4 resolves each base ref once (AC4) — count the underlying git calls, not the
function calls:

```bash
grep -n 'full_check_base_ref\|full_check_gito_base_ref' scripts/sd-ai-command-pack-full-check.sh
```

Expect the memo assignment inside each function and no `readonly` in `main`.

R2 no longer forks per predicate:

```bash
grep -c '\$(normalize_repo_path' scripts/sd-ai-command-pack-review-scope.sh
```

Expect `0`. Before the change this is `5`.

R3 issues one `rev-list` per range, not per commit (AC3):

```bash
grep -n "runGit(\['rev-list'" scripts/sd-ai-command-pack-review-preflight.mjs
```

Template/root parity and the full gate:

```bash
make sync && git diff --stat && make check
```

**Not verified by any of the above:** the ~8.8 ms/spawn figure the PRD's ~0.9 s
and ~2.6 s estimates rest on. That number came from the audit, not from this
checkout, and the estimates scale linearly with it — if the real per-spawn cost
on the measuring machine is half that, R3's payoff is half. Re-measure it
against the baseline from step 1 and report the observed delta, not the
projected one. Also unverified: that AC2's "378-target pack-refresh diff" is
representative — the fork count is linear in changed files, so a small diff
shows almost no improvement and a large one shows more than typical. State the
diff size alongside the number.

## Review gates

- Baseline captured with `SD_AI_COMMAND_PACK_SCOPE_CHECK` truthy (step 1).
- No new documentation-list code (step 2).
- Two separate base-ref memos, `gito` fallback intact (step 4).
- No `readonly` base-ref variable; no cache named in the
  `SD_AI_COMMAND_PACK_FULL_CHECK_*_BASE_REF` input namespace (step 5).
- Both R1 caches reset in `runReviewPreflight` **and**
  `runBookkeepingValidator` (step 8).
- `$(normalize_repo_path` count is zero (step 9) — not just the grep replaced.
- Predicate names, argument order, and return codes unchanged (step 11).
- Loop B is not collapsed into a single `rev-list` (step 13).
- Per-commit finding count unchanged on a fixture with multiple defects in one
  commit (step 14).
- Fixtures include noncontiguous commits (step 16).

## Rollback

Each commit reverts independently; none depends on another.

R4, R1, and R2 are output-neutral by construction — a bad revert costs speed,
not correctness. **R3 is the exception**: it is the only change where a mistake
produces wrong bookkeeping findings rather than slow correct ones. If AC3's
fixtures are not in place, do not land it; a silently reordered finding set is
worse than 2.6 s.

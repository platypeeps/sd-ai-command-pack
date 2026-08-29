# Implementation — cut redundant worktree hashing and payload-size classifier scans

**Two commits, R3 first.** Not the PRD's order. R3 is mechanical and fully
covered by existing fixtures; R1/R2 must not land until the mutation fixtures in
AC1 exist and pass, because its failure mode is a *missed mutation*.

No shared code between them. Either can be dropped.

## Order

### Commit 1 — R3, pr-body-scope classifier

1. **Do not re-do the normalization; it is already cached.**
   `ScopeRule.__post_init__` (`scripts/sd-ai-command-pack-pr-body-scope.py:95-105`)
   precomputes `normalized_patterns`, with the reason in a code comment: "so the
   path x rule x pattern classify loop never re-normalizes a static pattern."

   **Gate:** the remaining cost is `fnmatchcase` per pattern (`:356`), not
   normalization. A change that re-derives normalized patterns is moving
   backwards.

2. **Correct the multiplier before benchmarking.** `_include_installed_targets`
   (`:467-482`) appends installed targets only `if rule.include_installed_targets`
   (`:480`), and that flag is `True` on exactly one of the six `ScopeRule`
   constructions (`:204`, "Tooling/generated scope"). R3 says "appends the full
   installed-targets tuple to every rule" — it does not.

   Real cost is `paths × ~180`, not `paths × rules × ~180`.

3. Add two derived fields to `ScopeRule` beside `normalized_patterns`: a
   `frozenset` of metacharacter-free literals and a tuple of the remaining
   globs, both computed in `__post_init__`.

   **Gate:** both must carry `init=False, compare=False, repr=False`, copying
   `:93` exactly. `ScopeRule` is `frozen=True` and used as a **dict key** in
   `_classify` (`matches: dict[ScopeRule, list[str]]`, `:506-514`). A field that
   participates in equality or hashing changes how results group — an output
   change, not an optimization.

4. **"Metacharacter-free" means none of `*`, `?`, `[`, `]`.** Not "does not end
   in `/**`".

   **Gate:** `_matches_normalized_pattern` (`:346-356`) has a `/**` branch
   *before* the plain `fnmatchcase` fallthrough, and `fnmatch` also expands `?`
   and `[...]` character classes. A literal path containing `[` routed into the
   set matches differently than it does today. When in doubt, route it to the
   glob tuple — the fast path is an optimization, not a requirement.

5. Check the literal set first, then the glob tuple, in both matching loops:
   `_classify` (`:506-514`) and the `unmatched` comprehension (`:551-559`).

5b. **Cache the rule hash — the split alone fails AC3.** Benchmarking after
   steps 3–5 (fixed reps, GC off) still showed `_classify` growing 1.25→1.64×
   per doubling; `cProfile` pinned it: `hash` was 77% of `_classify`. `_classify`
   hashes each rule once per matched path and the generated `__hash__` rehashes
   the O(patterns) `patterns` tuple every call, so classify is O(paths × patterns)
   through the hash — the split fixed only the glob scan. Add a `compare=False`
   `_hash` field, compute `hash((label, headings, patterns, include_installed_targets))`
   once in `__post_init__`, and add a class-body `__hash__` returning it. A
   class-body `__hash__` overrides the generated one (`has_explicit_hash`); the
   frozen instance is invariant, so the cached value is O(1) per lookup and equal
   to the value it replaces. Equality is untouched. Result: flat 0.99–1.02× per
   doubling at 180/360/720/1440 targets.

6. `make sync`, changelog, version bump.

### Commit 2 — R1/R2, sd-check worktree hashing

7. **Read the three symlink/regular/other branches before proposing anything.**
   `scripts/sd-ai-command-pack-check.py:279-293`:

   ```
   :279   S_ISLNK  -> b"symlink\0" + os.readlink(path)
   :285   S_ISREG  -> b"file\0"    + _hash_regular_file(path, digest)
   :292   else     -> f"node:{stat.S_IFMT(...)}"
   ```

   **Gate:** this is why R2 exists. A retargeted symlink changes the hashed
   readlink value and a same-size rewrite changes the hashed content; a
   metadata-only digest sees neither. The PRD's own note records that the first
   draft proposed the metadata digest and that adversarial review rejected it.
   It will look like the obvious optimization again. It is not available.

8. **The alternative R2 offers is closed — do not spend time proving it.**

   - `_index_digest` (`:296-309`) hashes `.git/index`, which covers tracked
     entries only and is rewritten by git operations, not by an arbitrary
     process writing a file. The worktree digest deliberately includes
     `--others` untracked files (`:254-256`).
   - `git status --porcelain` decides dirtiness from `lstat` metadata with
     racy-timestamp handling — a same-size rewrite with `mtime_ns` restored is
     precisely the case it reports as clean.

   **Gate:** R2's "substitute git's own index/status plumbing and prove
   equivalence" cannot be satisfied. Take R2's first branch: one full content
   hash per run as the authority, cheap digest only to skip redundant re-hashes
   inside the run.

9. **Fix the baseline arithmetic.** There are **three** snapshot sites:

   ```
   check.py:805    before, once
   check.py:841    per row, inside run_and_guard
   check.py:1050   final, once
   ```

   Cost is `113 ms × (N + 2)`. AC2's "~113 ms × (N+1)" omits `:1050`.

10. **Fix the spawn attribution too.** `state_snapshot` (`:311-339`) makes five
    git spawns *per snapshot, total* — `rev-parse --verify HEAD`,
    `symbolic-ref -q HEAD`, `for-each-ref`, `rev-parse --git-path index`,
    `ls-files -z`. The eight `GUARDED_PATHS` (`:103-112`) make **zero**;
    `_hash_path` (`:165-190`) walks them with `rglob` plus `lstat`. R1's "(5 git
    spawns each)" attached to the guarded paths reads as 40 per snapshot.

    **Gate:** the guarded-path cost is filesystem work. Optimizing git spawns
    will not touch it, and optimizing the rglob will not reduce spawn count.
    Know which one is being cut before claiming a number.

11. **Decide the granularity trade explicitly, and write the decision down.**
    Today `run_and_guard` (`:838-845`) snapshots after every row and returns
    `False` on the first difference, so the guard names the offending check and
    stops. A cheap per-row digest cannot see a same-size, `mtime_ns`-restored
    rewrite, so:

    - the **run** still fails, because the final snapshot at `:1050` re-hashes
      from scratch and is the authority;
    - the **row** is no longer identified, and the remaining checks run against
      a mutated tree.

    **Gate:** this is a behavior change under R4 for the mutating case — the
    verdict is preserved, the attribution is not. Put it in the changelog. If
    per-row attribution must be kept, the per-row snapshot has to stay
    content-authoritative and the only win available is making one full hash
    cheaper, not doing fewer of them. Choose before writing code; do not
    discover this in review.

12. Implement the per-run content-hash cache keyed by path, invalidated by
    `(size, mtime_ns, mode, symlink target)`. Cached hash reused when the
    signature is unchanged; real re-hash when it moved.

    **Gate:** the cache must be dropped wholesale before the final snapshot
    (`:1050`) so that snapshot is a true from-scratch hash. A cache that
    survives into the final snapshot removes the only authoritative check in the
    run and turns R2 into the metadata digest it forbids.

13. **Do not touch the six snapshot keys.** `state_snapshot` returns `head`,
    `headReference`, `refs`, `index`, `worktree`, `guarded`; `_state_changes`
    (`:342`) publishes the differing key names through `stateGuard.changed`.

    **Gate:** R4's "same output bytes" freezes the key set. Merging `worktree`
    and `guarded`, or dropping `index`, changes published output.

14. Write the AC1 fixtures **before** the optimization: a mid-run same-size
    content rewrite with `mtime_ns` restored, a symlink retarget, and an
    ordinary edit. Each must still produce a failing mutation verdict.

15. `make sync`, changelog (including step 11's trade), version bump.

## Validation

Mutation detection survives — the decisive check for R2, and the reason this
commit exists at all:

```bash
python3 -m pytest tests/test_check.py -q
```

The three AC1 cases must be in that run. A pass without the same-size /
`mtime_ns`-restored fixture verifies nothing about R2.

Classifier output is byte-identical (AC3):

```bash
python3 -m pytest tests/test_pr_body_scope.py -q
```

R3 fields stay out of equality:

```bash
grep -n 'compare=False' scripts/sd-ai-command-pack-pr-body-scope.py
```

Expect five — four field definitions (`normalized_patterns`, `literal_patterns`,
`glob_patterns`, `_hash`) plus one in the explanatory comment. The cached `_hash`
is `compare=False` so equality stays value-based; the class-body `__hash__`
returns it.

Snapshot count is unchanged (only its cost should move):

```bash
grep -n 'state_snapshot(repo)' scripts/sd-ai-command-pack-check.py
```

Expect `:805`, `:841`, `:1050`.

Full gate and parity:

```bash
make sync && git diff --stat && make check
```

**Not verified by any of the above:** the 113 ms per-snapshot figure and the
2,155-file count. Both came from the audit, not from this checkout, and AC2's
"flat in N rather than linear" is a claim about *this* machine's numbers —
re-measure before and after and report the observed pair, not the projected
ratio. Also unverified by any test here: that the cheap signature never misses a
mutation *within a row*. It provably can (step 11) — the final snapshot is what
makes the run verdict sound, and no unit test distinguishes "caught at the row"
from "caught at the end" unless a fixture asserts on `stateGuard.changed`
attribution. If AC1 is reported as met, say which of the two it was.

## Review gates

- No metadata-only digest anywhere in the diff (step 7).
- No `git status --porcelain` or index-only substitute presented as equivalent
  (step 8).
- The per-run hash cache is cleared before the `:1050` snapshot (step 12).
- All six snapshot keys present, same names (step 13).
- AC1 fixtures committed before or with the optimization, never after (step 14).
- Step 11's granularity decision is in the changelog, not only in this file.
- R3's new `ScopeRule` fields carry `init=False, compare=False, repr=False`
  (step 3), including the cached `_hash` (step 5b).
- The cached class-body `__hash__` returns the same value the generated hash did;
  equality is unchanged (step 5b). Without it AC3 fails — the split alone does not.
- The literal fast path excludes `*`, `?`, `[`, `]` — not just `/**` (step 4).
- No re-normalization added to the classify loop (step 1).

## Rollback

R3 reverts cleanly; it is output-neutral by construction.

R1/R2 is the asymmetric one. Its failure mode is a **missed mutation** —
`sd-check` reporting clean on a tree something modified mid-run — which no
downstream check compensates for. If anything about the mutation fixtures is
uncertain, revert rather than fix forward: the pre-change behavior is slow and
correct, and 1.0 s is not worth a guard that reports clean when it is not.

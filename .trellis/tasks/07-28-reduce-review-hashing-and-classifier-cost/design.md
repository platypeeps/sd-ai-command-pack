# Design — cut redundant worktree hashing and payload-size classifier scans

## Scope boundary

Two unrelated helpers, no shared code, no shared commit. R1/R2 change *when*
`sd-check` hashes; R3 changes *how* `pr-body-scope` matches. Neither changes any
verdict, exit code, or output byte.

R2 is the whole difficulty. R3 is mechanical once three construction facts are
respected.

## Confirmed measurements

### 1. The current worktree digest is already content-authoritative — R2's concern is real

`scripts/sd-ai-command-pack-check.py:253-294`. Per path from
`git ls-files -z --cached --others --exclude-standard`:

```
:279   if stat.S_ISLNK(...):  digest.update(b"symlink\0"); digest.update(os.readlink(path))
:285   elif stat.S_ISREG(...): digest.update(b"file\0");    _hash_regular_file(path, digest)
:292   else:                   digest.update(f"node:{stat.S_IFMT(...)}")
```

A retargeted symlink changes the hashed readlink value; a same-size rewrite
changes the hashed content. Both survive any metadata-only digest. R2 is not a
hypothetical — it is a description of what these three branches do.

### 2. There are three snapshot sites, not two

```
check.py:805    before  = state_snapshot(repo)      once, before the rows
check.py:841    current = state_snapshot(repo)      inside run_and_guard, per row
check.py:1050   final   = state_snapshot(repo)      once, after
```

The PRD names `:805` and `:841` and omits `:1050`. So the cost is
**113 ms × (N + 2)**, and AC2's "~113 ms × (N+1) baseline" is one snapshot short.

### 3. "5 git spawns each" is misattributed by a factor of eight

Per `state_snapshot` (`:311-339`), the git spawns are:

```
rev-parse --verify HEAD          head
symbolic-ref -q HEAD             headReference
for-each-ref --format=...        refs
rev-parse --git-path index       index   (via _index_digest, :296)
ls-files -z --cached --others    worktree
```

**Five git spawns per snapshot, total.** The eight `GUARDED_PATHS` (`:103-112`)
cost **zero** git spawns — `_hash_path` walks them with `rglob("*")` plus
`lstat` and content hashing (`:165-190`). The PRD's "an rglob over eight guarded
paths at `:311` (5 git spawns each)" reads as 40 spawns per snapshot; the real
figure is 5, and the guarded-path cost is filesystem work, not process work.
(The loop is at `:313`, not `:311`; `:311` is the `def`.)

### 4. The snapshot is six independently reported keys, and R4 freezes them

```python
{"head", "headReference", "refs", "index", "worktree", "guarded"}
```

`_state_changes` (`:342`) returns the sorted list of keys that differ, and that
list is published as `stateGuard.changed`. R4's "same output bytes" therefore
freezes the key names and the granularity: a replacement may not merge
`worktree` and `guarded`, drop `index`, or add a key.

### 5. The cheap-authority substitutes R2 offers as an alternative do not actually work

R2 permits "substitute an equally strong invariant (for example git's own
index/status plumbing) and prove equivalence." Measured against what the current
digest covers, neither candidate is equivalent:

- **The index** (`_index_digest`, `:296-309`) hashes `.git/index`, which records
  tracked entries only and is rewritten by git operations — not by an arbitrary
  process writing a file. It says nothing about the `--others` untracked files
  the worktree digest deliberately includes.
- **`git status --porcelain`** decides dirtiness from `lstat` metadata with
  racy-timestamp heuristics. A same-size rewrite with `mtime_ns` restored is
  exactly the case it is designed to report as clean.

So the alternative branch of R2 is closed. **The remaining option is the first
one**: keep one full content hash per run as the authority, and use a cheap
digest only to skip redundant re-hashes inside the run.

### 6. R3's construction facts, measured

- **`normalized_patterns` is already precomputed.** `ScopeRule.__post_init__`
  (`:95-105`) normalizes every pattern once, with an in-code comment stating the
  purpose: "so the path x rule x pattern classify loop never re-normalizes a
  static pattern." The residual cost is `fnmatchcase` per pattern, not
  normalization.
- **Installed targets are appended to opt-in rules, not to every rule.**
  `_include_installed_targets` (`:467-482`) rebuilds a rule with
  `patterns=rule.patterns + installed_targets` **only** `if
  rule.include_installed_targets` (`:480`). That flag is `True` on exactly one
  of the six `ScopeRule` constructions (`:204`, "Tooling/generated scope"), plus
  any config rule that sets it. A-105's "appends the full installed-targets
  tuple to every rule" overstates the multiplier — the real cost is
  `paths × ~180`, not `paths × rules × ~180`.
- **`ScopeRule` is a frozen dataclass used as a dict key.** `_classify` (`:506`)
  builds `matches: dict[ScopeRule, list[str]]`, and `normalized_patterns`
  carries `compare=False` (`:93`) precisely so the derived field stays out of
  equality and hashing.
- **`_matches_normalized_pattern` (`:346-356`) has a `/**` branch** before the
  plain `fnmatchcase` fallthrough, and `fnmatch` treats `?` and `[...]` as
  metacharacters as well as `*`.

Second matching loop confirmed at `:551-559` (PRD says `:553`), same shape.

## The central tension

**R1 and R2 are in direct conflict, and the resolution costs detection
granularity rather than detection.**

Today `run_and_guard` (`:838`) snapshots after *every* row and returns `False`
on the first difference, so the guard identifies which check row mutated the
tree and stops before running the rest. Any scheme that defers the authoritative
content hash to the end still catches the mutation — the final snapshot at
`:1050` is a full hash — but it can no longer say *which row* did it, and the
remaining checks run against an already-mutated tree.

That is the actual trade on the table. It is not stated anywhere in the PRD, and
it is the thing to decide before writing code:

- **Keep per-row granularity**: the per-row snapshot must remain
  content-authoritative, so the only available win is making one full hash
  cheaper (incremental re-hash of paths whose cheap digest moved), not doing
  fewer of them.
- **Accept run-level granularity**: per-row snapshots use the cheap digest and
  may miss a same-size/mtime-restored rewrite; the final full hash catches it
  and fails the run. `stateGuard.changed` then names the run, not the row.

The second is a smaller diff and a bigger speedup. It is also a **behavior
change** under R4 for the mutating case — the verdict is preserved, the
attribution is not.

## Contract

**R1/R2.** A per-run content-hash cache keyed by path, invalidated by a cheap
per-path signature (`size`, `mtime_ns`, `mode`, plus symlink target). Paths whose
signature is unchanged reuse the cached content hash; paths whose signature moved
are re-hashed for real. The digest fed into the `worktree` key stays
byte-identical to today's for any given tree state.

This preserves per-row granularity **and** the same-size/mtime-restored
detection, because a same-size rewrite with `mtime_ns` restored leaves the
signature unchanged — so the cache returns a stale hash and the mutation is
missed. **Therefore the cache must be invalidated wholesale at least once per
run**, at the final snapshot (`:1050`), which re-hashes from scratch and is the
authority. Per-row snapshots become fast and slightly weaker; the run verdict
does not.

State that explicitly in the code and the changelog. It is the trade, not a bug.

**Count the hashes this produces, because the PRD's original AC1 got it wrong.**
Cold cache at the first snapshot is one full hash; the cache is dropped before
the final snapshot, which is a second. Snapshots 2..N are cheap signature scans.
So the run performs **exactly two** full content hashes regardless of N, against
today's N+1. AC1 was written as "at most one" before this trade was worked out
and is amended to two — the flatness in N is the actual win and is unaffected.

**Keys.** All six keys keep their names, their per-key comparison, and their
publication through `stateGuard.changed` (measurement 4).

**R3.** Split each rule's normalized patterns at construction into a
`frozenset` of metacharacter-free literals and a tuple of globs. Check set
membership first, then iterate globs. Both new fields carry `init=False,
compare=False, repr=False` exactly like `normalized_patterns`.

"Metacharacter-free" means containing none of `*`, `?`, `[`, `]` — not merely
"does not end in `/**`". A pattern with any of them goes in the glob tuple, so
the `/**` branch and fnmatch's character classes keep their current semantics.

**R3, corrected: the literal/glob split alone does not satisfy AC3.** The split
made the *glob scan* payload-independent (~30–68× faster absolutely, near-flat
per doubling), but a fixed-reps benchmark still showed `_classify` growing
1.25→1.64× per doubling. `cProfile` located it: `hash` was **77%** of
`_classify` — `<string>:__hash__`, the frozen-dataclass hash. `_classify` uses
each rule as a `dict` key and hashes it once per matched path, and the generated
`__hash__` rehashes the whole `patterns` tuple (O(patterns)) on every call. So
classify wall-clock is O(paths × patterns) through the *hash*, independent of the
match cost the split addressed. Raw `frozenset` membership was provably flat the
whole time; the growth lived entirely in the dict-key hash.

The fix is an **explicit cached `__hash__`**: `__post_init__` computes the value
hash once (frozen instance ⇒ invariant) into a `compare=False` `_hash` field, and
a class-body `__hash__` returns it. A class-body `__hash__` is respected
(`has_explicit_hash`) over the generated one, so per-lookup hashing collapses to
O(1). Equality stays value-based on the `compare=True` fields, so equal rules
still hash equal and `matches` keying is unchanged. Measured: all-hit `_classify`
at 180/360/720/1440 targets drops to a flat 0.99–1.02× per doubling (was 2.98×
at 180→720), comfortably inside AC3's 1.2× bound.

## Compatibility

Both files are shipped payload with `templates/` originals and root mirrors:
`make sync`, version bump, changelog, candidate restamp.

`_tracked_worktree_digest`'s output format is unchanged, so a digest recorded by
an older `sd-check` still compares equal against a newer one for the same tree.
`ScopeRule`'s equality is unchanged (the new fields are `compare=False`) and its
hash *value* is unchanged — the explicit `__hash__` returns the same value the
generated one produced, just cached — so `matches` keying and any pickling of
rules behave as before.

Independent of `07-25-reduce-review-tooling-spawns` — different files, no shared
code, either order.

## Rollout and rollback

Two commits, R3 first:

1. **R3** — mechanical, fully covered by existing classification fixtures, and
   its acceptance criterion (byte-identical output plus a scaling benchmark) is
   directly measurable.
2. **R1/R2** — lands only once the mutation fixtures in AC1 exist and pass:
   same-size content rewrite with `mtime_ns` restored, symlink retarget, and an
   ordinary edit.

Reverting R3 is a straight revert. Reverting R1/R2 restores the slow guard,
which is the safe direction — the failure mode of a bad R1 is a *missed
mutation*, so the revert is always preferable to a fix-forward under time
pressure.

## Risk

1. **Shipping the metadata-only digest anyway.** The PRD's own note records that
   the first draft proposed it and adversarial review rejected it. Measurement 1
   shows exactly which two attacks it drops. This is the risk R2 exists to
   prevent, and it will look like the obvious optimization again.
2. **Substituting `git status` or the index and calling it equivalent.**
   Measurement 5: neither sees a same-size, mtime-restored rewrite, and the
   index does not cover untracked files that the current digest includes.
3. **Losing per-row attribution silently.** If per-row snapshots go cheap, the
   guard still fails but `stateGuard.changed` stops identifying the offending
   check, and the remaining checks run against a mutated tree. Decide it, record
   it, do not discover it.
4. **Adding R3's split fields without `compare=False`.** `ScopeRule` is frozen
   and used as a dict key in `_classify`; changing its equality changes how
   `matches` groups, which is an output change.
5. **Treating "no glob" as "does not end in `/**`".** A literal path containing
   `[` or `?` routed to the set behaves differently than under `fnmatchcase`.
6. **Benchmarking R3 against the wrong multiplier.** The cost is `paths × ~180`
   for the one opt-in rule (measurement 6), not `paths × rules × ~180`, so the
   improvement will be smaller than A-105's framing suggests. AC3's 1.2x growth
   bound is still the right test; the headline number is not.
7. **Measuring R1 against an (N+1) baseline.** There are N+2 snapshots
   (measurement 2).

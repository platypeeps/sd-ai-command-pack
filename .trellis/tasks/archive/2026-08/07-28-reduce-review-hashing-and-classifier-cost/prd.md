# Cut redundant worktree hashing and payload-size classifier scans

## Goal

Two review-path helpers pay cost that scales with the repository or the installed
payload rather than with the change under review: `sd-check` re-hashes the whole
worktree after every check row, and `pr-body-scope` fnmatches the full
installed-target list per changed path per rule. Remove both without weakening the
mutation guard `sd-check` exists to enforce.

## Origin

Split out of `07-25-reduce-review-tooling-spawns` on 2026-07-28. That task's goal is
process-spawn reduction in `review-preflight.mjs` and `review-scope.sh`; these two
findings are hashing and matching cost in different files, so they were widening its
title. Adversarial review recommended the split and the pack owner accepted it.

Both findings come from `.trellis/audit/report-2026-07-28.md` — A-101 and A-105,
P2/P3 · S/M · Plausible, performance dimension. Neither had an owner before the
2026-07-28 stale-task pass.

## Requirements

- R1 (A-101): `scripts/sd-ai-command-pack-check.py` must stop re-hashing the whole
  worktree once per check row. `:805` takes the before snapshot, `run_and_guard` at
  `:841` re-snapshots after each row, and `_tracked_worktree_digest` at `:253`
  SHA-256s every tracked and untracked file plus an rglob over eight guarded paths
  at `:311` (5 git spawns each). Measured at 113 ms per snapshot over 2,155 files,
  nine snapshots cost ~1.0 s — roughly the rest of the check surface combined, and
  it scales linearly with the number of configured checks.

- R2 (A-101, constraint on R1): the replacement must stay content-authoritative.
  This is a mutation *guard*, so a cheap inventory digest (path, size, `mtime_ns`,
  mode) is not a safe substitute on its own: a same-size rewrite with `mtime_ns`
  restored, or a retargeted symlink, passes a metadata-only digest that the current
  content hash catches. Either keep one full content hash per run as the authority
  and use a cheap digest only to skip *redundant* re-hashes inside that run, or
  substitute an equally strong invariant (for example git's own index/status
  plumbing) and prove equivalence. A weaker guard is not an acceptable trade for
  the speedup.

- R3 (A-105): `scripts/sd-ai-command-pack-pr-body-scope.py` must stop matching ~180
  literal installed-target paths per changed path per rule. `:509` is the triple
  loop (a second at `:553`), `:467` appends the full installed-targets tuple to
  every rule, and `:347` pushes exact literals through `fnmatchcase`. Split the
  patterns into a literal set and a glob tuple at construction and check the set
  first, so classifier cost tracks the diff rather than the payload size.

- R4: no behavior change. Both helpers keep their current verdicts, exit codes, and
  output bytes for every input the existing suite covers.

## Acceptance Criteria

- [x] R1/R2: `sd-check` produces the same mutation-guard verdicts — including
      positive detection of a mid-run same-size content rewrite with `mtime_ns`
      restored, a symlink retarget, and an ordinary edit — while performing at most
      **two** full content hashes per run in the unmutated case, independent of the
      number of configured checks.

      Amended 2026-07-28. This criterion originally said "at most one". The design
      establishes that the final snapshot must re-hash from scratch to stay
      authoritative — a signature-keyed cache cannot see a same-size,
      `mtime_ns`-restored rewrite, so if the cache survives into the final
      snapshot the run loses its only real check. That forces one cold hash at the
      first snapshot and one authoritative hash at the last: exactly two, never
      more. The win is unchanged and is the point of R1 — today's cost is N+1 full
      hashes for N checks, and flatness in N is what the next criterion measures.
- [x] R1: a repository fixture with N configured checks shows snapshot cost flat in
      N rather than linear, measured against the current ~113 ms × (N+1) baseline.
- [x] R3: `pr-body-scope` classification is byte-identical on a fixture diff, and a
      benchmark over a fixed 50-path diff at 180 / 360 / 720 installed targets shows
      wall-clock growth no worse than 1.2x across each doubling.
- [x] `make check` passes.
- [x] Changelog + version; fleet rollout via normal refresh.

## Notes

- Sibling task `07-25-reduce-review-tooling-spawns` keeps R1–R4 (preflight
  memoization, review-scope batching, the per-commit git loops, and full-check
  base-ref resolution). There is no shared code between the two sets, so they can
  land in either order.
- R2 exists because the first draft of this requirement proposed the metadata-only
  digest outright. Adversarial review caught that it weakens the guard; the
  constraint is recorded here so the cheap-digest idea is not reintroduced as an
  obvious optimization.
- Complex task. Planning complete 2026-07-28: `design.md` and `implement.md` added.
- **R2's concern is confirmed in code.** `check.py:279-293` hashes symlink targets via
  `os.readlink` and regular-file contents via `_hash_regular_file`, so a retargeted symlink
  and a same-size rewrite are both caught today and both invisible to a metadata-only
  digest.
- **R2's alternative branch is closed.** "Substitute git's own index/status plumbing and
  prove equivalence" cannot be satisfied: `_index_digest` (`:296-309`) hashes `.git/index`,
  which covers tracked entries only and is rewritten by git operations rather than by an
  arbitrary write, while the worktree digest deliberately includes `--others` untracked
  files (`:254-256`); and `git status --porcelain` decides dirtiness from `lstat` with
  racy-timestamp handling, so a same-size rewrite with `mtime_ns` restored is exactly what
  it reports as clean. Only R2's first branch remains.
- **There are three snapshot sites, not two.** `:805` (before), `:841` (per row), and
  `:1050` (final). Cost is `113 ms × (N + 2)`; AC2's "~113 ms × (N+1) baseline" is one
  snapshot short.
- **"(5 git spawns each)" is misattributed by 8×.** `state_snapshot` (`:311-339`) makes five
  git spawns *per snapshot, total* (`rev-parse --verify HEAD`, `symbolic-ref -q HEAD`,
  `for-each-ref`, `rev-parse --git-path index`, `ls-files -z`). The eight `GUARDED_PATHS`
  (`:103-112`) make zero — `_hash_path` (`:165-190`) walks them with `rglob` plus `lstat`.
  The guarded-path cost is filesystem work, not process work. The loop is at `:313`; `:311`
  is the `def`.
- **Undeclared trade: R1 and R2 conflict, and the resolution costs attribution.**
  `run_and_guard` (`:838-845`) snapshots after every row and aborts on the first difference,
  so today the guard names the offending check. A cheap per-row digest cannot see a
  same-size, `mtime_ns`-restored rewrite, so the run still fails at the authoritative
  `:1050` snapshot but `stateGuard.changed` no longer identifies the row, and later checks
  run against a mutated tree. That is a behavior change under R4 for the mutating case.
  Decide and record it before implementing.
- **`state_snapshot` returns six independently reported keys** — `head`, `headReference`,
  `refs`, `index`, `worktree`, `guarded` — and `_state_changes` (`:342`) publishes the
  differing names through `stateGuard.changed`. R4 therefore freezes the key set; a
  replacement may not merge `worktree` and `guarded` or drop `index`.
- **R3's normalization is already cached.** `ScopeRule.__post_init__`
  (`pr-body-scope.py:95-105`) precomputes `normalized_patterns` with an in-code comment
  giving exactly that reason. The residual cost is `fnmatchcase` per pattern (`:356`).
- **R3 overstates the multiplier.** `_include_installed_targets` (`:467-482`) appends
  installed targets only `if rule.include_installed_targets` (`:480`), which is `True` on
  one of six `ScopeRule` constructions (`:204`). Cost is `paths × ~180`, not
  `paths × rules × ~180`.
- **Two construction traps for R3's split.** `ScopeRule` is `frozen=True` and used as a dict
  key in `_classify` (`:506-514`), so new derived fields must copy `normalized_patterns`'
  `init=False, compare=False, repr=False` (`:93`) or rule equality changes how results
  group. And "literal" must mean free of `*`, `?`, `[`, and `]` — not merely "does not end
  in `/**`" — because `_matches_normalized_pattern` (`:346-356`) has a `/**` branch ahead of
  the plain `fnmatchcase` fallthrough and `fnmatch` expands character classes too.
- Second matching loop is at `:551-559` (R3 cites `:553`); `_classify` is at `:506` (R3
  cites `:509`).

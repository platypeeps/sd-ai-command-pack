# Design: kcov-lane flake — diagnosability first, no masking

## Problem shape

Two transient git failures in one test, different sites, kcov lane only
(see `prd.md` for the full evidence). Fingerprint 2 (fixture `git commit`
→ `fatal: could not parse HEAD`) is diagnosable only to its assertion's
current limit — `run_git` merges stderr into the assertion message, and
a third identical occurrence would add nothing beyond that message. Fingerprint 1
(validator scan `git diff --raw` exits nonzero) is a diagnostic dead end:
`bookkeepingChangedEntries` (`scripts/sd-ai-command-pack-review-preflight.mjs:1952-1956`)
returns `null` on nonzero exit and the composed finding says only that
git "could not inspect" a delta — the exit status and stderr that
`runGit`'s `spawnSync` already captured are thrown away.

Root cause is not pinned. Both failures are consistent with transient
resource pressure on the runner during one of the highest-git-spawn
tests in the suite (~150 short-lived git processes on the normal path;
see `prd.md`), but "consistent with" is not a diagnosis. The design therefore ships diagnosability now and defers the
targeted fix to the first occurrence that lands with real error text.

## Remedy choice

**Chosen: enrich the failure findings with the captured git argv, exit
status, and bounded stderr; change nothing about validation semantics or
control flow.**

Rejected alternatives:

- **Retry the failed git invocation.** Masks whatever is actually wrong,
  turns a loud advisory failure into silent latency, and — worse — a
  retry that succeeds destroys the only evidence of the underlying
  fault. Rejected outright; `prd.md` requirement 6 bans silent retries.
- **Batch the completion-recovery scan into one `git log --raw` walk.**
  Would collapse the per-window diff spawns (worst case ~200 when no
  anchor exists) into one walk and shrink the exposure surface, but it
  rewrites a heavily tested recovery path to mitigate an advisory-lane
  flake whose cause is unproven. Rejected for this task; noted in
  `prd.md` Out of scope as the fallback if the flake persists after
  diagnostics land.
- **CI-side auto-rerun of the kcov lane.** Hides the signal the lane
  exists to give and generalizes badly (every future real regression
  gets one free pass). Rejected.
- **Skip/soften the test under kcov.** Loses real coverage of the
  long-history anchor bound for a lane whose whole point is measuring
  reality. Rejected.

## Mechanics

### Failure-detail capture

`bookkeepingChangedEntries` keeps its `null`-on-failure contract (9
callsites depend on it). On the `result.status !== 0` branch it
additionally records the failure detail in a module-level slot, and the
sites that compose user-facing `*_unavailable` findings read that slot
immediately after observing `null`:

```js
let lastBookkeepingGitFailure = null; // { command, status, stderr }

function describeGitFailure(prefix) {
  const f = lastBookkeepingGitFailure;
  if (!f) return prefix;
  return `${prefix} (git ${f.command} exited ${f.status}: ${f.stderr})`;
}
```

- `command` is the joined subcommand argv (no paths beyond what git
  itself prints), `status` the numeric exit code, `stderr` trimmed and
  bounded (first line, capped ~200 chars) so a pathological git cannot
  bloat the receipt.
- Stale-safety is engineered, not assumed. Two leak paths exist and both
  are closed:
  - `bookkeepingChangedEntries` also returns `null` on **status-0
    malformed output** (`bundle_diff_malformed`, `:1966-1978`); a slot
    set by an earlier nonzero-status failure would otherwise be read by
    a later malformed-null caller. Closure: the function clears the slot
    to `null` as its first statement and sets it only on the
    nonzero-status branch, so every `null` return leaves the slot
    describing *that call* or nothing; `describeGitFailure` degrades to
    the bare prefix when the slot is empty.
  - `runBookkeepingValidator` is exported and re-invocable in one
    process, and already resets module state on entry (`rootDir`,
    `config`, `readTextCache`, `:579-583`). The slot joins that reset.
  - Regression test: one process invocation sequence
    failure-then-malformed asserting the malformed call's finding does
    NOT contain the earlier failure's stderr text.
  - Within a call the script is synchronous and single-threaded, and the
    slot is read on the statement after the `null` check — no async
    interleave. (The module slot was chosen over changing the return
    type to `{entries}|{failure}` because the alternative touches all 9
    callsites mechanically for the same information, with more diff
    surface in a validator whose behavior must not change.)
- Sites enriched — by rule, with the current enumeration:
  - **Rule A (slot readers):** every composer of an `*_unavailable`
    finding that observes a `null` return from a silent-probe
    (`() => {}`) `bookkeepingChangedEntries` call reads the slot.
    Current enumeration (grep `bookkeepingChangedEntries(` for `() =>
    {}` callers followed by an unavailable finding): the
    completion-recovery scan's "candidate journal delta" / "candidate
    archive delta" pair (`:1238-1256`, the fingerprint-1 sites), the
    active-task recovery twin (`:1432-1446`), the active-task
    successor-range per-commit and whole-range sites (`:1543-1552`,
    `:1577-1586`), and the completion-successor range site (`:1891-1900`).
    Re-run the grep at implementation time; the list above is a
    2026-08-09 snapshot, not the contract.
  - **Rule B (local status):** sites with a failed `runGit` result in
    scope enrich their message directly from it — the `rev-list`
    history enumerations (`:1217`, `:1411`), the active-task
    successor-range `rev-list` (`:1509-1517`), the completion-successor
    range `rev-list` (`:1841-1849`), the commit-subject probe
    (`:1874-1880`), the whitespace validation's empty-output nonzero
    branch (`bundle_whitespace_unavailable`, `:1994-1999`, local
    `result` in scope), and the planning-recovery parents probe
    (`planning_recovery_commit_unavailable`, `:2559-2568`, local
    `parentResult` in scope). No slot involved. As with Rule A, re-grep
    `completion_successor_history_unavailable` (11 sites at the
    2026-08-09 snapshot) plus the other git-caused `*_unavailable`
    reason codes at implementation time — every site whose proximate
    cause is a failed git subprocess must land in exactly one rule.
  - **Rule C (real-`add` callers):** callsites passing the real `add`
    (`:1111`, `:1661`, `:2579`) already surface
    `bundle_diff_unavailable` from inside `bookkeepingChangedEntries`;
    enriching that one message (`:1955`) covers them all.
  - The `completion_successor_history_non_linear` findings whose
    `rev-list --parents` probe failed (`:1529-1541`, `:1861` region)
    keep their reason code and are out of the minimum scope
    (`prd.md` requirement 1); enrich opportunistically only if the
    change stays trivial.
- `runGit`'s throw paths (spawn error / signal) already carry their
  reason in `GitCommandError` and are out of scope.

### What does not change

- Reason codes, `status` values, dispositions, `schemaVersion: 1`,
  control flow, and every pass/fail outcome under identical git
  behavior. The enrichment is append-only text inside existing
  `message` strings.
- The templates twin `templates/scripts/sd-ai-command-pack-review-preflight.mjs`
  must stay byte-identical to `scripts/…` (Makefile checks both; repo
  convention).
- Fixture side: one bounded addition, because fingerprint 2's existing
  diagnosis has hit its ceiling — a recurrence of `fatal: could not
  parse HEAD` with today's assertion adds nothing beyond the second
  occurrence. The capture lives in the **assertion wrappers** `run_git`
  and `git_output` (`tests/install_test_support.py:242-249`), not in
  `_run_git_process`: the latter has no failure branch by design
  (`check=False`) and is called directly by tests that treat nonzero
  exits as expected outcomes (e.g. `check-ignore` expecting 1,
  `tests/test_claude_planning_review.py:49`,
  `tests/test_install_core.py:2185`) — enriching there would tax
  passing predicate calls. On an unexpected nonzero status the wrappers
  append a bounded repo-state block to the assertion message: raw bytes
  of `.git/HEAD`; if `.git` is a worktree pointer file (linked
  worktrees exist in this suite, `tests/test_recovery_artifacts.py:112`),
  say so and follow the `gitdir:` target for the reads; existence of
  the loose ref file HEAD names; the named ref's bounded
  membership/value line in `packed-refs` (mere `packed-refs` existence
  cannot distinguish a validly packed ref from a missing one); and any
  `*.lock` entries in the git directory. That discriminates the
  candidate causes (torn/empty HEAD read vs genuinely missing ref vs
  packed-only ref vs lock contention) on the next hit. Capture happens
  only on the failing-assertion path, so passing runs pay nothing.

### Tests

Reuse the selective git-stub pattern from
`test_completion_successor_reports_unavailable_commit_subject`
(`tests/test_bookkeeping_validator.py:1152+`): a stub `git` on PATH that
fails specific subcommands with a known exit status and stderr and execs
the real git otherwise.

1. **Scan-path test (fingerprint 1's exact site):** build the
   post-archive successor repo normally (real git), then run the
   validator with a PATH-prepended stub that fails `diff --raw` **only
   for the specific `baseOid archiveOid` pair** of the anchor window
   (exit 128, stderr `fatal: injected diff failure`), passed to the
   stub via environment variables computed from the fixture
   (`archiveOid` = the archive commit, `baseOid` = its parent "fixture
   work" commit). Pair-selectivity matters twice over: the successor
   fixture invokes `final-bundle` with `--base` == `--head`, so the
   direct-bundle call (`:1111`) diffs identical oids and must pass; and
   the scan diffs the journal window (`archiveOid
   bookkeepingHeadOid`, `:1238`) **before** the archive window
   (`:1248`) and returns on the first failure — a stub keyed merely on
   "oids differ" would fire at the journal-delta site and the observed
   "candidate archive delta" finding would never be reached. Assert:
   `status: indeterminate`, reason
   `completion_successor_history_unavailable`, the message names the
   candidate **archive** delta, and it contains both `128` and
   `injected diff failure`.
2. **Direct-bundle test:** a stub failing all `diff --raw` against a
   `final-bundle` invocation whose base ≠ head, asserting the enriched
   `bundle_diff_unavailable` message at the `:1111` path.
3. **Bounding test:** stub emits multi-line/oversized stderr; assert the
   receipt message contains the first line and stays within the cap.
4. **Stale-slot regression:** in one process, a failing invocation
   followed by a malformed-output (status-0) invocation via the exported
   `runBookkeepingValidator`. Positive control first: assert the FIRST
   receipt's finding carries the injected stderr and status (this is
   what fails against the pre-change script — a negative-only test
   would pass pre-change, since the old code never embedded stderr
   anywhere). Then assert the second receipt's
   `bundle_diff_malformed`/`*_unavailable` findings contain none of the
   first invocation's stderr text.
5. **Rule B subject-site upgrade:** the existing exit-73 subject-probe
   test (`test_completion_successor_reports_unavailable_commit_subject`,
   `tests/test_bookkeeping_validator.py:1150+`) gains a known stderr in
   its stub and asserts the enriched message carries `73` and that
   stderr; a sibling assertion covers the range `rev-list` site.
6. **Fixture-context test:** drive `run_git`/`git_output` into their
   unexpected-nonzero assertion path deterministically (e.g., a git
   subcommand against a corrupted or non-repo fixture, caught via
   `assertRaises`) and assert the raised message contains the
   repo-state block markers.

Every forced-failure **validator receipt** test (1, 2, 3, 4, 5) also
asserts receipt shape: `schemaVersion: 1`, unchanged top-level key set,
and unchanged reason codes/dispositions for the exercised path — the
no-schema-break requirement is proven on the enriched failure receipts,
not only on a healthy window. The fixture-context test (6) exercises
Python assertion output, not a receipt; its baseline obligation is to
fail against the **pre-change test-support helper**, not the validator
script. Baselines for the fails-before/passes-after checks come from
temporary copies via `git show HEAD:<path>` — never stash or revert the
working tree.

Existing tests asserting exact `*_unavailable` message strings (if any)
are updated to the enriched form; a grep for the current literal
messages enumerates them.

### Characterization (timeboxed, recorded either way)

- Local spawn-storm: loop the single test N times **with a mandatory
  bounded concurrent-load phase** (parallel CPU/fork pressure alongside
  the loop) — the failures were only ever observed under the loaded
  full-suite kcov lane, so a serial-only negative result would not test
  the stated hypothesis. Record iterations, concurrency level, and
  environment (machine, OS) alongside hit/no-hit counts.
- Git-source reasoning for `fatal: could not parse HEAD` at exit 128 in
  a repo whose HEAD had just been updated ~105 times (ref file read
  path, EINTR/ENOMEM behavior), recorded as analysis, not speculation.
- Outcome lands in `research/characterization.md`. A negative result is
  the expected result; it still discharges `prd.md` requirement 5.

## Mitigation decision (prd requirement 6)

**Diagnose and wait.** No retry, no suppression, no lane change. Revisit
trigger: the next kcov-lane occurrence of either fingerprint —
fingerprint 1's receipt then names the exact git subcommand, exit
status, and stderr (today it names none of them), and fingerprint 2's
assertion then carries the repo-state block that discriminates its
candidate causes (today it repeats what the second occurrence already
showed). At that point a targeted fix (or the batched-walk fallback)
gets its own task with evidence instead of conjecture.

## Rollback

Single-commit revert of the script pair + tests. No schema, workflow, or
data migration surface.

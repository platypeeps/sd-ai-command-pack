# Shell coverage kcov lane flakes on test_completion_successor_finds_recent_anchor_in_long_history

## Goal

Stop the recurring kcov-lane flake from burning rerun time — or, where the
root cause cannot be pinned from available evidence, make the next
occurrence carry enough diagnostics to pin it. The flake is advisory-lane
noise (`Shell coverage` is not in `ci-result.needs`), but it hit twice in
one evening on 2026-08-09 and each hit costs a manual rerun and an
investigation that dead-ends on discarded error output.

## Observed occurrences (2026-08-09, both on attempt 1, both reruns green)

Two failures of the same test,
`tests/test_bookkeeping_validator.py::test_completion_successor_finds_recent_anchor_in_long_history`,
with **different failure sites** — this is one flake pattern, not one bug
site:

1. **PR #386 run 31291158452, job 93188502655** — the test itself ran; the
   validator under test returned `status: indeterminate`, reason
   `completion_successor_history_unavailable`, finding message
   `Git could not inspect a candidate archive delta during completion
   recovery`. That message means a `git diff --raw -z --find-renames
   <base> <head>` spawned by `bookkeepingChangedEntries`
   (`scripts/sd-ai-command-pack-review-preflight.mjs:1952-1956`) exited
   nonzero — and the git exit status and stderr were **discarded**, so
   which git error occurred is unknowable from the log.
2. **main run 31291862939, job 93190348754** — the test failed in fixture
   setup before the validator ran: `run_git(root, "commit", "-m", "fixture
   work")` (`tests/test_bookkeeping_validator.py:975`) failed with
   `AssertionError: 128 != 0 : fatal: could not parse HEAD`
   (`tests/install_test_support.py:244`), after 101 empty prehistory
   commits had just succeeded in the same repository.

Shared context:

- The test passes locally (~2.4 s) and in all three `unittest` matrix
  lanes on every observed run; only the kcov lane has failed, and only
  under load (the lane's total suite time was 272–316 s on the failing
  attempts).
- This is among the highest-git-churn tests in the suite: fixture setup
  spawns ~115 `git` processes (101 empty commits plus config/seed/work/
  archive/journal commits and `rev-parse` reads), and the validator's
  completion-recovery scan spawns two `git diff --raw` per first-parent
  window until the first shaped anchor tail, then breaks
  (`scripts/sd-ai-command-pack-review-preflight.mjs:1286-1287`) and runs
  the successor-range and historical-bundle evaluations (more spawns).
  In this test the anchor sits at the second window, so a passing run is
  on the order of 150 git spawns total; the ~100-window bound
  (`MAX_BOOKKEEPING_ANCHOR_SEARCH_COMMITS = 100`, `:35`) is the
  worst-case exposure when no anchor exists, not this test's normal
  path.
- Test-side git hygiene already exists: every fixture git call runs with
  `-c gc.auto=0` and merges stderr into the assertion output
  (`tests/install_test_support.py:223-245`) — which is why occurrence 2
  is diagnosable (`fatal: could not parse HEAD`) and occurrence 1 is not.
- The `gh timed out after 60s` lines adjacent to occurrence 1 in the log
  belong to a different test's captured output (`sd-review-learnings`
  scan) printed by the sequential unittest runner; they are evidence of
  runner-wide slowness, not part of this test.

## Requirements

1. **Validator diagnosability.** When a git invocation issued by the
   bookkeeping validation paths fails in a way that produces an
   `*_unavailable`-class finding — `bundle_diff_unavailable` from
   `bookkeepingChangedEntries`, every
   `completion_successor_history_unavailable` site whose proximate cause
   is a failed git subprocess, `bundle_whitespace_unavailable`'s
   empty-output nonzero branch, and
   `planning_recovery_commit_unavailable` — the emitted finding must
   carry the failing git subcommand, its exit status, and a bounded
   excerpt of its stderr (where git produced none, say so rather than
   omit the enrichment). The next occurrence of fingerprint 1 must be
   diagnosable from the CI log alone.
2. **No schema break.** `schemaVersion` stays 1; reason codes, `status`
   values, and finding `disposition`s are unchanged. Enrichment lands in
   existing free-text `message` fields (or additive evidence fields), so
   consumers keyed on reason codes are unaffected.
3. **No semantic change.** Identical git behavior must produce identical
   validation outcomes (pass/fail/indeterminate) before and after. This
   task adds information to failure paths; it does not add retries,
   fallbacks, or new failure conditions inside the validator.
4. **Deterministic proof.** The enrichment is proven by deterministic
   tests that force a git failure (the existing PATH-stub pattern used by
   `test_completion_successor_reports_unavailable_commit_subject`) and
   assert the finding contains the exit status and stderr text — not by
   waiting for the flake to recur.
5. **Characterization attempt, honestly bounded.** A timeboxed attempt to
   reproduce or narrow the two fingerprints (spawn-storm loops, review of
   what makes git exit 128 with `could not parse HEAD` in a repository
   whose HEAD was just written ~5 times) is made and its outcome —
   including a negative one — is recorded in this task's `research/`.
   The attempt must include a bounded **concurrent-load** phase, not only
   serial repetition: the failures were observed exclusively under the
   loaded kcov lane, so a serial-only negative tests nothing the evidence
   points at. Record iterations, concurrency, and environment. A negative
   result is an acceptable outcome; an unrecorded attempt is not.
6. **Mitigation decision recorded.** Either the root cause is pinned and
   deterministically fixed (with a regression test), or the task records
   an explicit decision on what happens next: what the revisit trigger is
   (the next occurrence, now carrying diagnostics), and why no retry or
   masking mechanism was added. Any mitigation that retries or suppresses
   must still surface the original failure; silent retries are rejected
   up front.
7. **Fingerprint-2 forward path.** Fingerprint 2 is already diagnosed to
   the limit of its assertion (`fatal: could not parse HEAD` with merged
   stderr); a third identical occurrence would add nothing. The test
   support's **assertion wrappers** (`run_git`/`git_output` — not
   `_run_git_process`, which has no failure branch and is called
   directly by tests expecting nonzero exits) must therefore capture
   bounded repo-state context in the assertion message on unexpected
   nonzero status: raw `.git/HEAD` bytes (following a worktree
   `gitdir:` pointer when `.git` is a file), loose-ref existence for
   the ref HEAD names, that ref's bounded membership/value in
   `packed-refs` (existence of the file alone cannot distinguish a
   validly packed ref from a missing one), and git-dir lock files. That
   discriminates torn/empty HEAD read vs genuinely missing ref vs
   packed-only ref vs lock contention. Assertion-failure path only;
   passing runs pay nothing.

## Acceptance Criteria

- [ ] A deterministic test forces `bookkeepingChangedEntries`'s git diff
      to fail (stubbed git exiting nonzero with known stderr) and asserts
      the resulting receipt's finding message contains both the exit
      status and the stub's stderr text. The test passes in the standard
      suite (`make test`).
- [ ] A deterministic test (or the same test) covers the completion-
      recovery scan path of fingerprint 1 — the
      `completion_successor_history_unavailable` finding produced via a
      failed candidate-delta inspection carries the same enrichment.
- [ ] The direct-`runGit` unavailable sites (design Rule B, including
      the completion-successor range and commit-subject probes) carry
      the enrichment, proven by upgrading the existing exit-73
      subject-probe stub test to a known stderr and asserting both
      values in the finding message.
- [ ] A stale-slot regression test (failing invocation followed by a
      status-0 malformed-output invocation in one process via the
      exported `runBookkeepingValidator`) asserts as a positive control
      that the first receipt carries the injected stderr/status — the
      half that fails pre-change — and then that the second receipt
      carries none of the first invocation's stderr.
- [ ] The forced-failure **validator receipt** tests (design tests
      1–5) assert receipt shape on the enriched failure receipts:
      `schemaVersion: 1`, unchanged top-level keys, unchanged reason
      codes and dispositions. (Design test 6, the fixture-context test,
      exercises assertion output, not a receipt, and is exempt.)
- [ ] A deterministic test forces the test-support assertion wrappers'
      unexpected-nonzero path and asserts the assertion message carries
      the repo-state context block (requirement 7); it fails against
      the pre-change test-support helper.
- [ ] The full existing suite passes with no test's asserted reason
      codes, statuses, or dispositions changed. Tests asserting exact
      message strings may be updated to the enriched strings; nothing
      else changes.
- [ ] `research/` contains a characterization note with the reproduction
      attempt's method and outcome, stated plainly if negative, and
      records iterations, the mandatory concurrent-load phase's
      concurrency level, and environment. If a root cause was pinned,
      the fix carries a regression test instead.
- [ ] The mitigation decision (fix, or diagnose-and-wait with revisit
      trigger) is recorded in `design.md`, and no retry/suppression
      mechanism exists in the shipped change unless it surfaces the
      original failure in the receipt.
- [ ] The change is validated by the normal PR gates. A green kcov lane
      on the PR is reported as what it is — one more non-failing sample of
      a probabilistic failure — and not claimed as proof the flake is
      gone.

## Out of scope

- General CI retry infrastructure or `ci-result.needs` changes; the lane
  stays advisory and stays loud.
- kcov version/pin changes, the from-source kcov build, and the shim
  (`.github/scripts/kcov-bash-shim.sh`) — no evidence implicates them
  beyond ambient load, and this test's subprocesses are not kcov-wrapped
  (they are node/git, not `SD_AI_COMMAND_PACK_TEST_BASH` bash).
- A shell-coverage floor (separately deferred by the lane's own design).
- Restructuring the completion-recovery scan to batch its per-window git
  spawns into one `git log --raw` walk. It would reduce the exposure
  surface but rewrites a heavily tested code path for an advisory-lane
  flake; consider only if the flake persists after diagnostics land.

## Notes

- Filed from session 349 wrap-up (journal-7.md); occurrence evidence read
  from the Actions API attempt-1 logs, not from memory.
- Priority P3→P2 rationale: two hits in one evening; every future hit
  costs a manual rerun plus a dead-end investigation until diagnostics
  land.

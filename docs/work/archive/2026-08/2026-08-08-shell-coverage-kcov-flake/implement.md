# Implementation plan: kcov-flake diagnosability

Ordered checklist. Validation commands named per step; a step's named
check failing blocks the next step.

1. **Characterization (timeboxed ~30 min, negative result acceptable).**
   Loop `python3 -m unittest tests.test_bookkeeping_validator.BookkeepingValidatorTests.test_completion_successor_finds_recent_anchor_in_long_history`
   N≥20 times locally, including a **mandatory bounded concurrent-load
   phase** (parallel CPU/fork pressure running alongside the loop);
   record hit/no-hit, iterations, concurrency level, and environment in
   `research/characterization.md` together with the `could not parse
   HEAD` analysis. Check: file exists with method, counts, load
   parameters, environment, and an explicit conclusion (pinned / not
   reproduced).
2. **Enumerate message-string couplings.** `grep -n "could not
   inspect\|could not enumerate\|bundle_diff_unavailable\|finalization
   delta" scripts/… tests/…` — list every test asserting the literal
   messages about to be enriched. Check: list recorded in
   `research/characterization.md` (or a sibling note); empty is a valid
   result.
3. **Implement capture + enrichment** in
   `scripts/sd-ai-command-pack-review-preflight.mjs` per `design.md`
   Rules A/B/C — re-running the Rule A silent-probe grep and the
   git-caused `*_unavailable` reason-code greps
   (`completion_successor_history_unavailable` — 11 sites at snapshot —
   plus `bundle_diff_unavailable`, `bundle_whitespace_unavailable`,
   `planning_recovery_commit_unavailable`) rather than trusting the
   design's line snapshot; slot
   cleared at `bookkeepingChangedEntries` entry and included in
   `runBookkeepingValidator`'s module-state reset. Check: `node --check`
   passes AND the greps show every git-failure-caused unavailable site
   lands in exactly one rule.
4. **Mirror to templates twin** byte-identically. Check:
   `cmp scripts/sd-ai-command-pack-review-preflight.mjs
   templates/scripts/sd-ai-command-pack-review-preflight.mjs` exits 0.
4b. **Fixture-side context capture** in the `run_git`/`git_output`
   assertion wrappers of `tests/install_test_support.py` per `design.md`
   (repo-state block on unexpected nonzero only; `_run_git_process`
   itself untouched — direct callers treat nonzero as expected; handle
   `.git` worktree pointer files). Check: covered by step 5's
   fixture-context test.
5. **Add the six tests** from `design.md` (scan-path with
   pair-selective stub reaching the candidate-**archive**-delta site,
   direct-bundle, stderr bounding, stale-slot regression with its
   positive control on the first receipt, Rule B subject-site upgrade +
   range-site assertion, fixture-context). The validator receipt tests
   (design tests 1–5) also assert receipt shape (`schemaVersion: 1`,
   keys, reason codes, dispositions); the fixture-context test (design
   test 6) is exempt. Check: each new/upgraded validator test fails against the
   pre-change script and the fixture-context test fails against the
   pre-change test-support helper — baselines taken as temporary copies
   via `git show HEAD:<path>` (never stash/revert the working tree) —
   and all pass against the new code. Proves they test the enrichment,
   not the stub.
6. **Full suite.** `make test` green; no existing test's reason-code /
   status / disposition assertions weakened or removed. Permitted edits
   to existing tests: the message-string updates enumerated in step 2,
   and the step 5 subject-probe upgrade (which only adds assertions).
   Check: `make test` exit 0 + `git diff` review of tests shows only
   the enumerated message updates, the additive subject-probe upgrade,
   and new tests.
7. **Receipt-schema sanity.** Run `final-bundle` against a healthy local
   window and diff the receipt's key set against pre-change output —
   expect identical keys, identical reason codes. The failure-receipt
   half of this obligation is discharged by step 5's in-test shape
   assertions. Check: no key/code drift on either path.
8. **Spec touch check.** Read
   `.trellis/spec/tooling/bookkeeping-validator.md`; if it quotes any
   enriched message literally, update it; otherwise record "no spec
   change needed". Check: grep the spec for the old literals returns
   nothing.
9. **Publish** via `sd-create-pr` flow (preflight gate, PR body scope
   section for tooling changes), Copilot review, CI green, merge on
   user instruction per repo convention.
10. **Finish flow** — journal session (with Testing section), evidence
    note that the kcov lane's green run is one sample, not proof;
    archive task in its own completion-bundle push, with any follow-up
    filings in a separate push (session-349 lesson).

Rollback point: steps 3–5 are one revertable commit; nothing outside the
script pair and tests changes.

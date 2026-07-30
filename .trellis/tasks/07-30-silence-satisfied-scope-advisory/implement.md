# Implementation plan

## Ordered checklist

1. [x] Extract `resolve_pr_body_scope_state` in
       `templates/scripts/sd-ai-command-pack-review-scope.sh`, emitting the
       state tokens from `design.md`. Move only resolution; leave every
       `warn`/`fail` call in the callers.
2. [x] Rewrite `check_pr_body_scope` as a mapper over those tokens, preserving
       each existing message and exit status verbatim. Keep the
       `scoped_count -eq 0` early return above the helper call.
3. [x] Replace the advisory branch in `main()` so it calls the helper and
       branches three ways: silent on `satisfied`, PR-exists wording on
       `unsatisfied:*`, existing pre-PR wording on `unknown:*`. Emit the
       `sd-ai-command-pack-scope-advisory: ` marker on both warning paths.
4. [x] Bound the advisory call: add `timeout: 10_000` and
       `killSignal: 'SIGKILL'` to the `spawnSync` in `checkScopeAdvisory`
       (`templates/scripts/sd-ai-command-pack-review-preflight.mjs:3479`). The
       existing `result.error` guard at :3485 already handles expiry — Node sets
       `result.error` on timeout. Do not add a shell-side timeout; it would sit
       on the enforcing path too. This closes the timeout acceptance criterion by
       inspection, not by test: a behavioral test would have to stall a stub `gh`
       for the full 10s. Record it as inspection-verified rather than leaving it
       unmarked. In the same edit, correct the stale header comment at `:3467-3470`,
       which still says the advisory names the section "before any PR exists" —
       after this change it also runs with a PR present.
5. [x] `bash -n` the template, then `make sync` to regenerate the root
       `scripts/` mirror. Never edit the mirror by hand.
6. [x] Add the seven advisory cases to `tests/test_review_scope.py` per
       `design.md`. Cases 1-3 and 7 use `SD_AI_COMMAND_PACK_SCOPE_PR_BODY` /
       `SD_AI_COMMAND_PACK_SCOPE_CHECK_GH`; cases 4-6 use a `gh` stub on `PATH`
       modeled on `tests/test_review_scope.py:806-819`. Case 4 is the only
       script-level test covering the shipped resolved-body path — do not skip
       it. Case 6 stubs a sentinel-touching `gh` on an unscoped branch and
       asserts the sentinel is never created, which keeps the zero-scope early
       return from regressing into a `gh` call on every branch. Case 7 is
       `SCOPE_CHECK_GH=0` plus a *satisfying* body — the only proof of the
       explicit-body reordering.
7. [x] Add the preflight-level case to `tests/test_review_preflight.py`: scoped
       change plus a stubbed `gh` returning a satisfying body must yield a
       preflight run with zero warnings. This is the only test that proves the
       user-visible outcome the task is named for. It overrides the suite default
       from step 8 in its own env dict.
8. [x] Isolate every test from the developer's real `gh`, per the "Test isolation
       is suite-wide" section of `design.md`:
       - `tests/test_review_preflight.py`: add a `setUp` to `ReviewPreflightTests`
         that patches `SD_AI_COMMAND_PACK_SCOPE_CHECK_GH=0` into `os.environ` with
         `addCleanup`. Do **not** pin the ~37 call sites individually. Every
         preflight test has a scoped change, because `run_install` writes
         `.sd-ai-command-pack/manifest.json`, so every one of them would otherwise
         reach `gh`. No assertion changes: `unknown:gh_disabled` and
         `unknown:no_pr` emit identical advisory wording.
       - `tests/test_review_scope.py`: pin per test, and only advisory ones —
         `:192-215` is the only existing case that needs it. A suite-wide default
         here could rewrite an enforcing-mode expectation.
9. [x] Update `templates/docs/SD_AI_COMMAND_PACK.md:1871-1877` — the template,
       not the root mirror — to describe the new behavior and drop the "without
       contacting `gh` or a PR" promise.
10. [x] `make sync` again after the doc edit.
11. [x] Edit `manifest.json` to 0.56.5 by hand and add the matching top
       `CHANGELOG.md` heading. This must come **before** `make check`, not after:
       `full-check.sh:709-714` folds working-tree and staged paths into
       `payload_changed`, and `:745-758` appends "release version drift: shipped
       payload changed without manifest version bump" when the manifest diff
       carries no `"version":` line. Running `make check` on the edited tree with
       an unbumped manifest is a guaranteed failure, not a flake.
       `make release-prep` does not write either artifact:
       `.github/scripts/prepare-release.py:249-259` raises "shipped payload
       changed without a manifest version bump" when the manifest still matches
       the base. The bump is an input to both gates, not an output of either.
12. [x] `make check`, then `make release-prep` to validate the bump and refresh
       the fleet candidate ledger. release-prep runs last; earlier generation or
       sync changes invalidate its evidence (`CONTRIBUTING.md:96-97`). The
       candidate ledger is not a `make check` input — `full-check.sh` never reads
       `docs/fleet/candidate-validation.json` — so there is no ordering deadlock
       between the two gates.
13. [ ] After the PR exists and its body carries the scope section, re-run the
       preflight and record the warning count. This is the only live proof of
       the resolved-body path and the only way to close the last acceptance
       criterion; the local pre-PR run cannot reach it, because no PR exists
       yet. Expect `0 warning(s)` where 0.56.4 reported 1.

## Validation commands

In this order. `make check` runs *after* the manifest bump of step 11, because
the release version gate in `full-check.sh:745` fails on a changed payload with
an unbumped manifest.

```bash
bash -n templates/scripts/sd-ai-command-pack-review-scope.sh
make sync
.venv/bin/python -m unittest tests.test_review_scope tests.test_review_preflight -v
# step 11: hand-edit manifest.json to 0.56.5 and add the CHANGELOG heading
make check
make release-prep
```

## Execution notes

Two step-12 deviations, both recorded rather than silently absorbed:

- **The `make check` / `make release-prep` order in step 12 is wrong, and the
  C-11 refutation behind it was too narrow.** `full-check.sh` genuinely never
  reads `docs/fleet/candidate-validation.json`, so that half held. But
  `tests/test_surface_closure.py` runs the shipped-surface closure checker,
  which does read the ledger, and `make check` runs that test. The first
  `make check` after the step-11 bump therefore failed with a single finding,
  `provenance.candidate-stale`: "candidate ledger packVersion is '0.56.4';
  expected '0.56.5'". `make release-prep` refreshes the ledger, so the working
  order is release-prep, then `make check` — the reverse of what step 12 says.
  Re-run `make check` afterwards; release-prep touches only the ledger, so it
  converges in one pass.
- **`make release-prep` also failed on a defect this task did not introduce**:
  "`.trellis/tasks/07-30-upstream-task-start-branch-recording/task.json` field
  description must be a non-empty string". That task was parked on this branch
  in `dbb4c2c2` with an empty `description`, and it sits inside this branch's
  diff, so the gate is unavoidable here. Fixed by writing the description;
  the file keeps its no-trailing-newline convention.

## Named falsifiable check

Before the work: the new advisory behavior must be provably conditional, not
just quiet. Two runs of the installed script on the same scoped diff, differing
only in the PR body, must produce different output — one with no marker, one
with the marker. A change that silenced both, or neither, fails.

That pair must be run twice: once with the body supplied through
`SD_AI_COMMAND_PACK_SCOPE_PR_BODY`, and once with the body coming from a stubbed
`gh pr view`. Only the second exercises the code path that ships. A suite that
passes on the supplied-body pair alone proves nothing about the fix — it is the
same class of gap as the untested `set-branch` write path in the preceding task.

Second check: enforcing mode must be untouched. Every test in
`tests/test_review_scope.py` that exercises the non-advisory path must pass
without edits. Any required edit to an enforcing-mode test is a failure of the
compatibility requirement, not a test that needs updating.

### Result

Both halves ran and passed.

- Supplied body, run directly against the installed script: marker count 0 with
  a satisfying body, marker present without it.
- Stubbed `gh pr view`, the path that ships: covered by
  `test_review_scope_advisory_is_silent_when_resolved_body_satisfies` and
  `..._warns_when_resolved_body_lacks_section`.
  `.venv/bin/python -m unittest tests.test_review_scope tests.test_review_preflight`
  reports `Ran 108 tests ... OK`.
- The preflight-level case was additionally proven non-vacuous by rerunning it
  with the stub body changed to one that lacks the section: the same fixture
  reports `Review preflight: 0 failure(s), 1 warning(s)` and the advisory WARN
  line, against `0 warning(s)` with the satisfying body. The probe edit was
  reverted.
- Enforcing mode untouched: `git diff tests/` removes exactly three lines, all
  inside the advisory case at `:197`. No enforcing-mode test is in the diff.
- `make check` exits 0; `make release-prep` ends `==> Full check complete` with
  `release version gate: shipped payload changed; manifest version 0.56.4 ->
  0.56.5` and `candidate ledger: valid for the current pack payload and fleet`.

Step 13 remains open: it needs a PR to exist, so the resolved-body path is
proven here only against a stub, not against live `gh`.

## Review gates

- After step 3, re-read the diff against `design.md`'s token table; a token that
  reaches a `fail` in advisory mode is a contract break.
- After step 3, confirm the resolver contains no `fail` call and no unguarded
  subprocess, and that the advisory caller captures with `|| true`.
- After step 8, confirm `git diff` touches only advisory-mode tests. Any
  enforcing-mode test in the diff fails the compatibility requirement.

## Rollback points

- After step 5: revert the script and preflight templates, re-run `make sync`.
- After step 12: revert `manifest.json`, the top `CHANGELOG.md` heading, and
  `docs/fleet/candidate-validation.json`. No checklist step commits, so there is
  no release-prep commit to undo; the version bump is the only
  irreversible-feeling artifact and it is not published until the PR merges.

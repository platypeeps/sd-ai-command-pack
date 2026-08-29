# Implementation plan

Order matters: steps 1–6 are the fix PR; steps 7–11 are post-merge
demonstrations and observations; step 12 closes out. Validation commands
accompany each step; rollback point after every commit.

## 1. Re-enumerate the diff-scoped exposure (evidence, no edits)

- Read `runReviewPreflight`'s check registration list in
  `scripts/sd-ai-command-pack-review-preflight.mjs` and classify every
  registered check as diff-scoped (touches `currentChangedPaths`,
  `currentDiffSources`, `currentReviewDiffStats`, or a baseline-ref
  helper such as `unchangedFromBaseline`) or repo-wide.
- Write the enumeration to `research/diff-scope-enumeration.md` with, per
  family: check name, scoping mechanism, failure/skip disposition when a
  relevant path is absent from the diff, and whether the PRD snapshot
  already named it (expect at least the root-task base_branch rule as a
  post-snapshot addition).
- Also enumerate the validated path families (AC floor: `package.json`
  consistency family, journal family) from the same source pass, as a
  full evidence matrix — one row per registered check: check name, path
  family, scoping mechanism, failing/advisory disposition, and an
  EVIDENCE column to be filled in step 11 (the exact demo-run output or
  controlled local fixture output that exercised it, or the stated
  reason it is unreachable in CI). A row without evidence blocks
  completion. "At least one more family" is explicitly rejected by the
  PRD — the enumeration must be total.

Check: enumeration lists every `registerCheck`-style entry — count them
in source (`grep -c` the registration call) and require the research file
row count to match.

## 2. Edit `.github/workflows/tests.yml`

Per design.md "Workflow changes":

- Un-gate `Install review preflight coverage tooling`; update its comment.
- Insert `Validate event head` (id `validate-event-head`, unconditional)
  before the bookkeeping step: env `AFTER_SHA`, `EVENT_BASE_SHA: ${{
  github.event.pull_request.base.sha || github.event.before }}`,
  `EVENT_NAME`, `SD_AI_COMMAND_PACK_DEFAULT_BRANCH: ${{
  github.event.repository.default_branch }}`; body =
  1. fail-closed base guard: `git rev-parse --verify
     "$EVENT_BASE_SHA^{commit}"` must succeed, AND on push events
     `git merge-base --is-ancestor "$EVENT_BASE_SHA" "$AFTER_SHA"` must
     hold; otherwise print the diagnostic and `exit 1`. NO fallback base
     ever (empty-diff fail-open is the defect class this task closes);
  2. whitespace check `git diff --check "$EVENT_BASE_SHA...$AFTER_SHA"
     -- .trellis/tasks .trellis/workspace`;
  3. emit `coverage_expected=true` to `$GITHUB_OUTPUT`;
  4. c8-instrumented preflight with
     `SD_AI_COMMAND_PACK_REVIEW_PREFLIGHT_BASE_REF="$EVENT_BASE_SHA"`
     into the shared coverage temp dir (`--clean=false`).
- Shrink `Validate bookkeeping head` to the final-bundle half (drop its
  whitespace check, bare preflight invocation, and the now-moved env
  exports; keep `VALIDATION_MODE` logic, `BEFORE_SHA`/`AFTER_SHA`, and
  the `bookkeeping` gate). Shell variables do not cross steps: this step
  RE-DECLARES `c8_temp_dir` and the `c8_run` array byte-identical to the
  event-head step's (`--clean=false`, same `--temp-directory`, same
  `--include`).
- Change `Report review preflight JavaScript coverage` gate to
  `!cancelled() && steps.validate-event-head.outputs.coverage_expected ==
  'true'`; keep the zero-line hard gate.
- Extend `Summarize CI scope` with the event-head outcome.
- State the base semantics (PR base / push before / no fallback,
  fail-closed guard) in workflow
  comments — this is the written-down behavior several ACs require.

Check: `python3 -c "import yaml,sys; yaml.safe_load(open('.github/workflows/tests.yml'))"`
exits 0; `actionlint` if installed. Diff review: classifier step,
expensive-job gates, `check-ci-result.sh`, `main-push-scope`,
`auto-tag-release` all untouched (`git diff --stat` shows only
tests.yml).

## 3. Local replay of the invocation (pre-publication)

- On the task branch with a scratch commit adding a known-bad task record
  (broken doc reference), run
  `SD_AI_COMMAND_PACK_REVIEW_PREFLIGHT_BASE_REF=origin/main node
  scripts/sd-ai-command-pack-review-preflight.mjs` → expect the failure
  line; drop the scratch commit.
- Clean branch, same command → expect pass.
- Guard replay: run the step body's guard logic with an unverifiable
  `EVENT_BASE_SHA` (e.g. 40 zeros) → expect the fail-closed diagnostic,
  exit nonzero.
- Zero-line-guard negative probe: run the report step's body with an
  empty c8 temp directory → expect exit 1 with the zero-line diagnostic
  (`c8 measured zero lines`). This is the AC evidence that the guard can
  still fire; capture the output into `research/`.

Check: four replays, expected exit codes 1/0/1/1, decisive lines quoted
in the implementation log.

## 4. Repo gates

- `make test` (via .venv) — no Python test asserts the old workflow
  shape, but the suite guards the preflight itself; expect green.
- `node scripts/sd-ai-command-pack-review-preflight.mjs` on the intended
  diff — expect 0 failures.
- Release payload gate expectation: no manifest bump (workflow +
  `.github/scripts` are not payload). If `make test` / the PR gate
  disagrees, follow its verdict (bump + CHANGELOG) instead of arguing.

## 5. Publish the fix PR

- `sd-create-pr` flow: task artifacts (prd/design/implement + research)
  plus the workflow edit, single branch, PR against `main`.
- The fix PR is NOT the no-Trellis-or-documentation-path specimen (its
  diff carries this
  task's `.trellis/tasks/**` artifacts — Demo E below owns that AC). It
  DOES supply: full-mode run with `Validate event head` green over a
  diff that touches validated paths, c8 summary line with non-zero
  measured lines in full mode. Record run ID, mode, event action, step
  conclusions, c8 line into `research/evidence-fix-pr.md`.
- Converge Copilot review + CI; merge on user instruction (merge
  commit, per repo convention).

Rollback point: revert the single workflow commit restores today's
behavior byte-for-byte.

## 6. Post-merge sanity on main

- Observe the `main` push run for the merge commit: classifier output,
  `Validate event head` conclusion, and its `before_sha`/base value —
  this is the push-event base observation AC (base = `event.before`,
  stated in workflow comments). Record run ID + values.

## 7. Demo A — opened/full defect fails (PR #358 replay shape)

- Branch `demo/preflight-full-a` off `main`: add one task directory whose
  `prd.md` contains a broken repository-relative reference (the
  `4cd89b5e` shape). Open DRAFT PR, no reviewers.
- Expect: mode `full`, action `opened`, `Validate event head` fails with
  the path-reference rule, `CI Result` failure.
- Capture via Actions API into `research/evidence-demo-a.md`: run ID,
  classified mode + action, failing step + rule line, `CI Result`
  conclusion. Close PR, delete branch.

## 8. Demo B — bookkeeping defect fails; expensive lanes still skipped

- Branch `demo/preflight-full-b`: push 1 = one VALID planning filing →
  DRAFT PR → wait green (opened/full). Push 2 = add broken reference
  inside the same task's files only (bookkeeping-shaped diff) → expect
  mode `bookkeeping`, `Validate event head` fails, `CI Result` fails,
  AND unittest/lint/security show `skipped` (cost saving intact).
- Capture run ID, mode, reason, failing line, per-job conclusions. Close,
  delete branch.

## 9. Demo C — incremental-base construction, bookkeeping lane

- Branch `demo/preflight-full-c`: push 1 = valid parent task.json naming
  child directory + valid child task → green (full). Push 2 = delete the
  child directory ONLY → bookkeeping mode; PR-base diff still contains
  the parent record → parent/child link validation fails.
- Trap check from PRD notes: push 1 must be fully valid or push 2 routes
  full via `prior_success_missing` and the bookkeeping lane is never
  exercised.
- Capture: push 2's own incremental diff file list (only the deleted
  child's task.json) vs the PR-base diff (parent included) — this is the
  gap-2 isolation evidence — AND the base value the preflight actually
  used, read from the run's step log (the AC requires the base read from
  the run, not from workflow source). Close, delete branch.

## 10. Demo D — same construction, full lane

- Branch `demo/preflight-full-d`: as C, but push 2 also adds an inert
  `.github/demo-marker.txt` (plain text, not `.md`; NOT under
  `scripts/`, `templates/`, or `docs/`, which drift gates watch) so the
  diff shape forces `full` (`changed_path_not_bookkeeping`,
  `bookkeeping_ci_scope.py:217`). Expect the same parent-link failure
  under mode `full`.
- Capture, close, delete branch.

## 10b. Demo E — no-Trellis-or-documentation-path absence specimen

Precision note: the marker file is NOT outside every registered family —
`isSourceReviewPath()` counts it for `checkDiffSize`. The AC's literal
scope is "no `.trellis/**` and no documentation change", which this
satisfies; evidence must claim exactly that, not "touches nothing the
preflight sees".

- Branch `demo/preflight-full-e`: single commit adding only
  `.github/demo-marker.txt` (no `.trellis/**`, no documentation change).
  DRAFT PR → expect mode `full`, `Validate event head` green, `CI
  Result` green. This green run is the absence-AC evidence (the fix PR
  cannot supply it — its diff touches `.trellis/tasks/**`).
- Capture run ID, mode, step conclusions. Close, delete branch.

## 11. Remaining observations (no new runs)

- Branch protection: read required status checks via API → exactly
  `CI Result`. Record.
- Verify demo evidence covers: both modes fail closed, bookkeeping
  successor cost saving, opened-action coverage, absence specimen (Demo
  E), push base statement (step 6), c8 non-zero lines (step 5) plus the
  zero-line-guard negative probe (step 3).
- Complete the step-1 family matrix's evidence column: for each of the
  registered checks, cite the demo-run output that exercised it, or run
  a controlled local fixture through the same invocation path and cite
  that output (stating it is a local exercise), or state the reason the
  family is unreachable in CI. Every row filled, none waved through.
- Map every PRD acceptance criterion to its evidence file/line in
  `research/ac-map.md`; any AC without evidence blocks completion.

## 12. Finish

- Spec update: `.trellis/spec/tooling/` CI-scope/bookkeeping contract
  pages likely describe the bookkeeping-only preflight — update to the
  every-head contract (+ index routing if a new section).
- `task.py finish` flow: journal, commit task artifacts + evidence,
  archive after user confirmation, push main.

## Named verification (contract)

The check that catches this work being wrong: Demos A–D — four CI runs
that must FAIL for the stated reason in the stated mode, plus the fix
PR's own run that must PASS. Local replays are advisory only; the PRD
explicitly rejects them as acceptance evidence. Failure of any demo to
reproduce its expected mode (e.g. C classifying full) means the
construction is wrong — fix the construction, not the criterion.

# Demonstration evidence (2026-08-09, post-merge of PR #386 / 9252d01d)

Five throwaway DRAFT PRs off `main`, no reviewers requested, closed
unmerged and branches deleted after capture. All values below read from
the Actions API / job logs, not from workflow source.

## Demo A — opened, full mode, defect fails (PR #387, run 31291939696)

- Head `53061ff1`, event `pull_request`, `EVENT_ACTION: opened` (from the
  classify step env in the job log), `CI_SCOPE_MODE: full` (from the CI
  Result job env).
- Step conclusions: `Validate event head` **failure**; `Validate
  bookkeeping head` skipped; `Report review preflight JavaScript
  coverage` success (instrumentation attempted → reporter ran even on
  the failing head, zero-line guard satisfied by real data).
- Base: `EVENT_BASE_SHA: 9252d01d…` — the PR's base, on a head that HAS
  no previous push.
- Failing line: `FAIL .trellis/tasks/08-09-demo-preflight-gap-a/prd.md:8
  references missing path docs/demo-preflight-gap-does-not-exist.md.`
- `CI Result`: failure. This is the PR #358 `4cd89b5e` replay shape
  (broken repository-relative reference on a full head) — the head that
  used to merge green now fails closed. Satisfies AC 1, AC 2, AC 10.

## Demo B — bookkeeping mode, defect fails, cost saving intact (PR #388)

- Push 1 (run 31291955405): valid filing, conclusion success.
- Push 2 (run 31292345434): `CI_SCOPE_MODE: bookkeeping` (classifier
  `BEFORE_SHA: c370450f` = push-1 head), `Validate event head` used
  `EVENT_BASE_SHA: 9252d01d` (PR base).
- Failing line: `FAIL .trellis/tasks/08-09-demo-preflight-gap-b/prd.md:11
  references missing path docs/demo-preflight-gap-b-does-not-exist.md.`
- `CI Result`: failure; `unittest`/`lint`/`security`/`Release payload
  gate` all `skipped` — the fast lane's cost saving intact on the same
  run that fails validation. Satisfies AC 3 and AC 8.

## Demo C — incremental-base construction, bookkeeping lane (PR #389)

- Push 1 (run 31291978463): valid parent
  (`children: ["08-09-demo-preflight-gap-c-child"]`) + valid child,
  success.
- Push 2 (run 31292345966): deletes ONLY the child directory. Its own
  incremental window (`9b071e33..head`) contains nothing but the deleted
  child's files; the untouched parent record is visible only in the
  PR-base diff.
- `CI_SCOPE_MODE: bookkeeping`; validation base read from the run:
  `EVENT_BASE_SHA: 9252d01d` (PR base), while the classifier's
  incremental `BEFORE_SHA: 9b071e33` — the two windows shown distinct in
  one run.
- Failing line: `FAIL .trellis/tasks/08-09-demo-preflight-gap-c-parent/task.json
  field children references missing task 08-09-demo-preflight-gap-c-child.`
- `CI Result`: failure. Under the old `BEFORE_SHA` base this head merges
  green (locally reproduced in `local-replays.md` logic: only the PR
  base sees the parent). Satisfies AC 4.

## Demo D — same construction, full lane (PR #390, run 31292347063)

- Push 2 additionally adds `.github/demo-marker.txt` →
  `changed_path_not_bookkeeping` → `CI_SCOPE_MODE: full`.
- Same failing line for `08-09-demo-preflight-gap-d-parent`; same
  `EVENT_BASE_SHA: 9252d01d`. `CI Result`: failure. Both lanes evaluate
  the same base and catch the same construction. Satisfies AC 5.

## Demo E — no-Trellis-or-documentation-path specimen (PR #391, run 31292003371)

- Single commit adding only `.github/demo-marker.txt`. Mode full (all
  expensive lanes ran and passed). `Validate event head` success with
  `EVENT_BASE_SHA: 9252d01d`; the diff-scoped checks each reported their
  empty-set pass line (`no changed Trellis task metadata records require
  integrity checks.` etc.); `Review preflight: 0 failure(s)`.
- `CI Result`: success. Nothing fails closed on absence; the written
  statement lives in the `Validate event head` workflow comment block.
  Satisfies AC 7 and (with the comment) AC 14.

## Observations without new runs

- **Branch protection** (`branches/main/protection` API):
  `required_status_checks.contexts == ["CI Result"]`, `strict: true` —
  still the single required context. With Demos A–D showing failing
  validation → failing `CI Result` in both modes, AC 13 is satisfied.
- **Main push run** (31291862939, merge commit `9252d01d`, event
  `push`): `Validate event head` ran with
  `EVENT_BASE_SHA: 3c247269` == `github.event.before` == classifier
  `BEFORE_SHA` — the push base stated in the workflow and observed from
  a real `main` run (AC 12). Preflight: `0 failure(s)`; coverage
  `40.36% (2193/5433 lines)`. Run conclusion success (after one
  shell-coverage flake rerun, see below).
- **Single shared invocation** (AC 11): the steps invoking the preflight
  against the event head enumerate to exactly one — `Validate event
  head` (its single `"${c8_run[@]}" node …` invocation). The
  bookkeeping step's remaining invocation is `final-bundle`, a different
  validation unit (bundle receipt against BEFORE/AFTER), asserted
  disjoint by contract test
  `test_bookkeeping_lane_reuses_canonical_validators` (bookkeeping step
  must NOT contain the bare invocation or `…_BASE_REF`).

## Flake note (not this task's defect)

`Shell coverage` (not in `ci-result.needs`) failed twice tonight on
`test_completion_successor_finds_recent_anchor_in_long_history` under
kcov instrumentation (fix-PR run 31291158452 first attempt; main run
31291862939 first attempt); both reruns passed and the test passes
locally and in all three unittest lanes every time. Recurring
infrastructure flake — follow-up task filed at wrap-up.

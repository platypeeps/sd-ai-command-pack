# Design: run the preflight on every head, against the pull request's base

## Remedy choice

Three shapes were considered:

1. **Unconditional validation inside `ci-scope`** (chosen). Split the
   current `Validate bookkeeping head` step; the preflight half runs on
   every head with an event-appropriate base, the final-bundle half stays
   bookkeeping-gated.
2. A separate always-on validation job. Rejected: `ci-result`'s aggregate
   script (`check-ci-result.sh`) fails when `ci-scope` is not `success`
   BEFORE any mode dispatch, so validation inside `ci-scope` already
   propagates to the required context in both modes with zero
   permitted-state-table changes. A new job would need a new `needs` edge,
   a new permitted-state row per mode/event combination, and would move the
   c8 plumbing across a job boundary (artifact upload) for no gain.
3. Reusable workflow/composite action for the invocation. Rejected as
   unnecessary: after the split there is still exactly ONE step invoking
   the preflight against the event head, which satisfies the
   shared-definition criterion directly; a composite action adds a second
   file that can drift from its single caller.

The classifier, its schema, and its reason codes are untouched. Mode keeps
deciding which expensive jobs run; it stops deciding whether content is
validated.

## Workflow changes (`.github/workflows/tests.yml`, `ci-scope` job)

Step-by-step:

- `Install review preflight coverage tooling` (`npm ci`): drop the
  `bookkeeping` gate — runs on every head. The comment saying installation
  is gated "instead of paying npm cost on every full-mode run" is updated:
  the preflight now runs on every head, so the tooling does too. Cost is
  one lockfile-pinned `npm ci` (~seconds, no network fetch beyond cache).
- NEW step `Validate event head` (unconditional, replaces the preflight
  half of the old step):
  - Env: `AFTER_SHA` (classifier output, same as today),
    `EVENT_BASE_SHA: ${{ github.event.pull_request.base.sha ||
    github.event.before }}`, `SD_AI_COMMAND_PACK_DEFAULT_BRANCH` (existing
    export, moves here with the preflight),
    `EVENT_NAME`.
  - Base resolution, stated in the workflow:
    - `pull_request`: the pull request's base (`pull_request.base.sha`).
      The preflight turns the base into a three-dot `diff <base>...HEAD`
      (`review-preflight.mjs` branch-diff helper), so passing the base
      branch tip yields the merge-base diff — the pull request's own
      diff, closing gap 2. On `opened` heads `github.event.before` is not
      a commit; this value is defined for every PR event including
      `opened`.
    - `push`: `github.event.before` — the same value `BEFORE_SHA` carries
      today. This is a deliberate, now-written-down retention: a push run
      validates the pushed range. (The PRD's push-base criterion asks for
      an observation of an existing run, not a behavior change.)
    - Guard, fail-closed: `git rev-parse --verify
      "$EVENT_BASE_SHA^{commit}"` must succeed, and on `push` events
      `git merge-base --is-ancestor "$EVENT_BASE_SHA" "$AFTER_SHA"` must
      also hold (a non-ancestor `before` — force push — makes the
      three-dot "pushed range" claim false). Either miss FAILS the step
      with a stated diagnostic. No fallback base: substituting
      `AFTER_SHA` yields an empty diff that silently skips every
      diff-scoped check (the every-head guarantee fails open), and
      leaving the env unset hands resolution to a discovery chain whose
      last resort is an arbitrary sorted remote ref. A red run from a
      vanishing base is re-runnable and honest; a green run from an
      empty window is the exact defect this task exists to close.
      Reachability: PR `base.sha` is on a fetched branch under
      `fetch-depth: 0` and is effectively always present; the push
      trigger fires only for `main`, whose `before` is a real ancestor
      outside history rewrites.
  - Body: `git diff --check "$EVENT_BASE_SHA...$AFTER_SHA" --
    .trellis/tasks .trellis/workspace` (whitespace check moves here, now
    spanning the PR diff), then the c8-instrumented
    `SD_AI_COMMAND_PACK_REVIEW_PREFLIGHT_BASE_REF="$EVENT_BASE_SHA" node
    scripts/sd-ai-command-pack-review-preflight.mjs` — the single
    event-head invocation. (`EVENT_BASE_SHA` throughout — the step
    declares no `$BASE` alias, so `set -u` has nothing undefined to
    trip on.)
- `Validate bookkeeping head` shrinks to the final-bundle half and keeps
  its `bookkeeping` gate and its `BEFORE_SHA`/`AFTER_SHA` semantics
  unchanged: the bundle certifies the finalization delta between
  consecutive heads, which is inherently an incremental,
  trusted-predecessor question — the PR base would be wrong here. The
  `VALIDATION_MODE=none` no-op case is preserved. Its preflight
  invocations remain c8-instrumented into the same shared temp directory
  — and because shell variables do not cross Actions steps, the
  bookkeeping step re-declares `c8_temp_dir` and the `c8_run` array
  itself, byte-identical to the event-head step's (`--clean=false`, same
  `--temp-directory`, same `--include`), rather than assuming them.
- `Report review preflight JavaScript coverage`: gate becomes
  `!cancelled() && steps.validate-event-head.outputs.coverage_expected ==
  'true'`. The event-head step emits `coverage_expected=true` to
  `$GITHUB_OUTPUT` immediately BEFORE its first c8 invocation (after the
  base guard and whitespace check). A status function suppresses the
  implicit `success()`, so without this flag the reporter would run after
  a checkout/install/guard failure and the zero-line gate would misreport
  broken plumbing when instrumentation was never attempted. Once
  instrumentation was attempted, the zero-line hard gate stays authorized
  to fire — in both modes now.
- `Summarize CI scope`: gains the event-head validation outcome alongside
  the existing bookkeeping outcome.

No changes to: the classifier step, `check-ci-result.sh`, the expensive
jobs' `full` gates, `main-push-scope`, `auto-tag-release`, branch
protection (the required context stays `CI Result`).

### Scope tension: push events, resolved

The out-of-scope bullet "Changing `main`-push and release behaviour"
reads as protecting the two named mechanisms (`main-push-scope`'s
direct-push boundary, `auto-tag-release`'s full-aggregate requirement),
both untouched here. The requirement "must run on any head … regardless
of classified mode" plus "State the base for `push` events too —
`BEFORE_SHA` is the natural value there and may well remain correct"
affirmatively includes push heads, so the unconditional step validating
push runs with base `event.before` is the requirement, not scope creep.
Operational consequence, stated: a direct `main` push carrying invalid
Trellis content now produces a red `main` run (and `auto-tag-release`
skips on the failed aggregate, as its existing contract already says).
The 2026-08-08 post-archive incident (stale references pushed as
`6796eedb`, fixed by `3c247269`) would have been a red run under this
design — detection, not breakage; the local finish-work preflight remains
the pre-push gate and already catches these before push when run.

## Why the aggregate contract holds without edits

`check-ci-result.sh` exits 1 on `scope_result != "success"` before the
mode `case`. A failing event-head validation fails the `ci-scope` job,
which fails `CI Result` on both `full` and `bookkeeping` heads and on both
`pull_request` and `push` events. The permitted-state table
(07-24-add-bookkeeping-only-ci-fast-lane design.md) is about the OTHER
lanes' skipped/success combinations per mode; this change adds no lane and
alters no lane gating, so the table is untouched. The bookkeeping cost
saving survives: expensive jobs still key on `mode == 'full'`.

## The exposure this closes, re-derived (AC: enumerate from source)

At implementation time, re-enumerate the diff-scoped checks from
`runReviewPreflight`'s registration list by reaching into each body for
`currentChangedPaths` / `currentDiffSources` / `currentReviewDiffStats` /
baseline-ref helpers — do not copy the PRD's 2026-08-08 snapshot (three
diff-scoped failing checks + the journal hybrid whose
`unchangedFromBaseline` gate also silences the contradictory-fallback
rules; the root-task base_branch rule added 2026-08-08 by
08-06-task-create-base-branch-seed is a fourth diff-scoped failing check
the snapshot predates — proof the re-enumeration requirement is not
theoretical). Record the enumeration and each family's disposition in the
implementation log.

## Demonstrations (the observational ACs)

CI runs a PR's own workflow definition for same-repo branches, so
demonstrations run AFTER the fix lands on `main`, each from a throwaway
branch off `main`, as DRAFT pull requests that are closed unmerged and
their branches deleted once evidence (run IDs, classified mode, step
conclusions, bases — all read from the Actions API) is captured into this
task's `research/`. Planned sequence:

- **Demo A — opened/full head fails.** Branch adds one task record with a
  broken repository-relative documentation reference (the PR #358
  `4cd89b5e` shape, satisfying that replay AC). Open PR → the `opened`
  head classifies `full`, `Validate event head` runs against the PR base,
  `CI Result` fails. Evidence: run's classified mode, event action,
  failing step, failing rule line.
- **Demo B — bookkeeping head with a defect fails (existing coverage not
  traded away).** Branch push 1: valid planning filing → opened/full →
  green. Push 2 (synchronize, bookkeeping-shaped diff): adds the broken
  reference → classifies `bookkeeping` (prior head succeeded) → fails.
  Also evidences: expensive jobs skipped on that head (cost saving
  intact, read from job conclusions).
- **Demo C — incremental-base construction, bookkeeping lane.** Push 1:
  valid parent task.json naming a child directory + that child (both
  valid) → green. Push 2: delete the child directory only → bookkeeping
  mode; the PR-base diff contains the parent record, whose link
  validation now dangles → fails. The only task.json in push 2's own
  incremental window is the deleted child's (skipped as missing), so
  only the PR base can catch it — this isolates gap 2 exactly as the
  PRD's criterion requires.
- **Demo D — same construction, full lane.** As C, but push 2 also
  touches a non-bookkeeping path so the diff shape forces `full`. Fails
  the same way, proving the base is correct in both lanes (AC "both
  modes").
- **Demo E — no-defect absence specimen.** The fix PR CANNOT serve here:
  it carries this task's `.trellis/tasks/**` artifacts, so its diff
  touches validated paths. A separate draft PR changing only
  `.github/demo-marker.txt` (a plain-text non-documentation file — no
  `.trellis/**`, no `.md`) classifies `full` and must run green through
  `Validate event head` and `CI Result`. Its green run is the recorded
  absence evidence; the written-down behavior lives in the workflow
  comments + the preflight's own pass lines. Close unmerged like the
  others. (The fix PR still supplies the full-mode c8 non-zero-lines
  evidence.)
- **Observations without new runs:** branch-protection required contexts
  read via the API (still exactly `CI Result`); an existing `main` push
  run's classifier `before_sha` read from the Actions API (push base
  stated + observed); c8 summary line with non-zero measured lines in the
  fix PR's own full-mode run. The zero-line guard's ability to FIRE is
  proven separately by a controlled local negative probe: run the report
  step's body against an empty c8 temp directory and require exit 1 with
  the zero-line diagnostic (source inspection alone does not prove the
  negative path executes).

Draft PRs will trip the repo's own review conventions (Copilot
auto-request etc.) minimally: drafts, no reviewers requested, closed
after evidence capture.

## Testing (repo-local, pre-publication)

The workflow logic is bash-in-YAML; CI-shape unit tests are impractical
locally, so pre-publication checks are:

- `actionlint` if available (else `node --check` N/A — validate YAML via
  `python3 -c "import yaml; yaml.safe_load(...)"`).
- Local replay of the event-head invocation for each base case: PR-base
  simulation (`SD_AI_COMMAND_PACK_REVIEW_PREFLIGHT_BASE_REF=origin/main`
  on a branch carrying a known-bad record → fails; on clean branch →
  passes), guard replay (an unverifiable base value → the step body's
  fail-closed diagnostic, exit nonzero), and the zero-line-guard negative
  probe (report body against an empty c8 temp dir → exit 1 with the
  zero-line diagnostic).
- The real acceptance evidence is the demo-PR sequence above — CI-run
  observations, per the PRD's insistence that local runs do not satisfy
  the criteria.

## Rollout / rollback

Lands as one workflow-edit PR (plus task artifacts). No shipped-payload
change: `tests.yml` and `.github/scripts/**` are repo CI, not manifest
payload — no version bump, no changelog entry, no fleet ledger change
(the release payload gate on the PR will confirm; if it disagrees, bump
per its verdict). Rollback is a workflow-only revert restoring the
`bookkeeping` gates and the `BEFORE_SHA` base; no Trellis content or
script behavior changes to unwind. The demo PRs are never merged, so
rollback never involves them.

# Design — pin the bookkeeping CI classifier against the PR base

## Scope boundary

The `ci-scope` job's `Classify exact-head CI scope` step
(`.github/workflows/tests.yml:43-190`) and the acceptance table it feeds
(`.github/scripts/check-ci-result.sh`). Not the classifier's own logic —
`bookkeeping_ci_scope.py`'s fail-closed reasons are explicitly out of bounds per
R5. Not the retain-or-retire question; `07-28-consolidate-ci-fast-lane-trust-stack`
owns that, and this task's fix survives either answer.

## The attack, re-derived 2026-07-28

Confirmed line by line:

- `tests.yml:47` — `BEFORE_SHA: ${{ github.event.before || '' }}`. On a
  `pull_request` `synchronize` event that is the PR's **own previous head**.
- `tests.yml:127-129` — the bookkeeping lane engages on `pull_request` only when
  `EVENT_ACTION` is `synchronize`. So the fast lane's trust anchor is, by
  construction, a commit the PR author wrote.
- `tests.yml:138-147` — the guards check the `ls-tree` record's mode (`100644`),
  type (`blob`), and path. All three hold for any file the author commits.
- `tests.yml:148` — `git show "$BEFORE_SHA:.github/scripts/bookkeeping_ci_scope.py"`
  into `$RUNNER_TEMP`.
- `tests.yml:151` — `py_compile`. Confirms it parses, not what it does.
- `tests.yml:189` — `python3 "$classifier_file" "${classifier_args[@]}"`. The
  author's program decides the mode.
- `tests.yml:9-11` — `cancel-in-progress` for `pull_request`, so the tamper
  commit's own run is cancelled and never lints or tests the tampered file.
- `tests.yml:464-465` — `CI Result`, the single required context (`:464` job key,
  `:465` display name), then reports on whatever the author's classifier selected.

Nothing between `:138` and `:189` establishes **identity**. That is the entire
defect and the entire fix.

## Correction: `PROTECTED_REF` is not a base-branch anchor

`tests.yml:52` sets `PROTECTED_REF: ${{ github.ref }}`. For a `pull_request`
event `github.ref` is `refs/pull/<n>/merge` — the merge of the PR head into base,
which **contains the PR author's version of the classifier**. Reading the
classifier from `PROTECTED_REF` would not fix anything on the exact event type
where the fast lane engages.

(This corrects a note in `07-28-consolidate-ci-fast-lane-trust-stack/design.md`,
which suggested `PROTECTED_REF` as the trusted source. The PRD here is right and
that note was wrong.)

The classifier itself already treats `--protected-ref` as a push-path value only:
`bookkeeping_ci_scope.py:281` uses `pull_request:<n>` scope on PRs and consults
`protected_ref` only at `:305` and `:361-362`, both non-PR branches.

**The correct anchor is `github.event.pull_request.base.sha`**, exactly as this
PRD's requirement 2 states. It is not in the `ci-scope` job env today; the
`release-payload-gate` job already uses it (`tests.yml:410`) under the name
`BASE_SHA`, so the idiom exists in this file.

## Scope the guard to `pull_request`

For `push` to `main`, `github.event.before` is the previous tip of the protected
branch — a commit that already passed `CI Result` and branch protection. It is a
legitimate trust anchor and needs no identity check. The bookkeeping lane's
push path is not affected by A-038.

So the identity comparison is a `pull_request`-only guard. Applying it to push
events would require a base that does not exist and would add a failure mode
with no threat behind it.

## The fix shape: fail-closed through the existing idiom

The step already has one fail-closed vocabulary — `select_full "<reason_code>"`,
used by all **eight** existing pre-execution guards, at `:129`, `:132`, `:135`,
`:139`, `:142`, `:146`, `:149`, `:152`. (Re-measured 2026-07-29: an earlier draft
said "six" while listing eight anchors, four of which pointed at the guard's `if`
line rather than its `select_full` call.) The identity check joins it:

```
if [ "$EVENT_NAME" = "pull_request" ]; then
  if [ -z "$BASE_SHA" ]; then
    select_full "prior_classifier_identity_unavailable"
  fi
  if ! before_blob="$(git rev-parse "$BEFORE_SHA:.github/scripts/bookkeeping_ci_scope.py" 2>/dev/null)"; then
    select_full "prior_classifier_identity_unavailable"
  fi
  if ! base_blob="$(git rev-parse "$BASE_SHA:.github/scripts/bookkeeping_ci_scope.py" 2>/dev/null)"; then
    select_full "prior_classifier_identity_unavailable"
  fi
  if [ "$before_blob" != "$base_blob" ]; then
    select_full "prior_classifier_not_base_identical"
  fi
fi
```

Placed **before** `:148`'s `git show`, so a mismatching blob is never written to
`$classifier_file` and never executed.

Three parts of that snippet are load-bearing and an earlier draft of this section
had none of them. Corrected 2026-07-29 after the review lanes flagged it; the
draft showed two bare assignments and one comparison.

- **`EVENT_NAME` scoping.** Push events have no base sha and no threat (see the
  section above). Without the conditional the guard would fail every push.
- **`[ -z "$BASE_SHA" ]` first.** `git rev-parse ":<path>"` with an empty prefix
  is a valid *index* lookup that exits 0 and returns the working-tree blob.
  Measured in this repo: with `BASE_SHA=""` the lookup returned
  `0afbb094ab36fcd865c5a1d954bfd78736e846de`, identical to
  `HEAD:.github/scripts/bookkeeping_ci_scope.py`. So an unset base does not fail
  the lookup — it makes the comparison compare the attacker's blob against
  itself and pass. Nothing downstream would notice.
- **`if ! …; then select_full` on both lookups.** The step runs under
  `set -euo pipefail` (`tests.yml:55`), so a bare assignment from a failing
  command substitution aborts the step instead of selecting full. The `if !`
  block form matches all eight existing call sites; the postfix
  `|| select_full` form is equivalent because `select_full` exits, but the
  block form is what this file already reads like.

Two reason codes, not one: `prior_classifier_identity_unavailable` covers an
absent base sha and a missing blob on either side,
`prior_classifier_not_base_identical` covers a resolvable mismatch. Keeping them
distinct is what makes the step summary say which of the two happened.
Resolution failure must select full, not hard-fail — a hard `exit 1` here turns
an unfetched base into a broken required context rather than a slow one.

`reasonCode` must match the `publish_result` pattern at `:100`,
`test("^[a-z0-9_]{1,80}$")`.

Keep the existing `:139-147` mode/type/path guard and `:151`'s `py_compile`. The
PRD requires it and it costs nothing; identity subsumes them logically but they
fail earlier with better reason codes.

## R4 is satisfied by R1's shape, not by a ninth argument

R4 says `check-ci-result.sh:52` must not report success for a `pull_request`
whose heavy lanes were skipped under a classifier that failed the identity check.
Read against the fix above, **that state cannot occur**: failing the identity
check calls `select_full`, which writes `mode: "full"`, and the `full)` branch at
`:37-51` then requires `unittest`, `lint`, and `security` to have succeeded.
There is no path that reaches the `bookkeeping)` branch at `:52` with a failed
identity check.

Recommendation: **do not add a ninth argument.** The script's eight-argument
signature is already named as a complexity problem by A-100, and a ninth
parameter would encode a state the workflow cannot produce — untestable by
construction, and load-bearing only if someone later implements the identity
check as an advisory signal instead of a mode selector.

What AC3 should assert instead: given a PR whose first push tampers with the
classifier, `CI Result` fails. It will, because the mode is `full` and the heavy
lanes must then pass on the tampered branch — which is the outcome A-038 wants.
Write the acceptance test against that observable, not against a new argument.

If a reviewer wants genuine defense in depth here, the honest form is an
assertion inside `check-ci-result.sh` that `bookkeeping` mode is never paired
with a `pull_request` whose reason code is one of the identity-failure codes —
which requires passing the reason, not a boolean, and is still a second copy of
the same decision. Recorded as considered and declined.

## R3 moved out — why, and what the measurement was worth

**R3 left this task on 2026-07-29** for
`07-29-resolve-evidence-run-id-through-api`, by maintainer decision after the
planning adversarial review raised it as C-14. The measurements below are kept
because they are what justified the split, and because the new task's PRD cites
them.

The drafted fix — resolve the ID via `repos/.../actions/runs/<id>` and require
`head_sha == BEFORE_SHA` — was **weaker than the contract it was meant to
enforce**. `.trellis/spec/backend/quality-guidelines.md:1623-1626` requires the
prior head to have a completed successful `Tests` workflow plus a GitHub Actions
`CI Result` for the same head. A `head_sha` match alone accepts a failed run, or a
run of an unrelated workflow, on that SHA — and the trusted Python classifier
already checks more, at `.github/scripts/bookkeeping_ci_scope.py:290-292`
(`name == "Tests"`, `path`, `head_sha`) and `:318-320` (`name == "CI Result"`,
`head_sha`). Shipping the draft would have replaced a positive-integer check with
something weaker than what already runs.

Compounding it, the test group the plan named cannot reach the code:
`BookkeepingCiScopeTests.classify` calls `bookkeeping_ci_scope.classify` directly
(`tests/test_bookkeeping_ci_scope.py:158`), which is the Python classifier, not the
workflow's inline `gh api` block. Deciding whether to widen the inline check or
narrow the requirement needs its own planning pass. It does not belong inside a P0.

### The measurement that made the split safe

Re-measured 2026-07-29. An earlier draft of this section claimed `evidenceRunId`
had **exactly one** non-test consumer, a `printf` at `tests.yml:252`. Both halves
were wrong. The full consumer set:

```
tests.yml:115   printf 'evidence_run_id=%s\n' "$(jq -r '.evidenceRunId // ""' "$result_file")"   # $GITHUB_OUTPUT
tests.yml:31    evidence_run_id: ${{ steps.classify.outputs.evidence_run_id }}                    # ci-scope JOB OUTPUT
tests.yml:236   EVIDENCE_RUN_ID: ${{ steps.classify.outputs.evidence_run_id }}                    # Summarize step env
tests.yml:249   printf '%s\n' "- Prior evidence: … run ${EVIDENCE_RUN_ID:-none}; …"               # $GITHUB_STEP_SUMMARY
```

`tests.yml:252` is a different line (`- Expensive jobs avoided: …`).
`bookkeeping_ci_scope.py:74` produces the value.

The load-bearing conclusion survives: no job or step reads
`needs.ci-scope.outputs.evidence_run_id`, so nothing gates on it and this task's
P0 ships complete without R3. But it is a **published job output**, not a
step-local printf, so the blast radius of a bogus value is wider than the earlier
framing implied and a future consumer could gate on it. That is why the split-out
task is real work rather than a shelf item.

**Implementation hazard, carried to the new task.** From the Codex lane
2026-07-29: a full-mode result legitimately carries `evidenceRunId: null`
(`tests.yml:82`), and the step runs under `set -euo pipefail` (`tests.yml:55`). An
unconditional `gh api` lookup would therefore fail every full-mode run — turning a
hardening change into an outage on the common path. The lookup must be conditional
on a non-null ID, and lookup failure must route through `select_full`, not
`exit 1`. `07-29-resolve-evidence-run-id-through-api/prd.md` carries this as a
requirement.

The jq clause at `:105-106` does two different things and only one of them is an
evidence check:

- `(if .mode == "bookkeeping" then .evidenceRunId != null and .evidenceCheckRunId != null else true end)`
  — a bookkeeping decision must *claim* evidence. A tampered classifier satisfies
  this by emitting `1`.
- `.evidenceRunId > 0 and .evidenceRunId == (.evidenceRunId | floor)` — a shape
  check on a number.

So R3 as originally stated was accurate about the weakness and wrong about its
severity: it is a shape check presented as an evidence check, guarding a summary
line. It is **not on A-038's attack path**, and once R1 lands the classifier is
trusted code whose evidence fields derive from the trusted `gh api` calls at
`:155-170` (the two calls are at `:156` and `:163`).

That severity reading is exactly why it could be split without weakening this
task: R1 does not depend on it, nothing gates on the field, and A-038 stays closed
either way.

## Compatibility

No contract changes. `select_full` already exists, the result schema already
carries `reasonCode`, and every new code is additive within the existing
`^[a-z0-9_]{1,80}$` pattern. Consumers of `mode` see only more `full` and less
`bookkeeping` — a strictly conservative direction.

Cost: PRs that touch `bookkeeping_ci_scope.py` lose the fast lane for that PR.
Correct, and rare.

The one thing that must not regress is the false-positive rate on `push`, since
the guard does not apply there. Confirm the push path is untouched.

## Rollout and rollback

Two commits after the 2026-07-29 split, in strict priority order:

1. **R1/R2** — `BASE_SHA` into the `ci-scope` job env, identity check before
   `:148`, new reason codes. This is the P0 and now the whole substance of this
   task.
2. ~~**R3** — `evidenceRunId` API resolution.~~ Moved to
   `07-29-resolve-evidence-run-id-through-api`. An earlier version of this section
   planned three commits.
3. **R4** — nothing to do if the recommendation above holds; otherwise the
   `check-ci-result.sh` change, with its own rationale recorded.

Rollback is a plain revert of a workflow file. There is no persisted state and no
consumer outside this workflow. Reverting commit 1 restores the vulnerability, so
it should only happen alongside a decision to retire the lane entirely.

## Risk

The failure mode to guard against is a guard that **looks** applied and is not:
placed after `:148`'s `git show` (already executed), or scoped so that the
common `synchronize` case falls through to a branch that skips it, or hard-failing
on an unresolvable base so that the identity check is later relaxed to make CI
green again.

The mitigation is behavioral, not inspectional. AC1 requires a rehearsal: a PR
whose first push modifies `bookkeeping_ci_scope.py` and whose second push carries
payload changes must select `mode: full`. A-038 is P0 · Verified; do not close it
by reading the diff.

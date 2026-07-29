# Design — pin the bookkeeping CI classifier against the PR base

## Scope boundary

The `ci-scope` job's `Classify exact-head CI scope` step
(`.github/workflows/tests.yml:42-190`) and the acceptance table it feeds
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
- `tests.yml:463` — `CI Result`, the single required context, then reports on
  whatever the author's classifier selected.

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
used by all six existing guards at `:132`, `:135`, `:137`, `:139`, `:141`, `:147`,
`:149`, `:152`. The identity check joins it:

```
before_blob="$(git rev-parse "$BEFORE_SHA:.github/scripts/bookkeeping_ci_scope.py")"
base_blob="$(git rev-parse "$BASE_SHA:.github/scripts/bookkeeping_ci_scope.py")"
[ "$before_blob" = "$base_blob" ] || select_full "prior_classifier_not_base_identical"
```

Placed **before** `:148`'s `git show`, so a mismatching blob is never written to
`$classifier_file` and never executed. Three conditions collapse to the same
`select_full`: base sha unresolvable, blob missing on either side, blobs differ.
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

## R3 protects a display field

Measured 2026-07-28: `evidenceRunId` has **exactly one** non-test consumer.

```
tests.yml:252  printf '%s\n' "- Prior evidence: ${EVIDENCE_SCOPE:-none}; run ${EVIDENCE_RUN_ID:-none}; …"
```

A `printf` into `$GITHUB_STEP_SUMMARY`. Nothing gates on it. `bookkeeping_ci_scope.py:74`
produces it; no workflow step, script, or job condition reads it back.

The jq clause at `:105-106` does two different things and only one of them is an
evidence check:

- `(if .mode == "bookkeeping" then .evidenceRunId != null and .evidenceCheckRunId != null else true end)`
  — a bookkeeping decision must *claim* evidence. A tampered classifier satisfies
  this by emitting `1`.
- `.evidenceRunId > 0 and .evidenceRunId == (.evidenceRunId | floor)` — a shape
  check on a number.

So R3 as stated is accurate about the weakness and wrong about its severity: it
is a shape check presented as an evidence check, guarding a summary line. It is
**not on A-038's attack path**, and once R1 lands the classifier is trusted code
whose evidence fields derive from the trusted `gh api` calls at `:155-170`.

Implement it — resolving the ID via `repos/.../actions/runs/<id>` and requiring
`head_sha == BEFORE_SHA` is a few lines in an already-`gh`-authenticated step —
but **it must not gate or delay R1**. R1 is the P0. Separate commits.

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

Three commits, in strict priority order:

1. **R1/R2** — `BASE_SHA` into the `ci-scope` job env, identity check before
   `:148`, new reason codes. This is the P0. Ships alone.
2. **R3** — `evidenceRunId` API resolution. Independent, lower value.
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

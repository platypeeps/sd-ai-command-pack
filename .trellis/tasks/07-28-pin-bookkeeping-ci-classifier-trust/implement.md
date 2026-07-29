# Implementation — pin the bookkeeping CI classifier against the PR base

## Order

### Step 1 — R1/R2, the P0. Lands alone.

1. Add `BASE_SHA: ${{ github.event.pull_request.base.sha }}` to the classify
   step's `env` block at `.github/workflows/tests.yml:44-52`.

   **Not** `PROTECTED_REF`. `tests.yml:52` sets it from `github.ref`, which on a
   `pull_request` event is `refs/pull/<n>/merge` — the PR author's content merged
   into base. It is not a trust anchor on the one event type where the fast lane
   engages. `release-payload-gate` already uses `base.sha` under the name
   `BASE_SHA` at `tests.yml:410`; follow that.

2. Insert the identity guard **before** `tests.yml:148`'s
   `git show "$BEFORE_SHA:…"`, so a mismatching blob is never written to
   `$classifier_file` and never executed.

   ```bash
   before_blob="$(git rev-parse "$BEFORE_SHA:.github/scripts/bookkeeping_ci_scope.py" 2>/dev/null)" \
     || select_full "prior_classifier_identity_unavailable"
   base_blob="$(git rev-parse "$BASE_SHA:.github/scripts/bookkeeping_ci_scope.py" 2>/dev/null)" \
     || select_full "prior_classifier_identity_unavailable"
   [ "$before_blob" = "$base_blob" ] || select_full "prior_classifier_not_base_identical"
   ```

   **Gate:** ordering. The guard must precede the `git show`. See Validation —
   there is an offline test for this.

3. Scope it to `pull_request`. For `push` to `main`, `github.event.before` is the
   previous protected-branch tip, which already passed `CI Result`; there is no
   base sha and no threat. Guard with the event name rather than letting an empty
   `BASE_SHA` produce a spurious full-mode selection on every main push.

4. Resolution failure selects full — it does not `exit 1`. An unfetched or
   unresolvable base must make CI slow, not broken. (Contrast `tests.yml:412`'s
   `git cat-file -e`, which hard-fails; different job, different semantics.)

5. Reason codes must match `publish_result`'s pattern at `tests.yml:100`:
   `test("^[a-z0-9_]{1,80}$")`.

6. Keep the existing mode/type/path guard (`:139-147`) and `py_compile` (`:151`).
   R5 forbids weakening any fail-closed reason, and they fail earlier with more
   specific codes.

7. **Keep the guard inside the existing classify step.** Do not add a new
   workflow step. `tests/test_bookkeeping_ci_scope.py:559` indexes
   `jobs["ci-scope"]["steps"][2]` for `bookkeeping-validation`; inserting a step
   shifts that index and breaks a passing test for no reason.

### Step 2 — AC1, the rehearsal

8. Reproduce the attack shape against the hardened workflow: a PR whose **first**
   push modifies `bookkeeping_ci_scope.py` and whose **second** push carries
   payload changes. Confirm `mode: full`.

   **Gate:** A-038 is P0 · Verified. Do not close it on diff inspection. The
   rehearsal is the acceptance evidence.

9. Confirm the same PR now reports `CI Result` **failure** if the heavy lanes do
   not pass on the tampered branch (AC3). No change to `check-ci-result.sh` is
   needed for this — see step 12.

10. Confirm the `push`-to-`main` bookkeeping path is unaffected: a bookkeeping-only
    push still selects `mode: bookkeeping`.

### Step 3 — R3, separate commit, does not gate step 1

11. Resolve `evidenceRunId` through the API rather than accepting any positive
    integer: `gh api repos/${GITHUB_REPOSITORY}/actions/runs/<id>` and require
    `head_sha == BEFORE_SHA`. The step is already `gh`-authenticated
    (`tests.yml:155-170`).

    Scope note, measured: `evidenceRunId`'s only non-test consumer is a `printf`
    into `$GITHUB_STEP_SUMMARY` at `tests.yml:252`. Nothing gates on it. The jq
    clause at `:105-106` is a shape check plus a "must claim evidence" check that
    a tampered classifier satisfies by emitting `1`. This is worth doing and is
    **not** on A-038's attack path — do not let it delay step 1.

    `tests/test_bookkeeping_ci_scope.py:544` asserts the current jq text; update
    it with the change.

### Step 4 — R4

12. Expected outcome: **no change to `check-ci-result.sh`.** With step 2's shape,
    an identity failure selects `mode: full`, and `check-ci-result.sh:37-51` then
    requires the heavy lanes to have succeeded. The `bookkeeping)` branch at `:52`
    is unreachable with a failed identity check, so a ninth argument would encode
    a state the workflow cannot produce.

    Record that conclusion in the task rather than leaving R4 silently unaddressed.
    If a reviewer insists on defense in depth, the honest form passes the *reason
    code* and rejects `bookkeeping` mode paired with an identity-failure reason —
    a second copy of the same decision, and A-100 already names the eight-argument
    signature as a complexity problem.

### Step 5

13. Changelog + version.

## Validation

Decisive offline check — the guard exists and precedes the execution path. The
workflow-contract suite already parses `tests.yml` and asserts on the classify
step's text (`tests/test_bookkeeping_ci_scope.py:520-548`), so extend
`test_scope_job_is_read_only_prior_head_and_exact_event_head` with an ordering
assertion:

```bash
python3 -m pytest tests/test_bookkeeping_ci_scope.py -q
```

The assertion to add: `classify.index('git rev-parse "$BASE_SHA:')` is less than
`classify.index('git show "$BEFORE_SHA:')`. This is the only automated check that
catches "guard added, but after the `git show`" — the highest-probability defect
in this change.

Reason codes are valid under the publish gate:

```bash
grep -n "select_full \"prior_classifier" .github/workflows/tests.yml
```

Every code must match `^[a-z0-9_]{1,80}$`.

```bash
make check
```

**Not automatable:** AC1's rehearsal needs a real PR with two pushes against live
GitHub Actions. Step 2 is manual and must be run before the task is closed. The
offline tests above prove the guard is present and ordered; only the rehearsal
proves the attack no longer succeeds.

## Review gates

- Step 1 is reviewed as a security-boundary change, not a CI tweak. One reviewer
  confirms the guard precedes `:148` by reading the final file, not the diff.
- No new workflow **step** — the guard is inline (step 7).
- `push`-path behavior is confirmed unchanged before merge (step 10). The guard
  is `pull_request`-only by design; a regression here is a self-inflicted outage
  on `main`.
- Step 3 does not block step 1. If R3 stalls, ship step 1.
- R5: no existing fail-closed reason removed or loosened. Diff the guard list
  before and after.

## Rollback

Plain revert of a workflow file; no persisted state, no consumer outside this
workflow. Reverting step 1 restores the vulnerability, so it should only happen
together with a decision to retire the fast lane
(`07-28-consolidate-ci-fast-lane-trust-stack`) — not as a fix for a red build.

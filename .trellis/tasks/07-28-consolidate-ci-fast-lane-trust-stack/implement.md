# Implementation — consolidate or retire the bookkeeping CI fast-lane trust stack

## Order

### Step 0 — harden A-038 first, before the measurement

1. Stop materializing the classifier from `BEFORE_SHA`. `tests.yml:148` runs
   `git show "$BEFORE_SHA:.github/scripts/bookkeeping_ci_scope.py"`, and on
   `synchronize` `BEFORE_SHA` is the PR's own previous head (`tests.yml:47`).
   Compare its blob hash against the same path at `github.event.pull_request.base.sha`
   and select full mode on mismatch. The mode/type/path guard at `:145` and
   `py_compile` at `:151` do not establish identity.

   **Not `PROTECTED_REF`.** `tests.yml:52` sets it from `github.ref`, which on a
   `pull_request` event is `refs/pull/<n>/merge` — the PR author's own content.
   An earlier revision of this step named it; that was wrong.
   `07-28-pin-bookkeeping-ci-classifier-trust` owns this work in full detail; if
   both tasks are active, do it there and treat this step as a dependency.

   **Gate:** reproduce A-038's failure scenario against the hardened workflow and
   confirm it no longer succeeds. A-038 is P0 · Verified; do not close it on
   inspection alone.

   This step is not wasted if the lane is later retired, and it does not depend
   on any measurement. Land it alone.

### Step 1 — measure

2. Over a representative window of merged PRs, record: how many runs took the
   fast lane, wall-clock and billable minutes for those runs, and the same for
   full-matrix runs. Frequency and per-hit saving are both needed — a large
   per-hit saving on a rarely-taken lane is a small saving.

3. Write the number and the retain-or-retire decision into the task.
   **Gate:** the decision cites the measured number. This is R1 and AC1; a
   decision without the number does not satisfy it.

### Step 2A — if retired

4. Remove the skip path, the classifier materialization, `bookkeeping_ci_scope.py`
   (477 lines), and `check-ci-result.sh`'s eight-argument acceptance table
   (`:52`). Let all lanes run.

5. Confirm A-038 and A-041 are resolved by removal and record that explicitly, so
   neither is rediscovered as open.

### Step 2B — if retained

6. Move the receipt validation and the `ls-tree` guard out of the inline
   workflow bash beginning at `tests.yml:57` (~200 lines plus multi-clause jq)
   into `bookkeeping_ci_scope.py` as **one** entry point.

7. Unit-test that entry point. This is the point of the move: a `run:` block
   cannot be unit-tested, and `.github/scripts/*.py` becomes coverage-measured
   once `07-28-measure-unmeasured-runtime-surface` R1 lands.

8. Derive `check-ci-result.sh`'s acceptance table from the same source as the
   classification rather than hand-maintaining it beside it.
   **Gate:** no trust decision remains in inline workflow bash (AC2).

### Step 3 — A-041, either path

9. Add a `--print-allowed-prefixes` mode to the classifier and consume it from
   `.githooks/pre-push:54` and `.github/scripts/check-main-push-scope.sh:71`, so
   the three copies become one source.

10. **Decide `.trellis/audit/**` deliberately.** Both shell guards allow it;
    `bookkeeping_ci_scope.py:26` does not. Today an audit-ledger chore push
    passes both push guards and then pays the full matrix. Record the decision
    and its reasoning — this is a scope decision, not a typo fix.

11. Test on a path that distinguishes shell `case` globs from Python string
    prefixes; the unified value does not unify the matching semantics.

## Validation

Decisive check for step 0 — the classifier must come from the protected ref:

```bash
grep -n "BEFORE_SHA" .github/workflows/tests.yml
```

Expect no `git show "$BEFORE_SHA:...bookkeeping_ci_scope.py"`.

Decisive check for step 3 — one allowlist, three consumers:

```bash
grep -rn "trellis/tasks" .githooks/pre-push .github/scripts/check-main-push-scope.sh .github/scripts/bookkeeping_ci_scope.py
```

Expect exactly one literal definition.

```bash
python3 -m pytest tests/ -k "bookkeeping or ci_scope" -q
```

```bash
make check
```

## Review gates

- Step 0 lands first, alone, and is reviewed as a security-boundary change rather
  than a CI tweak. A-038's failure scenario is re-run, not reasoned about.
- Step 1's decision is not accepted without the measured number attached.
- If retained: no `run:` block still makes a trust decision (AC2).
- Step 10's `.trellis/audit/**` answer is written down either way. Silently
  aligning the third copy to the other two is a scope change made by accident.

## Rollback

Step 0 is a small diff to one workflow step and reverts cleanly. Step 2B is
revertable per commit. Step 2A (retirement) is the expensive one to undo —
restoring the lane means restoring the trust stack — so an ambiguous measurement
should resolve to retain-and-harden.

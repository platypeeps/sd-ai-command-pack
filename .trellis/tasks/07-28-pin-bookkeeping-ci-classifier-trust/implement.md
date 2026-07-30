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

   This is byte-identical to the snippet in `design.md`. Both were written in the
   postfix `cmd || select_full` form in an earlier draft and converted to the
   `if ! …; then select_full …; fi` block form 2026-07-29. Either works —
   `select_full` ends in `exit 0` (`tests.yml:121-125`), so the short-circuit is
   genuine — but all eight existing call sites (`:129`, `:132`, `:135`, `:139`,
   `:142`, `:146`, `:149`, `:152`) use the block form, and the Validation
   assertions below are written against behavior rather than either syntax.

   **Gate:** ordering. The guard must precede the `git show`. See Validation —
   there is an offline test for this.

   **Gate: the empty-`BASE_SHA` check is load-bearing and must not be dropped as
   redundant.** Measured 2026-07-29 — an empty `BASE_SHA` does *not* make
   `git rev-parse` fail:

   ```
   BASE_SHA=""; git rev-parse "$BASE_SHA:.github/scripts/bookkeeping_ci_scope.py"
     → 0afbb094ab36fcd865c5a1d954bfd78736e846de   exit=0
   git rev-parse "HEAD:.github/scripts/bookkeeping_ci_scope.py"
     → 0afbb094ab36fcd865c5a1d954bfd78736e846de   (identical)
   ```

   `:path` with an empty prefix is a valid **index** lookup. Without the emptiness
   check the guard silently compares `$BEFORE_SHA`'s blob against the checked-out
   index — a comparison with no base commit behind it, exit 0, no diagnostic, and
   `select_full` never reached. That is precisely the "guard looks applied and is
   not" failure `design.md` names under Risk.

3. The event guard in step 2's snippet is what scopes this to `pull_request`, and
   it is not optional. For `push` to `main`, `github.event.before` is the previous
   protected-branch tip, which already passed `CI Result`; there is no base sha and
   no threat.

   An earlier draft of this step justified the scoping by saying an empty
   `BASE_SHA` would "produce a spurious full-mode selection on every main push."
   That was wrong in the more dangerous direction — per the measurement above it
   produces no selection at all, just a meaningless comparison against the index.

4. Resolution failure selects full — it does not `exit 1`. An unfetched or
   unresolvable base must make CI slow, not broken. (Contrast `tests.yml:412`'s
   `git cat-file -e`, which hard-fails; different job, different semantics.)

5. Reason codes must match `publish_result`'s pattern at `tests.yml:100`:
   `test("^[a-z0-9_]{1,80}$")`.

6. Keep the existing mode/type/path guard (`:139-147`) and `py_compile` (`:151`).
   R5 forbids weakening any fail-closed reason, and they fail earlier with more
   specific codes.

7. **Keep the guard inside the existing classify step.** Do not add a new
   workflow step. `tests/test_bookkeeping_ci_scope.py:560` indexes
   `jobs["ci-scope"]["steps"][2]` for `bookkeeping-validation`; inserting a step
   shifts that index and breaks a passing test for no reason.

### Step 2 — AC1, the rehearsal

8. Reproduce the attack shape against the hardened workflow: a PR whose **first**
   push modifies `bookkeeping_ci_scope.py` and whose **second** push carries
   payload changes. Confirm `mode: full`.

   **Gate:** A-038 is P0 · Verified. Do not close it on diff inspection. The
   rehearsal is the acceptance evidence.

   **Done 2026-07-29. AC1 evidence captured.** Rehearsal PR #278,
   `rehearsal/a038-identity-guard` into this branch — deliberately not into `main`,
   which is possible because `pull_request:` at `.github/workflows/tests.yml:4`
   carries no branch filter. Basing on this branch means the base tree holds the
   guard and an untampered classifier, which is the comparison the guard makes.

   | push | head | event action | mode | reason |
   | --- | --- | --- | --- | --- |
   | 1 — tamper `bookkeeping_ci_scope.py` | `ad4cd325` | `opened` | `full` | `pull_request_action_not_synchronize` |
   | 2 — bookkeeping-eligible payload | `dbc6edc8` | `synchronize` | `full` | `prior_classifier_not_base_identical` |

   Push 2 is the A-038 attack shape: `BEFORE_SHA` was `ad4cd325`, the
   author-controlled tamper commit, and the changed-path increment was entirely
   under `.trellis/tasks/`, so it satisfied `ALLOWED_PATH_PREFIXES`
   (`.github/scripts/bookkeeping_ci_scope.py:30`) and the fast lane would have
   engaged had the guard not fired first. It selected `full` instead, and `lint`,
   `security`, `Release payload gate` and all three `unittest` matrix legs ran —
   which is the independent, observable signature of `full`, since `bookkeeping`
   skips them. Run `30515960389`, job `90785786135`.

   The tamper was a comment. The guard's condition is blob inequality, which a
   comment produces identically to a hostile rewrite, so the same code path and
   the same reason code are exercised. Reaching `mode: bookkeeping` from a hostile
   classifier would additionally require fabricating the evidence fields; that gap
   is `07-29-resolve-evidence-run-id-through-api`, not AC1.

9. Confirm the same PR now reports `CI Result` **failure** if the heavy lanes do
   not pass on the tampered branch (AC3). No change to `check-ci-result.sh` is
   needed for this — see step 12.

   **AC3's automated evidence already exists; cite it rather than staging a live
   skipped-lane run.** Verified 2026-07-29 —
   `tests/test_bookkeeping_ci_scope.py:505`
   (`test_rejects_failures_skips_and_impossible_combinations`) asserts exit 1 for

   ```python
   ("pull_request", "success", "full", "skipped", "success", "success", "success", "skipped")
   ```

   at `:508` — a `pull_request`, `mode=full`, heavy lane skipped. That is the AC3
   shape exactly. Note the literal PRD wording ("heavy lanes skipped under a
   classifier that failed the identity check") describes a state the fixed workflow
   cannot reach at all, because an identity failure selects `full` and the heavy
   lanes then run; see step 12. So AC3 closes on this existing unit assertion plus
   step 12's rationale, and a live rehearsal is required only for AC1.

10. Confirm the `push`-to-`main` bookkeeping path is unaffected: a bookkeeping-only
    push still selects `mode: bookkeeping`.

    **Not observable before merge, and deliberately not forced. Stated plainly
    rather than claimed.** `push:` is filtered to `branches: [main]`
    (`.github/workflows/tests.yml:6-8`), so the only event that exercises this path
    is a push to the default branch, and the hardened workflow does not exist on
    `main` until this branch merges. Two facts bound the risk in the meantime:

    - Correct by construction — the guard opens with
      `if [ "$EVENT_NAME" = "pull_request" ]`, so a `push` event never enters it and
      reaches `git show` exactly as before.
    - Asserted in source — `test_prior_classifier_is_pinned_to_the_pull_request_base`
      locates the guard *by* that conditional, so a guard moved outside it fails the
      test rather than passing quietly.

    Settle it post-merge on the first bookkeeping-only push to `main`: the `CI scope`
    job must report `mode: bookkeeping`. If it reports `full` with
    `prior_classifier_*`, the guard leaked out of the `pull_request` branch and this
    change must be reverted.

### Step 3 — R3 moved out of this task

11. **R3 is no longer in scope here.** Split to
    `.trellis/tasks/07-29-resolve-evidence-run-id-through-api/` on 2026-07-29 by
    maintainer decision, recorded as concern C-14 in this task's planning
    adversarial review.

    The reason it moved: R3 as drafted here required only
    `head_sha == BEFORE_SHA`, which is weaker than
    `.trellis/spec/backend/quality-guidelines.md:1623-1626` demands and weaker than
    the trusted classifier already enforces at
    `.github/scripts/bookkeeping_ci_scope.py:290-292` and `:318-320`. And the test
    group the plan named cannot reach the workflow block it would live in
    (`tests/test_bookkeeping_ci_scope.py:158` calls the Python classifier, not the
    inline `gh api` block). Deciding widen-vs-narrow needs its own planning pass;
    the new task carries the full evidence and the open decision.

    Nothing in step 1 depends on it. `evidenceRunId` is not on A-038's attack path
    and nothing reads `needs.ci-scope.outputs.evidence_run_id`, so this task's P0
    ships complete without R3.

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

13. **No changelog entry, no version bump, no mirror regeneration.**

    **Corrected at implementation time 2026-07-29 — this step previously said
    "Changelog entry only", and that was wrong.** `CHANGELOG.md` documents the
    shipped pack payload the fleet consumes, and the measurement below proves
    none of this task's edits are in that payload. There is also no valid place
    to put an entry. The repository has no `Unreleased` convention, and
    introducing one is actively harmful:
    `scripts/sd-ai-command-pack-full-check.sh:774-781` takes the **first** `## `
    line as the release heading, so an `## Unreleased` section would fail the
    changelog gate on the next real version bump. Appending to
    `## 0.56.3 - 2026-07-29` instead would misstate a released version that is
    currently mid-rollout to the fleet.

    Repo precedent agrees. Of the last eight commits touching
    `.github/workflows/tests.yml`, seven carried no changelog entry — including
    `e85f2550` ("fix: require prior evidence for bookkeeping CI"), the
    immediately prior hardening of this same classifier lane. The one that did,
    `b5a27635`, also bumped `manifest.json` and edited `templates/scripts/`, so
    its entry documents that payload change rather than the workflow.

    The file set this step must check is the set this plan actually edits:

    | Path | Edited by |
    | --- | --- |
    | `.github/workflows/tests.yml` | steps 1–2 (R1/R2) |
    | `tests/test_bookkeeping_ci_scope.py` | step 9 and Validation |

    `.github/scripts/bookkeeping_ci_scope.py` and
    `.github/scripts/check-ci-result.sh` are **read but not edited** — R5 forbids
    touching the former and step 12 declines the latter. An earlier draft of this
    step checked those two instead of the test and the changelog, which is the
    wrong evidence for the wrong claim. Re-measured 2026-07-29 against the real
    set:

    ```
    jq '..|strings|select(test("workflows/tests\\.yml|test_bookkeeping_ci_scope|CHANGELOG"))' manifest.json
      → empty            exit 0
    ls templates/.github/workflows/tests.yml \
       templates/tests/test_bookkeeping_ci_scope.py \
       templates/CHANGELOG.md
      → No such file or directory (all three)
    ```

    None of the three is in the shipped payload and none has a `templates/` twin,
    so `make check`'s release version gate reports no shipped payload change, no
    `templates/` mirror needs regenerating, and this task does not gate or
    reshuffle the 0.56.3 fleet rollout. An earlier draft of this step said
    "Changelog + version"; a version bump here would be a release with no payload
    behind it.

    **`make sync` is still required — an earlier draft of this step said
    "nothing needs `make sync`" and that was wrong.** `CONTRIBUTING.md:108-111`:
    run `make sync` "After changing shipped payload, **and before full-check
    after README, docs, spec, or task edits**". This task edits
    `.trellis/tasks/**`, so the second clause applies even though the first does
    not. `make sync` is `install.py . --force` plus
    `scripts/sd-ai-command-pack-update-spec-kb.py` (`Makefile`, `sync` target);
    it does **not** touch `.obsidian-kb`. Run it before `make check`, not after.

    Confirm at implementation time by reading the gate's own words in the
    `make check` output — `release version gate: no shipped payload changes
    detected` and `release changelog gate: manifest version unchanged` — rather
    than re-deriving it. If either line differs, the edit set grew beyond this
    plan and step 13 is wrong, not the gate.

    **`make check` writes outside this repository. Accepted by the maintainer
    2026-07-29 — expected behavior, run it normally.**
    `scripts/sd-ai-command-pack-full-check.sh` runs an Obsidian KB freshness check
    and, when it reports stale, refreshes the output automatically (`:530` check,
    `:557-561` refresh). In this checkout `.obsidian-kb` is a symlink:

    ```
    .obsidian-kb -> ~/Documents/<obsidian-vault>/raw/sd-ai-command-pack
    ```

    The auto-refresh is gated on the path being git-ignored, and it is
    (`git check-ignore -q -- .obsidian-kb` exits 0), so the write path is live,
    not hypothetical. AC4 is "`make check` passes", so satisfying AC4 means
    running a command that may write into `~/Documents/sdelmas-llm-wiki/`.

    This is a standing property of `make check` in this checkout rather than a
    defect introduced by this task, and it applies to every task in this repo.
    Recorded here because this task's acceptance criteria depend on it. Raised by
    the Codex lane as C-13b, put to the maintainer, and accepted: run `make check`
    normally and let the refresh happen. No `--check`-only workaround, no symlink
    relocation.

## Validation

Decisive offline check — the guard exists and precedes the execution path. The
workflow-contract suite already parses `tests.yml` and asserts on the classify
step's text (`tests/test_bookkeeping_ci_scope.py:525-548`, in the
`BookkeepingWorkflowContractTests` class that opens at `:520`), so extend
`test_scope_job_is_read_only_prior_head_and_exact_event_head` with an ordering
assertion:

```bash
bash scripts/sd-ai-command-pack-toolchain.sh run-python -- -m unittest tests.test_bookkeeping_ci_scope
```

This repo has no pytest — `.github/scripts/run-tests.sh:114` shards the suite as
`coverage run --parallel-mode -m unittest tests.<module>`. An earlier draft of
this section gave a `python3 -m pytest tests/test_bookkeeping_ci_scope.py -q`
command that cannot run here. Baseline before the change: `Ran 21 tests`, `OK`.

**One ordering assertion is not enough.** The Codex lane raised this 2026-07-29
and it is correct: a dead or advisory `rev-parse` line placed above the `git show`
satisfies an index-comparison test while execution still reaches the
attacker-controlled `git show` (`tests.yml:148`) and `python3 "$classifier_file"`
(`tests.yml:189`). The existing contract test is substring-based the same way
(`tests/test_bookkeeping_ci_scope.py:538`). Assert all five:

1. **Ordering** — `classify.index('git rev-parse "$BASE_SHA:')` <
   `classify.index('git show "$BEFORE_SHA:')`.
2. **`BASE_SHA` is wired in** — the classify step's `env` block contains
   `BASE_SHA: ${{ github.event.pull_request.base.sha }}`. Without this the guard
   compares against the index (see step 2's measurement) and the ordering
   assertion still passes.
3. **Emptiness check present** — the classify text tests `BASE_SHA` for emptiness
   before the first `git rev-parse "$BASE_SHA:`. Match **either** polarity:
   `[ -z "$BASE_SHA" ]` or `[ -n "$BASE_SHA" ]`. An earlier draft of this
   assertion demanded the literal `[ -n "$BASE_SHA" ]` while step 2's snippet
   used `[ -z "$BASE_SHA" ]` — the plan contradicted itself, and a correct
   implementation would have failed its own planned test. The snippet is the
   authority; this assertion follows it.
4. **Every failure path reaches `select_full`** — assert on *behavior*, not on
   either syntax. The guard block contains exactly **three** occurrences of
   `select_full "prior_classifier_identity_unavailable"` — empty base, `BEFORE_SHA`
   lookup, `BASE_SHA` lookup — and exactly one
   `select_full "prior_classifier_not_base_identical"`. Assert the exact counts,
   not "at least two": three is what the snippet produces, and a floor of two
   would pass a block that dropped the emptiness guard, which is the exact defect
   C-1 identified. Also assert that no `git rev-parse` of the classifier path
   appears in the block outside a construct reaching one of those calls. An
   earlier draft required the literal `|| select_full` postfix, which would have
   failed a correct implementation in the `if ! …; then select_full …; fi` block
   form that all eight existing call sites use. Assert on the guard block, not on
   the file as a whole.
5. **`pull_request`-scoped** — the guard block sits inside an
   `if [ "$EVENT_NAME" = "pull_request" ]` conditional.

Honest limit: all five are still text assertions over a YAML `run:` block. They
prove the guard is present, wired, ordered, and fail-closed in source. They cannot
prove it executes on the live event. Only AC1's rehearsal does that, which is why
step 8 is mandatory and not substitutable by this suite.

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
- R3 is no longer in this task (split 2026-07-29 to
  `07-29-resolve-evidence-run-id-through-api`), so nothing downstream can stall
  the P0. An earlier version of this list said "Step 3 does not block step 1".
- R5: no existing fail-closed reason removed or loosened. Diff the guard list
  before and after.

## Rollback

Plain revert of a workflow file; no persisted state, no consumer outside this
workflow. Reverting step 1 restores the vulnerability, so it should only happen
together with a decision to retire the fast lane
(`07-28-consolidate-ci-fast-lane-trust-stack`) — not as a fix for a red build.

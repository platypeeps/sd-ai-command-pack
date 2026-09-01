---
title: The shell-coverage lane runs the whole suite, so flakes read as coverage failures and two gates disagree about blocking
status: planning
parked: 2026-09-01 bulk-park (D2)
created: 2026-08-08
---
# The shell-coverage lane runs the whole test suite, so ordinary flakes fail a job that two gates disagree about

## Goal

Stop the shell-coverage lane from reporting general test failures as coverage
failures, and make one answer true for whether that lane blocks a merge. Today
the lane runs the entire suite and the two gates that read its result disagree:
GitHub branch protection ignores it, and the pack's own eligibility receipt
blocks on it.

## Problem

### The lane runs the whole suite, not a coverage measurement

`.github/workflows/tests.yml:461-474`:

```yaml
      - name: Measure shipped shell coverage
        # Routes the bash the subprocess tests spawn through kcov-bash-shim.sh
        # so kcov records which lines of the shipped shell the suite reaches.
        # This is a measurement-only lane: no floor is enforced (measure before
        # gating), and the report step fails only on a zero-line measurement.
        env:
          SD_AI_COMMAND_PACK_TEST_BASH: ${{ github.workspace }}/.github/scripts/kcov-bash-shim.sh
          ...
        run: |
          set -euo pipefail
          mkdir -p "$SD_AI_COMMAND_PACK_KCOV_DIR"
          python3 -m unittest discover -s tests -p 'test_*.py'
```

The comment is accurate about the *coverage floor* — none is enforced. It is
wrong about everything else. `report-shell-coverage.sh` (`:480`) does not fail
"only on a zero-line measurement": it exits 1 on an unset `SD_AI_COMMAND_PACK_KCOV_DIR`,
on finding no kcov run directories (`:21`), on a failed `kcov --merge` —
unguarded under `set -e` at `:26`, so it propagates kcov's own status — on no
`cobertura.xml` under the merged directory (`:38`), and on unreadable measurement
data (`:47`). And the comment is silent about the step *preceding* the report,
which runs the full suite under `set -euo pipefail` — so any failing test fails
that step and turns the job red before the report policy is consulted at all.

There are two structural differences between this lane and `unittest`. The
first is the strongest lead; neither is yet established as the cause.

**It bypasses the Git-maintenance guard.** The matrix job runs the suite through
`.github/scripts/run-tests.sh` (`tests.yml:385`), which exports
`maintenance.auto=false` and companions for every test subprocess
(`run-tests.sh:65-76`: `maintenance.auto`, `gc.auto`, and `receive.autogc`).
The comment there states the exact hazard:

```
# Git 2.54 can detach automatic maintenance after commits and pushes. The test
# suite creates and removes many short-lived repositories, so a detached repack
# can race either TemporaryDirectory cleanup or a cached fixture copy.
```

The shell-coverage lane does not use `run-tests.sh`. It calls
`python3 -m unittest discover` directly (`tests.yml:474`), so none of those
exports exist and detached maintenance is live. Both observed failures are
bookkeeping-validator tests that build real Git repositories — one creates 51
commits, the other deletes Git objects — which is precisely the workload the
guard was added to protect.

**It is the only single-process serial run.** The matrix shards; this lane runs
the whole suite in one interpreter in discovery order. That could also expose
ordering or shared-state coupling.

The kcov shim is *not* a candidate, though it is the intuitive guess.
`SD_AI_COMMAND_PACK_TEST_BASH` (`:467`) is read in exactly one place —
`tests/install_test_support.py:107`, feeding `_bash_path` at `:120` — which only
affects tests that spawn bash. Neither failing test does: both live in
`tests/test_bookkeeping_validator.py`, which contains no reference to bash and
drives the validator through `node` and `git` subprocesses. Any fix premised on
shim timing would be built on a cause that was never established.

### Two gates disagree about whether it blocks

`ci-result` is the aggregate branch-protection context, and its `needs` omits
this job (`:639`):

```yaml
    needs: [ci-scope, unittest, lint, security, release-payload-gate, main-push-scope]
```

with the intent stated at `:633-634`: "protection requires only 'CI Result' so
matrix or lane changes never strand a PR waiting on a renamed context." By that
path a red Shell coverage leaves the PR mergeable.

The pack's merge gate reads a different set.
`scripts/sd-ai-command-pack-pr-eligibility.py` parses the full
`statusCheckRollup` (`:457-509`, requested at `:561`) and counts a completed
check as blocking unless its conclusion is `SUCCESS`, `SKIPPED`, or `NEUTRAL`
(`:474-479`) — with no notion of whether branch protection requires it. A red
Shell coverage is `FAILURE`, so it blocks
`sd-ai-command-pack-housekeeping.sh`.

Both behaviours are defensible in isolation. Together they mean "does shell
coverage block the merge" has no single answer, and which one an operator sees
depends on which tool they ask.

## Evidence

Two failures observed on 2026-08-08, both only in the Shell coverage job:

| Run | PR | Test |
| --- | --- | --- |
| `31262580948` | #367 | `test_completion_successor_reports_unavailable_candidate_diff` |
| `31263603397` | #366 | `test_completion_successor_enforces_commit_bound` |

For each, on the same commit:

- every `unittest` matrix shard passed;
- the test passed locally on `main` via
  `bash scripts/sd-ai-command-pack-toolchain.sh run-python -- -m unittest ...`;
  and
- `gh run rerun --failed` passed with no code change.

Three independent signals for flakiness, and both tests build real Git
repositories — the workload `run-tests.sh`'s maintenance guard exists to protect
and that this lane runs without.

Both PRs needed a manual `gh run rerun --failed` before the housekeeping gate
would pass. Whether GitHub's own protection would have allowed the merge in that
state was not observed directly, but it follows from `ci-result`'s `needs` list:
the aggregate context does not depend on this job, so a red Shell coverage
cannot make `CI Result` red.

## Policy decision

The lane is advisory, and the fix should make that true everywhere rather than
promote it to required. The workflow says so in its own comment (`:464-465`:
"measure before gating"), there is no coverage floor to enforce, and the job
takes roughly ten minutes because kcov wraps every spawned bash (`:412`) — a
cost the project deliberately kept off the critical path.

That fixes the direction of requirement 2: eligibility must stop treating a red
Shell coverage as blocking, and `ci-result`'s `needs` list stays as it is. The
mechanism is a `design.md` question, but two candidates are already ruled out
here:

- **Emitting `NEUTRAL` from the job** does not solve the stated problem. It hides
  the failure from eligibility by never presenting one, so a genuine `FAILURE`
  conclusion would still block. Requirement 3 asks for the `FAILURE` case to be
  non-blocking.
- **Reading the repository's required-contexts from the GitHub API** is a general
  policy change to how eligibility treats every non-required check, which this
  task puts out of scope.

That leaves a narrow, explicit classification of advisory lanes inside
eligibility. `design.md` must justify whatever it picks against those two
rejections. Because the change touches the merge gate, this is a complex task:
it needs both `design.md` and `implement.md` before `task.py start`, per the
Trellis workflow's rule for complex tasks.

## Requirements

1. The lane keeps running the full suite — that is how the measurement is
   produced — but a suite failure is no longer presented as a coverage failure.
   The job name, step name, or failure output must make the distinction legible
   from the job summary alone.
2. Eligibility stops treating a `FAILURE` on this lane as blocking.
   `ci-result`'s `needs` list is unchanged.
3. The eligibility change fails closed: any check the mechanism does not
   explicitly classify as advisory still blocks. Advisory classification is by
   GitHub CheckRun name (`Shell coverage`), not by workflow job ID — `ci-result`'s
   `needs` list holds YAML job IDs (`tests.yml:639`) and the two namespaces are
   not interchangeable. The allow-list contains exactly one entry when this task
   lands.
4. The comment at `:464-465` is corrected on both counts: the report script's
   actual failure surface (`report-shell-coverage.sh:21`, `:38`, `:47`, plus an
   unguarded `kcov --merge` under `set -e` at `:26`) and the fact that the
   measure step runs the full suite and fails on any test failure.
5. The two observed failures are diagnosed before anything is suppressed. Test
   the Git-maintenance hypothesis first — it has a named mechanism and a
   one-line fix — by exporting `run-tests.sh`'s `GIT_CONFIG_*` values in this
   lane, or by routing it through `run-tests.sh`. Confirmation means the two
   named tests pass ten consecutive serial runs under the guard. Fall back to the
   ordering/shared-state hypothesis only if that does not hold.
6. If the fix changes which tests run in this lane, record the covered-line count
   before and after, state the delta, and explain any decrease. `kcov`, the shim, the include filter,
   and the absence of a floor stay as they are.

## Acceptance criteria

- A deliberately failing test in this lane produces output identifying it as a
  suite failure rather than a coverage shortfall, verifiable from the job summary
  alone.
- A synthetic `statusCheckRollup` carrying a `FAILURE` CheckRun named
  `Shell coverage` yields `checks.blockingCount == 0`, proven by a unit test —
  not by inspection of the workflow file. (`blockingCount` and `items` are the
  receipt's actual fields, `sd-ai-command-pack-pr-eligibility.py:864-868`.)
- The same test with any other check name still yields a nonzero
  `blockingCount`, including at least one name not in the allow-list. This is the
  fail-closed half of requirement 3 and must not be omitted.
- The workflow comment's two corrected claims are checked against
  `report-shell-coverage.sh` and the measure step by a reviewer, and the PR
  description quotes the before and after text. `make check` does not establish
  semantic accuracy and is not evidence for this criterion.
- Requirement 5's first hypothesis is settled either way: either the lane gains
  the Git-maintenance guard and the two tests pass ten consecutive serial runs
  under it, or the hypothesis is disproven with the evidence that disproved it
  and the second hypothesis is tested in turn. "Could not reproduce" alone does
  not close this.
- If and only if the test set changed, covered-line counts before and after are
  reported with the delta and any decrease explained.
- `make check` passes. If the change touches a shipped payload, the
  `templates/**` side is updated first and the root mirror re-verified
  (`AGENTS.md:29-33`).

## Out of scope

- Introducing a coverage floor. The lane is deliberately measure-before-gating.
- Redesigning eligibility's general policy on non-required checks. This task
  makes the two gates agree about *this* lane through the narrowest mechanism
  that fails closed.
- Rewriting the completion-successor tests' design. If diagnosis exposes a deeper
  coupling, file it as a follow-up rather than expanding here.

---
title: sd-review gates on a memoized check that reads live inputs
status: done
created: 2026-08-07
branch: fix/review-check-recompute-contract
---
# sd-review gates on a memoized check that reads live inputs

## Goal

Stop the review coordinator from gating on a stale typed `sd-check` report, so a
run that fixes the input a check actually reads — the live PR body — is not
blocked by the failure it just fixed.

The memoization of the expensive stages is correct and stays. Only the
deterministic check is wrong to cache, and only because a constituent check reads
an input the state identity deliberately does not capture.

## Current state, measured 2026-08-12 at pack 0.71.0

Half of this task shipped while it sat in the backlog, and the half that
shipped is the half the Problem section below is written about. Read that
section as the historical diagnosis it is; read this one for what is still
broken.

`47d5dfbb`, `fix(review): stop caching terminal-failure verdicts in attempt
state`, first tagged `v0.66.2`, introduced `_record_stage` and stopped
persisting a **failing** check. The gate now reads
(`run`, `templates/scripts/sd-ai-command-pack-review.py:1919-1932` — the file
is 2212 lines at this version, so every `v0.64.27` line number below is stale
and must be re-located by symbol):

```python
if state.get("check") is None:
    check = _run_check(repo)
    _record_stage(
        state_path, state, "check",
        resumable=isinstance(check, dict) and check.get("status") == "passed",
        check=check,
    )
```

So the shipped remedy is exactly the alternative this PRD records as
**rejected** below: reuse a cached check only when it passed. It fixes the
stale-failure direction and leaves the stale-pass direction untouched, which
is what the consolidation note already ruled on — "recompute wins, correctness
over reuse. Do not resurrect the reuse AC."

Measured, not inferred. Two invocations at one unchanged head, with
`_run_check` stubbed to return `passed` then `failed`:

| Invocation | Exit | Status | `_run_check` calls |
|---|---|---|---|
| first | 0 | `ready` | 1 |
| second | 0 | `ready` | 1 (not called again) |

The second run served the stored pass and proceeded, though the check it
claims to gate on would have failed. That is the live defect, and it is the
same shape as the original in reverse: `pack.review-scope` reads the live pull
request body, so a body that **loses** its scope heading after a passing check
— an operator editing the PR, a template regeneration, any edit at an
unchanged head — is reviewed as though the gate had passed.

What is already guarded, and must stay guarded:

- `test_failed_check_is_recomputed_on_the_next_invocation`
  (`tests/test_review_controller.py:1483`) pins the stale-failure fix.
- `test_unchanged_passing_stages_still_replay_from_the_cache` (same file,
  `:1524`) asserts `run_check.call_count == 1`. That assertion **is** the
  reuse contract this task supersedes, so the test must be split rather than
  deleted: the local and remote replay assertions it also makes are the
  memoization guarantee that has to survive.

The consumer evidence below is unchanged in substance but not in cost: since
`v0.66.2` a stale *failure* no longer replays, so the round-budget
exhaustion described under "Second consumer" is fixed. The two consumers
pinned at `0.64.3` are pinned by the whole 0.64→0.71 gap now, not by this
defect alone.

## Problem

> Citations are pinned to `v0.64.27`:
> `templates/scripts/sd-ai-command-pack-review.py` at 2091 lines, byte-identical
> to this repository's own installed `scripts/` copy. A bare `` `:NNN` `` means
> that file; citations into
> `templates/scripts/sd-ai-command-pack-check.py` and
> `templates/scripts/sd-ai-command-pack-review-scope.sh` name their path or say
> "same file". Each citation names its enclosing symbol — re-locate by symbol, not
> by line, on any other version.

`run` computes the check only when the persisted state has none, then gates on
whatever the state holds (`run`,
`templates/scripts/sd-ai-command-pack-review.py:1827-1830`):

```python
if state.get("check") is None:
    check = _run_check(repo)
    _advance(state_path, state, "check", check=check)
check = state["check"]
if not isinstance(check, dict) or check.get("status") != "passed":
    return 1, _report(..., limitations=("deterministic-check-not-passed",))
```

`state["check"]` is initialised to `None` (`:670`) and is **never invalidated
anywhere in the file** — the only other reads are the report projection
(`:1653`) and the gate above. So the first computed report is final for the life
of the attempt state.

### One blocking check reads an input the identity does not capture

The attempt identity (`_state_identity`, `:560-576`) records repository, scope,
head, base, `worktreeDigest`, `prNumber`, and controls. It does not record the
live PR body, and `worktreeDigest` excludes gitignored paths (`--exclude-standard`)
and is `None` for PR scope (`:1737`). Against that:

- **`pack.review-scope`** requires a recognized scope heading in the **live PR
  body**, fetched per run via `gh pr view --json body,title,url,state`
  (`resolve_pr_body_scope_state`,
  `templates/scripts/sd-ai-command-pack-review-scope.sh:211`) and failed when
  absent (`check_pr_body_scope`, same file `:290`). Hand-authoring that section changes the
  check's answer without changing `prNumber` or the head. This is the blocking
  case, and it alone is enough.

That is precisely the input an operator fixes *in response to* the check failing.
Caching the verdict means the fix cannot be observed.

`knowledge.obsidian-kb` is a second live-input check — its helper inspects the
gitignored `.obsidian-kb` target — but it is **not** a blocking example in the
common topology, and this task must not claim it is. `7865666c`, first shipped in
`v0.64.22`, downgrades a *failed* external-symlink KB freshness row to `skipped`,
and `skipped` is absent from `AGGREGATE_PRECEDENCE`, so it cannot contribute to
the aggregate verdict (`kb_freshness_row`,
`templates/scripts/sd-ai-command-pack-check.py:1033-1053`, and
`_is_external_symlink`, same file `:715-733`). This
repository's own `.obsidian-kb` and the cited consumer's are both external
symlinks, so for both the KB row can only be `skipped`, never blocking. It still
blocks for an in-repo symlink or a tracked directory, which is the only
configuration in which it demonstrates the defect.

Note what `7865666c` chose: it removed a non-deterministic input from the
blocking set rather than making the gate recompute. That precedent is real and is
addressed under Out of scope.

### The failure mode is a permanent block, not a delay

The post-finalization successor-head review is where this bites, and it is
structural rather than incidental. Planning finalization commits the journal and
workspace index, `pack.review-scope` fires on the successor head, the run
hand-authors the scope section — and a resumed review serves the cached failure.
There is no head change to invalidate it, because the body is what changed.

A consumer observed exactly this sequence: `pack.review-scope` failed twice
before the PR body gained a hand-authored `Tooling/generated scope` section, and
passed only on a third attempt. Under a cached gate the third attempt does not
pass either.

### A consumer has already fixed this, and this pack reverts the fix

`platypeeps/se-ai-command-pack` carries a committed local fix in its installed
copy — `bc01bc2`, `fix(review): recompute deterministic sd-check every run,
don't serve stale cache` — which extracts a `_resolve_check` helper. Behaviourally:
it runs the check unconditionally, persists the fresh report either as the first
phase advance or as an in-place state update, and returns it. Read the commit for
the implementation; this PRD deliberately does not restate it, because how to
write the helper is a design decision and not a requirement.

It persists the fresh report without regressing the phase on resume, and leaves
the local and remote stages memoized because their inputs *are* captured by
`worktreeDigest`/head. It ships with five guard tests — `ResolveCheckTest` in
that repository's `test_review_coordinator.py`, under its `tests/` tree, not a
path in this one — and that commit records
`test_stale_cached_failure_is_recomputed_fresh` as proven to fail against the
pre-fix caching. That is the consumer's own criterion numbering in `bc01bc2`, not
this PRD's — do not map them onto each other.

Those tests stub `_run_check` and assert against synthetic passed and failed
reports. They pin the recompute-and-persist contract, which is what this task
needs from them; they do not exercise a real `pack.review-scope` or
`knowledge.obsidian-kb` failure, so they are not evidence that the live-input
failure reproduces end to end. The acceptance criteria below require that
separately.

The symbol `_resolve_check` exists in no version of this pack — checked all 33
`v0.6*` tags across 1975 commits. Because the file is `install: "always"`, every
refresh of that consumer reverts the fix. Confirmed on 2026-08-07: refreshing it
from `0.64.3` to `0.64.27` removed `_resolve_check` and errored all five tests,
so the refresh was reverted and the consumer is still on `0.64.3`.

The gap is **23 tagged releases**, not 24: `v0.64.4` through `v0.64.27` with
`v0.64.25` never tagged. Twenty-four is the patch-number delta and is the wrong
number to quote.

That is the operative cost. The bug is not merely unfixed here; it is actively
holding a consumer back from every other fix in those 23 releases.

## Requirements

- The deterministic `sd-check` must be recomputed on every coordinator
  invocation rather than gated on a persisted report. There is one call site
  (`_run_check`, `:690`, called once from `run` at `:1828`); this requirement is
  not about a second code path.
- The coordinator's gate must agree with what a direct `sd-check` run reports on
  the same tree at the same moment. The coordinator invokes `sd-check` as a
  subprocess and then memoizes the returned report; the direct CLI holds no
  durable state, so only the coordinator can diverge. Closing that divergence is
  the requirement. "Nested" in the consumer's test names means this
  coordinator-mediated invocation, not a separate branch inside the coordinator.
- The fresh report must still be persisted for reporting, and persisting it must
  not regress the attempt phase on a resume.
- The expensive local and remote stages must remain memoized. Their inputs are
  captured by `worktreeDigest`/head, and recomputing them is the cost this state
  exists to avoid.
- A PR body with no scope section must still block. The fix removes stale
  *passes* as well as stale failures.
- Add regression coverage that fails against the current caching behaviour and
  passes after the change. At least one test must assert that a cached failure
  is recomputed fresh when the live input has changed at an unchanged head.
- State in the change whether the consumer's local fork is now redundant, so
  that repository can drop its fork rather than carrying it indefinitely.

## Acceptance Criteria

Renumbered 2026-08-12 against the measured current state. The stale-failure
criteria are kept as regression guards rather than deleted: they describe
behaviour `v0.66.2` shipped, and a recompute contract that broke them would be
a regression, not a simplification.

- [x] **The live defect.** A stored passing check at an unchanged head is
      recomputed, and a run whose live input has since broken is blocked.
      Two pieces of evidence, because one cannot live where the other does:
      a repository test that stubs `_run_check` and pins the recompute
      contract, **and** a measurement recorded in this task against
      `pack.review-scope` with a real pull-request body that loses its scope
      heading between two coordinator runs at one head. The stub cannot show
      that the live input is what moved; the measurement cannot live in a suite
      that must run without network or a pull request. Neither alone satisfies
      this criterion.
- [x] **Regression guard, already shipped.** A failing check at an unchanged
      head is still recomputed, and a run that fixed the live input still
      proceeds. `test_failed_check_is_recomputed_on_the_next_invocation` must
      still pass unmodified.
- [x] The coordinator's gate verdict equals a direct `sd-check` run's verdict on
      the same tree, for both a pass and a fail, with the coordinator's state
      pre-seeded to the opposite verdict in each case. Exercise the real
      subprocess, not a stubbed `_run_check`, since a stub cannot show the two
      agreeing.
- [x] The attempt phase does not regress when a resumed run recomputes the
      check. `_record_stage(resumable=True)` delegates to `_advance`, which
      assigns `state["phase"]` unconditionally, so a resume that already
      reached `capability` or `local` would be rewound to `check` by a naive
      unconditional recompute. Assert the phase of a resumed run explicitly.
- [x] Local and remote stage results are still served from state on a resume,
      verified by asserting they are not recomputed. The existing
      `test_unchanged_passing_stages_still_replay_from_the_cache` must be split
      so its local/remote assertions survive and its
      `run_check.call_count == 1` assertion is replaced by the recompute
      contract.
- [x] At least one new test is shown to fail against the pre-change code and
      pass after it. Demonstrated, not asserted. The stale-pass test is the one
      that must be shown failing.
- [x] The change states whether `platypeeps/se-ai-command-pack`'s `_resolve_check`
      fork is now redundant, verified by running that fork's `ResolveCheckTest`
      suite against the shipped file in a throwaway clone. Converting the
      consumer itself is out of scope: mutating a repository outside this one
      needs explicit per-cohort authorization, so a gap found here is filed as a
      follow-up, not fixed by this task.

### Verification, measured 2026-08-12 at pack version 0.71.1

The live measurement, taken against this task's own pull request (#430) at
head `60e5d7f4` under one attempt id `review-aa43432067b5966f9f46b38c`. No
commit was made between the runs; only the GitHub pull-request body changed,
which is the point — the remediated artifact does not live in the working tree
at all.

| Run | Pull-request body | Exit | Status | `check` |
|---|---|---|---|---|
| 1 | scope section present | 0 | `ready` | `passed` |
| 2 | scope section removed | 1 | `blocked` | `failed`, row `pack.review-scope` |
| 3 | scope section restored | 0 | `ready` | `passed` |

Run 2 is the criterion: before this change the stored pass was served and the
gate reported `ready` for a body it had never seen. Run 3 costs no numbered
attempt — the attempt id is unchanged across all three.

Repository tests, `tests/test_review_controller.py`, 43 tests OK:

- `test_stored_passing_check_is_recomputed_and_can_still_block` — the
  stale-pass direction, stubbed.
- `test_the_gate_agrees_with_a_direct_check_run_in_both_directions` — the real
  subprocess, via `CHECK_SCRIPT` pointed at a fixture helper whose verdict
  turns on a file outside the attempt key, with the state pre-seeded to the
  opposite verdict in each direction.
- `test_recomputing_the_check_does_not_rewind_the_attempt_phase` — the phase
  assertion.
- `test_unchanged_passing_stages_still_replay_except_the_check` — the split;
  `run_check.call_count == 2` while `run_local.call_count == 1`.
- `test_failed_check_is_recomputed_on_the_next_invocation` — unmodified, still
  passing.

Run against the pre-change source with the new tests in place: 3 of the 4
failed, including both directions of the real-subprocess test. The fourth
(phase) passed pre-change, because code that never recomputed could not rewind
anything — it guards the new path rather than reproducing the old defect.

`make check` and `make release-prep` both exit 0.

**The consumer fork is gone, so redundancy is moot.** Measured in a throwaway
clone of `platypeeps/se-ai-command-pack` at `b6d19a0`: `_resolve_check` is
absent from its tree and its installed pack is **0.64.33**, not the `0.64.3`
this PRD recorded. It dropped the fork and refreshed forward on its own. Its
`ResolveCheckTest` suite could therefore not be run against the shipped file —
the suite no longer exists there, and that is the answer to the question the
criterion asked rather than a gap in the evidence. What remains for that
consumer is an ordinary version gap: its installed coordinator still carries
`if state.get("check") is None:` and has no `_record_stage`, so it holds
neither the `v0.66.2` fix nor this one until it refreshes past the release
carrying them. Nothing here changes that repository.

Dropped on 2026-08-12, with reasons:

- The `knowledge.obsidian-kb` criterion. It asked for the stale-**failure**
  direction under an in-repo symlink or tracked `.obsidian-kb`; `v0.66.2`
  already fixed that direction for every check, and the repository's own KB is
  an external symlink whose failure `7865666c` downgrades to `skipped`.
  Constructing a tracked-KB topology to re-demonstrate a shipped fix buys
  nothing the first regression-guard criterion does not already cover. The
  stale-**pass** direction is covered by the criterion above it, against the
  check that actually blocks.
- The consumer-refresh criterion, as written ("can refresh past `0.64.27` with
  its fork removed"), asserted an outcome in another repository. It is
  restated above as a verification this repository can actually perform.

## Out of scope

- Changing what the typed `sd-check` checks, or the behaviour of
  `knowledge.obsidian-kb` and `pack.review-scope` themselves.
- Extending the attempt identity to capture the PR body or the KB target.
  Recomputing a cheap idempotent gate is the smaller change; making identity
  capture live external state is a larger design with its own tradeoffs. If that
  is preferred, it needs its own justification.
- Downgrading `pack.review-scope` to advisory the way `7865666c` downgraded
  external-symlink KB freshness. That precedent exists in this pack and is the
  obvious third option, so state why it does not transfer rather than leaving it
  unaddressed: an external vault's freshness is genuinely non-deterministic and
  never shipped, whereas an absent scope section in a PR body is a deterministic
  fact about the PR under review and is exactly what the gate is for. Making it
  advisory would delete the check rather than fix the cache. If someone wants that
  outcome anyway, it is a separate decision with a separate justification.
- Memoizing the local or remote stages differently.
- The consumer's own record of its fork, which is tracked there as
  `08-07-review-py-local-fork`.

## Notes

- Found from a consumer on 2026-08-07, the same route as the three defects filed
  in `6f810484` from auditing `hoa-manager`. The consumer's install audit could
  not surface the fork: provenance records installed hashes and the consumer
  deliberately re-recorded its own after the fix, so
  `install.py --check --audit` reports "vouched file hashes match" against a
  file that differs from its template by 26 changed lines. Worth knowing when reasoning
  about what a consumer is actually running; it is not a defect in this task's
  scope.
- The consumer's fix is the reference implementation and its commit message is
  the fullest existing statement of the defect. Read `bc01bc2` before designing
  a different remedy.
- Planning depth: PRD-only. The remedy is one extracted function with an
  established reference implementation and a bounded test surface, which is the
  lightweight case the workflow contract allows. This PRD states behaviour and
  constraints only — the helper's implementation is deliberately left to `bc01bc2`
  and to the implementing change, so that the requirements stay free of technical
  design. The one genuine alternative, downgrading the check to advisory, is named
  under Out of scope with its reason rather than explored here; if it is preferred,
  that reopens the task as a design question and wants a `design.md`.

## Absorbed: 08-06-review-check-receipt-pinning (2026-08-08 consolidation)

That task filed the same defect from the coordinator side: a stored `check`
result whose status is not `passed` is replayed indefinitely
(`scripts/sd-ai-command-pack-review.py:1796` caches a failed result exactly
like a passing one; `--attempt N` does not escape because the attempt ID
derives from head plus controls).

Carried as regression evidence only — three observed occurrences, each as
fail / repair out-of-band / re-invoke / observe pass:

- PR #338: `knowledge.obsidian-kb` failed on gitignored `.obsidian-kb/` state;
  repaired by `scripts/sd-ai-command-pack-update-spec-kb.py` with no commit;
  attempts 3, 4, 5 replayed the byte-identical stale diagnostic
  (`attemptId review-2b627e56c0dd09b5851e97dd`); only a fresh
  `--artifact-root` re-ran live and passed.
- PR #339: `pack.review-scope` failed on the pull request body (remote state);
  repaired via `gh pr edit --body-file`; re-run at the same head `b4b6f028`
  replayed the stale diagnostic; fresh `--artifact-root` passed.
- PR #361 (`platypeeps/anomaly-metric-creator`): same `knowledge.obsidian-kb`
  shape in a consumer repo; a fresh `--attempt-id` cleared it, localizing the
  cache key to the attempt ID.

Regression tests must cover the local-gitignored and remote-PR-body sequences.
Policy conflict resolved at consolidation: the source's cached-pass-reuse AC
("a passing check on an unchanged head is still reused") is superseded by this
task's recompute contract — recompute wins, correctness over reuse. Do not
resurrect the reuse AC.

## Second consumer, and a cost this PRD does not yet name (2026-08-09)

`platypeeps/sd-github-review` hit this independently, five times, while still on
`0.64.3`. It is a second consumer held at that version, distinct from the
`se-ai-command-pack` fork described above; it carries no local fork, because its
own `pack.install-audit` blocks one — `LOCAL_ALLOWED_PACK_FILES` covers only
`.sd-ai-command-pack/*.json`, so the reference fix has no sanctioned home there.
That closes off the workaround the other consumer used, which is why the defect
is being pushed back here rather than patched locally again.

### The replay consumes the round budget, so it manufactures an operator gate

This is the part the PRD's "permanent block, not a delay" section understates.
The `remoteIntegration` roundLimit refusal fires in `run` **before** the state
file is loaded, so a spent attempt is spent whether or not it ever reached the
cache. Attempts that exist only to prove the replay still count.

Observed on that consumer's PR #71 at head `d9e31e9`, subject
`pack.review-scope`:

| Attempt | Result |
| --- | --- |
| 3 | `failed`, `durationMs: 733` |
| 4 | `failed`, `durationMs: 733` |
| 5 | `failed`, `durationMs: 733` |
| 6 | `status: invalid`, `phase: setup` — "attempt exceeds remoteIntegration roundLimit; record the structured review.round-extension decision before continuing" |
| 3 (fresh `--attempt-id`) | `ready`, `durationMs: 858` |

Byte-identical `durationMs` across 3/4/5 is the replay evidence; the differing
`858` on the escape run is the live re-execution. Attempts 4 and 5 ran no
provider and revealed nothing.

So the failure mode compounds: a stale cache that merely delayed a run now
exhausts the round budget and demands a human `review.round-extension` decision
for a check that was already remediated. Any acceptance criterion for this task
should assert that escaping a replay costs no numbered attempt — recomputing at
the **same** attempt number must reach the live result.

### The remediated subject can live entirely outside the working tree

The PRD's `pack.review-scope` analysis is confirmed and should be strengthened:
the remediated artifact was the GitHub pull-request body, regenerated with this
pack's own `sd-ai-command-pack-pr-body-scope.py --prepare-tooling-body` and
applied via `gh pr edit --body-file`. No tracked file changed, so the head stayed
`d9e31e9` — the subject is further outside the content digest than a gitignored
path, because it does not live in the working tree at all.

Four earlier recurrences on that consumer (PRs #41, #68, #70, and one between)
were `knowledge.obsidian-kb` against an **external symlink**. Per `7865666c`
those would now downgrade to `skipped` rather than block, which is consistent
with this PRD's read; they are recorded as replay evidence, not as blocking
cases.

### A rejected alternative, from a consumer that tried it

That consumer designed and validated the smaller change — reuse a cached check
only when it is a well-formed report whose `status` is `passed`, and hold a
failing report in memory rather than on disk — with a hermetic five-scenario
self-test. It works, and mutation testing showed the pass-only predicate is the
load-bearing half while the non-persistence guard is only state hygiene.

It is recorded here as a **rejected** alternative, not a proposal: it preserves
cached-pass reuse, which this PRD's consolidation explicitly supersedes ("Do not
resurrect the reuse AC"), and it therefore leaves the stale-**pass** direction
unfixed. The recompute contract remains the requirement. The consumer's finding
is still useful as design input: whichever remedy ships, the failing report must
stay in the emitted result, because the coordinator's `check` diagnostics are how
all five recurrences were identified in the first place.

### Sixth recurrence, and proof that both documented escapes are unreachable (2026-08-09)

`platypeeps/sd-github-review` PR #72, pack 0.64.3. Subject `knowledge.obsidian-kb`
again, so under `7865666c` this one would downgrade to `skipped` rather than
block — it is recorded for the escape evidence below, not as a blocking case.

Shape as before: a spec edit made the KB stale, the check failed correctly, then
`sd-ai-command-pack-update-spec-kb.py` reported `copies: 500 / 500, conflicts:
none` and the standalone gate reported 7/7. The coordinator kept replaying
`copies: 495 / conflicts: - Backend Spec` at an unchanged head. Escaped again
with `--attempt-id review-1eb519c-kbfresh`.

What is new is that **both documented escapes were tried first and neither
works**, so the undocumented `--attempt-id` remains the only exit:

| Escape | Result |
|---|---|
| `local=none` | `indeterminate` — *"optional router absence requires a clean local review"*, limitations `router-not-configured`, `local-skipped` |
| `--successor bookkeeping` | identical result |

Both produce a local receipt with `outcome: skipped`, and `sd-review`'s
router-absent completion rule requires a **clean** local receipt: *"A router
classified `absent` may complete locally only when routing is optional and the
local receipt is clean."* A skipped receipt is not a clean one, so the rule
refuses the very state the escape produces. The two escapes are not merely
inapplicable to this check — they are unreachable in general whenever the
router is absent, which is the only situation anyone would reach for them in.

Worth pinning in whichever remedy ships: the escape hatch operators are told to
use is gated on a receipt state the escape itself cannot produce.

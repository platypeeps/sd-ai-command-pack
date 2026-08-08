# sd-review gates on a memoized check that reads live inputs

## Goal

Stop the review coordinator from gating on a stale typed `sd-check` report, so a
run that fixes the input a check actually reads — the live PR body — is not
blocked by the failure it just fixed.

The memoization of the expensive stages is correct and stays. Only the
deterministic check is wrong to cache, and only because a constituent check reads
an input the state identity deliberately does not capture.

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
`worktreeDigest`/head. It ships with five guard tests
(`tests/test_review_coordinator.py::ResolveCheckTest`), and that commit records
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

- [ ] A cached failing check at an unchanged head is recomputed, and a run that
      fixed the live input proceeds. Demonstrated against `pack.review-scope` with
      a real PR body edited between two runs at one head — not with a stubbed
      report. This is the criterion that proves the defect, so it must use the one
      check that actually blocks.
- [ ] The same, demonstrated against `knowledge.obsidian-kb` under an in-repo
      symlink or tracked `.obsidian-kb` directory. State explicitly that an
      external-symlinked KB cannot satisfy this criterion because `7865666c`
      downgrades its failure to `skipped`, and do not substitute a stub to make it
      appear to pass.
- [ ] A cached passing check at an unchanged head is recomputed, and a run whose
      live input has since broken is blocked. The stale-pass direction is tested,
      not only the stale-failure direction.
- [ ] The attempt phase does not regress when a resumed run recomputes the check.
- [ ] Local and remote stage results are still served from state on a resume,
      verified by asserting they are not recomputed.
- [ ] The coordinator's gate verdict equals a direct `sd-check` run's verdict on
      the same tree, for both a pass and a fail, with the coordinator's state
      pre-seeded to the opposite verdict in each case. Exercise the real
      subprocess, not a stubbed `_run_check`, since a stub cannot show the two
      agreeing.
- [ ] At least one new test is shown to fail against the pre-change code and pass
      after it. Demonstrated, not asserted.
- [ ] `platypeeps/se-ai-command-pack` can refresh past `0.64.27` with its fork
      removed and its `ResolveCheckTest` suite passing against the shipped file.
      This is the criterion that closes the consumer's blocker; verify it rather
      than inferring it.

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

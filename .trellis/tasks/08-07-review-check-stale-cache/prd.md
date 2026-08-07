# sd-review gates on a memoized check that reads live inputs

## Goal

Stop the review coordinator from gating on a stale typed `sd-check` report, so a
run that fixes the input a check actually reads — the KB symlink target or the PR
body — is not blocked by the failure it just fixed.

The memoization of the expensive stages is correct and stays. Only the
deterministic check is wrong to cache, and only because two of its constituent
checks read inputs the state identity deliberately does not capture.

## Problem

> Citations are pinned to `v0.64.27`:
> `templates/scripts/sd-ai-command-pack-review.py` at 2091 lines, byte-identical
> to this repository's own installed `scripts/` copy. Each citation names its
> enclosing symbol — re-locate by symbol, not by line, on any other version.

`main` computes the check only when the persisted state has none, then gates on
whatever the state holds (`templates/scripts/sd-ai-command-pack-review.py:1827-1830`):

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

### Two checks read inputs the identity does not capture

The attempt identity records `worktreeDigest` and `prNumber` (`:575-576`). It
does not record the PR body, and `worktreeDigest` excludes gitignored paths and
is `None` for PR scope. But:

- **`knowledge.obsidian-kb`** compares against the `.obsidian-kb` symlink
  target, which is gitignored — so refreshing the KB changes the check's answer
  without changing `worktreeDigest`.
- **`pack.review-scope`** requires a recognized scope heading in the **live PR
  body** — so hand-authoring that section changes the check's answer without
  changing `prNumber` or the head.

Both are precisely the inputs an operator fixes *in response to* the check
failing. Caching the verdict means the fix cannot be observed.

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
don't serve stale cache` — which extracts `_resolve_check`:

```python
check = _run_check(repo)              # unconditional
if state.get("check") is None:
    _advance(state_path, state, "check", check=check)
else:
    state["check"] = check
    state["updatedAt"] = int(time.time())
    _atomic_json(state_path, state)
return check
```

It persists the fresh report without regressing the phase on resume, and leaves
the local and remote stages memoized because their inputs *are* captured by
`worktreeDigest`/head. It ships with five guard tests
(`tests/test_review_coordinator.py::ResolveCheckTest`), and that commit records
the AC1 test as proven to fail against the pre-fix caching.

The symbol `_resolve_check` exists in no version of this pack — checked all 33
`v0.6*` tags across 1975 commits. Because the file is `install: "always"`, every
refresh of that consumer reverts the fix. Confirmed on 2026-08-07: refreshing it
from `0.64.3` to `0.64.27` removed `_resolve_check` and errored all five tests,
so the refresh was reverted and the consumer is now pinned 24 versions behind by
this defect.

That is the operative cost. The bug is not merely unfixed here; it is actively
holding a consumer back from every other fix in 24 releases.

## Requirements

- The deterministic `sd-check` must be recomputed on every coordinator
  invocation, in both the direct and nested paths, rather than gated on a
  persisted report.
- The fresh report must still be persisted for reporting, and persisting it must
  not regress the attempt phase on a resume.
- The expensive local and remote stages must remain memoized. Their inputs are
  captured by `worktreeDigest`/head, and recomputing them is the cost this state
  exists to avoid.
- A genuinely stale KB, or a PR body with no scope section, must still block —
  in both the direct and nested paths. The fix removes stale *passes* as well as
  stale failures.
- Add regression coverage that fails against the current caching behaviour and
  passes after the change. At least one test must assert that a cached failure
  is recomputed fresh when the live input has changed at an unchanged head.
- State in the change whether the consumer's local fork is now redundant, so
  that repository can drop its fork rather than carrying it indefinitely.

## Acceptance Criteria

- [ ] A cached failing check at an unchanged head is recomputed, and a run that
      fixed the live input proceeds. Demonstrated against both
      `knowledge.obsidian-kb` and `pack.review-scope`.
- [ ] A cached passing check at an unchanged head is recomputed, and a run whose
      live input has since broken is blocked. The stale-pass direction is tested,
      not only the stale-failure direction.
- [ ] The attempt phase does not regress when a resumed run recomputes the check.
- [ ] Local and remote stage results are still served from state on a resume,
      verified by asserting they are not recomputed.
- [ ] The nested path behaves identically to the direct path for both a pass and
      a fail.
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
- Memoizing the local or remote stages differently.
- The consumer's own record of its fork, which is tracked there as
  `08-07-review-py-local-fork`.

## Notes

- Found from a consumer on 2026-08-07, the same route as the three defects filed
  in `6f810484` from auditing `hoa-manager`. The consumer's install audit could
  not surface the fork: provenance records installed hashes and the consumer
  deliberately re-recorded its own after the fix, so
  `install.py --check --audit` reports "vouched file hashes match" against a
  file that differs from its template by 29 lines. Worth knowing when reasoning
  about what a consumer is actually running; it is not a defect in this task's
  scope.
- The consumer's fix is the reference implementation and its commit message is
  the fullest existing statement of the defect. Read `bc01bc2` before designing
  a different remedy.
- Planning depth: PRD-only. The remedy is one extracted function with an
  established reference implementation; there is no design space to explore.

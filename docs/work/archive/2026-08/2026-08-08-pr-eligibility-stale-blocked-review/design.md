# Design: separating a stale `BLOCKED` from a branch-protection block

Implements `prd.md` in this directory. One shipped helper changes —
`templates/scripts/sd-ai-command-pack-pr-eligibility.py` and its three
byte-identical mirrors — plus one shipped reference doc and one test module.

## Open question 1: re-query inside the probe, or retryable-indeterminate?

**Decision: a bounded re-query inside the probe, whose changed-value outcome is
reported as a retryable indeterminate.** Both, in that order — not one or the
other.

The PRD's requirement 4 decides it: "no dependence on a caller that may not be
a settle-watch." Reporting the ambiguity and leaving the re-read to the
sd-ship watch coordinator works only for the one caller that polls.
`sd-ai-command-pack-housekeeping.sh` invokes this probe synchronously and acts
on a single result; for that caller, "ambiguous, ask again" is a diagnostic it
can never resolve, so the operator is left reading a hedge instead of an
answer. Requirement 5's acceptance criterion — "a caller that does not poll
still receives an accurate, non-misleading diagnostic" — makes the non-polling
caller the deciding case, and only the in-probe re-read serves it.

The `retryable` flag is not discarded, though. Once the re-read shows the
merge state actually moved, the probe knows the snapshot was stale but does
*not* know what the settled state is — one changed read proves staleness, it
does not prove mergeability. So the verdict becomes
`status="indeterminate"`, `retryable=true`, which the watch coordinator's
existing rule 2 already keeps polling and which housekeeping already refuses
to merge on. No new consumer, no new poll loop, no new sleep in any caller.

### The bound

Stated once, in two module constants:

```
MERGE_STATE_RECHECK_ATTEMPTS = 2
MERGE_STATE_RECHECK_DELAY_SECONDS = 3.0
```

`recheck_merge_state` is a plain `for` loop over `range(ATTEMPTS)` with no
deadline, no growing backoff, and no caller-supplied count, so a synchronous
caller's worst case is fixed at 6 seconds and 2 extra `gh pr view` calls — and
only on the single ambiguous branch, never on a CLEAN, DIRTY, BEHIND, or
conversation-blocked path. The loop stops early on the first read that differs
from `BLOCKED`. The bound is asserted in the test, not merely commented: the
stable case asserts `sleeps == [DELAY] * ATTEMPTS` and exactly
`1 + ATTEMPTS` full reads.

## Open question 2: does `blocked` → `indeterminate` break additive-only?

In letter, yes: the docstring promised "this never changes the verdict." In
spirit, no. Both statuses land in the same `blocked|indeterminate)` arm of
`maybe_merge_ready_open_pr` and `maybe_merge_ready_dependency_pr` in
`scripts/sd-ai-command-pack-housekeeping.sh`, which records an anomaly and
returns without merging. No consumer treats `indeterminate` as a weaker
obstacle than `blocked`; the watch coordinator treats it as *more* reason to
keep waiting. The docstring's promise is restated as the one that actually
matters and is actually enforced: every verdict this function returns is
`blocked` or `indeterminate`, never `eligible`.

## Open question 3: a new reason code, or reuse the generic block?

One new code, `merge_state_unsettled`, for the one case that is genuinely new
information: the merge state changed under a bounded re-read. Every other
outcome reuses an existing code.

In particular, a re-read that is *unavailable* — `gh` failed, the payload was
malformed, or the read landed on a different pull request — degrades to the
existing generic `merge_state_not_clean` block rather than earning a second
new code. That matches the function's existing convention for an unreadable
review-thread list, and it is the fail-closed direction: absent evidence never
buys the terminal-sounding verdict, and never buys eligibility either.

## Open question 4: testing without depending on GitHub's timing

`tests/test_pr_eligibility.py` drives all four shapes through the existing
injected `FixtureRunner`, with a new ordered `pr_payload_queue` for successive
`gh pr view` reads and an injected `sleeper` so no test pays the real delay.
No network, no real `gh`, no wall-clock dependence.

Ordering evidence, both runs offline against the same fake two-read sequence
(`BLOCKED` then `CLEAN`):

```
before: status=blocked        reasonCodes=['merge_blocked_review']    retryable=False
after:  status=indeterminate  reasonCodes=['merge_state_unsettled']   retryable=True
```

## What did not change

The gate cannot now pass anything it previously blocked. `merge_blocked_review`
still fires for a `BLOCKED` that is stable across every read, and the only
verdict transition introduced is `blocked` → `indeterminate`, which is strictly
less confident. Neither status reaches `gh pr merge`.

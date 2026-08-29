---
title: pr-eligibility returns merge_blocked_review from a single possibly-stale mergeStateStatus read
status: done
created: 2026-08-08
branch: task/pr-eligibility-stale-blocked-review
---
# `merge_blocked_review` is a terminal verdict derived from one possibly-stale read

## Goal

Stop `pr-eligibility` from reporting a self-clearing GitHub state as a
branch-protection problem that needs a human. Two situations are
indistinguishable in a single `mergeStateStatus` snapshot and need opposite
operator responses: one clears by waiting, the other never does.

## Origin

Converted from GitHub issue platypeeps/sd-ai-command-pack#348, filed
2026-08-07 against pack `main` @ `244b0f8d` and closed in favour of this task.
The issue's analysis was verified against `main` @ `0115d552` on 2026-08-08 and
still holds; line numbers below are from that verification, not from the issue.

## Problem

`classify_non_clean_merge_state`
(`scripts/sd-ai-command-pack-pr-eligibility.py:661-726`, and its byte-identical
twin at `templates/scripts/sd-ai-command-pack-pr-eligibility.py:661`) diagnoses
a non-CLEAN `mergeStateStatus` from a single snapshot with no re-query.

That is correct for every cause it currently names, because each is a stable
state:

- `merge_blocked_conflicts` — `mergeable == "CONFLICTING"` or `DIRTY` (`:689`)
- `merge_blocked_out_of_date` — `BEHIND` (`:696`)
- `merge_blocked_conversation` — `BLOCKED`, no blocking checks, at least one
  green check, and `unresolvedCount > 0` (`:713`)

It is wrong for one cause it does not name: a `BLOCKED` that GitHub clears on
its own within roughly a minute, typically after a draft-to-ready transition,
because the mergeability snapshot has not been recomputed yet.

That case falls through to the last `BLOCKED` branch (`:720-725`):

```text
return (
    ["merge_blocked_review"],
    f"PR #{number} is mergeable with checks green but blocked "
    "(mergeStateStatus BLOCKED); a required approval or branch-protection "
    "rule is unsatisfied",
)
```

The message names a cause that requires a human decision, for a state that
resolves itself. An operator following it inspects branch protection and finds
nothing wrong.

## Observed

From the originating issue, merging `platypeeps/anomaly-metric-creator#346`
immediately after `gh pr ready`:

```text
PR #346 merge state is BLOCKED, not CLEAN; skipped auto-merge
```

`gh pr view` reported `CLEAN` at the same moment. Re-running housekeeping
unchanged succeeded, with nothing about the pull request changed in between.

Corroborated on 2026-08-08 in this repository, though not on the identical
branch of the classifier: `mergeStateStatus` was observed as `UNKNOWN`
immediately after fetch on PRs #375 and #376, settling to `BEHIND` on the next
poll, and PR #349 reported `BLOCKED` alongside a check rollup that was still
empty. The recompute lag is real and routine here; what the issue adds is that
one branch of the classifier converts that lag into a terminal-sounding verdict.

## Why this is not the already-fixed case

`merge_blocked_conflicts`, `merge_blocked_out_of_date`, and
`merge_blocked_conversation` were added after the issue's author first hit
this, and they cover the causes that would otherwise have been reported.
`merge_blocked_conversation` in particular correctly diagnosed a separate
`BLOCKED` held on one unresolved thread under `required_conversation_resolution`
(`platypeeps/anomaly-metric-creator#348`).

The residual gap is narrow: a genuine branch-protection block and a stale
snapshot both reach `:720` with green checks and zero unresolved threads. Both
causes are real — a `BLOCKED` can also persist indefinitely — which is exactly
why one snapshot cannot separate them.

## The design tension to resolve

The classifier's own docstring (`:672-679`) states the constraint:

```text
ADDITIVE-ONLY: this never changes the verdict. Every caller still returns
status="blocked" and never reaches gh pr merge; this only replaces the
generic merge_state_not_clean with a specific, actionable reason code
and message ... A missing/unknown signal degrades to the generic block —
it never invents eligibility.
```

The function returns only `(reason_codes, message)`; the callers at `:939` and
`:1286` set the status. So "return an indeterminate instead" is a change to
that contract, not a change inside the function, and it is the decision this
task exists to make.

There is existing machinery that fits. The result already carries a
`retryable` flag (`:882`, `:907`), set today for `head_unavailable` and
`head_changed`, both of which also set `status = "indeterminate"`. The sd-ship
watch coordinator already consumes that pair:
`.claude/skills/sd-ship/references/watch-coordinator.md:42-44` keeps polling a
retryable indeterminate within its ceiling, and stops immediately on a
non-retryable one.

An ambiguous `BLOCKED` reported as retryable-indeterminate therefore needs no
new sleep, no new poll loop, and no new consumer: the settle-watch that already
exists would wait it out and re-read. Whether that is preferable to a bounded
re-query inside the probe is the open question — the issue suggested the
re-query, this task records that the existing flag may make it unnecessary.

Both shapes preserve the "never invents eligibility" guarantee. Neither may
report `eligible`.

## Requirements

### Functional

1. A `BLOCKED` state that GitHub clears without operator action is not reported
   with a diagnostic naming approval or branch protection.
2. A `BLOCKED` state that is genuinely held on branch protection is still
   reported distinctly and actionably. Losing that diagnosis is not an
   acceptable price for fixing the false one.
3. When the two cannot be separated from available evidence, the result says so
   rather than choosing the terminal-sounding one.
4. The distinguishing mechanism is bounded. No unbounded polling, and no
   dependence on a caller that may not be a settle-watch.

### Non-functional

5. The probe never reports `eligible` for any state reachable through this
   path. The additive-only guarantee against inventing eligibility is
   preserved whatever shape is chosen.
6. `scripts/` and `templates/scripts/` copies of `pr-eligibility.py` stay
   byte-identical.
7. Any new reason code is documented wherever the existing `merge_blocked_*`
   codes are, and any status change is reflected in the watch coordinator's
   classification order.

## Open questions (resolve in design)

1. **Re-query inside the probe, or retryable-indeterminate for the caller?**
   The issue proposed one bounded re-read after a short delay. The `retryable`
   flag suggests instead reporting the ambiguity and letting the existing
   settle-watch re-read. The second adds no sleep to a probe that callers may
   invoke synchronously; the first works even for a caller that does not poll.
   Requirement 4 makes a non-polling caller the deciding case.
2. **Does changing the status break the additive-only contract in spirit or
   only in letter?** Moving from `blocked` to `indeterminate` is strictly less
   confident, never more, so it cannot invent eligibility. Confirm no consumer
   treats `indeterminate` as weaker evidence than `blocked` in a way that
   matters.
3. **A new reason code, or reuse the generic block?** `merge_state_not_clean`
   already exists as the degrade-to path. A distinct
   `merge_blocked_indeterminate` is more informative but is another code every
   consumer must learn.
4. **How is the fix tested without depending on GitHub's timing?** The
   stale-snapshot window is short and not reproducible on demand. A fixture
   returning two different `mergeStateStatus` reads is the likely shape, and
   the test matters more than usual because the real condition is hard to
   reproduce.

## Acceptance criteria

- [x] Given two successive reads where the first is `BLOCKED` and the second is
      `CLEAN`, the probe does not emit `merge_blocked_review`
- [x] Given a `BLOCKED` that is stable across reads with green checks and zero
      unresolved threads, the probe still reports the branch-protection
      diagnosis distinctly
- [x] No path through the change can report `eligible` for a `BLOCKED` state
- [x] The distinguishing work is bounded, with the bound stated in the code and
      exercised by a test
- [x] A caller that does not poll still receives an accurate, non-misleading
      diagnostic
- [x] Open question 1 is answered in `design.md` with the decision and its
      rationale
- [x] `scripts/` and `templates/scripts/` `pr-eligibility.py` are byte-identical
- [x] If a status or reason code changed, the watch coordinator's
      classification order is updated to match

## Notes

Filed 2026-08-08 by converting issue #348, which was closed pointing here. The
issue's author offered to implement whichever shape the pack prefers; open
question 1 is that choice.

Related: the issue's closing line referenced the `stop`-after-`pause` work-loop
lock defect as still open. That shipped as PR #349 on 2026-08-08.

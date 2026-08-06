# sd-review pins a failed sd-check receipt to the head

## Goal

Let the `sd-review` coordinator re-run its typed deterministic `sd-check` when a
previously failing check covered a **worktree-local, gitignored** condition that
has since been repaired, without requiring a new commit or a throwaway
`--artifact-root`.

## Problem

`scripts/sd-ai-command-pack-review.py:1796`:

```python
if state.get("check") is None:
    check = _run_check(repo)
    _advance(state_path, state, "check", check=check)
check = state["check"]
if not isinstance(check, dict) or check.get("status") != "passed":
    return 1, _report(state=state, status="blocked", ...)
```

The stored `check` result is re-read on every subsequent invocation and is only
computed when it is `None`. A **failed** result is therefore cached exactly like
a passing one, and the attempt is pinned to it.

`--attempt N` does not escape this: the attempt ID is derived from head plus
controls, not the attempt number. Observed on PR #338 — attempts 3, 4, and 5 all
resolved to the same `attemptId` `review-2b627e56c0dd09b5851e97dd` and replayed
the identical stale diagnostic, while the same command run by hand exited 0.

### Why this is more than an inconvenience

Most deterministic checks fail on committed content, so the natural fix moves the
head and mints a new attempt ID. But `knowledge.obsidian-kb` checks
`.obsidian-kb/`, which is **gitignored**. Its documented remediation — "run
sd-update-spec or `python3 scripts/sd-ai-command-pack-update-spec-kb.py`" —
produces no commit, so it can never clear the pinned receipt. The check's own
remediation is unreachable through the coordinator.

Observed sequence on PR #338:

1. `task.py archive` moved the task, making the KB stale (917 of 920 copies).
2. `sd-review --attempt 3` ran `sd-check`, which failed on `knowledge.obsidian-kb`,
   and stored that failure.
3. `update-spec-kb.py` repaired the KB; `--check` exited 0 with `conflicts: none`.
4. Attempts 3, 4, and 5 still returned the byte-identical stale diagnostic.
5. Only a fresh `--artifact-root` produced a live re-run, which passed.

## Requirements

### Functional

- R1: a stored `check` result whose status is not `passed` must not be replayed
  indefinitely. Re-running the coordinator for the same head must be able to
  re-evaluate it.
- R2: a *passing* check result must remain reusable — the idempotent-resume
  guarantee in the `sd-review` skill is the point of the durable receipt and must
  not regress into re-running the full gate on every poll.
- R3: whatever re-evaluation rule is chosen must not weaken the gate. The check
  must actually run and actually pass; no path may mark it passed from stored
  state, an argument, or an operator assertion.
- R4: the behavior must be discoverable. If the coordinator declines to re-run,
  its report must say the result is a replay and name what would cause a
  re-evaluation, instead of presenting a stale diagnostic as current.

## Constraints

- Do not remove or weaken `--artifact-root`; it stays a documented control.
- Do not make `--attempt` the invalidation key. The skill explicitly forbids
  incrementing the attempt to work around a delayed receipt, and that rule exists
  to stop wasted paid remote rounds — the fix must not blur it.
- The `sd-review` skill text must end up consistent with the implementation.

## Open questions (resolve in design)

- Should re-evaluation be unconditional for a non-`passed` check, time-bounded,
  or keyed to a worktree digest? `_worktree_digest` already exists at
  `review.py:555` but is currently computed only for non-PR scopes
  (`review.py:1706`), and `.obsidian-kb` is gitignored, so whether it is inside
  that digest needs verifying before it can be used as the invalidation key.
- Is re-running `sd-check` cheap enough to simply never cache a failure? Its
  observed duration on this repository should be measured, not assumed.
- Do the other cached phases (`local`, `capability`, `remoteReceipt`) have the
  same replay-a-failure shape, or is `check` the only one?

## Acceptance Criteria

- [ ] A failing `knowledge.obsidian-kb` check, repaired by `update-spec-kb.py`
      alone with no new commit, clears on the next `sd-review` invocation for the
      same head and the same artifact root.
- [ ] A passing check on an unchanged head is still reused, proven by an
      assertion that the check subprocess runs once across two invocations.
- [ ] No new path can report `check: passed` without the check process exiting 0
      in that run or in a reused passing result.
- [ ] A regression test covers the exact PR #338 sequence: fail, repair
      out-of-band, re-invoke, observe pass.
- [ ] `.agents/skills/sd-review/SKILL.md` describes the actual invalidation rule.

## Notes

- Source: A-046 iteration on 2026-08-06, PR #338. The workaround used there was a
  throwaway `--artifact-root`, which re-ran the gate live and passed
  (`check: passed`, `local: clean`, `exactHeadReady: true`).
- Complex enough to need `design.md` and `implement.md` before `task.py start`:
  the invalidation rule is a real design choice with a correctness constraint
  (R3) on either side of it.

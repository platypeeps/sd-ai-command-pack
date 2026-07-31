# Design — a validated receipt for the ship → work-loop handoff

## Scope boundary

`.agents/skills/sd-ship/SKILL.md` (emit), `scripts/sd-ai-command-pack-work-loop.py`
(parse, validate, record), and the consuming instruction in
`.agents/skills/sd-work-backlog/SKILL.md:274`. Template twins move with them. No
change to the merge itself or to `sd-housekeeping`.

## The gap

`sd-ship` emits `SD_SHIP_MERGE_RESULT` as a free-text block. The work loop's
`record_result` then accepts agent-typed values. Verified in source:

```python
counter_key = {"completed": …, "parked": …, "blocked": …,
               "skipped": …, "failed": "failures"}.get(outcome)
if counter_key is None:
    raise WorkLoopError(f"unknown iteration outcome: {outcome}")
if review_rounds < 0 or ci_retries < 0:
    raise WorkLoopError("review rounds and CI retries must be non-negative")
```

That is the entire validation: enum membership and non-negative integers. Nothing
ties the values to what actually happened. This is the one unattended boundary in
the loop with no parser — outcome and counters cross it through an LLM
transcription step.

Two further confirmed defects in the same function:

```python
if outcome == "completed" and pr_number is not None:
    state["counters"]["mergedPrs"] += 1     # incremented from the typed string
...
state["phase"] = "complete"                 # direct assignment
```

`transition_state` exists and enforces `LEGAL_TRANSITIONS[current_phase]`, raising
`illegal work-loop transition` otherwise. `record_result` bypasses it entirely, so
`complete` is reachable from any phase.

## State has no home for half the payload

```python
CURRENT_FIELD_ORDER = ("task", "branch", "head", "baseBranch",
                       "prNumber", "prUrl", "lastShippedSha")
```

Seven fields. The receipt must carry merge state, final head, review rounds,
finish-work state, housekeeping state, and anomalies — **four of those have no
destination today**. Extending `CURRENT_FIELD_ORDER` is therefore part of this
task, not a follow-on, and it interacts with `STABLE_CURRENT_FIELDS` and
`TRANSITION_CURRENT_FIELDS`, which decide what survives a transition. Decide
deliberately which new fields are stable across transitions; getting that wrong
silently drops receipt data at the next phase change.

## Contract

Schema-v1 JSON receipt, emitted **alongside** the existing human-readable block,
which becomes display-only. The work loop gains `result --from-receipt`.

Model it on the peer contract that already works:
`--finish-work-receipt --json` with independent recompute
(`.agents/skills/sd-housekeeping/SKILL.md:28`). "Independent recompute" is the
important half — the receipt asserts, the work loop verifies against git and the
PR rather than trusting the assertion. A receipt that is merely *parsed* rather
than *checked* moves the transcription risk without removing it.

Minimum cross-checks:

- receipt PR URL/number must match the PR the loop validated
- receipt final head must exist and match the merge commit
- `mergedPrs` increments from the verified merge state, never from `outcome`

Fail closed with a named reason code on mismatch, malformed JSON, or version
mismatch. The reason-code table at the top of `work-loop.py` is the existing
idiom; add there rather than inventing a parallel error vocabulary.

## Compatibility

`SD_SHIP_MERGE_RESULT` has exactly one code reference today — a presence
assertion at `tests/test_sdlc_commands.py:724` — and the consuming instruction at
`sd-work-backlog/SKILL.md:274` is prose with no command block and no `--json`.
The blast radius is small. Keep the free-text block emitting so the presence
assertion holds and operators keep their readable output; only its *authority*
is removed.

`--from-receipt` is additive. The existing typed path stays until the receipt
path is proven, then is removed in a follow-up — not in this change.

## Rollout and rollback

Ships in a normal pack release; fleet rollout via normal refresh. Rollback is
revert plus release-level reinstall. Because the typed path remains during this
change, a receipt-side failure degrades to today's behavior rather than blocking
the loop.

## Risk

`tests/test_work_loop.py:3257` currently passes a PR URL that disagrees with the
validated PR and the loop accepts it. That test encodes the defect. It must be
changed to assert rejection — and changing it is the clearest single proof the
task worked.

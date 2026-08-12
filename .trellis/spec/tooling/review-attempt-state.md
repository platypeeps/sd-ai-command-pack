# Review Attempt State: What May Be Memoized

> When changing what `scripts/sd-ai-command-pack-review.py` (+ the
> `templates/scripts/` mirror) stores in, or serves from, its per-attempt
> state file.

---

## Scenario: Adding Or Changing A Memoized Review Stage

### 1. Scope / Trigger

Trigger: any change to what the review coordinator persists in its private
attempt state, or to which stage results a resume replays instead of
recomputing. The attempt state is a durable cache whose key does not cover
every input its stages read, so "cache this too" is a correctness decision,
not a performance one.

This has been rediscovered from consumer repositories at least six times and
has produced its own tasks each time. Read this before deciding a stage is
cacheable.

### 2. Signatures

```python
_state_identity(...) -> dict          # the attempt key
_load_or_create_state(path, *, attempt_id, identity) -> dict
_advance(path, state, phase, **updates) -> None        # persists; sets phase
_record_stage(path, state, phase, *, resumable, **updates) -> None
_run_check(repo) -> dict              # one subprocess; typed sd-check report
```

### 3. Contracts

`_state_identity` captures: repository, scope, base, head, `worktreeDigest`,
`prNumber`, and the typed controls. It captures **nothing else**. In
particular it does not capture:

- the live pull-request body (`pack.review-scope` reads it via
  `gh pr view --json body`, and `worktreeDigest` is `None` for PR scope);
- gitignored working-tree state (`worktreeDigest` uses
  `--exclude-standard`), such as an `.obsidian-kb` target;
- provider or network reachability;
- argv the caller supplies per invocation, such as `--local-disposition`.

The rule that follows:

> A stage result may be served from state only when every input that can
> change its verdict is part of the attempt key. Otherwise the stage
> recomputes on every invocation.

`_record_stage(resumable=False)` updates `state` in memory — so `_report`
shows what this run computed — without writing the state file, which also
leaves `phase` naming the last stage that genuinely completed.

A stage that recomputes on every invocation and then persists a result must
pass the **current** phase back rather than its own name:
`str(state.get("phase", "resolve")) if already_stored else "<stage>"`.
`_advance` assigns `phase` unconditionally, and `phase` is where a resume
re-enters, so naming the stage would rewind an attempt that already completed
later stages.

### 4. Validation & Error Matrix

| Condition | Behavior |
|---|---|
| Stage verdict turns on an input outside the attempt key | Recompute every invocation; do not gate on a stored verdict |
| Recompute produces a non-resumable outcome | Report it, do not write it; earlier persisted results survive |
| Recompute re-persists a result at an attempt already past that stage | Keep the existing later `phase`; never rewind |
| Expensive stage whose inputs the key does cover (local, remote) | Replay from state; recomputing is the cost the state exists to avoid |
| Caller wants to escape a stale verdict | Never by a fresh `--attempt-id` — that discards the attempt's local and remote review evidence too |

### 5. Good/Base/Bad Cases

- **Good:** the deterministic `sd-check` — one cheap idempotent subprocess
  reading live inputs — recomputed every run, its passing result still
  persisted for reporting and resume phase.
- **Base:** the local provider stage — expensive, inputs covered by
  `worktreeDigest`/head — replayed from state, refreshed only when the caller
  supplies dispositions.
- **Bad:** gating on a stored `sd-check` verdict. A stored **failure**
  false-blocks a run that already remedied the input the check read; a stored
  **pass** false-allows a run whose live input has since broken. Both were
  shipped defects (`47d5dfbb` fixed the first, `0.71.1` the second).

### 6. Tests Required

In `tests/test_review_controller.py`, per memoization decision:

- both verdict directions across two invocations at one unchanged head, with
  the stub returning different verdicts, asserting the call count is 2 and the
  second gate verdict follows the second computation;
- the expensive stages still replay — assert their call count stays 1 in the
  same test that proves the cheap stage recomputed;
- the resumed attempt's persisted `phase` is unchanged by the recompute;
- at least one test that exercises the real subprocess by patching
  `CHECK_SCRIPT` to a fixture helper whose verdict turns on a file outside the
  attempt key, seeding the state with the opposite verdict in each direction.
  A stubbed `_run_check` cannot show the coordinator and a direct run agreeing,
  because it replaces the thing under test.

### 7. Wrong vs Correct

#### Wrong

```python
if state.get("check") is None:
    check = _run_check(repo)
    _record_stage(state_path, state, "check", resumable=..., check=check)
check = state["check"]                       # serves whatever was stored
```

#### Correct

```python
stored = state.get("check") is not None
check = _run_check(repo)                     # every invocation
_record_stage(
    state_path,
    state,
    str(state.get("phase", "resolve")) if stored else "check",
    resumable=isinstance(check, dict) and check.get("status") == "passed",
    check=check,
)
check = state["check"]
```

---

## Common Mistake: Downgrading The Check Instead Of Fixing The Cache

**Symptom**: a live-input check keeps blocking, so it is made advisory.

**Cause**: `7865666c` set the precedent by downgrading a *failed* external-symlink
KB freshness row to `skipped`, and that precedent reads as general.

**Fix**: it is not general. An external vault's freshness is genuinely
non-deterministic and never shipped. An absent scope section in a PR body is a
deterministic fact about the pull request under review and is exactly what the
gate is for — making it advisory deletes the check rather than fixing the
cache.

**Prevention**: ask whether the input is non-deterministic or merely *live*.
Live inputs get recomputed; non-deterministic ones get downgraded, and only
with their own justification.

# Design: `start` must never silently replace an existing ledger

## Current lines

The PRD cites `:2852-2903` / `:2860` / `:2897` from 0.64.27. Those are stale.
`scripts/sd-ai-command-pack-work-loop.py` and its `templates/scripts/` mirror
are still byte-identical (`diff -q` clean), so one table serves both:

| What | Line |
|---|---|
| `STATUSES` — `active`, `paused`, `stopped`, `completed` | `:57` |
| `LOCK_RELEASING_STATUSES` — `paused`, `stopped`, `completed` | `:62` |
| recovery reason → reference map | `:68-76` |
| `new_state()` | `:951` |
| `acquire_lock()` | `:1149` |
| `recovery_reason_code()` | `:2468` |
| `start` handler | `:2858` |
| existing-state block (`if state_path.is_file():`) | `:2870` |
| the resume gate `if state["status"] in {"active", "paused"}:` | `:2877` |
| the `--run-id` mismatch guard, **inside** that gate | `:2878-2881` |
| conflict guards (`--mode` / `--selector` / `--until`, focus) | `:2882-2900` |
| the unconditional `state = new_state(...)` fall-through | `:2914` |

The defect is exactly the shape the PRD describes: `:2877` matches only
`active`/`paused`, so a `stopped` or `completed` ledger falls out of the block
and reaches `:2914`, and the `--run-id` guard at `:2878` never sees the
invocation it was written for.

## Open question 1: resume or refuse by default?

**Refuse.** `start` against a ledger whose status is neither `active` nor
`paused` exits nonzero with a typed reason and mutates nothing. `--resume`
reactivates it; `--reset` archives it and mints a new run.

Four reasons, in order of weight:

1. **The repository already routes this case somewhere else.**
   `recovery_reason_code()` (`:2468`) returns `run_stopped` for a stopped
   ledger, and `RECOVERY_REFERENCE_BY_REASON` (`:68-76`) maps it to
   `references/run-recovery.md`, which prescribes `reconcile` — reload live
   evidence, agree with it, then continue. `sd-work-backlog`'s prerequisites
   section already tells the controller to read status *before* `start` and
   load only the reference the reason code selects. Resuming from inside
   `start` would put a second, evidence-free recovery path beside the
   documented one, and it is the weaker of the two: `start` reads no branch,
   head, PR, or task state.

2. **A stopped run carries a decision, and a stop reason explaining it.**
   `stop --status stopped --reason` requires that text, and `sd-status`
   prints it. Silently reactivating past it discards an operator's terminal
   judgment the same way the current code discards their counters — a smaller
   loss, the same failure mode.

3. **`completed` and `stopped` want the same answer, and resume is wrong for
   `completed`.** A completed run has nothing left to resume. One rule
   covering every non-resumable status is simpler than a status-by-status
   table, and refusal is the only answer that reads correctly for all of them.
   Note the asymmetry this closes: `recovery_reason_code` tests only
   `status == "stopped"` (`:2498`), so a `completed` ledger classifies as
   `normal` and no reference routes it anywhere. Refusal is the only signal
   that case will ever get.

4. **Refusal is the recoverable error.** A refusal costs one re-invocation
   with a flag. The other two defaults cost either a destroyed ledger (today)
   or a run continued past its own stop (resume-by-default), and neither is
   visible at the moment it happens.

The cost is real and is accepted: every caller that today relies on `start`
minting a fresh run after the previous one ended must now say `--reset`. That
includes this pack's own controller. See **Blast radius**.

## Open question 2: archive the outgoing ledger?

**Yes, one generation.** `--reset` writes the outgoing ledger to a sibling
`replaced.json` beside `state.json` in the same private state directory before
writing the new one, wrapping it as:

```json
{
  "schemaVersion": 1,
  "kind": "work-loop-replaced-ledger",
  "replacedAt": "<UTC>",
  "replacedRunId": "<outgoing runId>",
  "state": { ...the complete outgoing ledger, verbatim... }
}
```

One generation, overwritten by the next `--reset`. The failure this protects
against is the immediately-regretted reset, which is discovered within minutes;
an unbounded archive would grow without a reader and would need its own
retention rule. The wrapper is a distinct `kind` so nothing mistakes it for a
ledger, and it is never read back automatically — recovery is an operator
copying it over `state.json`, deliberately.

`state_paths()` (`:360`) returns the state and lock paths from one directory;
`replaced.json` is the third sibling in it.

`status` reports it as a boolean plus the replaced run ID and timestamp, so the
loss is discoverable from the tool rather than from a hand-written note in a
free-text field, which is the only reason the `hoa-manager` incident is known
at all. The read follows `_read_status_lock`'s pattern (`:2506`): status is
read-only and must not turn a malformed sibling into an exception, so an
unreadable `replaced.json` reports present-but-unreadable rather than raising.

## The `--run-id` guard

Move it out of the resume gate so it guards every existing ledger:

```python
if state_path.is_file():
    state = upgrade_state(read_json(state_path))
    validate_state(state)
    if state["repository"]["digest"] != identity["digest"]:
        raise WorkLoopError(...)                      # unchanged
    if args.run_id and args.run_id != state["runId"]:
        raise WorkLoopError(f"... already exists as run {state['runId']}")
    ...
```

This satisfies acceptance criterion 2 on its own for the mismatch case. The
match case needs one more rule: `--reset --run-id <the outgoing run ID>` is
refused, because a fresh ledger carrying the replaced run's ID is precisely
the indistinguishable artifact the PRD names. `--reset` without `--run-id`
mints a fresh UUID; `--reset --run-id <unused ID>` is allowed.

## Resulting matrix

`E` = an existing ledger for this repository identity. Repository-identity
mismatch still raises first, before any of this.

| existing status | no flag | `--resume` | `--reset` |
|---|---|---|---|
| none | new run | error: nothing to resume | new run (nothing to archive) |
| `active` | resume (today) | resume | archive + new run |
| `paused` | resume (today) | resume | archive + new run |
| `stopped` | **error: not resumable** | reactivate | archive + new run |
| `completed` | **error: not resumable** | reactivate | archive + new run |

Only the two bold cells change an existing behavior; the rest are new surfaces
or unchanged paths. `--resume` and `--reset` together are an error.

The `--reset` column is subject to the existing lock gate, which this task does
not touch: `acquire_lock` (`:1149`) refuses a live lock, so `--reset` against an
`active` ledger whose owner is still running fails there, before anything is
archived or written. That is the correct order — the archive happens only on a
path that is actually going to write a new ledger — and it means `--reset` is
practically a `stopped`/`paused`/`completed` operation, with
`--recover-stale-lock` the existing escape for an abandoned owner.

`--resume` on `active`/`paused` is exactly today's resume, so the flag is an
explicit spelling of the default rather than a second code path. `--resume` on
`stopped`/`completed` runs the same conflict guards (`--mode`, `--selector`,
`--until`, focus), acquires the lock — `stop` released it, per
`LOCK_RELEASING_STATUSES` (`:62`) — sets `status` to `active`, and leaves every
counter, the phase, and `current` untouched. It does **not** clear
`stopReason`: the run's history keeps saying why it stopped, and `status`
reports both. It does not clear `terminalReconciliation` either; a ledger
carrying one still routes through `terminal_reconciliation` on the next status
read, which is the existing recovery contract and not this task's to change.

## Error shape

Refusals raise `WorkLoopError` like every other guard here, so the CLI's
existing `error: <message>` / nonzero-exit path is unchanged. The message names
the status, the run ID, and both flags:

```text
error: loop state for this repository is stopped (run 4e2c...); resume it with
--resume, or discard it with --reset (the replaced ledger is archived beside
it)
```

No new exit code, no JSON error envelope, and no machine-readable reason code:
`start` has never had one, every existing guard here raises prose, and the
callers that parse this surface parse `status --json`. The refusal is not a
status. Naming the flags in the message is what makes it actionable; the
matrix above labels rows for this document's benefit, not the CLI's.

## Blast radius

**Code**: `scripts/sd-ai-command-pack-work-loop.py` and the byte-identical
`templates/scripts/` mirror; `plugins/sd/**` copies are regenerated by
`make sync` + `make generate`.

**Callers that must now pass `--reset`.** This is the part that fails silently
if missed, so enumerate it from the filesystem rather than from memory —
`grep -rn "work-loop.py \\\\\?$\|work-loop.py start"` across `templates/`,
`.agents/`, `.claude/`, `docs/`, and `plugins/`. Known at design time:

- `.agents/skills/sd-work-backlog/SKILL.md` and its `.claude/` and `plugins/`
  copies document the `start` invocation. The controller already reads
  `status` first and routes `run_stopped` to `references/run-recovery.md`, so
  the change is additive: a genuinely new run after a stopped or completed one
  passes `--reset`, and the reference gains the `--resume` option beside
  `reconcile`.
- `docs/SD_AI_COMMAND_PACK.md`'s work-loop section describes `start`'s
  resume behavior and must describe the refusal and both flags.

**Not affected**: `rank`, `transition`, `evidence`, `reconcile`,
`reconcile-terminal`, `result`, `focus`, `checkpoint`, `stop`, `heartbeat`.
None of them writes `new_state`, and none reads `replaced.json`.

## Compatibility

An existing `state.json` is read by `upgrade_state()` unchanged; no schema
version bump, because `replaced.json` is a new sibling file rather than a new
ledger field. A state directory written by an older pack has no
`replaced.json`, and `status` reports its absence as the ordinary case rather
than as an anomaly.

## Rejected alternatives

- **Archive-and-replace by default, no new flags.** Keeps every caller
  working and makes the loss recoverable, which is most of the harm. Rejected
  because PRD requirement 1 says the overwrite must not be implicit, and
  because "we replaced your ledger but kept a copy" still hands the operator a
  zeroed run under the ID they asked to resume — criterion 2 fails.
- **Refuse only when `--run-id` is supplied.** Fixes the observed incident
  exactly and nothing else. Rejected: the incident is a symptom of the
  fall-through at `:2914`, and a run started without `--run-id` against a
  stopped ledger loses the same counters just as quietly.
- **A `--force` flag rather than `--reset`.** `force` reads as "do it anyway"
  across this pack's surfaces and is used where a gate is being overridden.
  Discarding a ledger deliberately is not a gate override; it is a distinct
  intent, and it deserves a name that says which of the three readings the
  caller means.
- **Unbounded archive history.** No reader, no retention rule, and the state
  root is private per repository identity. One generation covers the failure
  mode that actually occurs.

## Risks

- **A caller updated in docs but not in behavior.** The controller is prose,
  not code, so nothing fails a test if a skill keeps the old invocation. The
  mitigation is the grep enumeration above plus a test that a stopped ledger
  refuses, so the failure is loud at the point of use rather than silent.
- **`--resume` on a stopped run that needs `reconcile` first.** `--resume`
  reactivates without consulting live state, so a run stopped for a state
  contradiction could be reactivated into the same contradiction. Accepted:
  `status` still reports the contradiction on the next read, and
  `contextHealth` survives the resume untouched — `--resume` does not reset it
  to green.

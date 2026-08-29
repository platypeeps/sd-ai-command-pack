---
title: start on a stopped work-loop run silently discards the ledger
status: done
created: 2026-08-07
branch: task/08-07-work-loop-start-refuses-stopped-ledger
---
# start on a stopped work-loop run silently discards the ledger

## Goal

Make `start` against an existing stopped ledger either resume it or refuse,
never silently replace it. Today the destructive reading is the default and
there is no way to opt out of it.

## Problem

`start` (`templates/scripts/sd-ai-command-pack-work-loop.py:2852-2903`) loads
an existing state file, then gates every resume path behind one membership
test:

```python
if state["status"] in {"active", "paused"}:
```

A `stopped` run does not match. Control falls out of the enclosing
`if state_path.is_file():` block and reaches `:2897`:

```python
state = new_state(
    identity,
    mode=args.mode or "backlog",
    selector=args.selector or "all",
    focus=focus,
    until=args.until or "merge",
    run_id=args.run_id,
)
```

The prior ledger is overwritten in place — no warning, no confirmation, no
backup copy, and no reason code.

## The run-id guard cannot fire on the case that needs it

The `--run-id` mismatch check sits at `:2861`, **inside** the active/paused
branch:

```python
if args.run_id and args.run_id != state["runId"]:
    raise WorkLoopError(f"resumable loop already exists as run {state['runId']}")
```

So `start --run-id <the-run-I-meant-to-resume>` against a *stopped* run does
not raise. It mints fresh state carrying the run ID that was passed in. The
resulting file is indistinguishable from the run the operator was trying to
resume, except that every counter has been reset to zero.

That is what makes this silent rather than merely destructive: the one
argument an operator supplies precisely because they mean "this specific
existing run" is the argument that gets copied onto the replacement.

## Problem, observed

`platypeeps/hoa-manager`, 2026-08-06. A `start --run-id` issued against a
stopped run reinitialized the ledger. Per the note written immediately
afterward, **8 completed / 8 mergedPrs / 29 reviewRounds** were lost with no
backup; the surviving counters read `completed 1, mergedPrs 1, reviewRounds 2`.

The loss exists in the record only because it was hand-written into the run's
own stop reason, which is where `sd-status` still prints it:

```text
stop reason: operator_pause: clean boundary on main after PR #232.
COUNTERS UNDER-REPORT: ledger was reinitialized 2026-08-06 by start --run-id
on a stopped run (work-loop.py:2864 falls through to new_state :2902);
8 completed / 8 mergedPrs / 29 reviewRounds lost, no backup.
Git/GitHub/Trellis authoritative.
```

No tool recorded it. Git, GitHub, and Trellis stayed authoritative so no
delivery work was lost — but the loop's own history was, and it is not
reconstructible from the ledger.

## Why it matters beyond one lost counter set

`stopped` is the state an operator is *most* likely to point `start` at: the
run ended and they want to resume, extend, or inspect it. Of the three
defensible readings — resume, refuse, discard — the code picks the only
irreversible one, picks it silently, and picks it for exactly the invocation
the `--run-id` guard was written to protect.

The counters also feed the run's own reporting. A ledger that can be zeroed
without trace means no downstream report can be trusted to reflect the run it
names.

## Requirements

### Functional

- `start` against an existing ledger whose status is outside `active`/`paused`
  must not overwrite it implicitly.
- The `--run-id` mismatch check must guard every existing state file, not only
  the active/paused branch. A run ID naming a stopped run must resume or
  refuse — never reinitialize under that same ID.
- Discarding an existing ledger must require an explicit caller opt-in
  (`--reset` / `--new-run` or equivalent). Today there is neither a way to
  request the discard nor a way to avoid it.

### Non-functional

- No change to the resume semantics of `active` or `paused` runs.
- No weakening of the existing lock, focus-conflict, or option-conflict guards.

## Open questions

1. Should `start` on a stopped run **resume** by default or **refuse** by
   default? Both are defensible and they imply different CLI surfaces; the
   answer decides whether `--reset` or `--resume` is the new flag.
2. Should the outgoing state be archived beside the new one when a discard is
   explicitly requested, so a mistaken `--reset` stays recoverable?

## Acceptance Criteria

- [x] `start` against a stopped ledger without an explicit opt-in does not
      write `new_state`; it either resumes or exits nonzero with a reason
- [x] `start --run-id <stopped-run-id>` never produces a fresh ledger carrying
      that run ID
- [x] A test covers each existing status (`active`, `paused`, `stopped`, and
      any other persisted value) against `start` with and without `--run-id`
- [x] Open question 1 is answered in `design.md` with a decision and rationale

## Notes

Filed 2026-08-07. Reproducible on pack source `main` @ `4378d37b` (0.64.27) at
`:2860` / `:2897`; the same logic is present in installed 0.64.3 at `:2864` /
`:2902`. Not a stale-install artifact.

`scripts/sd-ai-command-pack-work-loop.py` and its `templates/scripts/` mirror
are byte-identical today, so the line references above hold in both and the fix
must land in both.

Concrete cost recorded above: one consumer's loop history destroyed, and the
destruction discoverable only because a human wrote it into a free-text field.

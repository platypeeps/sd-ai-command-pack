# Duplicate journal session entries: identical session recorded twice under consecutive numbers

> NOTE (pack-internal, remove before filing): do not file this upstream
> until the root cause is confirmed to be in Trellis-owned code. The
> repro below involves our recorder wrapper calling `add_session.py`;
> the double-write could originate in the wrapper. The investigation is
> tracked as R4 of the pack task `07-06-close-fleet-refresh-loop`. If
> the wrapper is at fault, this becomes a pack bug instead.

## Summary

A developer journal contains two consecutive session entries —
"Session 29" and "Session 30", both dated 2026-07-05, same title
"Expand SD command pack workflows", same commit `34ea5d8` — whose
bodies are byte-identical (verified by diffing the two sections with
their headings stripped). One recording produced two numbered entries,
inflating the session index and corrupting session-count-based
tooling assumptions.

## Evidence

- Journal file: developer workspace `journal-1.md`, headings at lines
  1149 (`## Session 29: ...`) and 1186 (`## Session 30: ...`).
- `diff` of the two section bodies (heading line excluded) reports no
  differences.
- The workspace index lists both sessions as separate rows.

## Repro status

Not yet reproduced on demand. The duplicate was created during a
session-recording flow that runs `add_session.py` once from a wrapper
script; no second invocation appears in the shell history we have.
Suspects: a retry path in the recording flow, or non-idempotent
append behavior in `add_session.py` when the journal/index commit races
with another write.

## Ask

- If `add_session.py` has any retry or partial-failure path that can
  append twice, make the append idempotent (e.g. skip when the previous
  session entry has identical title+date+commits+body).
- A `--dry-run` or verbose mode printing the session number it is about
  to write would make diagnosis of this class much easier.

## Environment

Trellis CLI vendored scripts at `.trellis/.version` 0.6.5.

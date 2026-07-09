# Duplicate journal session entries: identical session recorded twice under consecutive numbers

> RESOLUTION (2026-07-09): do not file this upstream. The root cause was
> confirmed in the pack-owned recorder wrapper, not Trellis-owned
> `add_session.py`. `scripts/sd-ai-command-pack-record-session.py` called
> Trellis `add_session.py --no-commit`, then performed pack-owned staging and
> commit work. If the Trellis append succeeded but the later `git add` or
> `git commit` failed, rerunning the wrapper called `add_session.py` again and
> appended a duplicate. The pack wrapper now detects a modified journal whose
> latest session heading matches the retry title and reuses that pending entry
> instead of appending another one. Covered by
> `test_record_session_wrapper_reuses_uncommitted_retry_entry`.

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

Reproduced in the pack wrapper by forcing `git add` to fail after
`add_session.py --no-commit` appended the journal entry. A retry without the
fix appended a second same-title session. With the fix, the retry patches and
commits the existing pending entry.

## Upstream action

No upstream Trellis issue is needed for this duplicate-session incident. The
pack may still benefit from the already-filed upstream structured-content issue
for simpler long-term journal recording, but this specific double-write path is
fixed locally.

## Environment

Trellis CLI vendored scripts at `.trellis/.version` 0.6.5.

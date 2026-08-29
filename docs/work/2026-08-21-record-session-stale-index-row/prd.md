---
title: Refresh the workspace index row after the session journal is patched
status: planning
created: 2026-08-21
---
# Refresh the workspace index row after the session journal is patched

## Context

Every session this wrapper records leaves the workspace index understating the
active journal's line count. Caught during the 0.71.45 fleet refresh: Copilot
flagged the row on `platypeeps/people-profiles` PR #8, and the same drift was
then found pre-push on `anomaly-metric-creator` and already merged on
`sd-github-review`.

The cause is ordering inside `scripts/sd-ai-command-pack-record-session.py`,
not in Trellis. The wrapper:

1. runs `add_session.py --no-commit` (`:496-517`), which writes the journal
   entry **and** derives the `@@@auto:active-documents` row from the journal
   **as it stands on disk at that moment**;
2. calls `patch_last_session` (`:559`), which replaces the entry's Testing and
   Next Steps sections and **changes the journal's length**. In practice it
   grows — real bullets replace the `(Add details)`, `(Add test results)`, and
   `(see git log)` placeholders at `:64` — but the fix must not assume a
   direction, only that the count is no longer the one already written;
3. stages both the journal and its sibling `index.md` and commits them together
   (`:573-598`).

The row committed in step 3 was computed in step 1, so it is stale by exactly
the length change made in step 2. `add_session.py` is not at fault: its
`count_journal_files` re-reads each journal from disk every time, and the file
is byte-identical (`sha256` prefix `c360a1971f16`) across sd-ai-command-pack,
people-profiles, sd-github-review, anomaly-metric-creator, and rwbp-website.

Two paths reach step 2. The retry path (`:486-487`) skips `add_session.py`
entirely and patches a journal that was already written by an earlier run, so
the index there is stale from the previous invocation as well.

## Requirements

- After `patch_last_session` succeeds and before the wrapper returns, the
  `@@@auto:active-documents` row for the active journal must match the journal
  on disk, measured the same way `add_session.py` measures it
  (`len(read_text(encoding="utf-8").splitlines())`). A row derived any other
  way — `wc -l`, a byte count, an arithmetic delta applied to the old number —
  is wrong for a file with no trailing newline and is not acceptable.
- The refresh must cover the `--no-commit` path as well. That path returns
  before staging, and its caller commits the same two files later, so leaving
  it unrefreshed just relocates the defect.
- The refresh must cover the retry path, which never invoked `add_session.py`
  in this run.
- Nothing else in `index.md` may change. This must not re-run `update_index`,
  which also rewrites session number, title, commit display, and date, and
  would double-record the session.
- Rows for archived journals are recomputed on the same terms rather than
  preserved, so a hand-edited or externally rotated journal converges instead
  of staying wrong.
- A missing or marker-less `index.md` must not fail the run. The journal entry
  is the deliverable; a bookkeeping row that cannot be located is reported and
  skipped, matching how the wrapper already treats a `git add` of a path that
  does not exist (`:574`).
- The measure must not be reimplemented if `add_session.py.count_journal_files`
  can be reused, so the two cannot drift apart later.

## Acceptance criteria

- [ ] A test records a session whose Testing and Next Steps patch grows the
      journal, then asserts the committed `index.md` row equals the journal's
      real line count — not merely that it changed.
- [ ] A test covers the `--no-commit` path and asserts the row on disk is
      already correct when the wrapper returns.
- [ ] A test covers the retry path (a modified journal already carrying the
      title) and asserts the row is corrected even though `add_session.py` did
      not run.
- [ ] A test asserts a journal with no trailing newline is counted the same way
      `add_session.py` counts it.
- [ ] A test asserts an absent or marker-less `index.md` leaves exit status 0
      and the journal entry intact.
- [ ] A test asserts no field of `index.md` outside the active-documents block
      differs from what the current code produces.
- [ ] `git grep -l sd-ai-command-pack-record-session.py` enumerates every
      shipped copy from the filesystem, and all of them carry the change.
- [ ] `make check` passes.

## Out of scope

- Correcting rows already committed in consumer repositories. `sd-github-review`
  is handled by platypeeps/sd-github-review#112; people-profiles and
  anomaly-metric-creator were corrected during the refresh.
- Any change to `.trellis/scripts/add_session.py`. It is vendored Trellis and
  its behavior is correct.

---
title: add_session.py --content-file duplicates the session skeleton
status: planning
created: 2026-08-09
---
# add_session.py --content-file duplicates the session skeleton

## Goal

Make `add_session.py --content-file` produce one well-formed journal
session whose first parsed sections carry the real content, so a
completion bundle recorded with it passes the CI bookkeeping validator
without hand repair.

## Problem

`--content-file` appends the supplied content *after* the generated
skeleton instead of merging into it. Observed on 2026-08-09 while
recording Session 351 (`.trellis/workspace/sdelmas/journal-8.md`,
commit `17a851ee`):

- The helper emitted its own `### Summary` (from `--summary`) and an
  **empty** `### Main Changes` heading, then pasted the content file —
  which carried its own `### Summary` / `### Main Changes` — below
  them, and finally appended a trailing skeleton `### Git Commits`
  table (`(see git log)` rows) and `### Status` block after the
  content's `### Next Steps`.
- The CI bookkeeping gate parses the *first* `### Main Changes`
  section, found it empty, and failed the main-branch completion push
  with `journal_content_missing` ("Session 351 Main Changes must
  contain real content") — CI scope job 93244074562, run 31312958386.
- Recovery required an in-place journal repair through the validator's
  journal-only recovery window (commit `67663cd3`), which additionally
  surfaced that the window rejects merge-commit and task-path commit
  citations — constraints a correct generator could respect up front.

## Requirements

1. When `--content-file` (or `--stdin`) supplies content containing
   recognized session headings (`### Summary`, `### Main Changes`,
   `### Git Commits`, `### Testing`, `### Status`, `### Next Steps`),
   the helper must merge them into the generated session — one heading
   of each kind, real content under the first parsed occurrence — not
   append a second copy.
2. Explicit flags (`--summary`, `--change`, `--test`, `--next-step`)
   and content-file sections must compose deterministically, with a
   documented precedence instead of silent duplication.
3. The generated session must pass the review-preflight journal
   session validation at generation time; a session the validator
   would reject should fail the helper run with the reason, not land
   in the journal.
4. The commit list (`--commit`) should warn (or split prose citation
   from structured citation) when a supplied hash is a merge commit,
   since downstream journal-only recovery rejects multi-parent cited
   commits.
5. Existing journal files are not rewritten; the fix applies to newly
   recorded sessions only.

## Acceptance Criteria

- [ ] Re-recording Session 351's exact inputs (`--title`, `--commit`,
      `--summary`, `--content-file` with its own Summary/Main
      Changes/Git Commits/Testing/Status/Next Steps sections) yields a
      session with exactly one occurrence of each heading and a
      non-empty first `### Main Changes`, and
      `final-bundle --mode completion` over a fixture range containing
      it reports `completion_bundle_valid`.
- [ ] A content file without recognized headings still lands under the
      generated skeleton sections unchanged (current behavior for
      plain prose is preserved).
- [ ] A helper run whose merged session would fail validation exits
      nonzero and writes nothing.

## Out of scope

- Repairing historical sessions (Session 351 was already repaired in
  `67663cd3`).
- Changing the CI bookkeeping validator or its recovery windows.
- The deployment-model reshape discussion (separate initiative).

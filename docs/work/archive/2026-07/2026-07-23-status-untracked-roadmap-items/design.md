# Design: Untracked roadmap follow-ups

## Report Contract

Remove the separate human `Roadmap` section and the JSON
`trellis.roadmap` inventory. `Tasks` remains the complete unarchived Trellis
inventory. Untracked items found in bounded roadmap sources join the existing
top-level `followUps` array with:

- `kind: "roadmap"`;
- a concise candidate summary;
- the repository-relative source path and one-based line number; and
- the normal report-local `F-*` selection ID assigned after follow-up ordering
  and deduplication.

Human output renders the source location with each roadmap follow-up. A later
`F-*` selection remains a new request and does not authorize task creation.
Because the JSON field is removed, the local and nested fleet status report
schema version advances from 1 to 2.
The typed housekeeping result remains schema version 1, but its delegated
status-input validator advances in lockstep to require status schema version 2.

## Source Discovery

Enumerate tracked and untracked-but-not-ignored repository files through Git's
read-only file inventory. Accept only regular, non-symlinked `.md`, `.mdx`, or
`.txt` files that meet one of these case-insensitive path rules:

- the normalized filename stem begins with `roadmap`, `backlog`, `todo`,
  `program_design`, or `implementation_plan`; or
- a directory component is exactly `roadmap`, `proposals`, or `rfcs`.

Do not traverse ignored/generated directories or follow symlinks. Bound file
count, file size, line length, and emitted item count with explicit incomplete
scan diagnostics rather than silently claiming completeness.

## Item Extraction

Parse files line by line without interpreting arbitrary Markdown:

- an unchecked task box (`- [ ]`, `* [ ]`, or `+ [ ]`) is a candidate at any
  indentation;
- an unmarked list item is a candidate only at column zero;
- a checked task box (`[x]` or `[X]`) is completed and ignored;
- nested unmarked bullets, headings, paragraphs, empty items, and overlong or
  control-character-bearing text are ignored or safely bounded.

Preserve the visible item text as the report summary after bounded Markdown
presentation normalization. Sort by normalized source path, line number, and
summary before adding the candidates to the existing follow-up precedence.
Duplicate candidate text across source files emits one follow-up carrying the
first deterministic source location.

## Trellis Deduplication

Build a match index from every valid direct-child task record already used by
the `Tasks` inventory:

- durable task ID;
- direct task-directory name/path; and
- normalized title, with optional display-only `PARKED:` removed.

A roadmap candidate is tracked when its raw/normalized Markdown contains a
bounded task ID or task-path reference, or when its normalized visible text
equals a normalized title. Case, whitespace, Markdown link/emphasis/code
presentation, and the `PARKED:` prefix are non-semantic. Do not use substring
title matching, edit distance, keyword overlap, or model inference.

## Safety And Compatibility

The scan is read-only and uses repository-local paths only. It performs no
network access and never creates, edits, or archives tasks. Existing Git,
GitHub, Trellis, work-loop, Follow-ups, Tasks, Next Steps, fleet, strict-mode,
and exit-status behavior remains unchanged except for adding roadmap follow-ups
and removing the duplicate roadmap inventory.

This changes shipped human and JSON semantics, so release it under the
repository's minor-version rule. Templates remain authoritative; `make sync`
updates dogfood mirrors and generated knowledge.

Rollback reverts the collector, housekeeping composition boundary,
skill/docs/spec text, tests, manifest, changelog, mirrors, and candidate ledger
together.

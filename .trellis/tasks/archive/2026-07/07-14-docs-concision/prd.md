# Docs concision from optimization review

## Goal

Cut duplication and verbatim bloat from README.md and the installed guide
(docs/SD_AI_COMMAND_PACK.md) — ~200-250 lines — without losing information a
reader needs. Conciseness/clarity only; no accuracy or structural-meaning
changes.

## Requirements

- R1: Trim the ~148-line verbatim generated `.gitignore` block in the guide
  (`docs/SD_AI_COMMAND_PACK.md`, the "Updating the pack" area). It reproduces the
  same 6-pattern set per platform dir and is regenerated into every consumer's
  real `.gitignore` on install. Keep ONE platform's pattern set as the example
  plus a one-line note that the same set repeats per active platform and the
  installer regenerates the full block. ~90 lines.
- R2: De-duplicate README Install ↔ guide "Updating the pack": the remove-mode
  prose, gitignore-management prose, upstream-manifest advisory, preserved-file
  prose, and SANDBOX_TMP/smoke-test block are near-verbatim in both. README keeps
  the commands + one-line summaries and defers detail to its existing guide
  pointer; delete the duplicated prose from README. ~35-45 lines.
- R3: Compress README Overview (the namespace/adapter/SessionStart/Codec-list
  narrative that duplicates the guide's "What is installed") to a few lines that
  point to the guide. ~20 lines.

## Constraints (HARD — verify each)

- **Do not break any string the test suite pins.** `tests/test_generated_parity.py`
  asserts ~23 exact README substrings and several guide substrings. Run
  `python3 -m unittest tests.test_generated_parity` (via .venv) after edits; if a
  pinned string was in deleted text, either keep that string or update the
  assertion — but prefer keeping pinned content and cutting around it.
- **Keep docs/SD_AI_COMMAND_PACK.md and templates/docs/SD_AI_COMMAND_PACK.md
  byte-identical** (`diff` must be empty) — apply every guide edit to both.
- No information loss: every fact removed from one doc must still exist in the
  other (README defers to guide, guide keeps the detail). No behavior, command,
  flag, or env-var reference removed or changed.
- The review-preflight doc-path checker must still pass
  (`node scripts/sd-ai-command-pack-review-preflight.mjs`) — do not create broken
  doc links.

## Acceptance Criteria

- [ ] R1-R3 applied; net ~200+ lines cut across README + guide; guide twin
      byte-identical.
- [ ] `make test` green (`test_generated_parity` in particular); `make lint`
      green; review-preflight passes.
- [ ] No fact/command/flag/env-var lost — spot-check the guide still documents
      everything README stopped duplicating.

## Non-goals

- The README audience-split / maintainer-vs-consumer restructure (docs finding
  4) — larger structural change, deferred.
- CHANGELOG/version bump and KB regeneration — the main session handles those at
  commit time (docs are shipped payload, so a manifest bump is required).
- Any change to command adapter files or the guide's substantive technical
  content.

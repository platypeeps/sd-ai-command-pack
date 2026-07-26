# Implementation Plan: Journal-Only Planning Recovery

## 1. Extend Focused Fixtures First

- Add a valid journal-only planning fixture whose referenced commits create and
  update active planning tasks before the captured base.
- Add failures for non-task scope, merge/non-linear history, non-ancestor and
  duplicate commits, no recovered task change, invalid lifecycle, and multiple
  new completed sessions.
- Preserve the existing completion and normal planning assertions.

## 2. Implement the Canonical Validator

- Update `templates/scripts/sd-ai-command-pack-review-preflight.mjs` first.
- Return bounded new-session commit evidence from journal validation.
- Detect the journal-only planning subtype only when the exact finalization
  range has no task entries.
- Revalidate each referenced single-parent commit using existing planning rules
  for lifecycle and baseline state plus strict non-task scope rejection. Keep
  the normal planning bundle's complete content-quality validation unchanged;
  recovery does not retroactively audit already-published planning content.
- Keep schema version, public modes, and success reason codes compatible.
- Synchronize `scripts/sd-ai-command-pack-review-preflight.mjs` byte-for-byte.

## 3. Update Lifecycle Contracts

- Update the canonical `templates/.agents/skills/sd-finish-work/SKILL.md` and
  root mirror to document automatic journal-only recovery and retained-result
  semantics.
- Extend backend review-preflight and frontend lifecycle-wrapper code specs.
- Update focused skill-contract tests without adding a public command or flag.

## 4. Validate and Recover

- Run focused bookkeeping-validator and SD lifecycle tests.
- Run source/template parity and the generic review preflight.
- Use an isolated checkout at `686f484` with the corrected helper to validate
  the exact `9c9b8c3..686f484` range without changing that commit.
- Run `make check`.
- Commit only the task-owned implementation and validation artifacts; do not
  amend or push the preserved journal commit until the recovery gate is valid.

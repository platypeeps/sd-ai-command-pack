---
title: Clear loadsmith's dangling pack-path citations
status: done
created: 2026-08-21
branch: docs/mark-absent-pack-path-citations
---
# Clear loadsmith's dangling pack-path citations

## Goal

`platypeeps/loadsmith` reports 24 review-preflight failures. All 24 are one
class: Trellis PRDs cite pack source paths repo-relative, and a thin install
vendors no copy of them. Clear them without falsifying the citations.

## Context

The failures are pre-existing and unrelated to the 0.71.43 `.claude/` rule —
loadsmith's delta under that change was 0. They block the repo from going green
on a refresh, which matters because loadsmith is the fleet's most-lagging
consumer (0.71.33 against a pack at 0.71.44).

The cited paths resolve on this machine, but not where the PRDs say:

| cited as | actually at |
| --- | --- |
| `scripts/sd-ai-command-pack-review-learnings.py` | `~/.agents/bin/…` |
| `scripts/sd-ai-command-pack-check.py` | `~/.agents/bin/…` |
| `scripts/sd-ai-command-pack-work-loop.py` | `~/.agents/bin/…` |
| `scripts/sd-ai-command-pack-review-preflight.mjs` | `~/.agents/bin/…` |
| `docs/SD_AI_COMMAND_PACK.md` | `~/.agents/docs/…` |

loadsmith has its own `scripts/` and `docs/` trees, so these are not missing
directories — they are pack paths written as if the pack were vendored.

Spread over six task directories, all `status=planning`:
`08-07-boundary-validation-fixtures`, `08-07-contract-drift-gate`,
`08-07-repomix-pack-refresh-coupling`, `08-07-task-metadata-gate`,
`08-07-test-harness-fidelity`, `08-07-unresolved-review-threads`.

## Requirements

- **Mark, do not repoint.** The citations carry line numbers
  (`…review-preflight.mjs:4345`) and sit in evidence tables that name a symbol
  and the line it was found at. Those are facts about a pack checkout at a
  point in time; `~/.agents/bin/…:4345` is a different artifact whose lines
  drift independently. Repointing them would falsify the evidence. This is the
  same call made for se-ai-command-pack, and reversed there once for the same
  wrong reason.
- **One marker per failing citation**, appended in place so the reason travels
  with the claim. Marker syntax: only spaces or tabs may separate the citation
  from `[absent: …]`; in a table cell the marker goes between the closing
  backtick and the `|`.
- **Do not touch citations that already resolve.** The sweep is driven by the
  checker's own report, not by pattern-matching every `scripts/` string.
- **Verify by re-running the checker**, not by counting edits.

## Acceptance Criteria

- [ ] `node …/sd-ai-command-pack-review-preflight.mjs` in loadsmith reports
      0 failures and 0 warnings.
- [ ] Exactly 24 markers added; no citation text otherwise changed
      (`git diff` shows only insertions inside existing lines).
- [ ] No task's `status` or planning content is altered — this is a citation
      bookkeeping pass over `planning` PRDs, not a re-plan.

## Out Of Scope

- Refreshing loadsmith onto 0.71.44. Separate work; this clears the gate so
  that refresh can go green.
- The six tasks' own substance. They stay in `planning`.
